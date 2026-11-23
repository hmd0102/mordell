"""Đường cong Mordell  E: y^2 = x^3 + b  trên GF(2^n): tính tung độ và sinh tập điểm."""
from __future__ import annotations

from .gf2n import GF2n


def mordell_y(field: GF2n, x: int, b: int) -> int:
    """Tung độ y duy nhất của điểm có hoành độ x: y = sqrt(x^3 + b)."""
    return field.sqrt(field.pow(x, 3) ^ b)


def mordell_points(field: GF2n, b: int) -> list[tuple[int, int]]:
    """Tập điểm P = {(x, y) : x thuộc GF(2^n)} theo thứ tự x = 0, 1, ..."""
    if b == 0:
        raise ValueError("Đường cong Mordell cần b != 0")
    return [(x, mordell_y(field, x, b)) for x in range(field.order)]


def is_on_curve(field: GF2n, point: tuple[int, int], b: int) -> bool:
    x, y = point
    return field.mul(y, y) == field.pow(x, 3) ^ b
