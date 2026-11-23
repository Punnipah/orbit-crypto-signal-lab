from __future__ import annotations

import sys
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Local tests import existing engine from a separately prepared test stub only
from orbit_market_dna import analyze_candles, summarize_tape, summarize_depth
from orbit_model_lab_engine import DataUnavailable


def candles(n=700):
    start = 1780000000000 // 300000 * 300000
    t = np.arange(n)
    close = 100 + np.sin(t/15.0)*1.3 + t*.001
    op = np.r_[close[0], close[:-1]]
    return pd.DataFrame(dict(open_ms=start+300000*t, open=op,
       high=np.maximum(op,close)+.22, low=np.minimum(op,close)-.22,
       close=close,volume=np.full(n,1000.0)))


class DnaTests(unittest.TestCase):
    def test_candles(self):
        dna=analyze_candles(candles())
        self.assertGreater(dna.resistance,dna.support)
        self.assertTrue(dna.observations)
    def test_no_future_used_in_levels(self):
        f=candles()
        base=analyze_candles(f)
        f.loc[f.index[-1],"high"]=max(base.resistance*2,f.high.iloc[-1])
        new=analyze_candles(f)
        self.assertEqual(base.resistance,new.resistance)
    def test_no_stale_tape(self):
        now=1780000000000
        trades=[{"p":"2","q":"1","T":now-200000,"m":True} for _ in range(30)]
        from datetime import datetime, timezone
        with self.assertRaises(DataUnavailable):
            summarize_tape("BINANCE_TH_SPOT",trades,now=datetime.fromtimestamp(now/1000,tz=timezone.utc))
    def test_tape_side(self):
        from datetime import datetime, timezone
        now=1780000000000
        trades=([{"p":"2","q":"2","T":now-5000,"m":False}]*20+
                 [{"p":"2","q":"1","T":now-2000,"m":True}]*20)
        outcome=summarize_tape("BINANCE_TH_SPOT",trades,now=datetime.fromtimestamp(now/1000,tz=timezone.utc))
        self.assertAlmostEqual(outcome["buy_share_pct"],66.66666667,places=5)
    def test_book(self):
        b={"bids":[[99.0-i*.1,2] for i in range(25)],"asks":[[101.0+i*.1,1] for i in range(25)]}
        v=summarize_depth("BINANCE_TH_SPOT", b)
        self.assertTrue(50 < v["bid_depth_share_pct"] < 80)
        self.assertGreater(v["spread_bps"],0)
    def test_book_cross(self):
        b={"bids":[[102,2]]*10,"asks":[[101,2]]*10}
        with self.assertRaises(DataUnavailable):
            summarize_depth("BINANCE_TH_SPOT", b)

if __name__=="__main__": unittest.main()
