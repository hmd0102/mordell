"""Số học trên trường hữu hạn GF(2^n) = GF(2)[x] / <f(x)>.

Mỗi phần tử (và cả đa thức f(x)) được biểu diễn bằng một số nguyên:
bit thứ i là hệ số của x^i.
"""
from __future__ import annotations

from functools import lru_cache


class GF2n:
    """Trường GF(2^n) xác định bởi đa thức bất khả quy `poly` bậc n."""

    def __init__(self, poly: int):
        if poly < 4:
            raise ValueError("Đa thức phải có bậc >= 2")
        self.poly = poly
        self.n = poly.bit_length() - 1
        self.order = 1 << self.n          # số phần tử của trường
        self._msb = 1 << self.n

    def __repr__(self) -> str:
        return f"GF2n(poly=0x{self.poly:X}, n={self.n})"

    @staticmethod
    def add(a: int, b: int) -> int:
        """Phép cộng (và trừ) trên GF(2^n) là XOR."""
        return a ^ b

    def mul(self, a: int, b: int) -> int:
        """Nhân hai đa thức rồi rút gọn modulo f(x) (thuật toán dịch-và-XOR)."""
        result = 0
        while b:
            if b & 1:
                result ^= a
            b >>= 1
            a <<= 1
            if a & self._msb:
                a ^= self.poly
        return result

    def pow(self, a: int, e: int) -> int:
        """Lũy thừa bằng bình phương liên tiếp."""
        result = 1
        while e:
            if e & 1:
                result = self.mul(result, a)
            a = self.mul(a, a)
            e >>= 1
        return result

    def inv(self, a: int) -> int:
        """Nghịch đảo nhân: a^(2^n - 2) (định lý Lagrange); quy ước 0^-1 = 0."""
        return self.pow(a, self.order - 2) if a else 0

    def sqrt(self, a: int) -> int:
        """Căn bậc hai: a^(2^(n-1)). Phép bình phương là song ánh (Frobenius)
        trên trường đặc số 2 nên mọi phần tử có đúng một căn bậc hai."""
        return self.pow(a, 1 << (self.n - 1)) if a else 0


def poly_mod(a: int, m: int) -> int:
    """Phần dư của phép chia đa thức a cho m trên GF(2)."""
    dm = m.bit_length()
    while a.bit_length() >= dm:
        a ^= m << (a.bit_length() - dm)
    return a


def is_irreducible(f: int) -> bool:
    """Kiểm tra bất khả quy bằng phép chia thử cho mọi đa thức bất khả quy
    có bậc từ 1 đến deg(f)/2."""
    deg = f.bit_length() - 1
    if deg < 1:
        return False
    for d in range(1, deg // 2 + 1):
        for g in irreducible_polynomials(d):
            if poly_mod(f, g) == 0:
                return False
    return True


@lru_cache(maxsize=None)
def irreducible_polynomials(n: int) -> tuple[int, ...]:
    """Danh sách đầy đủ các đa thức monic bất khả quy bậc n trên GF(2)."""
    if n == 1:
        return (0b10, 0b11)             # x, x + 1
    return tuple(f for f in range(1 << n, 1 << (n + 1)) if is_irreducible(f))


def poly_to_str(p: int) -> str:
    """Chuyển đa thức (dạng số nguyên) thành chuỗi 'x^n + ... + 1'."""
    terms = []
    for i in range(p.bit_length() - 1, -1, -1):
        if p >> i & 1:
            terms.append("1" if i == 0 else "x" if i == 1 else f"x^{i}")
    return " + ".join(terms)


# Danh sách 30 đa thức bất khả quy bậc 8, tính một lần khi nạp module.
DEGREE_8_IRREDUCIBLES: tuple[int, ...] = irreducible_polynomials(8)
assert len(DEGREE_8_IRREDUCIBLES) == 30
