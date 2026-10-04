"""In các giá trị trung gian của quy trình: dẫn xuất f(x) từ khóa, sinh tập điểm,
sinh S-box, mã hóa và giải mã một khối AES-256-CBC.

Chạy từ thư mục gốc mordell/:
    python -m experiments.chapter2_example
In ra màn hình và lưu results/chapter2/vi_du_chuong2.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import core.aes as A
from core import GF2n, build_sbox, key_to_polynomial, normalize_key, mordell_points, poly_to_str, format_matrix
from core.gf2n import irreducible_polynomials

KEY_STR = "day-la-mot-khoa-bi-mat-vi-du"
IV = bytes.fromhex("f53f3244c51a230ec14c7bd6bdc2734f")
P1 = bytes([120, 45, 200, 78, 33, 189, 12, 156, 67, 234, 90, 5, 201, 88, 150, 60])


def hx(b: bytes) -> str:
    h = b.hex()
    return " ".join(h[i:i + 8] for i in range(0, len(h), 8))


def main() -> dict:
    out = {}
    K = normalize_key(KEY_STR)
    print(f"K_demo = SHA-256('{KEY_STR}') = {hx(K)}")
    B0 = hashlib.sha256(K + (0).to_bytes(4, "big")).digest()
    print(f"B0 = SHA-256(K || 0)       = {hx(B0)}")

    poly, tried = key_to_polynomial(K, return_trace=True)
    for v in tried:
        f = 0x100 | v
        print(f"  byte 0x{v:02X} -> {poly_to_str(f):32s} {'BẤT KHẢ QUY' if f == poly else 'khả quy, loại'}")
    print(f"f(x) = {poly_to_str(poly)}  (= {poly} = 0x{poly:X})")
    out.update(K=K.hex(), B0=B0.hex(), tried=tried, poly=poly)
    out["irreducible_counts"] = {n: len(irreducible_polynomials(n)) for n in (4, 6, 8, 10)}
    print("Số đa thức bất khả quy theo bậc:", out["irreducible_counts"])

    F = GF2n(poly)
    pts = mordell_points(F, 1)
    out["points_first8"] = pts[:8]
    out["distinct_y"] = len({y for _, y in pts})
    print("8 điểm đầu trên y^2 = x^3 + 1:", pts[:8], "| số y phân biệt:", out["distinct_y"])

    out["inverses_first9"] = [(x, F.inv(x)) for x in range(9)]
    S = build_sbox(key=K)
    out["sbox"] = S
    print("x^-1 (x = 0..8):", out["inverses_first9"])
    print("S-box:")
    print(format_matrix(S))

    rk = A.key_expansion(K, S)
    out["round_keys"] = {r: rk[r].hex() for r in range(15)}
    X1 = bytes(a ^ b for a, b in zip(P1, IV))
    trace: list = []
    C1 = A.encrypt_block(X1, rk, S, trace)
    out["X1"], out["C1"] = X1.hex(), C1.hex()
    out["round1"] = [(name, v.hex()) for r, name, v in trace if r <= 1]
    out["rounds"] = {r: v.hex() for r, name, v in trace if name == "AddRoundKey" and r >= 1}
    print("K0, K1, K14:", rk[0].hex(), rk[1].hex(), rk[14].hex())
    print("X1 = P1 ⊕ IV =", hx(X1))
    for r, v in out["rounds"].items():
        print(f"  sau vòng {r:2d}: {v}")
    print("C1 =", hx(C1))

    # ECB vs CBC với hai khối giống nhau 0x80..80
    P = bytes([0x80]) * 16
    e = A.encrypt_block(P, rk, S)
    c1 = A.encrypt_block(bytes(a ^ b for a, b in zip(P, IV)), rk, S)
    c2 = A.encrypt_block(bytes(a ^ b for a, b in zip(P, c1)), rk, S)
    out["ecb"], out["cbc"] = [e.hex(), e.hex()], [c1.hex(), c2.hex()]
    print("ECB:", e.hex(), e.hex(), "\nCBC:", c1.hex(), c2.hex())

    dtrace: list = []
    Xr = A.decrypt_block(C1, rk, S, dtrace)
    P1r = bytes(a ^ b for a, b in zip(Xr, IV))
    out["decrypt_first_steps"] = [(r, name, v.hex()) for r, name, v in dtrace[:5]]
    out["P1_recovered"] = P1r.hex()
    assert P1r == P1
    print("Giải mã: P1 khôi phục =", hx(P1r), "(khớp)")

    os.makedirs(os.path.join(ROOT, "results", "chapter2"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "chapter2", "vi_du_chuong2.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return out


if __name__ == "__main__":
    main()
