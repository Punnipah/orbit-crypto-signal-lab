# Orbit Scalp Signal v5.6 — คู่มือติดตั้ง (31 ต.ค. 2026)

อัปเกรดแยกจาก Spot Day Trade / Futures Day Trade / Frozen Watch เดิมทั้งหมด
ไม่มีการสั่งซื้อขาย ไม่มีการขอ Binance API Key และไม่มีการเปิด Futures อัตโนมัติ

## สิ่งที่ทำได้

- `⏱️ Scalp` ในหน้าจอมือถือ Streamlit ดูสถานะสด Spot Binance TH และ Futures Binance Global
- สแกน 4 คู่ `BTCUSDT`, `ETHUSDT`, `PEPEUSDT`, `DOGEUSDT` แยกตามตลาด (ปรับรายการที่ `scalp_config.json` ได้)
- ใช้ **แท่งปิดแล้วจริง**: 15m แนวโน้ม, 5m breakout, 1m volume + taker-buy confirmation
- Binance TH: ดึง Public Open REST API (`exchangeInfo`, `time`, `klines`, `ticker/bookTicker`, `depth`) โดยไม่มี API Key
- Futures: Binance Global USDⓈ-M Public REST API ซึ่งต้องเข้าถึงได้จริงจากเครื่องที่รัน ถ้า `HTTP 451` ขึ้น `DATA_UNAVAILABLE` **ไม่เอา Binance TH Spot / Kraken / Bybit มาปลอมเป็น Futures READY**
- ตรวจ symbol TRADING, minQty, stepSize, minNotional, Tick Size, Spread, Depth, อายุข้อมูล
- ค่าธรรมเนียม/Slippage/Spread หักในการคำนวณ Net R:R และ Position Size ก่อนขึ้น READY
- Spot BUY เท่านั้น; ขาลง Spot แสดง `SELL WATCH / EXIT_WATCH` เพื่อพิจารณาจัดการเหรียญที่ถือ **ไม่ใช่ SHORT**
- Futures LONG/SHORT เฉพาะเมื่อ **Binance Global** ส่งข้อมูลจริงได้
- `WATCH` = เตรียมเฝ้าดู, `READY` = แท่ง 1m ปิดยืนยัน/เวลาจำกัด, `RISK_BLOCK` = งดเข้า, `CANCELLED/EXPIRED` = แผนเดิมใช้ไม่ได้
- Telegram ส่งเฉพาะการเปลี่ยนสถานะ, ไม่สแปมทุก 5 นาที, สถานะบันทึกบน branch `orbit-scalp-state` แยกจากระบบเดิม
- TTL: READY หมดอายุ 180 วินาทีจากแท่ง 1m ที่ใช้ยืนยัน หาก GitHub รันช้าก็ **ทิ้งข้อความหมดอายุ**

## ข้อจำกัดสำคัญที่ตรวจพบจริง

วันที่ 31 ต.ค. 2026 ได้ทดสอบ Public API จาก environment ที่ใช้พัฒนา:

| Venue | ตรวจสอบได้ | ผล |
|---|---|---|
| Binance TH Spot | BTC, ETH, PEPE, DOGE: exchangeInfo, 1m/5m/15m, Bid/Ask, Depth | **HTTP 200 ทั้ง 4 คู่** |
| Binance Global USDⓈ-M Futures | `/fapi/v1/time`, `/fapi/v1/klines` | **HTTP 451 (Restricted)** — ไม่ส่ง READY Futures |

HTTP 200 บนเครื่องทดสอบ **ไม่รับประกัน** HTTP 200 บน runner ของ GitHub/เครื่องผู้ใช้ ต้องกด workflow `mode: probe` อีกครั้งหลังอัปโหลด

ราคาตลาดระหว่างทดสอบมี **PEPEUSDT Spot Spread ~19.9 bps** ขณะที่ Config กำหนดสูงสุด 12 bps จึงเป็น `RISK_BLOCK` โดยตั้งใจ **ไม่แก้เกณฑ์ให้เกิด READY เทียม**

**ข้อมูลใน v5.6 นี้เป็นข้อมูลการซื้อขายจาก Exchange Public API ไม่ใช่ข้อมูลธุรกรรมบนเชน (on-chain)**; การเทรดความถี่ 1–5 นาทีต้องใช้ Order Book / Trades ที่ทันเวลา ไม่จำเป็นต้องเชื่อม Blockchain RPC อย่างไร้เหตุผล

GitHub Actions schedule มีรอบต่ำสุด 5 นาทีและอาจรันช้า/ข้ามบางรอบ **ไม่ใช่ 1-minute realtime bot 24/7 แบบรับประกัน** โดยเฉพาะ Scalping ที่ยืนยัน 1m บางครั้งระบบอาจพลาดจุดเข้า; ควรใช้สำหรับโอกาสที่ยังใหม่เท่านั้น และไม่ควรซื้อเพราะข้อความเก่า

## ค่าเริ่มต้น (แก้ได้ที่ `scalp_config.json`)

| พารามิเตอร์ | ค่า |
|---|---|
| ทุน Scalp จำลอง | 80 USDT |
| Risk ต่อ 1 Candidate | 0.25% ของทุน (ประมาณ 0.20 USDT สูงสุด) |
| Daily Risk Budget ของการแจ้งเตือน | 1.0% หรือ READY สูงสุด 4 Setup/วัน (เวลาไทย) |
| Max Notional | ไม่เกินทุน 1 เท่า (ไม่ใช้ Leverage ในตัวอย่าง) |
| Min Net R:R TP2 | ≥1.5:1 รวม fee/slip/spread ที่ประมาณไว้ |
| Spot Fee สมมติ/ด้าน | 0.10% (ตรวจค่าบัญชีจริงก่อนเทรด) |
| Futures Fee สมมติ/ด้าน | 0.05% (ตรวจค่าบัญชีจริงก่อนเทรด) |
| Slippage สมมติ/ด้าน | 0.05% |
| Max Spread | 12 bps |
| Min Depth 20 ระดับ | 5 เท่าของ Notional |
| Setup 5m หมดอายุ | 10 นาที |
| 1m READY หมดอายุ | 180 วินาที |
| Execute order | ไม่มี (PAPER ONLY) |

