"""Thử xác thực và dẫn xuất khóa của lớp tệp (mục 3.5.6 của đồ án).

Chạy từ thư mục gốc mordell/:
    python -m experiments.chapter3_security
Kết quả: results/chapter3_security/ket_qua.json

Gồm: tấn công sửa bit CBC ở lớp mảng (không có xác thực), cùng các kiểu sửa dữ liệu ở
lớp tệp (có HMAC), tốc độ đoán mật khẩu khi băm một lần so với khi dùng PBKDF2, và PSNR
sau giải mã ở các mức nhiễu của Bảng 13 trong [1] (mục 3.5.4).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
from PIL import Image

from core import AuthenticationError, decrypt_array, decrypt_file, encrypt_array, encrypt_file, load_image
from core.image_cipher import KDF_ITERATIONS, derive_file_keys
from metrics.image_metrics import psnr

OUT = os.path.join(ROOT, "results", "chapter3_security")
LENA = os.path.join(ROOT, "data", "images", "lena.png")
BABOON = os.path.join(ROOT, "data", "images", "baboon.png")
PASSWORD = "day-la-mot-khoa-bi-mat-vi-du"
K = hashlib.sha256(PASSWORD.encode()).digest()
IV = hashlib.sha256(b"iv-thuc-nghiem-chuong-3").digest()[:16]


def bit_flip_without_mac(gray: np.ndarray) -> dict:
    """Sửa IV và bản mã ở lớp mảng: giải mã vẫn chạy, không có gì báo lỗi."""
    enc = encrypt_array(gray, K, IV)
    target = 0x55
    iv = bytearray(IV)
    iv[0] ^= int(gray.reshape(-1)[0]) ^ target
    dec = decrypt_array(enc, K, bytes(iv), gray.shape[0])
    changed_iv = int((dec != gray).sum())

    tampered = enc.copy()
    tampered.reshape(-1)[160] ^= 1
    dec2 = decrypt_array(tampered, K, IV, gray.shape[0]).reshape(-1)
    plain = gray.reshape(-1)
    return {
        "iv_flip": {"first_byte_after": int(dec.reshape(-1)[0]), "target": target, "changed_bytes": changed_iv},
        "cipher_bit_flip": {
            "block_hit_changed": int((dec2[160:176] != plain[160:176]).sum()),
            "next_block_changed": int((dec2[176:192] != plain[176:192]).sum()),
            "others_changed": int((dec2[:160] != plain[:160]).sum() + (dec2[192:] != plain[192:]).sum()),
        },
    }


def tamper_cases(folder: str) -> list[dict]:
    """Mỗi kiểu sửa dữ liệu trên một tệp mới; kỳ vọng đều bị từ chối, không ghi tệp."""
    source = os.path.join(folder, "goc.png")
    Image.fromarray(np.array(Image.open(LENA).convert("L"))[:64, :64]).save(source)
    enc, dec = os.path.join(folder, "enc.png"), os.path.join(folder, "dec.png")

    def edit_meta(change):
        with open(enc + ".meta", encoding="utf-8") as f:
            meta = json.load(f)
        change(meta)
        with open(enc + ".meta", "w", encoding="utf-8") as f:
            json.dump(meta, f)

    def edit_pixels(change):
        arr = load_image(enc).copy()
        change(arr)
        Image.fromarray(arr).save(enc)

    def flip_iv(meta):
        meta["iv"] = "%02x" % (int(meta["iv"][:2], 16) ^ 1) + meta["iv"][2:]

    def swap_blocks(arr):
        raw = arr.reshape(-1)
        raw[:16], raw[16:32] = raw[16:32].copy(), raw[:16].copy()

    def flip_pixel(arr):
        arr[5, 5] ^= 1

    cases = [
        ("Khóa đúng, không sửa gì", None, PASSWORD),
        ("Sai khóa", None, "khoa-sai"),
        ("Sửa 1 bit điểm ảnh của ảnh mã hóa", lambda: edit_pixels(flip_pixel), PASSWORD),
        ("Đổi chỗ hai khối mã", lambda: edit_pixels(swap_blocks), PASSWORD),
        ("Sửa 1 bit của IV", lambda: edit_meta(flip_iv), PASSWORD),
        ("Đổi chế độ CBC thành ECB", lambda: edit_meta(lambda m: m.__setitem__("cipher_mode", "ecb")), PASSWORD),
        ("Sửa số hàng gốc", lambda: edit_meta(lambda m: m.__setitem__("orig_height", 1)), PASSWORD),
        ("Sửa muối", lambda: edit_meta(lambda m: m.__setitem__("salt", "00" * 16)), PASSWORD),
        ("Gỡ trường HMAC để hạ cấp định dạng", lambda: edit_meta(lambda m: m.pop("mac")), PASSWORD),
    ]
    rows = []
    for name, attack, key in cases:
        if os.path.exists(dec):
            os.remove(dec)
        encrypt_file(source, enc, PASSWORD)
        if attack:
            attack()
        try:
            decrypt_file(enc, dec, key)
            rejected = False
        except AuthenticationError:
            rejected = True
        rows.append({"case": name, "rejected": rejected, "output_written": os.path.exists(dec)})
        print(f"{name}: {'từ chối' if rejected else 'giải mã được'}", flush=True)
    return rows


def guessing_rate() -> dict:
    """Số lần thử mật khẩu mỗi giây trên một luồng của máy thực nghiệm."""
    n = 200_000
    start = time.perf_counter()
    for i in range(n):
        hashlib.sha256(b"%d" % i).digest()
    sha_rate = n / (time.perf_counter() - start)
    runs = []
    for i in range(5):
        start = time.perf_counter()
        derive_file_keys(b"%d" % i, bytes(16), KDF_ITERATIONS)
        runs.append(time.perf_counter() - start)
    kdf_time = float(np.median(runs))
    guesses = 10 ** 6
    return {
        "sha256_per_s": sha_rate, "kdf_iterations": KDF_ITERATIONS, "kdf_seconds": kdf_time,
        "kdf_per_s": 1 / kdf_time, "ratio": sha_rate * kdf_time,
        "digits6_guesses": guesses, "digits6_sha256_s": guesses / sha_rate, "digits6_kdf_days": guesses * kdf_time / 86400,
    }


def noise_levels(image: np.ndarray) -> dict:
    """PSNR sau giải mã ở các mức nhiễu muối tiêu, hiểu mức nhiễu là tỷ lệ byte bị đổi."""
    enc = encrypt_array(image, K, IV)
    rows = []
    for density in (0.001, 0.01, 0.1, 0.3, 0.5):
        values, hit = [], []
        for seed in range(1, 6):
            rng = np.random.default_rng(seed)
            noisy = enc.copy()
            mask = rng.random(noisy.shape) < density
            noisy[mask] = rng.choice([0, 255], size=int(mask.sum()))
            values.append(float(psnr(image, decrypt_array(noisy, K, IV, image.shape[0]))))
            changed = (noisy != enc).reshape(-1)
            hit.append(float(changed[:changed.size // 16 * 16].reshape(-1, 16).any(axis=1).mean()))
        rows.append({"density": density, "psnr_mean": float(np.mean(values)), "psnr_min": min(values),
                     "psnr_max": max(values), "block_hit": float(np.mean(hit))})
    random_image = np.random.default_rng(9).integers(0, 256, image.shape, dtype=np.uint8)
    return {"levels": rows, "random_image_psnr": float(psnr(image, random_image))}


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    os.makedirs(OUT, exist_ok=True)
    gray = np.array(Image.open(LENA).convert("L"))
    folder = tempfile.mkdtemp(prefix="chapter3_security_")
    try:
        baboon = np.array(Image.open(BABOON).convert("RGB"))
        result = {"bit_flip": bit_flip_without_mac(gray), "tamper": tamper_cases(folder), "guessing": guessing_rate(),
                  "noise_baboon": noise_levels(baboon)}
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    with open(os.path.join(OUT, "ket_qua.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: result[k] for k in ("bit_flip", "guessing", "noise_baboon")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
