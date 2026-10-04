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
    """f_b(x) cho x = 0..255, dạng +-1 (1 nếu bit=0, -1 nếu bit=1) — thuận
    tiện cho biến đổi Walsh-Hadamard nhanh (FWHT)."""
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
    """NL(S) = min trên mọi mặt nạ đầu ra b != 0 của NL(f_b), với
    NL(f) = 2^(n-1) - (1/2) * max_a |W_f(a)|."""
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
    """Ma trận phụ thuộc SAC 8x8: D[i][j] = xác suất bit đầu ra
    j thay đổi khi bit đầu vào i bị đảo, tính trên toàn bộ 256 giá trị x.
    Trả về (ma trận, giá trị trung bình, độ lệch lớn nhất so với 0.5)."""
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
    """BIC-Nonlinearity và BIC-SAC: với mọi cặp bit đầu ra
    (i, j), i != j, xét hàm tổng hợp g = f_i XOR f_j (ứng với mặt nạ đầu
    ra b = (1<<i)|(1<<j)); BIC-NL là NL trung bình của các g này, BIC-SAC
    là độ lệch trung bình so với 0.5 của ma trận phụ thuộc SAC áp dụng cho
    từng g."""
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
    # BIC-SAC trả về giá trị trung bình (không phải độ lệch so với 0.5).
    bic_sac = sum(sac_vals) / len(sac_vals)
    return bic_nl, min(nl_vals), bic_sac


def lap(sbox):
    """Xác suất xấp xỉ tuyến tính lớn nhất, dùng đúng biến đổi
    Walsh-Hadamard đã tính ở nonlinearity(): với mặt nạ đầu ra b, hệ số
    Walsh W_b(a) tại mặt nạ đầu vào a liên hệ trực tiếp với số lần phương
    trình a.x = b.S(x) đúng: #đúng = (256 + W_b(a)) / 2, độ lệch so với
    một nửa là |W_b(a)| / (2*256) — LAP = max trên mọi a, b != 0."""
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
    """Bảng phân bố vi sai (DDT) và DAP lớn nhất: với mỗi sai
    khác đầu vào delta_x != 0, DDT[delta_x][delta_y] = số x sao cho
    S(x XOR delta_x) XOR S(x) = delta_y. DAP = max(DDT bỏ delta_x=0) / 256."""
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
    nl_min, _ = nonlinearity(sbox)
    _, sac_avg, sac_dev = sac(sbox)
    bic_nl, bic_nl_min, bic_sac = bic(sbox)
    lap_val, lap_ab = lap(sbox)
    dap_count, dap_val, dap_pair = dap(sbox)

    result = {
        "label": label,
        "NL": nl_min,
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
        f"  NL (phi tuyến)   : {r['NL']}            (tối ưu 112)",
        f"  SAC trung bình   : {r['SAC_avg']:.4f}       (lý tưởng 0.5; lệch max {r['SAC_max_dev']:.4f})",
        f"  BIC-NL trung bình: {r['BIC_NL_avg']:.2f}       (min {r['BIC_NL_min']})",
        f"  BIC-SAC          : {r['BIC_SAC']:.4f}       (lý tưởng 0.5)",
        f"  LAP              : {r['LAP']:.4f}       (tối ưu 0.0625)",
        f"  DAP              : {r['DAP']:.4f} = {r['DAP_count']}/256  (tối ưu 4/256)",
    ])
