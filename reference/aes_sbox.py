"""S-box chuẩn AES: nghịch đảo trên GF(2^8)/0x11B rồi biến đổi affine
b_i = y_i ⊕ y_(i+4) ⊕ y_(i+5) ⊕ y_(i+6) ⊕ y_(i+7) ⊕ c_i,  c = 0x63."""
from __future__ import annotations

from core.gf2n import GF2n

AES_POLY = 0x11B
AFFINE_CONST = 0x63


def affine(y: int, c: int = AFFINE_CONST) -> int:
    out = 0
    for i in range(8):
        bit = ((y >> i) ^ (y >> (i + 4) % 8) ^ (y >> (i + 5) % 8)
               ^ (y >> (i + 6) % 8) ^ (y >> (i + 7) % 8) ^ (c >> i)) & 1
        out |= bit << i
    return out


def build_aes_sbox() -> list[int]:
    f = GF2n(AES_POLY)
    return [affine(f.inv(x)) for x in range(256)]
