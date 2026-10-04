"""Tiêu chí đánh giá ảnh mã hóa: entropy, hệ số tương quan các điểm
ảnh lân cận, GLCM (contrast, homogeneity, energy), NPCR, UACI; thêm kiểm định
khi bình phương cho histogram và PSNR.

Các hàm cơ sở nhận một kênh (mảng 2D uint8). Các hàm *_image tính cho từng kênh
rồi lấy trung bình (cách trình bày phổ biến với ảnh màu).
"""
from __future__ import annotations

import numpy as np

LEVELS = 256
_U = np.arange(LEVELS).reshape(-1, 1)
_V = np.arange(LEVELS).reshape(1, -1)
_DIFF2 = (_U - _V) ** 2
CHI2_CRIT_255 = 293.2478   # ngưỡng χ² (255 bậc tự do, mức ý nghĩa 5%)


def channels(img: np.ndarray) -> list[np.ndarray]:
    return [img] if img.ndim == 2 else [img[..., c] for c in range(img.shape[2])]


def entropy(ch: np.ndarray) -> float:
    p = np.bincount(ch.ravel(), minlength=LEVELS) / ch.size
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def chi_square(ch: np.ndarray) -> float:
    obs = np.bincount(ch.ravel(), minlength=LEVELS)
    e = ch.size / LEVELS
    return float(((obs - e) ** 2 / e).sum())


def correlation(ch: np.ndarray, direction: str) -> float:
    """Hệ số tương quan Pearson trên TOÀN BỘ cặp điểm lân cận theo hướng
    'horizontal' | 'vertical' | 'diagonal'."""
    c = ch.astype(np.float64)
    a, b = {"horizontal": (c[:, :-1], c[:, 1:]),
            "vertical": (c[:-1, :], c[1:, :]),
            "diagonal": (c[:-1, :-1], c[1:, 1:])}[direction]
    a, b = a.ravel() - a.mean(), b.ravel() - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den else float("nan")


def glcm(ch: np.ndarray, levels: int = LEVELS) -> np.ndarray:
    """GLCM chuẩn hóa, khoảng cách 1, hướng ngang. levels < 256: lượng tử hóa
    ảnh về `levels` mức xám trước khi đếm."""
    q = ch.astype(np.int64) * levels // 256
    idx = q[:, :-1].ravel() * levels + q[:, 1:].ravel()
    m = np.bincount(idx, minlength=levels * levels).reshape(levels, levels).astype(float)
    return m / m.sum()


def glcm_features(ch: np.ndarray, levels: int = LEVELS) -> dict:
    """Contrast = Σ(u-v)²p ; Energy = Σp².
    Homogeneity: levels = 256 -> Σ p/(1+(u-v)²) ; levels = 8 -> Σ p/(1+|u-v|)."""
    m = glcm(ch, levels)
    u = np.arange(levels).reshape(-1, 1); v = np.arange(levels).reshape(1, -1)
    d = u - v
    homog = (m / (1 + d ** 2)).sum() if levels == LEVELS else (m / (1 + np.abs(d))).sum()
    return {"contrast": float((m * d ** 2).sum()), "homogeneity": float(homog),
            "energy": float((m ** 2).sum())}


def npcr(c1: np.ndarray, c2: np.ndarray) -> float:
    return float((c1 != c2).mean() * 100)


def uaci(c1: np.ndarray, c2: np.ndarray) -> float:
    return float((np.abs(c1.astype(float) - c2.astype(float)) / 255).mean() * 100)


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = float(((a.astype(float) - b.astype(float)) ** 2).mean())
    return float("inf") if mse == 0 else 10 * np.log10(255 ** 2 / mse)


def _avg(f, img, *args):
    return float(np.mean([f(c, *args) for c in channels(img)]))


def evaluate_image(img: np.ndarray) -> dict:
    """Các chỉ số của MỘT ảnh (trung bình các kênh)."""
    g = [glcm_features(c) for c in channels(img)]
    g8 = [glcm_features(c, 8) for c in channels(img)]
    return {
        "entropy": _avg(entropy, img),
        "chi2": _avg(chi_square, img),
        "corr": {d: _avg(correlation, img, d) for d in ("horizontal", "vertical", "diagonal")},
        "glcm": {k: float(np.mean([x[k] for x in g])) for k in g[0]},
        "glcm8": {k: float(np.mean([x[k] for x in g8])) for k in g8[0]},
    }


def compare_images(c1: np.ndarray, c2: np.ndarray) -> dict:
    """NPCR/UACI giữa hai ảnh mã hóa cùng kích thước (trung bình các kênh)."""
    if c1.shape != c2.shape:
        raise ValueError("Hai ảnh phải cùng kích thước")
    return {"NPCR": float(np.mean([npcr(a, b) for a, b in zip(channels(c1), channels(c2))])),
            "UACI": float(np.mean([uaci(a, b) for a, b in zip(channels(c1), channels(c2))]))}


def format_report(r: dict) -> str:
    c, g = r["corr"], r["glcm"]
    return "\n".join([
        f"  Entropy       : {r['entropy']:.4f}   (lý tưởng 8)",
        f"  Chi-square    : {r['chi2']:.2f}   ({'đạt' if r['chi2'] < CHI2_CRIT_255 else 'không đạt'}, ngưỡng {CHI2_CRIT_255})",
        f"  Tương quan    : ngang {c['horizontal']:.4f} | dọc {c['vertical']:.4f} | chéo {c['diagonal']:.4f}",
        f"  GLCM (256 mức): contrast {g['contrast']:.2f} | homogeneity {g['homogeneity']:.4f} | energy {g['energy']:.2e}",
    ])
