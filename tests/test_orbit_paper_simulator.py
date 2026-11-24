"""Deterministic, no-network checks for Orbit Paper Simulator (closed 5m)."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orbit_model_lab_engine import INTERVAL_MS, DataUnavailable
from orbit_paper_simulator import (
    PaperError,new_account,request_paper_position,advance_account,cancel_pending,
    account_metrics,dump_account,load_account,estimate_open_net,
)
BASE=1_800_000_000_000//INTERVAL_MS*INTERVAL_MS

def dt(ms):return datetime.fromtimestamp(ms/1000,timezone.utc)
def candles(n=520):
    return pd.DataFrame({
        "open_ms":BASE+np.arange(n,dtype=np.int64)*INTERVAL_MS,
        "open":np.ones(n),"high":np.full(n,1.001),
        "low":np.full(n,.999),"close":np.ones(n),
        "volume":np.full(n,1000.)
    })
def queue(side="LONG",venue="BITGET_USDT_FUTURES",**kw):
    time=BASE+520*INTERVAL_MS+1000
    return request_paper_position(new_account(100),venue=venue,symbol="PEPEUSDT",
                                  direction=side,requested_at=dt(time),reference_close=1,
                                  **kw)
def tick(a,bars):
    return advance_account(a,bars,now=dt(int(bars.open_ms.iloc[-1])+INTERVAL_MS+1000))

class PaperTests(unittest.TestCase):
    def test_pending_and_no_instant_fill(self):
        a=queue()
        self.assertEqual(a["active"]["status"],"PENDING")
        self.assertEqual(tick(a,candles())["active"]["status"],"PENDING")
        self.assertEqual(tick(a,candles(521))["active"]["status"],"PENDING")
        b=tick(a,candles(522))
        self.assertEqual(b["active"]["status"],"OPEN")
        self.assertEqual(b["active"]["entry_open_ms"],BASE+521*INTERVAL_MS)
        self.assertEqual(tick(b,candles(522))["active"]["bars_held"],1)

    def test_same_bar_stop_and_target_stop_wins(self):
        f=candles(522)
        f.loc[521,"high"]=1.05
        f.loc[521,"low"]=.98
        a=tick(queue(),f)
        self.assertIsNone(a["active"])
        self.assertEqual(a["trades"][0]["reason"],"STOP")
        self.assertLess(a["trades"][0]["net_usdt"],0)

    def test_long_target_after_fee(self):
        f=candles(522)
        f.loc[521,"high"]=1.03
        a=tick(queue(fee_bps=10,slippage_bps=5),f)
        self.assertEqual(a["trades"][0]["reason"],"TARGET")
        self.assertGreater(a["trades"][0]["net_usdt"],0)

    def test_short_futures_target(self):
        f=candles(522)
        f.loc[521,"low"]=.96
        a=tick(queue(side="SHORT"),f)
        self.assertEqual(a["trades"][0]["direction"],"SHORT")
        self.assertEqual(a["trades"][0]["reason"],"TARGET")

    def test_short_spot_forbidden(self):
        with self.assertRaises(PaperError):
            queue(side="SHORT",venue="BINANCE_TH_SPOT")

    def test_cancel_only_pending(self):
        b=cancel_pending(queue())
        self.assertIsNone(b["active"])
        with self.assertRaises(PaperError):cancel_pending(b)

    def test_bad_gap_is_blocked(self):
        f=candles(522).drop(index=520)
        with self.assertRaises(DataUnavailable): tick(queue(),f)

    def test_account_export_import(self):
        a=queue()
        self.assertEqual(load_account(dump_account(a).encode())["active"]["status"],"PENDING")
        with self.assertRaises(PaperError):load_account(b'{"version":99}')

    def test_open_mark_not_recorded_as_profit(self):
        a=tick(queue(),candles(522))
        self.assertLess(estimate_open_net(a["active"],1),0)
        self.assertEqual(account_metrics(a)["trades"],0)

    def test_expiry_closes(self):
        a=tick(queue(max_hold_bars=3),candles(524))
        self.assertEqual(a["trades"][0]["reason"],"TIME")

    def test_risk_limit(self):
        with self.assertRaises(PaperError):queue(risk_pct=5)
        with self.assertRaises(PaperError):new_account(-5)

    def test_provenance_from_orbit(self):
        f=candles(522)
        f.loc[521,"low"]=.97
        a=tick(queue(source="ORBIT_PAPER_SIGNAL"),f)
        self.assertEqual(a["trades"][0]["source"],"ORBIT_PAPER_SIGNAL")

if __name__=="__main__":unittest.main()
