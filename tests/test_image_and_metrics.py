"""Kiểm thử mã hóa ảnh và các chỉ số đánh giá."""
import os
import tempfile
import unittest

import numpy as np

from core import decrypt_array, encrypt_array, decrypt_file, encrypt_file, load_image
from metrics import image_metrics as im, sbox_metrics as sm
from core import build_sbox
from reference import build_aes_sbox, build_chaos_sbox, build_weierstrass_sbox

KEY = "khoa-kiem-thu"


class TestImageCipher(unittest.TestCase):
    def test_roundtrip_shapes(self):
        rng = np.random.default_rng(0)
        for shape in [(32, 32), (17, 13, 3), (10, 7, 4)]:        # có trường hợp cần đệm hàng
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
            decrypt_file(enc, dec, KEY)          # tự đọc chế độ từ .meta
            self.assertTrue(np.array_equal(load_image(dec), a))

    def test_legacy_meta_without_cipher_mode_uses_cbc(self):
        import json
        from PIL import Image
        a = np.random.default_rng(5).integers(0, 256, (20, 30), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as d:
            src, enc, dec = (os.path.join(d, n) for n in ("a.png", "e.png", "d.png"))
            Image.fromarray(a).save(src)
            encrypt_file(src, enc, KEY)          # CBC mặc định
            path = enc + ".meta"
            with open(path, encoding="utf-8") as f:
                meta = json.load(f)
            meta.pop("cipher_mode")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(meta, f)
            decrypt_file(enc, dec, KEY)
            self.assertTrue(np.array_equal(load_image(dec), a))

    def test_invalid_mode_rejected(self):
        a = np.zeros((16, 16), dtype=np.uint8)
        with self.assertRaises(ValueError):
            encrypt_array(a, KEY, bytes(16), mode="ofb")


class TestMetrics(unittest.TestCase):
    def test_image_metrics_basic(self):
        rng = np.random.default_rng(2)
        noise = rng.integers(0, 256, (256, 256), dtype=np.uint8)
        self.assertGreater(im.entropy(noise), 7.99)
        self.assertLess(abs(im.correlation(noise, "horizontal")), 0.02)
        self.assertEqual(im.npcr(noise, noise), 0.0)
        self.assertEqual(im.entropy(np.zeros((8, 8), np.uint8)), 0.0)

    def test_sbox_metrics_known_values(self):
        # Giá trị đã biết của các chỉ số S-box
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
