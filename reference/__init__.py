"""Ba S-box tham chiếu dùng để so sánh."""
from .aes_sbox import build_aes_sbox
from .weierstrass import build_weierstrass_sbox
from .chaos import build_chaos_sbox

REFERENCE_SBOXES = {
    "aes": build_aes_sbox,
    "weierstrass": build_weierstrass_sbox,
    "chaos": build_chaos_sbox,
}

__all__ = ["build_aes_sbox", "build_weierstrass_sbox", "build_chaos_sbox", "REFERENCE_SBOXES"]
