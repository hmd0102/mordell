"""Chương trình dòng lệnh: sinh S-box động từ đường cong Mordell, mã hóa/giải mã
ảnh bằng AES-256-CBC và đánh giá kết quả. Danh sách lệnh: python main.py -h
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from core import (DEGREE_8_IRREDUCIBLES, build_sbox, decrypt_file, encrypt_array, encrypt_file,
                  format_matrix, key_to_polynomial, load_image, normalize_key, poly_to_str, properties)
from metrics import image_metrics as im, sbox_metrics as sm
from reference import REFERENCE_SBOXES


def cmd_encrypt(a):
    t = time.perf_counter()
    meta = encrypt_file(a.input, a.output, a.key, bytes.fromhex(a.iv) if a.iv else None)
    print(f"Đã mã hóa -> {a.output} (+ {a.output}.meta)")
    print(f"  f(x) = {poly_to_str(meta['poly'])}   IV = {meta['iv']}   ({time.perf_counter() - t:.2f} s)")


def cmd_decrypt(a):
    t = time.perf_counter()
    decrypt_file(a.input, a.output, a.key)
    print(f"Đã giải mã -> {a.output}  ({time.perf_counter() - t:.2f} s)")


def _pick_sbox(a) -> tuple[str, list[int]]:
    if getattr(a, "ref", None):
        return f"S-box tham chiếu: {a.ref}", REFERENCE_SBOXES[a.ref]()
    if a.poly is not None:
        return f"S-box Mordell, f(x) = {poly_to_str(a.poly)} ({a.poly})", build_sbox(poly=a.poly)
    p = key_to_polynomial(a.key)
    return f"S-box Mordell từ khóa, f(x) = {poly_to_str(p)} ({p} = 0x{p:X})", build_sbox(key=a.key)


def cmd_sbox(a):
    title, s = _pick_sbox(a)
    print(title)
    print(format_matrix(s, hexa=a.hex))
    pr = properties(s)
    print(f"Song ánh: {pr['bijective']} | Tự nghịch đảo: {pr['involution']} | Điểm bất động: {pr['fixed_points']}")


def cmd_eval_sbox(a):
    title, s = _pick_sbox(a)
    print(title)
    print(sm.format_report(sm.evaluate(s)))


def cmd_eval_image(a):
    key = normalize_key(a.key)
    iv = bytes(16)
    img = load_image(a.input)
    t = time.perf_counter()
    enc = encrypt_array(img, key, iv)
    dt = time.perf_counter() - t
    print(f"Ảnh {a.input}: {img.shape}, mã hóa mất {dt:.2f} s")
    print("Ảnh GỐC:");      print(im.format_report(im.evaluate_image(img)))
    print("Ảnh MÃ HÓA:");   print(im.format_report(im.evaluate_image(enc)))
    img2 = img.copy(); img2.reshape(-1)[0] ^= 1          # đổi 1 bit ở điểm ảnh đầu tiên
    c = im.compare_images(enc, encrypt_array(img2, key, iv))
    print(f"Độ nhạy bản rõ (đổi điểm ảnh đầu): NPCR = {c['NPCR']:.4f}%  UACI = {c['UACI']:.4f}%")
    k2 = bytearray(key); k2[0] ^= 1
    c = im.compare_images(enc, encrypt_array(img, bytes(k2), iv))
    print(f"Độ nhạy khóa (đổi 1 bit khóa)   : NPCR = {c['NPCR']:.4f}%  UACI = {c['UACI']:.4f}%")


def cmd_compare(a):
    rows = [("Đề xuất (" + a.key + ")", build_sbox(key=a.key))] + \
           [(n, f()) for n, f in REFERENCE_SBOXES.items()]
    print(f"{'S-box':<28}{'NL':>5}{'SAC':>8}{'BIC-NL':>9}{'BIC-SAC':>9}{'LAP':>8}{'DAP':>8}")
    for name, s in rows:
        r = sm.evaluate(s)
        print(f"{name[:27]:<28}{r['NL']:>5}{r['SAC_avg']:>8.4f}{r['BIC_NL_avg']:>9.2f}"
              f"{r['BIC_SAC']:>9.4f}{r['LAP']:>8.4f}{r['DAP']:>8.4f}")


def cmd_selftest(a):
    import unittest
    here = os.path.dirname(os.path.abspath(__file__))
    suite = unittest.defaultTestLoader.discover(os.path.join(here, "tests"), top_level_dir=here)
    ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    sys.exit(0 if ok else 1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="S-box động từ đường cong Mordell trên GF(2^8) và mã hóa ảnh AES-256-CBC")
    sub = p.add_subparsers(dest="cmd", required=True)
    DK = "day-la-mot-khoa-bi-mat-vi-du"

    s = sub.add_parser("encrypt", help="mã hóa ảnh")
    s.add_argument("input"); s.add_argument("output", help="tệp .png")
    s.add_argument("--key", required=True); s.add_argument("--iv", help="IV 32 ký tự hex (mặc định: ngẫu nhiên)")
    s.set_defaults(func=cmd_encrypt)

    s = sub.add_parser("decrypt", help="giải mã ảnh (cần tệp .meta đi kèm)")
    s.add_argument("input"); s.add_argument("output"); s.add_argument("--key", required=True)
    s.set_defaults(func=cmd_decrypt)

    for name, func, hlp in (("sbox", cmd_sbox, "in bảng S-box 16x16"),
                            ("eval-sbox", cmd_eval_sbox, "đánh giá NL, SAC, BIC, LAP, DAP")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("--key", default=DK)
        s.add_argument("--poly", type=int, choices=DEGREE_8_IRREDUCIBLES, metavar="N",
                       help="chọn trực tiếp đa thức bất khả quy bậc 8 (dạng thập phân)")
        s.add_argument("--ref", choices=sorted(REFERENCE_SBOXES), help="dùng S-box tham chiếu")
        if name == "sbox":
            s.add_argument("--hex", action="store_true")
        s.set_defaults(func=func)

    s = sub.add_parser("eval-image", help="mã hóa và đánh giá một ảnh (entropy, tương quan, NPCR...)")
    s.add_argument("input"); s.add_argument("--key", default=DK)
    s.set_defaults(func=cmd_eval_image)

    s = sub.add_parser("compare", help="so sánh S-box Mordell với 3 S-box tham chiếu")
    s.add_argument("--key", default=DK)
    s.set_defaults(func=cmd_compare)

    s = sub.add_parser("selftest", help="chạy toàn bộ kiểm thử")
    s.set_defaults(func=cmd_selftest)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
