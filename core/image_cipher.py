"""Mã hóa / giải mã ảnh bằng AES-256 (CBC hoặc ECB) với S-box động.

Ảnh được đọc thành chuỗi byte (các kênh của mỗi điểm ảnh ghép liên tiếp, theo
hàng). Để bản mã vẫn là một ảnh xem được, chuỗi được đệm thêm các HÀNG điểm ảnh
bằng 0 cho tới khi tổng số byte chia hết cho 16 (tối đa 15 hàng). Ảnh mã hóa
lưu dạng PNG (không nén mất dữ liệu) kèm tệp `<tên>.meta` (JSON) chứa IV,
chế độ mã hóa và kích thước gốc — các giá trị này không cần giữ bí mật.
Đa thức f(x) KHÔNG được ghi vào .meta: nó được dẫn xuất từ khóa K nên ghi ra
sẽ làm lộ bảng thế và khoảng 4,9 bit thông tin phụ thuộc K. Bên giải mã tự tính
lại f(x) từ K.

Lớp tệp (encrypt_file, decrypt_file) bảo vệ thêm bằng dẫn xuất khóa và xác thực:
mật khẩu + muối ngẫu nhiên -> PBKDF2-HMAC-SHA256 -> khóa gốc, rồi tách bằng HMAC
thành khóa mã hóa K và khóa xác thực. HMAC-SHA256 (encrypt-then-MAC) phủ .meta và
bản mã; sai khóa hoặc dữ liệu bị sửa thì từ chối trước khi giải mã, không ghi tệp.
Lớp mảng (encrypt_array, decrypt_array) dùng trực tiếp khóa K, không có xác thực.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

import numpy as np
from PIL import Image

from .aes_fast import AES256
from .keyderive import normalize_key
from .sbox import build_sbox

CHANNELS = {"L": 1, "RGB": 3, "RGBA": 4}
CIPHER_MODES = ("cbc", "ecb")
META_VERSION = 2
SALT_SIZE = 16
KDF_ITERATIONS = 600_000
MAX_KDF_ITERATIONS = 10_000_000
_HIGH_DEPTH_MODES = ("I", "F", "I;16", "I;16L", "I;16B", "I;16N")


class AuthenticationError(ValueError):
    """Sai khóa hoặc ảnh mã hóa, tệp .meta đã bị sửa."""


def derive_file_keys(password: bytes | str, salt: bytes, iterations: int) -> tuple[bytes, bytes]:
    """Trả về (khóa mã hóa K, khóa xác thực) từ mật khẩu và muối."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    master = hashlib.pbkdf2_hmac("sha256", password, salt, iterations, 32)
    return (hmac.new(master, b"image-encryption-key", hashlib.sha256).digest(),
            hmac.new(master, b"image-authentication-key", hashlib.sha256).digest())


def _file_tag(mac_key: bytes, meta: dict, enc: np.ndarray) -> str:
    """HMAC-SHA256 trên .meta (trừ trường mac), kích thước và dữ liệu ảnh mã hóa."""
    fields = {k: v for k, v in meta.items() if k != "mac"}
    header = json.dumps({"meta": fields, "shape": enc.shape}, sort_keys=True, separators=(",", ":"))
    return hmac.new(mac_key, header.encode("utf-8") + enc.tobytes(), hashlib.sha256).hexdigest()


def _check_mode(mode: str) -> str:
    """Chuẩn hóa và kiểm tra chế độ mã hóa khối."""
    mode = mode.lower()
    if mode not in CIPHER_MODES:
        raise ValueError(f"Chế độ không hợp lệ: {mode!r} (chỉ nhận 'cbc' hoặc 'ecb')")
    return mode


