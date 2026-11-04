"""Isolated Telegram contract; no network, secrets, or actual messages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orbit_live_telegram import (display_price, signal_key, signal_text,
                                 scan_and_send, collect_recent_signals)


def fake_signal(now: datetime):
    return SimpleNamespace(
        status="SIGNAL LONG", direction="LONG", regime="UPTREND",
        strength="3/3 TF ยืนทิศเดียวกัน", reference_close=.00000480,
        closed_at=now - timedelta(minutes=5), entry_reference=.00000480,
        entry_zones=(("ZONE 1", .00000470, .00000485, "รอยืนยัน"),
                     ("ZONE 2", .00000455, .00000462, "รอเด้ง"),
                     ("ZONE 3", .00000490, .00000495, "รอปิดเหนือ")),
        stop=.00000450, take_profit_1=.00000525, take_profit_2=.00000555,
        max_notional_usdt=70.0,
    )


class TelegramNotifierTests(unittest.TestCase):
    def test_consecutive_signal_bars_send_only_first_transition(self):
        now = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
        plan = fake_signal(now)
        scans = [SimpleNamespace(**{**vars(plan), "status": "WATCH LONG"}),
                 plan, plan, plan, plan]
        with patch("orbit_live_telegram.fetch_candles", return_value=pd.DataFrame({"close": range(100)})), \
             patch("orbit_live_telegram.build_live_plan", side_effect=scans):
            result = collect_recent_signals("BINANCE_GLOBAL_USDM", "PEPEUSDT", now=now)
        self.assertEqual(len(result), 1)

    def test_message_has_time_prices_and_explicit_caveat(self):
        now = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
        text = signal_text("BINANCE_GLOBAL_USDM", "PEPEUSDT", fake_signal(now))
        self.assertIn("PEPEUSDT", text)
        self.assertIn("SIGNAL LONG", text)
        self.assertIn("0.0000048", text)
        self.assertIn("Stop Loss", text)
        self.assertIn("Take Profit", text)
        self.assertIn("ไม่รับประกันกำไร", text)
        self.assertLess(len(text), 4000)
        self.assertEqual(display_price(.00000480), "0.0000048")

    def test_closed_candle_key_prevents_repeat_sends(self):
        now = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
        signal = fake_signal(now)
        self.assertNotEqual(
            signal_key("BINANCE_TH_SPOT", "PEPEUSDT", signal),
            signal_key("BINANCE_GLOBAL_USDM", "PEPEUSDT", signal),
        )
        state = {"version": 1, "sent": {}}
        messages = []

        class FakeStore:
            def __init__(self, *args):
                pass
            def load(self):
                return state
            def save(self, next_state):
                self.assert_state(next_state)
            def assert_state(self, next_state):
                assert next_state["sent"]

        environment = {"TELEGRAM_BOT_TOKEN": "not-a-real-token",
                       "TELEGRAM_CHAT_ID": "12345", "GITHUB_TOKEN": "fake",
                       "GITHUB_SHA": "a" * 40,
                       "GITHUB_REPOSITORY": "owner/repo"}
        with patch.dict(os.environ, environment), \
             patch("orbit_live_telegram.GitHubAlertState", FakeStore), \
             patch("orbit_live_telegram.collect_recent_signals", return_value=[signal]), \
             patch("orbit_live_telegram.send_telegram", side_effect=lambda *p: messages.append(p)):
            first = scan_and_send(now=now, venues=("BINANCE_GLOBAL_USDM",),
                                  symbols=("PEPEUSDT",))
            second = scan_and_send(now=now, venues=("BINANCE_GLOBAL_USDM",),
                                   symbols=("PEPEUSDT",))
        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(second["already_sent"], 1)
        self.assertEqual(len(messages), 1)


if __name__ == "__main__":
    unittest.main()
