# Orbit Futures Day Trade Alerts v1 — แยกจาก Orbit Spot

## จุดประสงค์

- คัดกรองโอกาส **LONG** และ **SHORT** จาก **Binance USDⓈ-M USDT Perpetual public market data** (ไม่ใช้ราคา Spot)
- ติดตาม PEPEUSDT, BTCUSDT, DOGEUSDT ตามค่าเริ่มต้น ทุก 15 นาทีผ่าน GitHub Actions
- 4H + 1H EMA20/EMA50 ต้องไปทางเดียวกัน, แท่ง 15m ปิดทะลุ high/low 12 แท่งพร้อม Volume ≥1.2 เท่า และ Taker Buy/Sell ยืนยัน
- ส่ง **WATCH** เมื่อพบ breakout: ยังไม่ใช่จุดเข้า / รอราคา retest; ส่ง **READY** เฉพาะเมื่อแท่ง 15m ถัดไป retest แล้วยืนยัน และราคา Futures ล่าสุดยังอยู่ Entry Zone
- มี Entry Zone, Stop, TP1/TP2 (TP2 เน้น estimated net reward:risk ≥2:1 หลังสมมติค่าธรรมเนียม+slippage), ขนาดความเสี่ยงเชิงตัวอย่าง
- ระงับสัญญาณเมื่อข้อมูลไม่สด, ราคาตลาดกับ mark price ต่างมาก, funding สูง, trend ขัดกัน, setup invalidated, หรือตำแหน่ง Stop ห่างเกินเกณฑ์
- ไม่ส่งซ้ำทุก 15 นาที; จดจำ setup และสถานะใน state branch แยกชื่อ `orbit-futures-state`
- **ไม่มีฟังก์ชันเทรดจริง ไม่มี exchange API key และไม่สร้างออร์เดอร์**

## ติดตั้งบน GitHub (แยก ไม่แก้ Spot เดิม)

จาก ZIP ที่เตรียมไว้:

1. เปิด Repository `Punnipah/orbit-crypto-signal-lab` → `Code` → `Add file` → `Upload files`
2. อัปโหลด **3 ไฟล์ที่โฟลเดอร์หลัก (root)**: `futures_daytrade.py`, `futures_daytrade_runner.py`, `futures_daytrade_config.json`
3. สร้างไฟล์ที่ **path ตรงนี้**: `.github/workflows/orbit-futures-daytrade.yml` (ต้องอยู่ในโฟลเดอร์ `.github/workflows` จริง ๆ ไม่ใช่ root) โดยกด `Add file` → `Create new file` แล้ววางเนื้อหาจากไฟล์ใน ZIP หรืออัปโหลดทั้งโฟลเดอร์ตามโครงสร้างที่ GitHub รองรับ
4. `Commit changes` ไปที่ default branch (`main` หาก repository ของคุณใช้ main)
5. ไม่ต้องแก้ `ORBIT_WATCH_LINKS` หรือ workflow เก่าของ Spot
6. Workflow Futures จะใช้ `TELEGRAM_BOT_TOKEN` กับ `TELEGRAM_CHAT_ID` **ตัวเดิม** ที่ตั้งเป็น GitHub Secrets อยู่แล้ว โดยข้อความจะขึ้นหัวข้อ `Orbit FUTURES DAY TRADE` แยกจาก Spot ชัดเจน
7. เข้า `Actions` → `Orbit Futures Day Trade (Long & Short)` → `Run workflow`:
   - ติ๊ก `send_test=true` เพื่อตรวจ Telegram **อย่างเดียว** (ไม่มีการวิเคราะห์กราฟ)
   - **ไม่ติ๊ก** `send_test` (`false`) เพื่อสแกนกราฟจริงหนึ่งรอบ
8. คลิก Run ล่าสุด → `futures-alerts` → ดู log `... Futures | status=...` และ `FUTURES run complete; ...` หากไม่มี setup ใหม่ Telegram จะไม่ส่งข้อความ

## ข้อควรรู้เกี่ยวกับเวลา

- GitHub cron `7,22,37,52 * * * *` ใน UTC เท่ากับนาที :07/:22/:37/:52 ตามเวลาไทยเช่นกัน (เวลาไทยบวก 7 ชั่วโมง)
- สแกนหลัง 15m ปิดแท่ง 7 นาทีเพื่อรอข้อมูลยืนยัน ไม่ใช่ระบบ Tick-by-Tick; กราฟอาจเคลื่อนไหวเกินโซนระหว่างการสแกน
- GitHub Schedule มีโอกาสดีเลย์หรือบางครั้งไม่เริ่มทำงาน ตรวจสอบ log ในแท็บ Actions ได้; **ห้ามถือว่า alert รับประกันความทันเวลา**

