"""Kiểm thử mã hóa ảnh và các chỉ số đánh giá."""
import os
import tempfile
import unittest

import numpy as np

import core.image_cipher as image_cipher
from core import (AuthenticationError, decrypt_array, encrypt_array, decrypt_file, derive_file_keys,
                  encrypt_file, load_image)
from metrics import image_metrics as im, sbox_metrics as sm
from core import build_sbox
from reference import build_aes_sbox, build_chaos_sbox, build_weierstrass_sbox

KEY = "khoa-kiem-thu"
image_cipher.KDF_ITERATIONS = 1000


class TestImageCipher(unittest.TestCase):
    def test_roundtrip_shapes(self):
        rng = np.random.default_rng(0)
        for shape in [(32, 32), (17, 13, 3), (10, 7, 4)]:
            a = rng.integers(0, 256, shape, dtype=np.uint8)
            iv = os.urandom(16)
            e = encrypt_array(a, KEY, iv)
            self.assertEqual(e.shape[1:], a.shape[1:])
            self.assertTrue(np.array_equal(decrypt_array(e, KEY, iv, a.shape[0]), a))

    def test_file_roundtrip(self):
        from PIL import Image
        a = np.random.default_rng(1).integers(0, 256, (20, 30, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as d:
            src, enc, dec = (os.path.join(d, n) for n in ("a.png", "e.png", "d.png"))
            Image.fromarray(a).save(src)
            encrypt_file(src, enc, KEY)
            self.assertTrue(os.path.exists(enc + ".meta"))
            decrypt_file(enc, dec, KEY)
            self.assertTrue(np.array_equal(load_image(dec), a))

    def test_wrong_key_gives_noise(self):
        a = np.zeros((64, 64), dtype=np.uint8)
        iv = bytes(16)
        e = encrypt_array(a, KEY, iv)
        wrong = decrypt_array(e, KEY + "x", iv, 64)
        self.assertGreater(im.entropy(wrong), 7.9)

    def test_ecb_roundtrip_array(self):
        a = np.random.default_rng(3).integers(0, 256, (17, 13), dtype=np.uint8)
        iv = bytes(16)
        e = encrypt_array(a, KEY, iv, mode="ecb")
        self.assertTrue(np.array_equal(decrypt_array(e, KEY, iv, a.shape[0], mode="ecb"), a))

    def test_ecb_file_roundtrip_and_meta(self):
        import json
        from PIL import Image
        a = np.random.default_rng(4).integers(0, 256, (20, 30, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as d:
            src, enc, dec = (os.path.join(d, n) for n in ("a.png", "e.png", "d.png"))
            Image.fromarray(a).save(src)
            meta = encrypt_file(src, enc, KEY, mode="ecb")
            self.assertEqual(meta["cipher_mode"], "ecb")
            with open(enc + ".meta", encoding="utf-8") as f:
                self.assertEqual(json.load(f)["cipher_mode"], "ecb")
            decrypt_file(enc, dec, KEY)
            self.assertTrue(np.array_equal(load_image(dec), a))

    def test_meta_does_not_expose_polynomial(self):
        import json
        from PIL import Image
        a = np.random.default_rng(2).integers(0, 256, (16, 16), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as d:
            src, enc, dec = (os.path.join(d, n) for n in ("a.png", "e.png", "d.png"))
            Image.fromarray(a).save(src)
            self.assertNotIn("poly", encrypt_file(src, enc, KEY))
            with open(enc + ".meta", encoding="utf-8") as f:
                self.assertEqual(set(json.load(f)),
                                 {"version", "iv", "mode", "cipher_mode", "orig_width", "orig_height",
                                  "salt", "iterations", "mac"})
            decrypt_file(enc, dec, KEY)
            self.assertTrue(np.array_equal(load_image(dec), a))

    def test_salt_makes_each_encryption_different(self):
        import json
        from PIL import Image
        a = np.random.default_rng(6).integers(0, 256, (16, 16), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as d:
            src, e1, e2 = (os.path.join(d, n) for n in ("a.png", "1.png", "2.png"))
            Image.fromarray(a).save(src)
            m1, m2 = encrypt_file(src, e1, KEY), encrypt_file(src, e2, KEY)
            self.assertNotEqual(m1["salt"], m2["salt"])
            self.assertFalse(np.array_equal(load_image(e1), load_image(e2)))

    def test_short_key_is_stretched_not_used_directly(self):
        self.assertEqual(len(derive_file_keys("a" * 32, bytes(16), 1000)[0]), 32)
        self.assertNotEqual(derive_file_keys("a" * 32, bytes(16), 1000)[0], b"a" * 32)
        enc_key, mac_key = derive_file_keys("mat-khau", bytes(16), 1000)
        self.assertNotEqual(enc_key, mac_key)
        self.assertNotEqual(enc_key, derive_file_keys("mat-khau", b"\x01" * 16, 1000)[0])

    def test_default_iterations_meet_recommendation(self):
        import importlib, subprocess, sys
        code = "import core.image_cipher as c; print(c.KDF_ITERATIONS)"
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertGreaterEqual(int(out.stdout), 600_000)


class TestFileAuthentication(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = folder.name
        self.src, self.enc, self.dec = (os.path.join(self.dir, n) for n in ("a.png", "e.png", "d.png"))
        self.plain = np.random.default_rng(7).integers(0, 256, (20, 30, 3), dtype=np.uint8)
        Image.fromarray(self.plain).save(self.src)
        encrypt_file(self.src, self.enc, KEY)

    def _edit_meta(self, change):
        import json
        path = self.enc + ".meta"
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
        change(meta)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f)

    def _assert_rejected(self):
        with self.assertRaises(AuthenticationError):
            decrypt_file(self.enc, self.dec, KEY)
        self.assertFalse(os.path.exists(self.dec))

    def test_valid_file_decrypts(self):
        decrypt_file(self.enc, self.dec, KEY)
        self.assertTrue(np.array_equal(load_image(self.dec), self.plain))

    def test_wrong_key_is_rejected(self):
        with self.assertRaises(AuthenticationError):
            decrypt_file(self.enc, self.dec, "khoa-sai")
        self.assertFalse(os.path.exists(self.dec))

    def test_changed_pixel_is_rejected(self):
        from PIL import Image
        arr = load_image(self.enc).copy()
        arr[3, 4, 1] ^= 1
        Image.fromarray(arr).save(self.enc)
        self._assert_rejected()

    def test_changed_iv_is_rejected(self):
        def change(meta):
            meta["iv"] = ("%02x" % (int(meta["iv"][:2], 16) ^ 1)) + meta["iv"][2:]
        self._edit_meta(change)
        self._assert_rejected()

    def test_changed_fields_are_rejected(self):
        for field, value in (("cipher_mode", "ecb"), ("orig_height", 1), ("orig_width", 1), ("mode", "L")):
            encrypt_file(self.src, self.enc, KEY)
            self._edit_meta(lambda meta: meta.__setitem__(field, value))
            self._assert_rejected()

    def test_malformed_or_downgraded_meta_is_rejected(self):
        changes = (lambda m: m.pop("mac"), lambda m: m.pop("version"), lambda m: m.__setitem__("version", 1),
                   lambda m: m.pop("salt"), lambda m: m.__setitem__("salt", "zz"),
                   lambda m: m.__setitem__("iterations", 0), lambda m: m.__setitem__("iterations", 10 ** 12),
                   lambda m: m.__setitem__("iterations", "x"))
        for change in changes:
            encrypt_file(self.src, self.enc, KEY)
            self._edit_meta(change)
            self._assert_rejected()

    def test_block_swap_is_rejected(self):
        from PIL import Image
        arr = load_image(self.enc).copy()
        raw = arr.reshape(-1)
        raw[:16], raw[16:32] = raw[16:32].copy(), raw[:16].copy()
        Image.fromarray(arr).save(self.enc)
        self._assert_rejected()


class TestMetrics(unittest.TestCase):
    def test_image_metrics_basic(self):
        rng = np.random.default_rng(2)
        noise = rng.integers(0, 256, (256, 256), dtype=np.uint8)
        self.assertGreater(im.entropy(noise), 7.99)
        self.assertLess(abs(im.correlation(noise, "horizontal")), 0.02)
        self.assertEqual(im.npcr(noise, noise), 0.0)
        self.assertEqual(im.entropy(np.zeros((8, 8), np.uint8)), 0.0)

    def test_sbox_metrics_known_values(self):
        r = sm.evaluate(build_sbox(poly=283))
        self.assertEqual((r["NL"], r["LAP"], r["DAP"]), (112, 0.0625, 0.015625))
        self.assertAlmostEqual(r["SAC_avg"], 0.5032, places=4)
        self.assertEqual(sm.evaluate(build_aes_sbox())["NL"], 112)
        self.assertEqual(sm.evaluate(build_weierstrass_sbox())["NL"], 96)
        self.assertEqual(sm.evaluate(build_chaos_sbox())["NL"], 92)

    def test_reference_sboxes_are_bijective(self):
        for s in (build_aes_sbox(), build_weierstrass_sbox(), build_chaos_sbox()):
            self.assertEqual(sorted(s), list(range(256)))
        self.assertEqual(build_aes_sbox()[:4], [0x63, 0x7C, 0x77, 0x7B])


if __name__ == "__main__":
    unittest.main()
