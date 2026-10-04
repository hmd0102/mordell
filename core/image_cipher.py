"""Mã hóa / giải mã ảnh bằng AES-256 (CBC hoặc ECB) với S-box động.

Ảnh được đọc thành chuỗi byte (các kênh của mỗi điểm ảnh ghép liên tiếp, theo
hàng). Để bản mã vẫn là một ảnh xem được, chuỗi được đệm thêm các HÀNG điểm ảnh
bằng 0 cho tới khi tổng số byte chia hết cho 16 (tối đa 16 hàng). Ảnh mã hóa
lưu dạng PNG (không nén mất dữ liệu) kèm tệp `<tên>.meta` (JSON) chứa IV,
chế độ mã hóa và kích thước gốc — IV không cần giữ bí mật.
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

from .aes_fast import AES256
from .keyderive import normalize_key, key_to_polynomial
from .sbox import build_sbox

CHANNELS = {"L": 1, "RGB": 3, "RGBA": 4}
CIPHER_MODES = ("cbc", "ecb")


def _check_mode(mode: str) -> str:
    """Chuẩn hóa và kiểm tra chế độ mã hóa khối."""
    mode = mode.lower()
    if mode not in CIPHER_MODES:
        raise ValueError(f"Chế độ không hợp lệ: {mode!r} (chỉ nhận 'cbc' hoặc 'ecb')")
    return mode


def load_image(path: str) -> np.ndarray:
    """Đọc ảnh thành mảng uint8 (H, W) hoặc (H, W, C); ảnh bảng màu, CMYK, 1-bit...
    được quy về RGB/RGBA."""
    with Image.open(path) as img:
        if img.mode not in CHANNELS:
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        return np.array(img)


def save_image(arr: np.ndarray, path: str) -> None:
    Image.fromarray(arr).save(path)


def _padded_height(n_bytes: int, row_bytes: int) -> int:
    h = -(-n_bytes // row_bytes)
    while (h * row_bytes) % 16:
        h += 1
    return h


def encrypt_array(arr: np.ndarray, key: bytes | str, iv: bytes, sbox: list[int] | None = None,
                  mode: str = "cbc") -> np.ndarray:
    """Mã hóa một mảng ảnh; trả về mảng ảnh mã hóa (có thể cao hơn vài hàng do đệm).
    `sbox=None`: sinh S-box động từ khóa. `mode`: 'cbc' (mặc định) hoặc 'ecb'."""
    key = normalize_key(key)
    mode = _check_mode(mode)
    sbox = build_sbox(key=key) if sbox is None else sbox
    w = arr.shape[1]
    ch = 1 if arr.ndim == 2 else arr.shape[2]
    h = _padded_height(arr.size, w * ch)
    data = arr.tobytes() + bytes(h * w * ch - arr.size)
    cipher = AES256(key, sbox)
    out = cipher.cbc_encrypt(data, iv) if mode == "cbc" else cipher.ecb_encrypt(data)
    shape = (h, w) if ch == 1 else (h, w, ch)
    return np.frombuffer(out, dtype=np.uint8).reshape(shape)


def decrypt_array(enc: np.ndarray, key: bytes | str, iv: bytes, orig_height: int,
                  sbox: list[int] | None = None, mode: str = "cbc") -> np.ndarray:
    key = normalize_key(key)
    mode = _check_mode(mode)
    sbox = build_sbox(key=key) if sbox is None else sbox
    data = enc.tobytes()
    cipher = AES256(key, sbox)
    plain = cipher.cbc_decrypt(data, iv) if mode == "cbc" else cipher.ecb_decrypt(data)
    return np.frombuffer(plain, dtype=np.uint8).reshape(enc.shape)[:orig_height]


def encrypt_file(in_path: str, out_path: str, key: bytes | str, iv: bytes | None = None,
                 mode: str = "cbc") -> dict:
    """Mã hóa tệp ảnh -> `out_path` (.png) + `out_path.meta`. Trả về metadata."""
    if not out_path.lower().endswith(".png"):
        raise ValueError("Ảnh mã hóa phải lưu dạng .png (JPEG làm hỏng bản mã)")
    mode = _check_mode(mode)
    key = normalize_key(key)
    iv = os.urandom(16) if iv is None else iv
    arr = load_image(in_path)
    enc = encrypt_array(arr, key, iv, mode=mode)
    save_image(enc, out_path)
    meta = {"iv": iv.hex(), "mode": Image.fromarray(arr).mode, "cipher_mode": mode,
            "orig_width": arr.shape[1], "orig_height": arr.shape[0],
            "poly": key_to_polynomial(key)}
    with open(out_path + ".meta", "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return meta


def decrypt_file(in_path: str, out_path: str, key: bytes | str) -> dict:
    meta_path = in_path + ".meta"
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"Thiếu tệp {meta_path} (chứa IV và kích thước gốc)")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    mode = meta.get("cipher_mode", "cbc")       # tệp .meta cũ chưa có khóa này -> CBC
    enc = load_image(in_path)
    plain = decrypt_array(enc, key, bytes.fromhex(meta["iv"]), meta["orig_height"], mode=mode)
    save_image(np.ascontiguousarray(plain), out_path)
    return meta
