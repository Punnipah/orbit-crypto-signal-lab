import unittest

from display_format import format_price, format_signed_price


class TestPriceFormatting(unittest.TestCase):
    def test_pepe_and_atr_are_not_rounded_to_zero(self):
        self.assertEqual(format_price(0.0000048463), "0.0000048463")
        self.assertEqual(format_price(0.00000018345), "0.00000018345")
        self.assertNotEqual(format_price(0.0000048463), "0.00000")

    def test_bitcoin_and_negative_values(self):
        self.assertEqual(format_price(72_543.781), "72,543.78")
        self.assertEqual(format_price(-0.0000048463), "-0.0000048463")

    def test_tiny_nonzero_values_use_explicit_scientific_notation(self):
        self.assertIn("e-", format_price(0.00000000000000000001))
        self.assertNotEqual(format_price(0.00000000000000000001), "0")

    def test_zero_and_invalid_values(self):
        self.assertEqual(format_price(0), "0")
        self.assertEqual(format_price(float("nan")), "ไม่พร้อม")

    def test_funding_precision(self):
        self.assertEqual(format_signed_price(0.000000019), "+0.000000019")


if __name__ == "__main__":
    unittest.main()
