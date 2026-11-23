"""Năm tiêu chí đánh giá chất lượng S-box 8x8: NL, SAC, BIC (NL và SAC),
LAP, DAP.

Hàm thành phần ứng với mặt nạ đầu ra b != 0: f_b(x) = parity(b AND S(x)).
"""
from __future__ import annotations

N_BITS = 8
N = 1 << N_BITS


def _popcount_parity_table():
    """table[v] = số bit 1 của v, modulo 2 (0..255)."""
    table = [0] * N
    for v in range(1, N):
        table[v] = table[v >> 1] ^ (v & 1)
    return table

_PARITY = _popcount_parity_table()


def _component_bits(sbox, b: int):
    """f_b(x) với x = 0..255, dưới dạng +1/-1."""
    return [1 if _PARITY[b & sbox[x]] == 0 else -1 for x in range(N)]


def _fwht(vec):
    """Biến đổi Walsh-Hadamard nhanh tại chỗ, độ dài phải là lũy thừa của 2."""
    a = list(vec)
    length = len(a)
    h = 1
    while h < length:
        for i in range(0, length, h * 2):
            for j in range(i, i + h):
                x, y = a[j], a[j + h]
                a[j] = x + y
                a[j + h] = x - y
        h *= 2
    return a


def nonlinearity(sbox):
    """NL(S): giá trị nhỏ nhất trên mọi mặt nạ đầu ra khác 0."""
    best = None
    per_mask = {}
    for b in range(1, N):
        walsh = _fwht(_component_bits(sbox, b))
        max_abs = max(abs(w) for w in walsh)
        nl_b = (N // 2) - max_abs // 2
        per_mask[b] = nl_b
        if best is None or nl_b < best:
            best = nl_b
    return best, per_mask


def sac(sbox):
    """Ma trận phụ thuộc SAC 8x8, giá trị trung bình và độ lệch lớn nhất."""
    D = [[0] * N_BITS for _ in range(N_BITS)]
    for i in range(N_BITS):
        ei = 1 << i
        for x in range(N):
            diff = sbox[x] ^ sbox[x ^ ei]
            for j in range(N_BITS):
                if diff & (1 << j):
                    D[i][j] += 1
    D = [[v / N for v in row] for row in D]
    avg = sum(sum(row) for row in D) / (N_BITS * N_BITS)
    max_dev = max(abs(v - 0.5) for row in D for v in row)
    return D, avg, max_dev


def bic(sbox):
    """BIC-NL và BIC-SAC trên mọi cặp bit đầu ra."""
    nl_vals = []
    sac_vals = []
    for i in range(N_BITS):
        for j in range(N_BITS):
            if i >= j:
                continue
            b = (1 << i) | (1 << j)
            walsh = _fwht(_component_bits(sbox, b))
            max_abs = max(abs(w) for w in walsh)
            nl_vals.append((N // 2) - max_abs // 2)

            g = [_PARITY[b & sbox[x]] for x in range(N)]
            probs = []
            for k in range(N_BITS):
                ek = 1 << k
                changed = sum(1 for x in range(N) if g[x] != g[x ^ ek])
                probs.append(changed / N)
            sac_vals.append(sum(probs) / len(probs))

    bic_nl = sum(nl_vals) / len(nl_vals)
    bic_sac = sum(sac_vals) / len(sac_vals)
    return bic_nl, min(nl_vals), bic_sac


def lap(sbox):
    """Xác suất xấp xỉ tuyến tính lớn nhất (LAP)."""
    best = 0.0
    best_ab = (0, 0)
    for b in range(1, N):
        walsh = _fwht(_component_bits(sbox, b))
        for a in range(N):
            bias = abs(walsh[a]) / (2 * N)
            if bias > best:
                best = bias
                best_ab = (a, b)
    return best, best_ab


def dap(sbox):
    """Bảng phân bố vi sai (DDT) và DAP lớn nhất."""
    max_count = 0
    best_pair = (0, 0)
    for dx in range(1, N):
        counts = [0] * N
        for x in range(N):
            dy = sbox[x ^ dx] ^ sbox[x]
            counts[dy] += 1
        m = max(counts)
        if m > max_count:
            max_count = m
            best_pair = (dx, counts.index(m))
    return max_count, max_count / N, best_pair


def evaluate(sbox, label: str = "S-box") -> dict:
    nl_min, per_mask = nonlinearity(sbox)
    nl_coord = [per_mask[1 << i] for i in range(N_BITS)]
    _, sac_avg, sac_dev = sac(sbox)
    bic_nl, bic_nl_min, bic_sac = bic(sbox)
    lap_val, lap_ab = lap(sbox)
    dap_count, dap_val, dap_pair = dap(sbox)

    result = {
        "label": label,
        "NL": nl_min,
        "NL_coord_mean": sum(nl_coord) / N_BITS,
        "SAC_avg": sac_avg,
        "SAC_max_dev": sac_dev,
        "BIC_NL_avg": bic_nl,
        "BIC_NL_min": bic_nl_min,
        "BIC_SAC": bic_sac,
        "LAP": lap_val,
        "DAP_count": dap_count,
        "DAP": dap_val,
    }
    return result


def format_report(r: dict) -> str:
    return "\n".join([
        f"  NL (phi tuyến)   : {r['NL']}            (tốt nhất đã biết 112)",
        f"  SAC trung bình   : {r['SAC_avg']:.4f}       (lý tưởng 0.5; lệch max {r['SAC_max_dev']:.4f})",
        f"  BIC-NL trung bình: {r['BIC_NL_avg']:.2f}       (min {r['BIC_NL_min']})",
        f"  BIC-SAC          : {r['BIC_SAC']:.4f}       (lý tưởng 0.5)",
        f"  LAP              : {r['LAP']:.4f}       (tốt nhất đã biết 0.0625)",
        f"  DAP              : {r['DAP']:.4f} = {r['DAP_count']}/256  (tốt nhất đã biết 4/256)",
    ])