ข้อควรเข้าใจ: Daily Risk Budget ในระบบนี้นับ **โควตาข้อความ READY จำลอง** ไม่ใช่ระบบตรวจ PnL หรือสถานะที่ผู้ใช้ซื้อจริง; ไม่มีการเชื่อมบัญชี ไม่สามารถรับประกันหยุดขาดทุนในบัญชีได้

## การติดตั้งใน GitHub `Punnipah/orbit-crypto-signal-lab`

ZIP นี้เป็น **แพตช์อัปเกรด**: เปิด ZIP แล้วอัปโหลดไฟล์ตามโครงสร้าง **ให้ตรงตำแหน่ง** บน branch หลักของ repository (ไม่ต้องลบไฟล์เดิม ไม่ต้องแตะ GitHub Secrets เดิม)

ไฟล์ที่โฟลเดอร์หลัก Repository:

1. `scalp_config.json`
2. `scalp_marketdata.py`
3. `scalp_engine.py`
4. `scalp_alerts.py`
5. `scalp_runner.py`
6. `mobile_ui.py` (**Replace** ไฟล์ v5.5 เดิม เฉพาะชุดจาก Patch นี้)
7. `app.py` (**Replace** ไฟล์ v5.5 เดิม เฉพาะชุดจาก Patch นี้)
8. `UPGRADE_V56_SCALP_TH.md`

ไฟล์ในโฟลเดอร์ลูก:

9. `.github/workflows/orbit-scalp-signal.yml` (**ต้องอยู่ตรง path นี้**, ไม่ใช่ใน root)
10. `tests/test_scalp_v56.py` (optional: ทดสอบออฟไลน์)

> GitHub Web: หากอัปโหลด ZIP ตรง ๆ เป็นไฟล์ ZIP **GitHub จะไม่แตกเป็นโค้ดให้** ต้องแตกไฟล์ก่อน หากหน้าเว็บสร้างโฟลเดอร์ `.github/workflows` ไม่สะดวก ใช้ **Add file → Create new file** แล้วใส่ชื่อเต็ม `.github/workflows/orbit-scalp-signal.yml` และวางเนื้อหาจากไฟล์ YAML

## วิธีทดสอบก่อนปล่อยแจ้งเตือน

1. หลัง Push/Commit เปิดแท็บ **Actions** จะเห็น `Orbit Scalp Signal v5.6 (Spot TH / Futures Global)`
2. **Run workflow → `mode: probe`** ต้องเห็น `Spot Binance TH: 4/4` และสถานะ Futures จริง (อาจ 0/4 เพราะ HTTP 451)
3. **Run workflow → `mode: dry_run`** ดูผล `WAIT/WATCH/READY/RISK_BLOCK` ทั้ง 8 ตลาด-คู่ โดยไม่ส่ง Telegram
4. **Run workflow → `mode: test_telegram`** ต้องได้รับข้อความ `TEST ONLY` ในห้อง Telegram ที่ตั้งไว้
5. ตรวจว่าที่ Repository **Settings → Actions → General → Workflow permissions** อนุญาต `Read and write permissions` ให้ `GITHUB_TOKEN` (หรือ branch state อาจสร้างไม่ได้)
6. **Run workflow → `mode: live_alerts`** สำหรับเปิดรอบจริงครั้งแรก แล้วระบบ schedule จะสแกนประมาณทุก 5 นาทีโดยอัตโนมัติ
7. เปิด Streamlit เดิม → เมนู `⏱️ Scalp` เลือกตลาด/เหรียญ ทดสอบข้อมูลสดจากโทรศัพท์

> ต้องมี GitHub Secrets เดิม `TELEGRAM_BOT_TOKEN` และ `TELEGRAM_CHAT_ID` อยู่แล้ว; ไม่ต้องใส่ `ORBIT_WATCH_LINKS` สำหรับ Scalp

ทดสอบในเครื่อง (ต้องมี pandas/numpy และ network ที่อนุญาต):

```bash
python -m unittest discover -s tests -q
python -m scalp_runner --validate-config
python -m scalp_runner --probe
python -m scalp_runner --dry-run
```

## หาก Futures แสดง 451

ไม่ใช่ Error ที่ต้องเปลี่ยนตัวเลขใน Config; มันคือการปฏิเสธการเข้าถึง Public API จากเครือข่ายนั้น อาจต้องใช้ runner/location ที่ Binance Global ให้บริการอย่างถูกต้องตามข้อกำหนดที่เกี่ยวข้องก่อน จึงจะมี Futures READY ได้ แนะนำให้คง Spot TH ให้ใช้ได้ก่อนและไม่ฝืนสร้าง Futures LONG/SHORT จากตลาดอื่น

**หมายเหตุ:** v5.6 เป็นระบบ Signal เชิงทดลอง ยังไม่มีผล Backtest/Walk-forward ของกฎ Scalp แบบ End-to-End ที่พิสูจน์ผลกำไร และไม่รับประกันสัญญาณ BUY/LONG/SHORT จะเกิดทุกวัน
