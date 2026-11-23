"""Kiểm thử nhánh n = 10, 12 và đối chiếu với các bảng in trong bài báo [1]."""
import unittest

from core.sbox import sbox_from_polynomial
from core.sbox_even import sbox_from_inverse
from metrics import sbox_metrics as sm
from reference.alali2024 import TABLE_11, printed_to_sbox


class TestEvenBranch(unittest.TestCase):
    def test_reproduces_paper_tables_exactly(self):
        for poly in (1315, 1789, 7105):
            self.assertEqual(sbox_from_inverse(poly), printed_to_sbox(poly))

    def test_degree_8_branch_reproduces_table_283(self):
        self.assertEqual(sbox_from_polynomial(283), printed_to_sbox(283))

    def test_rejects_wrong_input(self):
        for poly in (0x11B, 529):
            with self.assertRaises(ValueError):
                sbox_from_inverse(poly)
        with self.assertRaises(ValueError):
            sbox_from_inverse(1 << 10)


class TestPaperNonlinearityConvention(unittest.TestCase):
    def test_published_nl_is_mean_of_output_bits(self):
        """NL trong Bảng 11 của [1] là trung bình 8 hàm bit đầu ra, không phải min."""
        for poly in (529, 787, 1315, 1789, 3441, 7105):
            r = sm.evaluate(printed_to_sbox(poly))
            self.assertEqual(r["NL_coord_mean"], TABLE_11[poly][0])
            self.assertAlmostEqual(r["BIC_NL_avg"], TABLE_11[poly][2], places=3)
            self.assertLess(r["NL"], TABLE_11[poly][0])


if __name__ == "__main__":
    unittest.main()
