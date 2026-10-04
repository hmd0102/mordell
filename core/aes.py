"""AES-256 theo chuẩn FIPS-197, bảng thế SubBytes/SubWord truyền vào như tham số.
Cài đặt từng bước theo đặc tả (dễ theo dõi, có ghi vết trạng thái); bản tối ưu
tốc độ dùng cho mã hóa ảnh nằm ở aes_fast.py.

Mọi phép toán nội tại của AES (MixColumns, Rcon) dùng đa thức cố định 0x11B,
độc lập với đa thức f(x) dùng để sinh S-box.
"""
from __future__ import annotations

AES_POLY = 0x11B
NB, NK, NR = 4, 8, 14      # số cột state, số từ của khóa 256 bit, số vòng

State = list[list[int]]    # state[hàng][cột]


def xtime(a: int) -> int:
    a <<= 1
    return (a ^ AES_POLY) & 0xFF if a & 0x100 else a


def gmul(a: int, b: int) -> int:
    """Nhân trên GF(2^8) của AES (modulo 0x11B)."""
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        a = xtime(a)
        b >>= 1
    return r


_MUL = {k: tuple(gmul(a, k) for a in range(256)) for k in (2, 3, 9, 11, 13, 14)}
_RCON = [1]
for _ in range(15):
    _RCON.append(xtime(_RCON[-1]))


def key_expansion(key: bytes, sbox: list[int]) -> list[bytes]:
    """15 khóa vòng K0..K14 (16 byte). SubWord dùng bảng thế động `sbox`."""
    if len(key) != 32:
        raise ValueError("AES-256 cần khóa 32 byte")
    w = [key[4 * i:4 * i + 4] for i in range(NK)]
    for i in range(NK, NB * (NR + 1)):
        t = w[i - 1]
        if i % NK == 0:
            t = bytes(sbox[b] for b in t[1:] + t[:1])          # SubWord(RotWord)
            t = bytes([t[0] ^ _RCON[i // NK - 1]]) + t[1:]      # ⊕ Rcon
        elif i % NK == 4:
            t = bytes(sbox[b] for b in t)                      # SubWord
        w.append(bytes(a ^ b for a, b in zip(w[i - NK], t)))
    return [b"".join(w[4 * r:4 * r + 4]) for r in range(NR + 1)]


def bytes_to_state(block: bytes) -> State:
    return [[block[c * 4 + r] for c in range(4)] for r in range(4)]


def state_to_bytes(s: State) -> bytes:
    return bytes(s[r][c] for c in range(4) for r in range(4))


def sub_bytes(s: State, sbox: list[int]) -> State:
    return [[sbox[v] for v in row] for row in s]


def shift_rows(s: State) -> State:
    return [[s[r][(c + r) % 4] for c in range(4)] for r in range(4)]


def inv_shift_rows(s: State) -> State:
    return [[s[r][(c - r) % 4] for c in range(4)] for r in range(4)]


def mix_columns(s: State) -> State:
    m2, m3 = _MUL[2], _MUL[3]
    out = [[0] * 4 for _ in range(4)]
    for c in range(4):
        a0, a1, a2, a3 = (s[r][c] for r in range(4))
        out[0][c] = m2[a0] ^ m3[a1] ^ a2 ^ a3
        out[1][c] = a0 ^ m2[a1] ^ m3[a2] ^ a3
        out[2][c] = a0 ^ a1 ^ m2[a2] ^ m3[a3]
        out[3][c] = m3[a0] ^ a1 ^ a2 ^ m2[a3]
    return out


def inv_mix_columns(s: State) -> State:
    m9, m11, m13, m14 = _MUL[9], _MUL[11], _MUL[13], _MUL[14]
    out = [[0] * 4 for _ in range(4)]
    for c in range(4):
        a0, a1, a2, a3 = (s[r][c] for r in range(4))
        out[0][c] = m14[a0] ^ m11[a1] ^ m13[a2] ^ m9[a3]
        out[1][c] = m9[a0] ^ m14[a1] ^ m11[a2] ^ m13[a3]
        out[2][c] = m13[a0] ^ m9[a1] ^ m14[a2] ^ m11[a3]
        out[3][c] = m11[a0] ^ m13[a1] ^ m9[a2] ^ m14[a3]
    return out


def add_round_key(s: State, rk: bytes) -> State:
    k = bytes_to_state(rk)
    return [[s[r][c] ^ k[r][c] for c in range(4)] for r in range(4)]


def encrypt_block(block: bytes, round_keys: list[bytes], sbox: list[int],
                  trace: list | None = None) -> bytes:
    """Mã hóa một khối 16 byte. Nếu truyền `trace` (list), trạng thái sau mỗi
    bước được ghi lại dạng (vòng, tên bước, bytes)."""
    def log(r, name, s):
        if trace is not None:
            trace.append((r, name, state_to_bytes(s)))
    s = add_round_key(bytes_to_state(block), round_keys[0]); log(0, "AddRoundKey", s)
    for r in range(1, NR + 1):
        s = sub_bytes(s, sbox); log(r, "SubBytes", s)
        s = shift_rows(s); log(r, "ShiftRows", s)
        if r != NR:
            s = mix_columns(s); log(r, "MixColumns", s)
        s = add_round_key(s, round_keys[r]); log(r, "AddRoundKey", s)
    return state_to_bytes(s)


def decrypt_block(block: bytes, round_keys: list[bytes], inv_sbox: list[int],
                  trace: list | None = None) -> bytes:
    """Giải mã một khối; `inv_sbox` là bảng S^-1 (với S-box Mordell, S^-1 = S)."""
    def log(r, name, s):
        if trace is not None:
            trace.append((r, name, state_to_bytes(s)))
    s = add_round_key(bytes_to_state(block), round_keys[NR]); log(NR, "AddRoundKey", s)
    for r in range(NR - 1, -1, -1):
        s = inv_shift_rows(s); log(r, "InvShiftRows", s)
        s = sub_bytes(s, inv_sbox); log(r, "InvSubBytes", s)
        s = add_round_key(s, round_keys[r]); log(r, "AddRoundKey", s)
        if r != 0:
            s = inv_mix_columns(s); log(r, "InvMixColumns", s)
    return state_to_bytes(s)
