"""Orbit paper-trading simulator using closed 5m bars only.

No orders, credentials, automatic trades, leverage or external writes.  All fills
are reconstructed from the next unopened candle AFTER the user's click and only
once that candle has closed.  STOP wins when STOP and TP touch in the same bar.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime
import json, math
import pandas as pd
from orbit_model_lab_engine import INTERVAL_MS, SYMBOLS, VENUES, validate_candles

VERSION=1
MAX_TRADES=500

class PaperError(ValueError): pass

def finite(v, lo, hi):
    try: x=float(v)
    except (ValueError,TypeError,OverflowError): raise PaperError("ตัวเลขไม่ถูกต้อง") from None
    if not math.isfinite(x) or not lo<=x<=hi: raise PaperError("ตัวเลขอยู่นอกช่วงที่รองรับ")
    return x

def timestamp(dt):
    if not isinstance(dt, datetime) or dt.tzinfo is None: raise PaperError("ต้องมี timezone")
    return int(dt.timestamp()*1000)

def new_account(capital_usdt=75):
    v=finite(capital_usdt,10,100000)
    return {"version":VERSION,"starting_usdt":v,"active":None,"trades":[],"cancelled":0}

def balance(a):
    return float(a["starting_usdt"])+sum(float(t["net_usdt"]) for t in a["trades"])

def request_paper_position(a, *, venue, symbol, direction, requested_at, reference_close,
                           risk_pct=.25, stop_pct=1., reward_r=2., fee_bps=10.,
                           slippage_bps=5., max_hold_bars=24,
                           source="MANUAL_PAPER_HYPOTHESIS"):
    if a.get("active"): raise PaperError("มีสถานะจำลองค้างอยู่")
    if len(a["trades"])>=MAX_TRADES: raise PaperError("ประวัติครบ 500 รายการแล้ว")
    if venue not in VENUES or symbol not in SYMBOLS: raise PaperError("ตลาด/เหรียญไม่รองรับ")
    if direction not in ("LONG","SHORT") or (venue=="BINANCE_TH_SPOT" and direction=="SHORT"):
        raise PaperError("Spot ไม่รองรับ Short หรือทิศทางไม่ถูกต้อง")
    if source not in ("MANUAL_PAPER_HYPOTHESIS","ORBIT_PAPER_SIGNAL"):
        raise PaperError("ประเภทสัญญาณไม่รองรับ")
    ref=finite(reference_close,1e-12,1e8)
    risk=finite(risk_pct,.1,1.)
    stop=finite(stop_pct,.2,5.)
    reward=finite(reward_r,1.,3.)
    fee=finite(fee_bps,0,100)
    slip=finite(slippage_bps,0,100)
    if not isinstance(max_hold_bars,int) or not 3<=max_hold_bars<=96:
        raise PaperError("ระยะเวลาไม่ถูกต้อง")
    if balance(a)<10: raise PaperError("ทุนจำลองไม่พอ")
    created=timestamp(requested_at)
    earliest=(created//INTERVAL_MS+1)*INTERVAL_MS
    out=deepcopy(a)
    out["active"]={"status":"PENDING","venue":venue,"symbol":symbol,
                   "direction":direction,"requested_ms":created,
                   "earliest_open_ms":earliest,"last_processed_ms":earliest-INTERVAL_MS,
                   "reference_close":ref,"risk_pct":risk,"stop_pct":stop,
                   "reward_r":reward,"fee_bps":fee,"slippage_bps":slip,
                   "max_hold_bars":max_hold_bars,"source":source}
    return out

def cancel_pending(a):
    if not a.get("active") or a["active"]["status"]!="PENDING":
        raise PaperError("ยกเลิกได้เฉพาะรายการที่ยังรอเปิด")
    out=deepcopy(a)
    out["active"]=None
    out["cancelled"]=int(out.get("cancelled",0))+1
    return out

def _fill(p, row, wallet):
    sign=1 if p["direction"]=="LONG" else -1
    entry=float(row.open)*(1+sign*p["slippage_bps"]/10000)
    risk_fraction=p["stop_pct"]/100
    cost_reserve=2*(p["fee_bps"]+p["slippage_bps"])/10000
    notional=min(wallet,wallet*p["risk_pct"]/100/(risk_fraction+cost_reserve))
    if notional<=0: raise PaperError("ทุนจำลองไม่เพียงพอ")
    return {**p,"status":"OPEN","entry_open_ms":int(row.open_ms),
            "last_processed_ms":int(row.open_ms)-INTERVAL_MS,
            "entry_exec":entry,"qty":notional/entry,"notional_usdt":notional,
            "stop":entry*(1-sign*risk_fraction),
            "target":entry*(1+sign*risk_fraction*p["reward_r"]),"bars_held":0}

def _exit_check(p,row):
    sign=1 if p["direction"]=="LONG" else -1
    o,h,l,c=(float(row[k]) for k in ("open","high","low","close"))
    stop,target=p["stop"],p["target"]
    if sign==1:
        if o<=stop: return "STOP_GAP",o
        if l<=stop: return "STOP",stop
        if o>=target or h>=target: return "TARGET",target
    else:
        if o>=stop: return "STOP_GAP",o
        if h>=stop: return "STOP",stop
        if o<=target or l<=target: return "TARGET",target
    if p["bars_held"]>=p["max_hold_bars"]: return "TIME",c
    return None,None

def _settle(p,reason,raw_exit,bar_ms,wallet):
    sign=1 if p["direction"]=="LONG" else -1
    exe=raw_exit*(1-sign*p["slippage_bps"]/10000)
    q=p["qty"]
    gross=sign*(exe-p["entry_exec"])*q
    fees=(exe+p["entry_exec"])*q*p["fee_bps"]/10000
    net=gross-fees
    return {"source":p["source"],"venue":p["venue"],"symbol":p["symbol"],
            "direction":p["direction"],"requested_ms":p["requested_ms"],
            "entry_open_ms":p["entry_open_ms"],"exit_open_ms":bar_ms,
            "entry":p["entry_exec"],"exit":exe,"stop":p["stop"],"target":p["target"],
            "notional_usdt":p["notional_usdt"],"qty":q,"gross_usdt":gross,
            "fees_usdt":fees,"net_usdt":net,"reason":reason,
            "net_pct_of_notional":net/p["notional_usdt"]*100,
            "bars_held":p["bars_held"],"balance_after_usdt":wallet+net}

def advance_account(account, candles, *, now):
    if not account.get("active"): return deepcopy(account)
    frame=validate_candles(candles,now=now,require_fresh=True)
    a=deepcopy(account)
    p=a["active"]
    if p["venue"] not in VENUES or p["symbol"] not in SYMBOLS:
        raise PaperError("ตลาดไม่ถูกต้อง")
    first=p["earliest_open_ms"] if p["status"]=="PENDING" else p["last_processed_ms"]+INTERVAL_MS
    frame=frame.loc[frame.open_ms>=first]
    if frame.empty: return a
    if int(frame.open_ms.iloc[0])!=first:
        raise PaperError("ข้อมูลแท่งย้อนหลังขาดช่วง จึงหยุดการจำลอง")
    for _,row in frame.iterrows():
        if p["status"]=="PENDING": p=_fill(p,row,balance(a))
        if p["status"]=="OPEN":
            p["bars_held"]+=1
            reason,ex=_exit_check(p,row)
            p["last_processed_ms"]=int(row.open_ms)
            if reason is not None:
                trade=_settle(p,reason,float(ex),int(row.open_ms),balance(a))
                a["trades"].append(trade)
                a["active"]=None
                break
    else: a["active"]=p
    return a

def estimate_open_net(p, reference_close):
    if p.get("status")!="OPEN": raise PaperError("สถานะยังไม่เปิด")
    close=finite(reference_close,1e-12,1e8)
    sign=1 if p["direction"]=="LONG" else -1
    ex=close*(1-sign*p["slippage_bps"]/10000)
    fee=(ex+p["entry_exec"])*p["qty"]*p["fee_bps"]/10000
    return sign*(ex-p["entry_exec"])*p["qty"]-fee

def account_metrics(a):
    trades=a["trades"]
    w=balance(a)
    peak=float(a["starting_usdt"])
    dd=0.
    for t in trades:
        bal=float(t["balance_after_usdt"])
        peak=max(peak,bal)
        dd=max(dd,(peak-bal)/peak*100 if peak>0 else 0)
    return {"trades":len(trades),"win_rate":100*sum(t["net_usdt"]>0 for t in trades)/len(trades) if trades else None,
            "balance_usdt":w,"realized_usdt":w-a["starting_usdt"],"max_drawdown_pct":dd}

def dump_account(a):
    return json.dumps(a,ensure_ascii=False,indent=2,allow_nan=False)

def load_account(blob):
    if not isinstance(blob,bytes) or len(blob)>750000: raise PaperError("ไฟล์ใหญ่เกิน")
    try: a=json.loads(blob.decode("utf-8"))
    except (UnicodeError,ValueError,TypeError): raise PaperError("รูปแบบไฟล์ไม่ถูกต้อง") from None
    if not isinstance(a,dict) or a.get("version")!=VERSION: raise PaperError("JSON คนละรุ่น")
    finite(a.get("starting_usdt"),10,100000)
    trades=a.get("trades")
    if not isinstance(trades,list) or len(trades)>MAX_TRADES: raise PaperError("ประวัติไม่ถูกต้อง")
    for t in trades:
        if not isinstance(t,dict) or t.get("source") not in ("MANUAL_PAPER_HYPOTHESIS","ORBIT_PAPER_SIGNAL"):
            raise PaperError("รายการนำเข้าไม่ถูกต้อง")
        if t.get("venue") not in VENUES or t.get("symbol") not in SYMBOLS: raise PaperError("ตลาดไม่ถูกต้อง")
        finite(t.get("net_usdt"),-100000,100000)
        finite(t.get("balance_after_usdt"),-100000,100000)
    p=a.get("active")
    if p is not None:
        if not isinstance(p,dict) or p.get("status") not in ("PENDING","OPEN"):
            raise PaperError("สถานะนำเข้าไม่ถูกต้อง")
        if p.get("venue") not in VENUES or p.get("symbol") not in SYMBOLS or p.get("direction") not in ("LONG","SHORT"):
            raise PaperError("ตลาดไม่ถูกต้อง")
        if p["venue"]=="BINANCE_TH_SPOT" and p["direction"]=="SHORT": raise PaperError("Spot Short ไม่รองรับ")
        if p.get("source") not in ("MANUAL_PAPER_HYPOTHESIS","ORBIT_PAPER_SIGNAL"):
            raise PaperError("แหล่งที่มาไม่ถูกต้อง")
        for k in ("requested_ms","earliest_open_ms","last_processed_ms"):
            finite(p.get(k),1,1e18)
        for k,lo,hi in (("risk_pct",.1,1),("stop_pct",.2,5),("reward_r",1,3),
                         ("fee_bps",0,100),("slippage_bps",0,100)):
            finite(p.get(k),lo,hi)
        if p["status"]=="OPEN":
            for k in ("entry_exec","stop","target","qty","notional_usdt"):
                finite(p.get(k),1e-14,1e10)
            finite(p.get("bars_held"),1,96)
    return a
