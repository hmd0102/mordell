"""AES-256 dạng bảng tra T-table: gộp SubBytes + ShiftRows + MixColumns thành
4 bảng 256 phần tử dựng sẵn từ S-box động. Kết quả giống hệt aes.py từng byte
nhưng nhanh hơn nhiều; dùng cho mã hóa ảnh.
"""
from __future__ import annotations

from .aes import NR, gmul, key_expansion


def _words(b: bytes, off: int = 0) -> tuple[int, int, int, int]:
    f = int.from_bytes
    return (f(b[off:off + 4], "big"), f(b[off + 4:off + 8], "big"),
            f(b[off + 8:off + 12], "big"), f(b[off + 12:off + 16], "big"))


def _pack(w0: int, w1: int, w2: int, w3: int) -> bytes:
    return (w0 << 96 | w1 << 64 | w2 << 32 | w3).to_bytes(16, "big")


def _inv_mix_word(w: int) -> int:
    a0, a1, a2, a3 = w.to_bytes(4, "big")
    return ((gmul(a0, 14) ^ gmul(a1, 11) ^ gmul(a2, 13) ^ gmul(a3, 9)) << 24 |
            (gmul(a0, 9) ^ gmul(a1, 14) ^ gmul(a2, 11) ^ gmul(a3, 13)) << 16 |
            (gmul(a0, 13) ^ gmul(a1, 9) ^ gmul(a2, 14) ^ gmul(a3, 11)) << 8 |
            (gmul(a0, 11) ^ gmul(a1, 13) ^ gmul(a2, 9) ^ gmul(a3, 14)))


