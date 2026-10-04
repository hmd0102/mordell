"""Dẫn xuất đa thức f(x) từ khóa bí mật K.

Luồng bit giả ngẫu nhiên:  B_i = SHA-256(K || i)  (i: số nguyên 4 byte big-endian,
bắt đầu từ 0), luồng = B_0 || B_1 || ...  Trích lần lượt từng byte v, xét đa thức
monic bậc 8  x^8 + v  và dừng ở đa thức bất khả quy đầu tiên.
"""
from __future__ import annotations

import hashlib
from typing import Iterator

from .gf2n import DEGREE_8_IRREDUCIBLES

KEY_SIZE = 32  # AES-256
_IRR8 = frozenset(DEGREE_8_IRREDUCIBLES)


def normalize_key(key: bytes | str) -> bytes:
    """Quy khóa về đúng 32 byte. Chuỗi hoặc khóa có độ dài khác 32 byte được
    băm SHA-256. Cùng một K này dùng cho cả hai vai trò: sinh S-box và làm
    khóa AES-256."""
    if isinstance(key, str):
        key = key.encode("utf-8")
    if len(key) != KEY_SIZE:
        key = hashlib.sha256(key).digest()
    return key


def hash_stream(key: bytes) -> Iterator[int]:
    """Sinh vô hạn các byte của luồng B_0 || B_1 || ..."""
    i = 0
    while True:
        yield from hashlib.sha256(key + i.to_bytes(4, "big")).digest()
        i += 1


def key_to_polynomial(key: bytes | str, return_trace: bool = False):
    """Trả về đa thức bất khả quy f(x) bậc 8 dẫn xuất từ khóa.

    return_trace=True: trả thêm danh sách các byte đã thử (byte cuối cùng là
    byte cho ra f(x)).
    """
    key = normalize_key(key)
    tried = []
    for v in hash_stream(key):
        tried.append(v)
        f = 0x100 | v
        if f in _IRR8:
            return (f, tried) if return_trace else f
    raise AssertionError("unreachable")
