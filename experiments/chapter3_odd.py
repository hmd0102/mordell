"""Đối chứng các nhánh sinh S-box n = 8, 9, 10, 11, 12 và đối chiếu với bài báo [1] (mục 3.6).

Chạy từ thư mục gốc mordell/:
    python -m experiments.chapter3_odd            # đầy đủ
    python -m experiments.chapter3_odd --quick    # lấy mẫu, ~10 giây
    python -m experiments.chapter3_odd --no-image # bỏ phần mã hóa ảnh

Kết quả: results/chapter3_odd/ket_qua.json

Nhánh n = 8 dùng nguyên core.sbox (hoành độ + nghịch đảo nhân).
Nhánh n = 9, 11 dùng core.sbox_odd (tung độ + mod 256), tức mục 3.2 của [1].
Nhánh n = 10, 12 dùng core.sbox_even (nghịch đảo của hoành độ + mod 256), mục 3.1 của [1].
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
from PIL import Image

from core import build_sbox, decrypt_array, encrypt_array
from core.gf2n import GF2n, irreducible_polynomials
from core.sbox_even import sbox_from_inverse
from core.sbox_odd import count_b_variants, key_to_polynomial_n, sbox_from_y
from metrics import image_metrics as im, sbox_metrics as sm
from reference.alali2024 import TABLE_11, printed_to_sbox

OUT = os.path.join(ROOT, "results", "chapter3_odd")
DATA = os.path.join(ROOT, "data", "images")

KEY_STR = "day-la-mot-khoa-bi-mat-vi-du"
K = hashlib.sha256(KEY_STR.encode()).digest()
IV = hashlib.sha256(b"iv-thuc-nghiem-chuong-3").digest()[:16]

METRICS = ("NL", "NL_coord_mean", "SAC_avg", "BIC_NL_avg", "BIC_SAC", "LAP", "DAP")


def summarize(sbox: list[int], name: str) -> dict:
    return sm.evaluate(sbox, name)


def agg(values: list[float]) -> dict:
    return {"min": float(min(values)), "mean": float(np.mean(values)), "max": float(max(values))}


def build_branch(p: int) -> list[int]:
    """S-box của nhánh tương ứng với bậc của đa thức p."""
    n = p.bit_length() - 1
    if n == 8:
        return build_sbox(poly=p)
    return sbox_from_y(p) if n % 2 else sbox_from_inverse(p)


def run_branch(n: int, sample: int | None = None) -> dict:
    polys = list(irreducible_polynomials(n))
    if sample is not None and len(polys) > sample:
        polys = polys[:sample]

    build = build_branch

    t = time.perf_counter()
    per_metric: dict[str, list[float]] = {m: [] for m in METRICS}
    bad = 0
    for p in polys:
        s = build(p)
        if len(set(s)) != 256:
            bad += 1
        r = summarize(s, str(p))
        for m in METRICS:
            per_metric[m].append(float(r[m]))
    elapsed = time.perf_counter() - t

    ts = []
    for _ in range(20):
        t = time.perf_counter()
        build(polys[0])
        ts.append(time.perf_counter() - t)

    print("n=%2d: %3d S-box, %d không là hoán vị, %.1fs" % (n, len(polys), bad, elapsed), flush=True)
    return {
        "n": n,
        "n_poly": len(irreducible_polynomials(n)),
        "n_tested": len(polys),
        "n_not_permutation": bad,
        "metrics": {m: agg(per_metric[m]) for m in METRICS},
        "time_per_sbox_ms": 1000 * float(np.mean(ts)),
    }


def run_b_variants() -> dict:
    """Số bảng thế phân biệt theo b (lý thuyết: đúng 256 với mọi n lẻ)."""
    out = {}
    res9 = count_b_variants(529)
    out["9"] = {"poly": 529, "scanned": 511, "distinct": res9, "sampled": False}
    print("b-variants n=9: %d / 511" % res9, flush=True)

    f = GF2n(3441)
    b_sample = [f.mul(i, i) for i in range(1, 257)]
    res11 = count_b_variants(3441, b_sample)
    out["11"] = {"poly": 3441, "scanned": len(b_sample), "distinct": res11, "sampled": True}
    print("b-variants n=11: %d / %d (mẫu thiết kế)" % (res11, len(b_sample)), flush=True)
    return out


def run_b_is_xor(poly: int = 529) -> dict:
    """Kiểm chứng S_b(x) = S_1(x) XOR hằng số với mọi b, và các chỉ số không đổi."""
    f = GF2n(poly)
    base = sbox_from_y(poly, 1)
    sqrt1 = f.sqrt(1)
    all_xor = all(
        sbox_from_y(poly, b) == [v ^ ((f.sqrt(b) ^ sqrt1) & 0xFF) for v in base]
        for b in range(1, f.order)
    )
    r1, r2 = (sm.evaluate(sbox_from_y(poly, b)) for b in (1, 7))
    same = all(r1[k] == r2[k] for k in METRICS)
    print("b chỉ XOR hằng số: %s; chỉ số không đổi: %s" % (all_xor, same), flush=True)
    return {"poly": poly, "b_scanned": f.order - 1, "only_xor_constant": all_xor,
            "metrics_unchanged": same}


def run_paper_compare() -> list[dict]:
    """Đối chiếu từng S-box trong [1]: số công bố, số đo lại, độ lệch so với cài đặt."""
    rows = []
    for poly in TABLE_11:
        n = poly.bit_length() - 1
        printed = printed_to_sbox(poly)
        ours = build_branch(poly)
        if n % 2:
            diff, c = min((sum((a ^ k) != p for a, p in zip(ours, printed)), k) for k in range(256))
        else:
            diff, c = sum(a != p for a, p in zip(ours, printed)), None
        is_perm = len(set(printed)) == 256
        m = sm.evaluate(printed if is_perm else ours, str(poly))
        rows.append({
            "poly": poly, "n": n,
            "published": dict(zip(("NL", "SAC", "BIC_NL", "BIC_SAC", "LAP", "DAP"), TABLE_11[poly])),
            "printed_is_permutation": is_perm,
            "measured_on": "bảng in" if is_perm else "chương trình",
            "diff_cells_vs_ours": diff, "best_xor_constant": c,
            "measured": {k: m[k] for k in ("NL", "NL_coord_mean", "SAC_avg", "BIC_NL_avg",
                                            "BIC_SAC", "LAP", "DAP")},
        })
        print("S-box-%d (n=%d): lệch %d ô, NL_TB=%s (công bố %s), NL_min=%s"
              % (poly, n, diff, m["NL_coord_mean"], TABLE_11[poly][0], m["NL"]), flush=True)
    return rows


def run_image_n9() -> dict | None:
    path = os.path.join(DATA, "lena.png")
    if not os.path.exists(path):
        print("bỏ phần ảnh: không thấy data/images/lena.png", flush=True)
        return None

    arr = np.array(Image.open(path).convert("L"))
    poly = key_to_polynomial_n(K, 9)
    sb = sbox_from_y(poly)
    h0 = arr.shape[0]

    t = time.perf_counter()
    c = encrypt_array(arr, K, IV, sb)
    enc_s = time.perf_counter() - t
    d = decrypt_array(c, K, IV, h0, sb)

    st = im.evaluate_image(c)
    flipped = arr.copy()
    flat = flipped.reshape(-1)
    flat[flat.size // 2] = (int(flat[flat.size // 2]) + 1) % 256
    c2 = encrypt_array(flipped, K, IV, sb)
    cmp = im.compare_images(c, c2)

    out = {
        "poly": poly,
        "poly_str": "0x%X" % poly,
        "decrypt_exact": bool(np.array_equal(arr, d)),
        "entropy": st["entropy"],
        "corr": st["corr"],
        "NPCR": cmp["NPCR"],
        "UACI": cmp["UACI"],
        "encrypt_s": enc_s,
    }
    print("ảnh n=9: entropy=%.4f, NPCR=%.2f%%, giải mã đúng=%s"
          % (out["entropy"], out["NPCR"], out["decrypt_exact"]), flush=True)
    return out


def print_table(rows: list[dict]) -> None:
    print("\n| Nhánh | Số S-box | NL (min) | NL (TB 8 bit) | SAC | BIC-NL | BIC-SAC | LAP | DAP |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        m = r["metrics"]
        print("| n = %d | %d | %.0f–%.0f (TB %.1f) | %.2f–%.2f (TB %.2f) | %.4f–%.4f | %.1f–%.1f | %.4f–%.4f | %.4f–%.4f | %.4f–%.4f |" % (
            r["n"], r["n_tested"],
            m["NL"]["min"], m["NL"]["max"], m["NL"]["mean"],
            m["NL_coord_mean"]["min"], m["NL_coord_mean"]["max"], m["NL_coord_mean"]["mean"],
            m["SAC_avg"]["min"], m["SAC_avg"]["max"],
            m["BIC_NL_avg"]["min"], m["BIC_NL_avg"]["max"],
            m["BIC_SAC"]["min"], m["BIC_SAC"]["max"],
            m["LAP"]["min"], m["LAP"]["max"],
            m["DAP"]["min"], m["DAP"]["max"],
        ))
    print()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="lấy mẫu 20 đa thức mỗi nhánh")
    ap.add_argument("--no-image", action="store_true", help="bỏ phần mã hóa ảnh")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    sample = 20 if args.quick else None

    R: dict = {
        "key_str": KEY_STR,
        "K_hex": K.hex(),
        "IV_hex": IV.hex(),
        "quick": args.quick,
        "branches": {},
        "b_variants": {},
        "demo_tables": {},
    }

    for n in (8, 9, 10, 11, 12):
        R["branches"][str(n)] = run_branch(n, sample)

    R["b_variants"] = run_b_variants()
    R["b_is_xor"] = run_b_is_xor()
    R["paper_compare"] = run_paper_compare()

    R["demo_tables"]["n9"] = {
        "poly": 529,
        "sbox": sbox_from_y(529, 1),
        "metrics": summarize(sbox_from_y(529, 1), "n9-529"),
    }
    R["demo_tables"]["n11"] = {
        "poly": 3441,
        "sbox": sbox_from_y(3441, 1),
        "metrics": summarize(sbox_from_y(3441, 1), "n11-3441"),
    }

    if not args.no_image:
        R["image_n9"] = run_image_n9()

    R["runtime_s"] = time.time() - t0
    R["env"] = {"python": sys.version.split()[0], "numpy": np.__version__,
                "cpu_count": os.cpu_count()}

    with open(os.path.join(OUT, "ket_qua.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=1, default=float)

    print_table([R["branches"][k] for k in ("8", "9", "10", "11", "12")])
    print("Đã ghi", os.path.join(OUT, "ket_qua.json"), "| %.1fs" % R["runtime_s"])


if __name__ == "__main__":
    main()
