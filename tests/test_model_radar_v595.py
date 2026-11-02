"""Research-only model comparison must never modify trading permissions."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_radar import evaluate_reference_models
from test_spot_range_v594 import CFG, NOW, snapshot


class RadarTests(unittest.TestCase):
    def test_every_status_is_non_executable(self):
        for venue in ("BINANCE_TH_SPOT", "BITGET_USDT_FUTURES", "BINANCE_GLOBAL_USDM"):
            snap = replace(snapshot(), venue=venue)
            models = evaluate_reference_models(snap, CFG)
            self.assertEqual({x.model for x in models}, {"BB20 Mean Reversion", "EMA9/21 Pullback"})
            self.assertTrue(all(x.state not in {"READY", "READY_LONG", "READY_SHORT"} for x in models))

    def test_stale_quote_fails_closed(self):
        models = evaluate_reference_models(snapshot(), CFG, now=NOW+timedelta(seconds=90))
        self.assertTrue(all(x.state == "DATA_BLOCK" for x in models))

    def test_missing_15m_fails_closed(self):
        snap = snapshot()
        snap = replace(snap, frames={"5m": snap.frames["5m"]})
        self.assertTrue(all(x.state == "DATA_BLOCK" for x in evaluate_reference_models(snap, CFG)))

    def test_spot_never_short(self):
        models = evaluate_reference_models(snapshot(), CFG)
        self.assertTrue(all(m.side != "SHORT" for m in models))

    def test_no_settings_mutation(self):
        before = repr(CFG)
        evaluate_reference_models(snapshot(), CFG)
        self.assertEqual(before, repr(CFG))


if __name__ == "__main__":
    unittest.main()
