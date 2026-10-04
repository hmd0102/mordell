"""Chạy toàn bộ thực nghiệm đánh giá S-box và mã hóa ảnh, xuất số liệu và hình vẽ.

Chạy từ thư mục gốc mordell/:
    python -m experiments.chapter3
Kết quả: results/chapter3/ket_qua.json, results/chapter3/hinh/*.png, results/chapter3/anh/*.png
(khoảng 1,5 phút)
"""
from __future__ import annotations

import hashlib, json, os, sys, time, random
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import core.aes as A
from core import (AES256, DEGREE_8_IRREDUCIBLES, build_sbox, inverse_sbox, key_to_polynomial,
                  encrypt_array, decrypt_array)
from core.sbox import properties
from metrics import sbox_metrics as sm, image_metrics as im
from reference import build_aes_sbox, build_weierstrass_sbox, build_chaos_sbox

OUT = os.path.join(ROOT, "results", "chapter3")
FIG = os.path.join(OUT, "hinh")
IMGDIR = os.path.join(OUT, "anh")
DATA = os.path.join(ROOT, "data", "images")

KEY_STR = "day-la-mot-khoa-bi-mat-vi-du"
K = hashlib.sha256(KEY_STR.encode()).digest()          # = normalize_key(KEY_STR)
IV = hashlib.sha256(b"iv-thuc-nghiem-chuong-3").digest()[:16]
R = {}
rng = random.Random(2026)


def enc_arr(arr, key, sb, iv=IV, mode="cbc"):
    return encrypt_array(arr, key, iv, sb, mode)


def dec_arr(carr, key, sb, h0, iv=IV):
    return decrypt_array(carr, key, iv, h0, sb)


def psnr(a, b):
    mse = float(((a.astype(float) - b.astype(float)) ** 2).mean())
    return im.psnr(a, b), mse


img_stats = im.evaluate_image


def flip_pixel(arr, pos):
    b = arr.copy()
    flat = b.reshape(-1)
    flat[pos] = (int(flat[pos]) + 1) % 256
    return b


