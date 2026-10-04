"""Sinh S-box động từ đường cong Mordell trên GF(2^8).

Ba giai đoạn:
  1. Dẫn xuất đa thức bất khả quy f(x) bậc 8 từ khóa K       (keyderive.py)
  2. Sinh tập điểm P = {(x, y)} trên E: y^2 = x^3 + b          (curve.py)
  3. S(x) = x^-1 trên GF(2)[x]/<f(x)> cho từng hoành độ x của P, theo thứ tự
     x = 0..255; quy ước S(0) = 0.

Với n = 8 bảng thế thu được đúng 256 giá trị, không cần bước rút gọn.
"""
from __future__ import annotations

from .curve import mordell_points
from .gf2n import GF2n, DEGREE_8_IRREDUCIBLES
from .keyderive import key_to_polynomial

DEFAULT_B = 1


def sbox_from_polynomial(poly: int, b: int = DEFAULT_B) -> list[int]:
    """S-box ứng với đa thức f(x) = poly (bậc 8, bất khả quy)."""
    if poly not in DEGREE_8_IRREDUCIBLES:
        raise ValueError(f"0x{poly:X} không phải đa thức bất khả quy bậc 8")
    field = GF2n(poly)
    points = mordell_points(field, b)            # giai đoạn 2
    return [field.inv(x) for x, _y in points]    # giai đoạn 3


def build_sbox(key: bytes | str | None = None, poly: int | None = None,
               b: int = DEFAULT_B) -> list[int]:
    """S-box động: truyền `key` (dẫn xuất f(x) từ khóa) hoặc `poly` (chọn trực tiếp đa thức)."""
    if (key is None) == (poly is None):
        raise ValueError("Truyền đúng một trong hai: key hoặc poly")
    if key is not None:
        poly = key_to_polynomial(key)            # giai đoạn 1
    return sbox_from_polynomial(poly, b)


def inverse_sbox(sbox: list[int]) -> list[int]:
    inv = [0] * 256
    for x, y in enumerate(sbox):
        inv[y] = x
    return inv


def to_matrix(sbox: list[int]) -> list[list[int]]:
    """Ma trận 16x16: hàng floor(x/16), cột x mod 16."""
    return [sbox[r * 16:(r + 1) * 16] for r in range(16)]


def format_matrix(sbox: list[int], hexa: bool = False) -> str:
    cell = (lambda v: f"{v:02x}") if hexa else (lambda v: f"{v:3d}")
    head = "     " + " ".join(f"{c:>3X}" if not hexa else f" {c:X}" for c in range(16))
    lines = [head]
    for r, row in enumerate(to_matrix(sbox)):
        lines.append(f"{r:>3X}  " + " ".join(cell(v) for v in row))
    return "\n".join(lines)


def properties(sbox: list[int]) -> dict:
    return {
        "bijective": len(set(sbox)) == 256,
        "involution": all(sbox[sbox[x]] == x for x in range(256)),
        "fixed_points": [x for x in range(256) if sbox[x] == x],
    }