## สถานะที่เห็นใน Logs / Telegram

| สถานะ | ความหมาย | Telegram |
| --- | --- | --- |
| `NO_TREND` | 1H/4H ไม่ไปทิศเดียวกัน | ไม่ส่ง |
| `NO_SETUP` | ยังไม่พบ 15M breakout ที่ผ่าน Volume/Taker | ไม่ส่ง |
| `WATCH_LONG`, `WATCH_SHORT` | พบ breakout แต่ **ยังห้ามเข้า** รอ retest | แจ้งครั้งแรกต่อ setup |
| `READY_LONG`, `READY_SHORT` | มีแท่ง 15M retest ยืนยันและราคาล่าสุดยังอยู่ในโซน | แจ้งครั้งแรกต่อ setup |
| `INVALIDATED` | ราคาเบรกผิดทาง ยกเลิก setup | แจ้งเมื่อ setup เดิมเคยถูก WATCH/READY |
| `RISK_BLOCK`, `DATA_UNAVAILABLE` | ข้อมูลหรือความเสี่ยงไม่ผ่าน | ไม่ส่ง |

ระบบนี้ไม่ใช้ Frozen Watch Plan และไม่มีการล็อกออร์เดอร์ที่โบรกเกอร์ ระบบ Spot เดิมยังคงทำงานของตัวเอง

## แก้ Config อย่างระมัดระวัง

ไฟล์ `futures_daytrade_config.json` ใช้ทุน **สมมติ 1,000 USDT** ไม่ใช่ทุนจริงของพรรณ จนกว่าจะปรับค่าเอง:

```json
{
  "symbols": ["PEPEUSDT", "BTCUSDT", "DOGEUSDT"],
  "capital_usdt": 1000,
  "risk_per_signal_pct": 0.5,
  "max_notional_multiple": 1.0,
  "min_net_reward_risk": 2.0,
  "round_trip_cost_pct": 0.16,
  "breakout_lookback": 12,
  "setup_expiry_bars": 6,
  "breakout_volume_ratio": 1.2,
  "entry_zone_atr_fraction": 0.45,
  "max_risk_distance_pct": 3.0,
  "max_mark_last_deviation_pct": 0.35,
  "max_abs_funding_rate_pct": 0.3
}
```

- `risk_per_signal_pct=0.5`: เสี่ยงสูงสุดประมาณ 0.5% ของทุนสมมติในแต่ละ setup; เป็นการประเมิน ไม่รับประกันขาดทุนสูงสุด
- `max_notional_multiple=1.0`: จำกัดมูลค่าโพซิชันอ้างอิงไม่เกินทุนสมมติ (ไม่ได้ตั้งค่า Leverage บน Exchange)
- `round_trip_cost_pct=0.16`: สมมติค่าใช้จ่ายสองทางรวมค่าธรรมเนียม+slippage; ถ้าค่าจริงสูงกว่า R:R จะต่ำลงและอาจขาดทุนเกินคาด
- `TP1/TP2` เป็นจุดเป้าหมายทางคณิตศาสตร์ **ไม่ใช่ระดับแนวต้าน/แนวรับที่ได้รับการยืนยัน**; ผลจริงขึ้นกับสภาพคล่องและการเคลื่อนราคา
- ระบบ **ยังไม่มีผล Backtest/Walk-forward สำหรับกลยุทธ์ Futures ชุดใหม่นี้** และยังไม่ผ่าน Live Run จากเครื่องของพรรณ ควรทดสอบบนข้อมูลย้อนหลังและ Paper Trading ก่อนนำไปใช้เงินจริง
- การเทรดฟิวเจอร์สมีความเสี่ยงขาดทุนสูง รวมถึงการถูกล้างพอร์ตจาก Leverage, funding, slippage และการเคลื่อนราคากะทันหัน

## การตั้งช่อง Telegram แยกภายหลัง

ค่าเริ่มต้นใช้แชตเดิมเพื่อสะดวก หากต้องการแชตหรือกลุ่ม Telegram ใหม่ สามารถเพิ่ม Secrets ชื่อ `FUTURES_TELEGRAM_BOT_TOKEN` / `FUTURES_TELEGRAM_CHAT_ID` และปรับ workflow Futures ให้อ้างอิง Secrets ใหม่ได้ **อย่าส่ง Token ในแชต**

## ตรวจสอบในเครื่อง (ไม่ส่ง Telegram)

```bash
python -m futures_daytrade_runner --validate-config
python -m futures_daytrade_runner --dry-run
python -m unittest discover -s tests -p 'test_futures_daytrade.py' -v
```

`--dry-run` ต้องมีการเชื่อมต่อ Public Futures API ของ Binance และอาจคืน `DATA_UNAVAILABLE` หากเชื่อมต่อไม่ได้
