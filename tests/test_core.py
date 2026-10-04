"""Kiểm thử phần lõi: trường GF(2^8), đường cong, dẫn xuất khóa, S-box."""
import unittest

from core import GF2n, DEGREE_8_IRREDUCIBLES, build_sbox, key_to_polynomial, mordell_points, properties
from core.curve import is_on_curve
from core.gf2n import irreducible_polynomials, is_irreducible

DEMO_KEY = "day-la-mot-khoa-bi-mat-vi-du"


class TestGF(unittest.TestCase):
    def test_irreducible_counts(self):
        # Số đa thức bất khả quy bậc n trên GF(2)
        self.assertEqual([len(irreducible_polynomials(n)) for n in (2, 3, 4, 6, 8)], [1, 2, 3, 9, 30])

    def test_aes_polynomial(self):
        self.assertTrue(is_irreducible(0x11B))
        self.assertFalse(is_irreducible(0x155))   # (x^4+x^3+x^2+x+1)^2

    def test_inverse_and_sqrt(self):
        for poly in DEGREE_8_IRREDUCIBLES[:5]:
            f = GF2n(poly)
            for a in range(1, 256):
                self.assertEqual(f.mul(a, f.inv(a)), 1)
                s = f.sqrt(a)
                self.assertEqual(f.mul(s, s), a)

    def test_known_aes_inverse(self):
        self.assertEqual(GF2n(0x11B).inv(0x53), 0xCA)


class TestCurveAndSbox(unittest.TestCase):
    def test_points_cover_field(self):
        f = GF2n(0x171)
        pts = mordell_points(f, 1)
        self.assertEqual([x for x, _ in pts], list(range(256)))
        self.assertTrue(all(is_on_curve(f, p, 1) for p in pts))

    def test_demo_key_polynomial(self):
        poly, tried = key_to_polynomial(DEMO_KEY, return_trace=True)
        self.assertEqual(poly, 0x171)
        self.assertEqual(tried, [0x55, 0x09, 0x71])

    def test_sbox_properties_all_30(self):
        for p in DEGREE_8_IRREDUCIBLES:
            pr = properties(build_sbox(poly=p))
            self.assertTrue(pr["bijective"])
            self.assertTrue(pr["involution"])
            self.assertEqual(pr["fixed_points"], [0, 1])

    def test_sbox_independent_of_b(self):
        self.assertEqual(build_sbox(poly=0x171, b=1), build_sbox(poly=0x171, b=77))

    def test_sbox_283_known_values(self):
        # Cột đầu của S-box ứng với đa thức 283: 0, 1, 141, 246, 203, ...
        self.assertEqual(build_sbox(poly=283)[:6], [0, 1, 141, 246, 203, 82])

    def test_demo_sbox_prefix(self):
        self.assertEqual(build_sbox(key=DEMO_KEY)[:8], [0, 1, 184, 208, 92, 159, 104, 134])


if __name__ == "__main__":
    unittest.main()
