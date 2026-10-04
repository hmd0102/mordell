"""S-box tham chiếu từ đường cong Weierstrass tổng quát trên GF(2^8)

    E_a: y^2 + x*y = x^3 + a*x^2 + b      (b cố định, a = 1, 2, 3, ...)

Với x != 0, đặt z = y/x, phương trình quy về z^2 + z = c, c = a + x + b/x^2, chỉ
có nghiệm khi Tr(c) = 0 (khi đó có 2 nghiệm y và y + x). Một đường cong chỉ phủ
khoảng một nửa số hoành độ, nên S-box được lấp bằng cách GHÉP ĐIỂM TỪ NHIỀU
ĐƯỜNG CONG: với mỗi a, quét x = 0..255, hoành độ còn trống nhận nghiệm y đầu tiên
chưa được dùng. Đây là S-box TĨNH, chỉ dùng để so sánh.
"""
from __future__ import annotations

from core.gf2n import GF2n

POLY = 0x11B
B_FIXED = 1
_F = GF2n(POLY)
# Bảng nghiệm Artin–Schreier: c -> một nghiệm z của z^2 + z = c
_AS: dict[int, int] = {}
for _z in range(256):
    _AS.setdefault(_F.mul(_z, _z) ^ _z, _z)


def solutions(x: int, a: int, b: int = B_FIXED) -> list[int]:
    """Các tung độ y (0, 1 hoặc 2 giá trị) của điểm có hoành độ x trên E_a."""
    if x == 0:
        return [_F.sqrt(b)]
    c = a ^ x ^ _F.mul(b, _F.inv(_F.mul(x, x)))
    if c not in _AS:
        return []
    y = _F.mul(x, _AS[c])
    return [y, y ^ x]


def build_weierstrass_sbox(b: int = B_FIXED) -> list[int]:
    sbox: list[int | None] = [None] * 256
    used: set[int] = set()
    for a in range(1, 257):
        for x in range(256):
            if sbox[x] is not None:
                continue
            for y in solutions(x, a, b):
                if y not in used:
                    sbox[x] = y
                    used.add(y)
                    break
        if len(used) == 256:
            return sbox  # type: ignore[return-value]
    raise RuntimeError("Không lấp đủ 256 giá trị")
