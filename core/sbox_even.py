"""Nhánh sinh S-box cho n chẵn lớn hơn 8 (n = 10, 12), theo mục 3.1 của Alali và cộng sự.

Với n chẵn, 2^n ≡ 1 (mod 3) nên x ↦ x^3 là ánh xạ 3-1 và không dùng được tung độ.
Quy trình: duyệt hoành độ x = 0, 1, ..., lấy nghịch đảo nhân x^-1 trên
GF(2)[x]/<f(x)>, rút gọn modulo 256 và giữ 256 giá trị phân biệt đầu tiên.

Hệ số b không tham gia. Mô-đun được giữ tách biệt khỏi core/sbox.py để nhánh n = 8
dùng trong mã hóa ảnh không bị thay đổi.
"""
from __future__ import annotations

from .gf2n import GF2n, irreducible_polynomials


def sbox_from_inverse(poly: int) -> list[int]:
    """S-box nhánh hoành độ ứng với đa thức f(x) = poly bậc 10 hoặc 12."""
    field = GF2n(poly)
    n = field.n
    if n % 2 or n <= 8:
        raise ValueError(f"n = {n}; nhánh này chỉ dùng cho n chẵn lớn hơn 8")
    if poly not in irreducible_polynomials(n):
        raise ValueError(f"0x{poly:X} không phải đa thức bất khả quy bậc {n}")

    out: list[int] = []
    seen: set[int] = set()
    for x in range(field.order):
        r = field.inv(x) & 0xFF
        if r not in seen:
            seen.add(r)
            out.append(r)
            if len(out) == 256:
                return out
    raise AssertionError("Không đủ 256 giá trị phân biệt")
