"""Pure mobile-view rules: UI may not promote WAIT to READY."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mobile_logic import concise_price, futures_look, normalize_symbol, spot_look


class MobileViewTests(unittest.TestCase):
    def test_any_usdt_coin_normalizes(self):
        self.assertEqual(normalize_symbol("pepe"), "PEPEUSDT")
        self.assertEqual(normalize_symbol("Bitcoin"), "BTCUSDT")
        self.assertEqual(normalize_symbol("doge/usdt"), "DOGEUSDT")
        self.assertEqual(normalize_symbol("XRPUSDT"), "XRPUSDT")

    def test_rejects_unsafe_symbol(self):
        for input_text in ("", "../btc", "BTC;DROP", "USDT", "<script>"):
            with self.subTest(input_text=input_text), self.assertRaises(ValueError):
                normalize_symbol(input_text)

    def test_wait_and_cancel_not_green(self):
        for status in ("MTF_WAIT", "WAIT_ZONE", "INVALIDATED", "EXPIRED", "DATA_GAP"):
            self.assertNotEqual(spot_look(status).tone, "good")

    def test_futures_watch_and_risk_are_not_ready(self):
        for status in ("WATCH_LONG", "WATCH_SHORT", "RISK_BLOCK", "INVALIDATED", "NO_SETUP"):
            self.assertNotEqual(futures_look(status, "LONG").tone, "good")
        self.assertEqual(futures_look("READY_SHORT", "SHORT").tone, "good")
        self.assertEqual(futures_look("READY_LONG", "LONG").tone, "good")

    def test_tiny_price_no_scientific_notation(self):
        self.assertEqual(concise_price(0.00000459), "0.00000459")
        self.assertEqual(concise_price(None), "—")


if __name__ == "__main__":
    unittest.main()
