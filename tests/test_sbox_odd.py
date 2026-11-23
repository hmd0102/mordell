"""Kiểm thử nhánh S-box cho n lẻ (n = 9, 11): core/sbox_odd.py."""
import unittest

from core import key_to_polynomial
from core.gf2n import GF2n, irreducible_polynomials
from core.sbox_odd import (build_sbox_odd, count_b_variants, key_to_polynomial_n,
                           sbox_from_y)
from metrics import sbox_metrics as sm

DEMO_KEY = "day-la-mot-khoa-bi-mat-vi-du"

POLY_N9 = (529, 787)
POLY_N11 = (3441,)


class TestIrreducibleLists(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(len(irreducible_polynomials(9)), 56)
        self.assertEqual(len(irreducible_polynomials(11)), 186)


class TestKeyDerivation(unittest.TestCase):
    def test_matches_degree8_behaviour(self):
        """key_to_polynomial_n(., 8) phải trùng key_to_polynomial trên mọi khóa."""
        keys = [DEMO_KEY, b"", b"a", b"khoa-ngan", bytes(range(32)),
                bytes([0xFF]) * 32, b"verify"]
        for key in keys:
            self.assertEqual(key_to_polynomial_n(key, 8), key_to_polynomial(key))

    def test_returns_irreducible_of_right_degree(self):
        for n in (9, 11):
            poly = key_to_polynomial_n(DEMO_KEY, n)
            self.assertEqual(poly.bit_length() - 1, n)
            self.assertIn(poly, irreducible_polynomials(n))


class TestSboxFromY(unittest.TestCase):
    def test_permutation(self):
        for poly in POLY_N9 + POLY_N11:
            s = sbox_from_y(poly)
            self.assertEqual(len(s), 256)
            self.assertEqual(len(set(s)), 256)
            self.assertTrue(all(0 <= v <= 255 for v in s))

    def test_known_prefix_n9_529(self):
        self.assertEqual(sbox_from_y(529, 1)[:8], [1, 0, 75, 237, 9, 14, 194, 98])

    def test_metrics_n9_529(self):
        r = sm.evaluate(sbox_from_y(529, 1), "n9-529")
        self.assertEqual(r["NL"], 92)
        self.assertAlmostEqual(r["LAP"], 0.1406, places=4)
        self.assertAlmostEqual(r["DAP"], 0.0391, places=4)

    def test_metrics_n11_3441(self):
        r = sm.evaluate(sbox_from_y(3441, 1), "n11-3441")
        self.assertEqual(r["NL"], 94)
        self.assertAlmostEqual(r["LAP"], 0.1328, places=4)
        self.assertAlmostEqual(r["DAP"], 0.0469, places=4)

    def test_b_changes_table(self):
        self.assertNotEqual(sbox_from_y(529, 1), sbox_from_y(529, 7))

    def test_b_only_xors_a_constant(self):
        f = GF2n(529)
        base = sbox_from_y(529, 1)
        for b in (2, 7, 300, 511):
            c = (f.sqrt(b) ^ f.sqrt(1)) & 0xFF
            self.assertEqual(sbox_from_y(529, b), [v ^ c for v in base])

    def test_b_variants_are_distinct(self):
        f = GF2n(529)
        b_values = [f.mul(i, i) for i in range(1, 33)]
        self.assertEqual(count_b_variants(529, b_values), 32)

    def test_even_n_rejected(self):
        with self.assertRaises(ValueError):
            sbox_from_y(0x11B)

    def test_b_zero_rejected(self):
        with self.assertRaises(ValueError):
            sbox_from_y(529, 0)

    def test_non_irreducible_rejected(self):
        with self.assertRaises(ValueError):
            sbox_from_y(0x201)

    def test_build_from_key(self):
        s = build_sbox_odd(key=DEMO_KEY, n=9)
        self.assertEqual(len(set(s)), 256)
        self.assertEqual(s, sbox_from_y(key_to_polynomial_n(DEMO_KEY, 9)))
        with self.assertRaises(ValueError):
            build_sbox_odd()
        with self.assertRaises(ValueError):
            build_sbox_odd(key=DEMO_KEY, poly=529)


if __name__ == "__main__":
    unittest.main()
