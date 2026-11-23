"""Nhánh sinh S-box cho n lẻ (n = 9, 11), theo mục 3.2 của Alali và cộng sự.

Với n lẻ, 2^n ≡ 2 (mod 3) nên 3 không chia hết 2^n - 1; do đó x ↦ x^3 là song
ánh trên GF(2^n) và y = sqrt(x^3 + b) cũng là song ánh. Lấy y mod 256 rồi chọn
256 giá trị phân biệt đầu tiên, ta thu được một hoán vị của 0..255.

Khác với nhánh n = 8 (hoành độ + nghịch đảo nhân), ở nhánh này b làm bảng thế đổi
giá trị, nhưng chỉ theo một cách tầm thường: y = sqrt(x)^3 + sqrt(b) nên
S_b(x) = S_c(x) XOR ((sqrt(b) XOR sqrt(c)) mod 256). Có đúng 256 bảng khác nhau,
song chúng chỉ sai khác một hằng số XOR ở đầu ra, nên NL, SAC, BIC, LAP, DAP
không phụ thuộc b.

Mô-đun được giữ tách biệt khỏi core/sbox.py để nhánh n = 8 đang dùng trong
Chương 3 của đồ án không bị thay đổi.
"""
from __future__ import annotations

from typing import Iterable

from .gf2n import GF2n, irreducible_polynomials
from .keyderive import hash_stream, normalize_key

DEFAULT_B = 1

_IRR_CACHE: dict[int, frozenset[int]] = {}


def _irreducibles(n: int) -> frozenset[int]:
    if n not in _IRR_CACHE:
        _IRR_CACHE[n] = frozenset(irreducible_polynomials(n))
    return _IRR_CACHE[n]


def key_to_polynomial_n(key: bytes | str, n: int) -> int:
    """Đa thức bất khả quy bậc n dẫn xuất từ khóa K."""
    if n < 2:
        raise ValueError("n phải >= 2")
    key = normalize_key(key)
    irr = _irreducibles(n)
    k = (n + 7) // 8
    mask = (1 << n) - 1
    it = hash_stream(key)
    while True:
        v = 0
        for _ in range(k):
            v = (v << 8) | next(it)
        f = (1 << n) | (v & mask)
        if f in irr:
            return f


def sbox_from_y(poly: int, b: int = DEFAULT_B) -> list[int]:
    """S-box nhánh tung độ ứng với đa thức f(x) = poly và hệ số b."""
    field = GF2n(poly)
    n = field.n
    if n % 2 == 0:
        raise ValueError(f"n = {n} là số chẵn; nhánh tung độ chỉ dùng cho n lẻ")
    if b == 0:
        raise ValueError("Đường cong Mordell cần b != 0")
    if b < 0 or b >= field.order:
        raise ValueError(f"b phải thuộc GF(2^{n})")
    if poly not in _irreducibles(n):
        raise ValueError(f"0x{poly:X} không phải đa thức bất khả quy bậc {n}")

    sqrt_b = field.sqrt(b)
    out: list[int] = []
    seen: set[int] = set()
    for x in range(field.order):
        s = field.sqrt(x)
        y = field.mul(field.mul(s, s), s) ^ sqrt_b
        r = y & 0xFF
        if r not in seen:
            seen.add(r)
            out.append(r)
            if len(out) == 256:
                break
    if len(out) != 256:
        raise AssertionError("Không đủ 256 giá trị phân biệt")
    return out


def build_sbox_odd(key: bytes | str | None = None, poly: int | None = None,
                   n: int = 9, b: int = DEFAULT_B) -> list[int]:
    """S-box nhánh n lẻ: truyền `key` (dẫn xuất f từ khóa) hoặc `poly`."""
    if (key is None) == (poly is None):
        raise ValueError("Truyền đúng một trong hai: key hoặc poly")
    if poly is None:
        poly = key_to_polynomial_n(key, n)
    return sbox_from_y(poly, b)


def count_b_variants(poly: int, b_values: Iterable[int] | None = None) -> int:
    """Số bảng thế phân biệt khi quét b."""
    field = GF2n(poly)
    if b_values is None:
        b_values = range(1, field.order)
    return len({tuple(sbox_from_y(poly, b)) for b in b_values})
