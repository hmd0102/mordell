"""Kiểm thử AES-256 (vector chuẩn FIPS-197) và các chế độ CBC/ECB."""
import os
import unittest

import core.aes as A
from core import AES256, build_sbox, inverse_sbox
from core.aes_fast import pkcs7_pad, pkcs7_unpad
from reference import build_aes_sbox

KEY = bytes(range(32))
PT = bytes.fromhex("00112233445566778899aabbccddeeff")
CT = bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")   # bản mã chuẩn


class TestAES(unittest.TestCase):
    def test_fips197_reference(self):
        s = build_aes_sbox()
        rk = A.key_expansion(KEY, s)
        self.assertEqual(A.encrypt_block(PT, rk, s), CT)
        self.assertEqual(A.decrypt_block(CT, rk, inverse_sbox(s)), PT)

    def test_fips197_fast(self):
        c = AES256(KEY, build_aes_sbox())
        self.assertEqual(c.encrypt_block(PT), CT)
        self.assertEqual(c.decrypt_block(CT), PT)

    def test_fast_equals_reference_with_dynamic_sbox(self):
        s = build_sbox(key="k")
        key, iv, data = os.urandom(32), os.urandom(16), os.urandom(16 * 64)
        rk = A.key_expansion(key, s)
        prev, ref = iv, b""
        for i in range(0, len(data), 16):
            prev = A.encrypt_block(bytes(a ^ b for a, b in zip(data[i:i + 16], prev)), rk, s)
            ref += prev
        c = AES256(key, s)
        self.assertEqual(c.cbc_encrypt(data, iv), ref)
        self.assertEqual(c.cbc_decrypt(ref, iv), data)
        self.assertEqual(c.ecb_decrypt(c.ecb_encrypt(data)), data)

    def test_cbc_hides_repeated_blocks(self):
        c = AES256(os.urandom(32), build_sbox(key="k"))
        data = bytes(64)
        ecb, cbc = c.ecb_encrypt(data), c.cbc_encrypt(data, os.urandom(16))
        self.assertEqual(ecb[:16], ecb[16:32])
        self.assertNotEqual(cbc[:16], cbc[16:32])

    def test_pkcs7(self):
        for n in (0, 1, 15, 16, 17):
            d = os.urandom(n)
            self.assertEqual(pkcs7_unpad(pkcs7_pad(d)), d)


if __name__ == "__main__":
    unittest.main()