def flip_key_bit(key, bit):
    k = bytearray(key); k[bit // 8] ^= 1 << (bit % 8); return bytes(k)


def ref_cbc_encrypt(data, key, sb, iv):
    """CBC dùng cài đặt tham chiếu core.aes (để so tốc độ với bản T-table)."""
    rk = A.key_expansion(key, sb); prev = iv; out = bytearray()
    for i in range(0, len(data), 16):
        prev = A.encrypt_block(bytes(x ^ y for x, y in zip(data[i:i + 16], prev)), rk, sb)
        out += prev
    return bytes(out)


def verify_fast():
    sb = build_sbox(key=b"verify"); key, iv = os.urandom(32), os.urandom(16)
    data = os.urandom(16 * 200)
    f = AES256(key, sb)
    return f.cbc_encrypt(data, iv) == ref_cbc_encrypt(data, key, sb, iv) and f.cbc_decrypt(f.cbc_encrypt(data, iv), iv) == data


def load_images():
    lena = np.array(Image.open(os.path.join(DATA, "lena.png")).convert("RGB"))
    baboon = np.array(Image.open(os.path.join(DATA, "baboon.png")).convert("RGB"))
    lena_g = np.array(Image.fromarray(lena).convert("L"))
    black = np.zeros((256, 256), dtype=np.uint8)
    # ảnh tổng hợp nhiều vùng màu phẳng (dùng cho so sánh ECB/CBC)
    syn = Image.new("L", (256, 256), 235)
    d = ImageDraw.Draw(syn)
    d.rectangle([24, 24, 120, 120], fill=40)
    d.ellipse([136, 24, 232, 120], fill=110)
    d.polygon([(24, 232), (72, 136), (120, 232)], fill=170)
    d.rectangle([136, 136, 232, 232], fill=80)
    d.rectangle([160, 160, 208, 208], fill=200)
    syn = np.array(syn)
    for name, a in [("lena_gray", lena_g), ("black", black), ("synthetic", syn)]:
        Image.fromarray(a).save(os.path.join(IMGDIR, f"{name}.png"))
    return {"Lena (RGB)": lena, "Baboon (RGB)": baboon, "Lena (xám)": lena_g,
            "Ảnh đen": black, "Ảnh tổng hợp": syn}


def part_A():
    t = time.perf_counter(); ok = verify_fast(); R["aes_fast_verified"] = ok
    # kiểm tra AES-256 với vector chuẩn
    s_aes = build_aes_sbox()
    rk = A.key_expansion(bytes(range(32)), s_aes)
    ct = A.encrypt_block(bytes.fromhex("00112233445566778899aabbccddeeff"), rk, s_aes).hex()
    R["fips197_c3"] = {"ciphertext": ct, "expected": "8ea2b7ca516745bfeafc49904b496089",
                       "pass": ct == "8ea2b7ca516745bfeafc49904b496089"}
    pt_back = A.decrypt_block(bytes.fromhex(ct), rk, inverse_sbox(s_aes)).hex()
    R["fips197_c3"]["decrypt_pass"] = pt_back == "00112233445566778899aabbccddeeff"

    poly = key_to_polynomial(K)
    s_prop = build_sbox(key=K)
    R["key_str"] = KEY_STR; R["K_hex"] = K.hex(); R["IV_hex"] = IV.hex()
    R["poly"] = poly; R["sbox_prop"] = s_prop
    R["sbox_prop_props"] = properties(s_prop)
    s_w = build_weierstrass_sbox()
    s_c = build_chaos_sbox()
    four = {"Đề xuất (Mordell)": s_prop, "AES chuẩn": s_aes, "Weierstrass": s_w, "Hỗn loạn (Logistic)": s_c}
    R["four_sboxes"] = {}
    for k, s in four.items():
        e = sm.evaluate(s, k)
        e["fixed_points"] = sum(s[x] == x for x in range(256))
        R["four_sboxes"][k] = e
    # toàn bộ 30 đa thức
    rows = []
    for p in DEGREE_8_IRREDUCIBLES:
        s = build_sbox(poly=p)
        e = sm.evaluate(s, str(p)); e["poly"] = p
        rows.append(e)
    R["all30"] = rows
    R["all30_distinct_sboxes"] = len({tuple(build_sbox(poly=p)) for p in DEGREE_8_IRREDUCIBLES})
    # phân bố f(x) theo khóa ngẫu nhiên
    N_KEYS = 30000
    cnt = {p: 0 for p in DEGREE_8_IRREDUCIBLES}
    for _ in range(N_KEYS):
        cnt[key_to_polynomial(hashlib.sha256(b"khoa-ngau-nhien-%d" % _).digest())] += 1
    e = N_KEYS / 30
    R["poly_dist"] = {"n_keys": N_KEYS, "counts": cnt,
                      "chi2": sum((v - e) ** 2 / e for v in cnt.values()), "df": 29,
                      "chi2_crit_0.05": 42.557}
    # độ nhạy S-box theo khóa: đổi 1 bit khóa -> f(x) đổi?
    changed = 0; diff_frac = []
    for bit in range(256):
        k2 = flip_key_bit(K, bit)
        s2 = build_sbox(key=k2)
        if s2 != s_prop:
            changed += 1
        diff_frac.append(sum(a != b for a, b in zip(s_prop, s2)) / 256)
    R["sbox_key_sens"] = {"bits": 256, "sbox_changed": changed, "mean_diff_frac": float(np.mean(diff_frac))}
    # thời gian
    ts = []
    for _ in range(20):
        t = time.perf_counter(); build_sbox(key=os.urandom(32)); ts.append(time.perf_counter() - t)
    R["time_sbox_ms"] = 1000 * float(np.mean(ts))
    t = time.perf_counter()
    for _ in range(20): A.key_expansion(K, s_prop)
    R["time_keyexp_ms"] = 1000 * (time.perf_counter() - t) / 20
    return four


def part_B(imgs, s_prop):
    res = {}
    for name, a in imgs.items():
        h0 = a.shape[0]
        c = enc_arr(a, K, s_prop)
        d = dec_arr(c, K, s_prop, h0)
        p, mse = psnr(a, d)
        r = {"shape": list(a.shape), "cipher_shape": list(c.shape),
             "plain": img_stats(a), "cipher": img_stats(c),
             "decrypt_mse": mse, "decrypt_exact": bool(np.array_equal(a, d))}
        # NPCR/UACI theo vị trí điểm ảnh bị đổi
        n = a.size
        positions = {"đầu ảnh": 0, "giữa ảnh": n // 2, "cuối ảnh": n - 1}
        npc = {}
        for lab, pos in positions.items():
            c2 = enc_arr(flip_pixel(a, pos), K, s_prop)
            cmp = im.compare_images(c, c2)
            npc[lab] = {"pos": pos, "NPCR": cmp["NPCR"], "UACI": cmp["UACI"]}
        rnd = []
        for _ in range(10):
            pos = rng.randrange(n)
            c2 = enc_arr(flip_pixel(a, pos), K, s_prop)
            cmp = im.compare_images(c, c2)
            rnd.append((pos / n, cmp["NPCR"], cmp["UACI"]))
        npc["ngẫu nhiên (TB 10 lần)"] = {"NPCR": float(np.mean([x[1] for x in rnd])),
                                        "UACI": float(np.mean([x[2] for x in rnd])),
                                        "samples": rnd}
        r["npcr"] = npc
        # độ nhạy khóa
        ks = []
        for bit in (0, 127, 255):
            k2 = flip_key_bit(K, bit)
            s2 = build_sbox(key=k2)
            c2 = enc_arr(a, k2, s2)
            cmp = im.compare_images(c, c2)
            dwrong = dec_arr(c, k2, s2, h0)
            cmpd = im.compare_images(a, dwrong)
            ks.append({"bit": bit, "same_poly": s2 == s_prop,
                       "enc_NPCR": cmp["NPCR"], "enc_UACI": cmp["UACI"],
                       "dec_NPCR_vs_plain": cmpd["NPCR"],
                       "dec_wrong_entropy": img_stats(dwrong)["entropy"]})
            if bit == 0:
                r["_wrong"] = dwrong
        r["key_sens"] = ks
        # chỉ đổi S-box (cùng khóa AES): chọn đa thức khác
        other = next(p for p in DEGREE_8_IRREDUCIBLES if p != R["poly"])
        s_other = build_sbox(poly=other)
        c3 = enc_arr(a, K, s_other)
        cmp = im.compare_images(c, c3)
        d3 = dec_arr(c, K, s_other, h0)
        r["sbox_only"] = {"other_poly": other, "NPCR": cmp["NPCR"], "UACI": cmp["UACI"],
                          "dec_NPCR_vs_plain": im.compare_images(a, d3)["NPCR"]}
        r["_c"], r["_d"] = c, d
        res[name] = r
        print("B done", name, flush=True)
    return res


def part_C(imgs, four):
    """So sánh 4 S-box trên Lena & Baboon, cùng K, IV."""
    out = []
    for name in ("Lena (RGB)", "Baboon (RGB)"):
        a = imgs[name]
        for sname, s in four.items():
            c = enc_arr(a, K, s)
            st = img_stats(c)
            c2 = enc_arr(flip_pixel(a, 0), K, s)
            cmp = im.compare_images(c, c2)
            out.append({"image": name, "sbox": sname, "entropy": st["entropy"],
                        "corr": st["corr"], "glcm": st["glcm"], "glcm8": st["glcm8"],
                        "NPCR": cmp["NPCR"], "UACI": cmp["UACI"]})
    return out


def part_D(imgs, s_prop):
    """ECB vs CBC, cắt xén/nhiễu, tốc độ."""
    D = {}
    syn = imgs["Ảnh tổng hợp"]
    D["_ecb"] = enc_arr(syn, K, s_prop, mode="ecb")
    D["_cbc"] = enc_arr(syn, K, s_prop)
    D["ecb_stats"] = img_stats(D["_ecb"]); D["cbc_stats"] = img_stats(D["_cbc"])
    # cắt xén / nhiễu trên Lena xám
    a = imgs["Lena (xám)"]; c = enc_arr(a, K, s_prop)
    rob = {}
    crop = c.copy(); crop[:128, :128] = 0
    dc = dec_arr(crop, K, s_prop, a.shape[0]); rob["crop_1_16"] = {"psnr": psnr(a, dc)[0]}
    crop4 = c.copy(); crop4[:256, :256] = 0
    dc4 = dec_arr(crop4, K, s_prop, a.shape[0]); rob["crop_1_4"] = {"psnr": psnr(a, dc4)[0]}
    nz = c.copy(); r2 = np.random.default_rng(1); m = r2.random(nz.shape) < 0.01
    nz[m] = r2.choice([0, 255], size=int(m.sum()))
    dn = dec_arr(nz, K, s_prop, a.shape[0]); rob["saltpepper_1pct"] = {"psnr": psnr(a, dn)[0]}
    D["robust"] = rob
    D["_rob_imgs"] = (crop, dc, crop4, dc4, nz, dn)
    # tốc độ
    lena = imgs["Lena (RGB)"]
    padded = lena.tobytes()  # 512x512x3 = 786.432 byte, chia hết cho 16
    sub = padded[:16 * 2048]
    t = time.perf_counter(); ref_cbc_encrypt(sub, K, s_prop, IV); tref = time.perf_counter() - t
    f = AES256(K, s_prop)
    t = time.perf_counter(); f.cbc_encrypt(padded, IV); tf = time.perf_counter() - t
    t = time.perf_counter(); f.cbc_decrypt(f.cbc_encrypt(padded, IV), IV); tfd = time.perf_counter() - t - tf
    D["speed"] = {"ref_KBps": len(sub) / 1024 / tref, "fast_KBps": len(padded) / 1024 / tf,
                  "lena_bytes": len(padded), "fast_enc_s": tf, "fast_dec_s": tfd,
                  "ref_est_lena_s": len(padded) / (len(sub) / tref)}
    return D


def figures(imgs, B, D, four):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.edgecolor": "#52514e",
                         "axes.labelcolor": "#0b0b0b", "xtick.color": "#52514e", "ytick.color": "#52514e"})
    BLUE, ORANGE = "#2a78d6", "#eb6834"

    def show(ax, a, title):
        ax.imshow(a, cmap="gray" if a.ndim == 2 else None, vmin=0, vmax=255)
        ax.set_title(title, fontsize=10); ax.axis("off")

    # ảnh gốc / mã hóa / giải mã cho 5 ảnh
    names = list(imgs)
    fig, axs = plt.subplots(len(names), 3, figsize=(8.2, 2.75 * len(names)))
    for i, n in enumerate(names):
        show(axs[i, 0], imgs[n], f"{n} – ảnh gốc")
        show(axs[i, 1], B[n]["_c"], "Ảnh mã hóa")
        show(axs[i, 2], B[n]["_d"], "Ảnh giải mã")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "H3_2_goc_ma_hoa_giai_ma.png"), dpi=170); plt.close(fig)

    # histogram (Lena RGB theo kênh; Lena xám; ảnh đen)
    fig, axs = plt.subplots(3, 2, figsize=(8.2, 7.2))
    cols = ["#d03b3b", "#008300", "#2a78d6"]
    lab = ["R", "G", "B"]
    for j, (src, t) in enumerate([(imgs["Lena (RGB)"], "Lena (RGB) – gốc"), (B["Lena (RGB)"]["_c"], "Lena (RGB) – mã hóa")]):
        ax = axs[0, j]
        for k in range(3):
            ax.plot(np.arange(256), np.bincount(src[..., k].ravel(), minlength=256), color=cols[k], lw=1.2, label=lab[k])
        ax.set_title(t); ax.set_xlim(0, 255); ax.set_ylim(0, 4600); ax.legend(frameon=False, fontsize=8, ncol=3)
    for row, n in ((1, "Lena (xám)"), (2, "Ảnh đen")):
        for j, (src, t) in enumerate([(imgs[n], f"{n} – gốc"), (B[n]["_c"], f"{n} – mã hóa")]):
            ax = axs[row, j]
            ax.bar(np.arange(256), np.bincount(src.ravel(), minlength=256), width=1.0, color=BLUE)
            ax.set_title(t); ax.set_xlim(-1, 256)
            if j == 1 and n == "Lena (xám)": ax.set_ylim(0, 2800)
    for ax in axs[-1]: ax.set_xlabel("Giá trị điểm ảnh")
    for ax in axs[:, 0]: ax.set_ylabel("Tần suất")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "H3_3_histogram.png"), dpi=170); plt.close(fig)

    # phân tán cặp điểm ảnh lân cận (Lena xám), 3 hướng
    a = imgs["Lena (xám)"].astype(int); c = B["Lena (xám)"]["_c"][:a.shape[0]].astype(int)
    r2 = np.random.default_rng(7)
    fig, axs = plt.subplots(2, 3, figsize=(8.2, 5.6))
    dirs = [("Ngang", (0, 1)), ("Dọc", (1, 0)), ("Chéo", (1, 1))]
    for row, (src, t) in enumerate([(a, "gốc"), (c, "mã hóa")]):
        H, W = src.shape
        for j, (dn, (dy, dx)) in enumerate(dirs):
            ys = r2.integers(0, H - dy, 3000); xs = r2.integers(0, W - dx, 3000)
            axs[row, j].scatter(src[ys, xs], src[ys + dy, xs + dx], s=1.5, color=BLUE if row == 0 else ORANGE, alpha=.6, linewidths=0)
            axs[row, j].set_xlim(0, 255); axs[row, j].set_ylim(0, 255)
            axs[row, j].set_title(f"{dn} – ảnh {t}", fontsize=10)
            axs[row, j].set_xlabel("p(x, y)", fontsize=8); axs[row, j].set_ylabel("điểm lân cận", fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "H3_4_tuong_quan.png"), dpi=170); plt.close(fig)

    # ECB vs CBC
    fig, axs = plt.subplots(1, 3, figsize=(8.2, 3.0))
    show(axs[0], imgs["Ảnh tổng hợp"], "Ảnh gốc"); show(axs[1], D["_ecb"], "AES-256-ECB"); show(axs[2], D["_cbc"], "AES-256-CBC")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "H3_5_ecb_cbc.png"), dpi=170); plt.close(fig)

    # độ nhạy khóa
    fig, axs = plt.subplots(1, 3, figsize=(8.2, 3.0))
    show(axs[0], B["Lena (xám)"]["_c"], "Ảnh mã hóa (khóa K)")
    show(axs[1], B["Lena (xám)"]["_d"], "Giải mã với K")
    show(axs[2], B["Lena (xám)"]["_wrong"], "Giải mã với K′ (lệch 1 bit)")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "H3_6_do_nhay_khoa.png"), dpi=170); plt.close(fig)

    # cắt xén / nhiễu
    crop, dc, crop4, dc4, nz, dn = D["_rob_imgs"]
    fig, axs = plt.subplots(2, 3, figsize=(8.2, 5.6))
    show(axs[0, 0], crop, "Mất 1/16 bản mã"); show(axs[0, 1], crop4, "Mất 1/4 bản mã"); show(axs[0, 2], nz, "Nhiễu muối tiêu 1%")
    show(axs[1, 0], dc, f"Giải mã – PSNR {D['robust']['crop_1_16']['psnr']:.2f} dB")
    show(axs[1, 1], dc4, f"Giải mã – PSNR {D['robust']['crop_1_4']['psnr']:.2f} dB")
    show(axs[1, 2], dn, f"Giải mã – PSNR {D['robust']['saltpepper_1pct']['psnr']:.2f} dB")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "H3_7_cat_xen_nhieu.png"), dpi=170); plt.close(fig)

    # phân bố đa thức theo khóa
    cnt = R["poly_dist"]["counts"]
    fig, ax = plt.subplots(figsize=(8.2, 3.2))
    ps = list(cnt); ax.bar(range(30), [cnt[p] for p in ps], color=BLUE, width=0.7)
    ax.axhline(R["poly_dist"]["n_keys"] / 30, color="#52514e", lw=1, ls="--")
    ax.text(29.4, R["poly_dist"]["n_keys"] / 30 + 110, "kỳ vọng 1000", ha="right", fontsize=8, color="#52514e")
    ax.set_ylim(0, 1250); ax.set_xticks(range(30)); ax.set_xticklabels(ps, rotation=90, fontsize=8)
    ax.set_xlabel("Đa thức bất khả quy f(x) (giá trị thập phân)"); ax.set_ylabel("Số khóa")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "H3_1_phan_bo_da_thuc.png"), dpi=170); plt.close(fig)

    # NPCR theo vị trí điểm ảnh thay đổi (Lena RGB)
    s = sorted(B["Lena (RGB)"]["npcr"]["ngẫu nhiên (TB 10 lần)"]["samples"])
    fig, ax = plt.subplots(figsize=(8.2, 3.0))
    xs = [0] + [x[0] for x in s] + [0.5, 1.0]
    ys = [B["Lena (RGB)"]["npcr"]["đầu ảnh"]["NPCR"]] + [x[1] for x in s] + \
         [B["Lena (RGB)"]["npcr"]["giữa ảnh"]["NPCR"], B["Lena (RGB)"]["npcr"]["cuối ảnh"]["NPCR"]]
    o = np.argsort(xs); xs = np.array(xs)[o]; ys = np.array(ys)[o]
    ax.plot(xs * 100, ys, color=BLUE, lw=2, marker="o", ms=5)
    ax.plot([0, 100], [99.6, 0], color="#52514e", lw=1, ls="--", zorder=0)
    ax.text(62, 52, "đường lý thuyết: 99,6 × (1 − vị trí)", fontsize=8, color="#52514e")
    ax.set_xlabel("Vị trí điểm ảnh bị thay đổi (% độ dài chuỗi byte)"); ax.set_ylabel("NPCR (%)")
    ax.set_xlim(0, 100); ax.set_ylim(0, 102)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "H3_8_npcr_vi_tri.png"), dpi=170); plt.close(fig)


def main():
    os.makedirs(FIG, exist_ok=True); os.makedirs(IMGDIR, exist_ok=True)
    t0 = time.time()
    four = part_A(); print("A done", flush=True)
    imgs = load_images()
    B = part_B(imgs, R["sbox_prop"])
    R["C"] = part_C(imgs, four); print("C done", flush=True)
    D = part_D(imgs, R["sbox_prop"]); print("D done", flush=True)
    figures(imgs, B, D, four)
    for n, a in imgs.items():
        Image.fromarray(B[n]["_c"]).save(os.path.join(IMGDIR, f"enc_{n.replace(' ', '_').replace('(', '').replace(')', '')}.png"))
    R["B"] = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in B.items()}
    R["D"] = {k: v for k, v in D.items() if not k.startswith("_")}
    R["runtime_s"] = time.time() - t0
    R["env"] = {"python": sys.version.split()[0], "numpy": np.__version__, "cpu_count": os.cpu_count()}
    with open(os.path.join(OUT, "ket_qua.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=1, default=float)
    print("xong", R["runtime_s"])


if __name__ == "__main__":
    main()
