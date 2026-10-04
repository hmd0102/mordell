"""S-box tham chiếu từ bản đồ hỗn loạn Logistic

    x_(n+1) = r * x_n * (1 - x_n),   r = 3.99, x_0 = 0.6, bỏ 51 bước đầu
    b_n = floor(x_n * 256)

Rời rạc hóa không bảo đảm song ánh, nên các vị trí bị trùng được
thay bằng các giá trị còn thiếu: sắp các vị trí trùng theo x_n tăng dần rồi ghép
lần lượt với các byte còn thiếu tăng dần (quy tắc tất định). S-box TĨNH.
"""
from __future__ import annotations

R, X0, TRANSIENT = 3.99, 0.6, 51


def logistic_sequence(count: int = 256, r: float = R, x0: float = X0,
                      transient: int = TRANSIENT) -> list[tuple[float, int]]:
    x = x0
    for _ in range(transient):
        x = r * x * (1 - x)
    seq = []
    for _ in range(count):
        seq.append((x, min(int(x * 256), 255)))
        x = r * x * (1 - x)
    return seq


def build_chaos_sbox(r: float = R, x0: float = X0, transient: int = TRANSIENT) -> list[int]:
    seq = logistic_sequence(256, r, x0, transient)
    sbox: list[int | None] = [None] * 256
    used, dups = set(), []
    for i, (xv, b) in enumerate(seq):
        if b in used:
            dups.append((i, xv))
        else:
            sbox[i] = b
            used.add(b)
    missing = sorted(set(range(256)) - used)
    for (i, _), m in zip(sorted(dups, key=lambda t: t[1]), missing):
        sbox[i] = m
    return sbox  # type: ignore[return-value]