def load_image(path: str) -> np.ndarray:
    """Đọc ảnh thành mảng uint8 (H, W) hoặc (H, W, C)."""
    with Image.open(path) as img:
        if img.mode in _HIGH_DEPTH_MODES:
            raise ValueError(f"Chỉ hỗ trợ ảnh 8 bit mỗi kênh (ảnh này có chế độ {img.mode})")
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
                  mode: str = "cbc", tick=None) -> np.ndarray:
    """Mã hóa một mảng ảnh."""
    key = normalize_key(key)
    mode = _check_mode(mode)
    sbox = build_sbox(key=key) if sbox is None else sbox
    w = arr.shape[1]
    ch = 1 if arr.ndim == 2 else arr.shape[2]
    h = _padded_height(arr.size, w * ch)
    data = arr.tobytes() + bytes(h * w * ch - arr.size)
    cipher = AES256(key, sbox)
    out = cipher.cbc_encrypt(data, iv, tick) if mode == "cbc" else cipher.ecb_encrypt(data, tick)
    shape = (h, w) if ch == 1 else (h, w, ch)
    return np.frombuffer(out, dtype=np.uint8).reshape(shape)


def decrypt_array(enc: np.ndarray, key: bytes | str, iv: bytes, orig_height: int,
                  sbox: list[int] | None = None, mode: str = "cbc", tick=None) -> np.ndarray:
    key = normalize_key(key)
    mode = _check_mode(mode)
    sbox = build_sbox(key=key) if sbox is None else sbox
    data = enc.tobytes()
    cipher = AES256(key, sbox)
    plain = cipher.cbc_decrypt(data, iv, tick) if mode == "cbc" else cipher.ecb_decrypt(data, tick)
    return np.frombuffer(plain, dtype=np.uint8).reshape(enc.shape)[:orig_height]


def encrypt_file(in_path: str, out_path: str, key: bytes | str, iv: bytes | None = None,
                 mode: str = "cbc", tick=None) -> dict:
    """Mã hóa tệp ảnh -> `out_path` (.png) + `out_path.meta`."""
    if not out_path.lower().endswith(".png"):
        raise ValueError("Ảnh mã hóa phải lưu dạng .png (JPEG làm hỏng bản mã)")
    mode = _check_mode(mode)
    iv = os.urandom(16) if iv is None else iv
    salt = os.urandom(SALT_SIZE)
    arr = load_image(in_path)
    enc_key, mac_key = derive_file_keys(key, salt, KDF_ITERATIONS)
    enc = encrypt_array(arr, enc_key, iv, mode=mode, tick=tick)
    if tick is not None:
        tick()
    meta = {"version": META_VERSION, "iv": iv.hex(), "mode": Image.fromarray(arr).mode,
            "cipher_mode": mode, "orig_width": arr.shape[1], "orig_height": arr.shape[0],
            "salt": salt.hex(), "iterations": KDF_ITERATIONS}
    meta["mac"] = _file_tag(mac_key, meta, enc)
    save_image(enc, out_path)
    with open(out_path + ".meta", "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return meta


def decrypt_file(in_path: str, out_path: str, key: bytes | str, tick=None) -> dict:
    meta_path = in_path + ".meta"
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"Thiếu tệp {meta_path} (chứa IV và kích thước gốc)")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    if not isinstance(meta, dict) or meta.get("version") != META_VERSION or "mac" not in meta:
        raise AuthenticationError("Tệp .meta không có thông tin xác thực (định dạng cũ hoặc đã bị sửa)")
    try:
        salt, iterations = bytes.fromhex(meta["salt"]), int(meta["iterations"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Tệp .meta không hợp lệ") from exc
    if not 1 <= iterations <= MAX_KDF_ITERATIONS:
        raise AuthenticationError("Tệp .meta không hợp lệ")
    enc = load_image(in_path)
    enc_key, mac_key = derive_file_keys(key, salt, iterations)
    if not hmac.compare_digest(str(meta["mac"]), _file_tag(mac_key, meta, enc)):
        raise AuthenticationError("Sai khóa hoặc dữ liệu đã bị sửa")
    plain = decrypt_array(enc, enc_key, bytes.fromhex(meta["iv"]), meta["orig_height"],
                          mode=meta["cipher_mode"], tick=tick)
    if tick is not None:
        tick()
    save_image(np.ascontiguousarray(plain), out_path)
    return meta