class AES256:
    """Bộ mã khối AES-256 với S-box tùy ý (khóa vòng tính sẵn khi khởi tạo)."""

    def __init__(self, key: bytes, sbox: list[int]):
        self.sbox = list(sbox)
        self.inv = [0] * 256
        for x, y in enumerate(self.sbox):
            self.inv[y] = x
        te = [[0] * 256 for _ in range(4)]
        td = [[0] * 256 for _ in range(4)]
        for x in range(256):
            s = self.sbox[x]
            s2, s3 = gmul(s, 2), gmul(s, 3)
            te[0][x] = s2 << 24 | s << 16 | s << 8 | s3
            te[1][x] = s3 << 24 | s2 << 16 | s << 8 | s
            te[2][x] = s << 24 | s3 << 16 | s2 << 8 | s
            te[3][x] = s << 24 | s << 16 | s3 << 8 | s2
            i = self.inv[x]
            a, b, c, d = gmul(i, 14), gmul(i, 9), gmul(i, 13), gmul(i, 11)
            td[0][x] = a << 24 | b << 16 | c << 8 | d
            td[1][x] = d << 24 | a << 16 | b << 8 | c
            td[2][x] = c << 24 | d << 16 | a << 8 | b
            td[3][x] = b << 24 | c << 16 | d << 8 | a
        self._te, self._td = te, td
        self.round_keys = key_expansion(key, self.sbox)
        self._ek = [_words(rk) for rk in self.round_keys]
        self._dk = ([self._ek[NR]]
                    + [tuple(_inv_mix_word(w) for w in self._ek[r]) for r in range(NR - 1, 0, -1)]
                    + [self._ek[0]])

    def _enc(self, s0, s1, s2, s3):
        T0, T1, T2, T3 = self._te
        k = self._ek[0]
        s0 ^= k[0]; s1 ^= k[1]; s2 ^= k[2]; s3 ^= k[3]
        for r in range(1, NR):
            k = self._ek[r]
            s0, s1, s2, s3 = (
                T0[s0 >> 24] ^ T1[s1 >> 16 & 255] ^ T2[s2 >> 8 & 255] ^ T3[s3 & 255] ^ k[0],
                T0[s1 >> 24] ^ T1[s2 >> 16 & 255] ^ T2[s3 >> 8 & 255] ^ T3[s0 & 255] ^ k[1],
                T0[s2 >> 24] ^ T1[s3 >> 16 & 255] ^ T2[s0 >> 8 & 255] ^ T3[s1 & 255] ^ k[2],
                T0[s3 >> 24] ^ T1[s0 >> 16 & 255] ^ T2[s1 >> 8 & 255] ^ T3[s2 & 255] ^ k[3])
        S, k = self.sbox, self._ek[NR]
        return ((S[s0 >> 24] << 24 | S[s1 >> 16 & 255] << 16 | S[s2 >> 8 & 255] << 8 | S[s3 & 255]) ^ k[0],
                (S[s1 >> 24] << 24 | S[s2 >> 16 & 255] << 16 | S[s3 >> 8 & 255] << 8 | S[s0 & 255]) ^ k[1],
                (S[s2 >> 24] << 24 | S[s3 >> 16 & 255] << 16 | S[s0 >> 8 & 255] << 8 | S[s1 & 255]) ^ k[2],
                (S[s3 >> 24] << 24 | S[s0 >> 16 & 255] << 16 | S[s1 >> 8 & 255] << 8 | S[s2 & 255]) ^ k[3])

    def _dec(self, s0, s1, s2, s3):
        T0, T1, T2, T3 = self._td
        k = self._dk[0]
        s0 ^= k[0]; s1 ^= k[1]; s2 ^= k[2]; s3 ^= k[3]
        for r in range(1, NR):
            k = self._dk[r]
            s0, s1, s2, s3 = (
                T0[s0 >> 24] ^ T1[s3 >> 16 & 255] ^ T2[s2 >> 8 & 255] ^ T3[s1 & 255] ^ k[0],
                T0[s1 >> 24] ^ T1[s0 >> 16 & 255] ^ T2[s3 >> 8 & 255] ^ T3[s2 & 255] ^ k[1],
                T0[s2 >> 24] ^ T1[s1 >> 16 & 255] ^ T2[s0 >> 8 & 255] ^ T3[s3 & 255] ^ k[2],
                T0[s3 >> 24] ^ T1[s2 >> 16 & 255] ^ T2[s1 >> 8 & 255] ^ T3[s0 & 255] ^ k[3])
        I, k = self.inv, self._dk[NR]
        return ((I[s0 >> 24] << 24 | I[s3 >> 16 & 255] << 16 | I[s2 >> 8 & 255] << 8 | I[s1 & 255]) ^ k[0],
                (I[s1 >> 24] << 24 | I[s0 >> 16 & 255] << 16 | I[s3 >> 8 & 255] << 8 | I[s2 & 255]) ^ k[1],
                (I[s2 >> 24] << 24 | I[s1 >> 16 & 255] << 16 | I[s0 >> 8 & 255] << 8 | I[s3 & 255]) ^ k[2],
                (I[s3 >> 24] << 24 | I[s2 >> 16 & 255] << 16 | I[s1 >> 8 & 255] << 8 | I[s0 & 255]) ^ k[3])

    def encrypt_block(self, block: bytes) -> bytes:
        return _pack(*self._enc(*_words(block)))

    def decrypt_block(self, block: bytes) -> bytes:
        return _pack(*self._dec(*_words(block)))

    def cbc_encrypt(self, data: bytes, iv: bytes) -> bytes:
        _check(data, iv)
        out = bytearray(len(data))
        p = _words(iv)
        for i in range(0, len(data), 16):
            x = _words(data, i)
            p = self._enc(x[0] ^ p[0], x[1] ^ p[1], x[2] ^ p[2], x[3] ^ p[3])
            out[i:i + 16] = _pack(*p)
        return bytes(out)

    def cbc_decrypt(self, data: bytes, iv: bytes) -> bytes:
        _check(data, iv)
        out = bytearray(len(data))
        prev = _words(iv)
        for i in range(0, len(data), 16):
            c = _words(data, i)
            x = self._dec(*c)
            out[i:i + 16] = _pack(x[0] ^ prev[0], x[1] ^ prev[1], x[2] ^ prev[2], x[3] ^ prev[3])
            prev = c
        return bytes(out)

    def ecb_encrypt(self, data: bytes) -> bytes:
        _check(data)
        return b"".join(_pack(*self._enc(*_words(data, i))) for i in range(0, len(data), 16))

    def ecb_decrypt(self, data: bytes) -> bytes:
        _check(data)
        return b"".join(_pack(*self._dec(*_words(data, i))) for i in range(0, len(data), 16))


def _check(data: bytes, iv: bytes | None = None) -> None:
    if len(data) % 16:
        raise ValueError("Độ dài dữ liệu phải là bội số của 16 byte")
    if iv is not None and len(iv) != 16:
        raise ValueError("IV phải dài 16 byte")


def pkcs7_pad(data: bytes) -> bytes:
    n = 16 - len(data) % 16
    return data + bytes([n]) * n


def pkcs7_unpad(data: bytes) -> bytes:
    n = data[-1]
    if not 1 <= n <= 16 or data[-n:] != bytes([n]) * n:
        raise ValueError("Đệm PKCS#7 không hợp lệ (sai khóa?)")
    return data[:-n]
