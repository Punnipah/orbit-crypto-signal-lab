# Orbit Scalp Signal v5.7 — อัปเกรดจาก v5.6 (31 ตุลาคม 2026)

**แพตช์นี้ใช้กับ GitHub Repository เดิม** และ **ไม่แตะไฟล์ Day Trade / Telegram Monitor เดิม**
การเปลี่ยนแปลงทั้งหมดเป็นระบบอ่านข้อมูล (PAPER ONLY) ไม่ขอ API Key เทรด และไม่ส่งออร์เดอร์

## 1) อัปเกรดอะไรบ้าง

- **Spot Binance TH:** ตรวจ 4 คู่ BTC/ETH/PEPE/DOGE แบบเดิม
- **Futures Binance Global:** ยังคงสแกนตลาดเดิมแยกต่างหาก ถ้า HTTP 451 จะเป็น `DATA_UNAVAILABLE` ไม่สร้าง LONG/SHORT หลอก
- **เพิ่ม Futures Bitget USDT Perpetual เป็น *อีกหนึ่งตลาดแยก*** (4 คู่) ข้อมูลมาจาก Bitget เองและข้อความ Telegram จะระบุ "Bitget" ชัดเจน **ห้ามนำราคา Entry ของ Bitget ไปใช้เป็นราคาเข้า Binance Global**
- **ตรวจสอบ Public Trade Fills Buy/Sell ของ Bitget อย่างจริงจัง:** API แท่ง 1m ไม่มีข้อมูล Taker Buy; Public Fills ระบุเพียง `side=buy/sell` ไม่ได้ยืนยันในเอกสารว่าเป็น Aggressor/Taker โดยตรง ระบบจึงใช้เป็น **Proxy ที่ติดป้ายแหล่งข้อมูลชัด** และยอมให้ยืนยันแท่งเฉพาะเมื่อข้อมูลครอบคลุมเวลาเต็ม 1m และ Volume ของ Fills ตรงกับ Volume ในแท่ง **95–105%** เท่านั้น; ถ้าไม่ครบจะแสดง WATCH/WAIT ไม่มี READY
- Futures Bitget ตรวจฟิลด์ **Mark Price / Funding Rate / Bid-Ask / Depth / ขนาดสัญญาขั้นต่ำ / Tick Size / Taker Fee ตาม API** จาก Public API
- **Adaptive Spread Gate**: ปกติสูงสุด 12 bps; เมื่อ 5m ATR สูงขึ้นจะขยายเพดานตามความผันผวนได้ แต่ไม่เกิน 25 bps (Spread จริงนับในค่าต้นทุนเสมอ); ไม่ได้ทำให้เกิด READY โดยข้ามการยืนยัน 15m/5m/1m
- **Research mode:** ประเมินการกระจาย ATR 5m และจำนวน Breakout ทางเทคนิคจากข้อมูลย้อนหลังจริง; ย้ำว่า **ไม่ใช่ผลกำไร/Win Rate/Full Backtest** เพราะไม่มีข้อมูล Bid/Ask, order book และ fill ย้อนหลัง
- Telegram ใช้ Secrets เดิมและ GitHub state branch `orbit-scalp-state` เดิม; ไม่ต้องตั้ง Bot ใหม่; `WATCH`, `READY`, `CANCELLED`, `EXPIRED` ยังส่งเฉพาะการเปลี่ยนสถานะ
- Daily Risk Budget ของการแจ้งเตือน READY รวมทั้งสามตลาดภายใน state เดียว 4 candidate/วัน (ประมาณความเสี่ยงต่อครั้ง 0.25% ของทุน 80 USDT)

## 2) ผลทดสอบ Public API จริง (31 ต.ค. 2026)

| ตลาด | คู่ที่อ่านได้ | รายละเอียด |
|---|---|---|
| Binance TH Spot | **4/4** | 1m/5m/15m, order book, trading filters พร้อม |
| Binance Global USD-M Futures | **0/4** | HTTP **451** จากเครื่องทดสอบ; ห้ามสร้าง READY |
| Bitget USDT Futures | **4/4** | 1m/5m/15m, fee, Bid/Ask, Depth, Mark/Funding, Public Fills พร้อม แต่ Fills บางเหรียญครอบคลุม 1m ไม่ครบ จึงไม่มี READY จนกว่าจะตรวจครบ |

Bitget `takerFeeRate` ที่ API แสดงในรอบทดสอบคือ `0.0006` หรือ **0.06% ต่อด้าน** ระบบใช้ค่าสูงกว่าระหว่างค่าจากตลาดกับ `futures_fee_each_side_pct` ใน Config เพื่อไม่ประมาณค่าธรรมเนียมต่ำเกินไป

สำคัญ: **HTTP 200 ในเครื่องทดสอบไม่ยืนยันว่า GitHub Actions จะเห็นผลเหมือนกัน** ต้องกด Run workflow ด้วย mode `probe` หลังอัปโหลด จึงยืนยันจาก GitHub ได้

## 3) วิจัย Volatility ย้อนหลังแบบบรรยาย (ไม่ใช่ Win Rate)

ข้อมูล Binance TH Spot 5m จำนวน **905 แท่งต่อเหรียญ** หลังตัดช่วงตั้งต้นและแท่งล่าสุดบางส่วน:

| เหรียญ | Median ATR 5m | Breakouts เมื่อ ATR >=0.10% | เมื่อ ATR >=0.07% |
|---|---:|---:|---:|
| BTC | 0.1409% | 22 | 26 |
| ETH | 0.1957% | 40 | 46 |
| PEPE | 0.8654% | 40 | 40 |
| DOGE | 0.2379% | 29 | 29 |

นี่คือ **จำนวน Breakout เชิงเทคนิคดิบ** ก่อนใช้เงื่อนไข Trend 15m, 1m Taker, Spread, Order Book, Entry, Fee/Slippage และ Stop/TP — **ห้ามตีความเป็นจำนวนสัญญาณ READY หรือกำไรที่ทำได้** จึงยังคง ATR floor ที่ 0.10% เพื่อไม่ลดมาตรฐานเพียงเพราะอยากเห็นสัญญาณบ่อยขึ้น

## 4) วิธีอัปเดตใน GitHub (เปลี่ยนเฉพาะไฟล์แพตช์)

**แตก ZIP ก่อน** อย่าอัปโหลดไฟล์ ZIP ตรง ๆ ลง GitHub เพราะจะไม่ถูกคลายเป็นโค้ด

**หน้าแรกของ Repository** → Code → Add file → Upload files → อัปโหลด 9 ไฟล์ต่อไปนี้ และ Commit:

1. `scalp_config.json` (Replace — เพิ่มรายการ Bitget Futures)
2. `scalp_marketdata.py` (Replace)
3. `scalp_bitget.py` (**New**)
4. `scalp_engine.py` (Replace)
5. `scalp_alerts.py` (Replace)
6. `scalp_runner.py` (Replace)
7. `scalp_research.py` (**New**)
8. `mobile_ui.py` (Replace — เพิ่มตัวเลือก Bitget Futures ในเมนู Scalp)
9. `UPGRADE_V57_SCALP_TH.md` (**New**)

**โฟลเดอร์ `.github/workflows`** → Upload file **1 ไฟล์**:

10. `orbit-scalp-signal.yml` (Replace — เพิ่ม mode `research` / เปลี่ยนชื่อ Workflow เป็น v5.7)

**โฟลเดอร์ `tests`** → Upload file **1 ไฟล์**:

11. `test_scalp_v56.py` (Replace — Regression Tests เดิม + Bitget)

**รวม 11 ไฟล์**; ไม่ต้องอัปโหลด `app.py` เพราะ v5.6 เดิมเรียกเมนู Scalp ผ่าน `mobile_ui.py` อยู่แล้ว และไม่ต้องแก้ Secret

## 5) วิธีตรวจครั้งเดียวให้ครบ

ใน GitHub ไป **Actions → Orbit Scalp Signal v5.7** แล้วรันตามลำดับ:

1. `probe`: ต้องเห็น Spot Binance TH 4/4, Bitget Futures 4/4 และ Binance Global อาจ 0/4 เมื่อ HTTP 451
2. `research`: ดู ATR / Breakout ย้อนหลังเชิงบรรยาย ไม่ใช่ Backtest กำไร
3. `dry_run`: ดูสถานะจริงทุกเหรียญ โดย **ไม่ส่ง Telegram**
4. `live_alerts`: ให้ระบบส่ง WATCH/READY ที่เพิ่งเกิดจริงและยังไม่หมดอายุ แล้วกลับไปดู Telegram

เมื่อวางไฟล์แล้ว GitHub schedule จะรันทุกประมาณ 5 นาทีด้วยตัวเอง ไม่ต้องกด `live_alerts` ซ้ำทุกครั้ง (อาจล่าช้า/ข้ามบางรอบตามข้อจำกัด GitHub)

**หมายเหตุเรื่องความเสี่ยงและสถานะบริการ:** Bitget เป็นตลาดนอกเหนือจาก Binance TH/Binance Global ผู้ใช้งานในไทยควรตรวจสอบสิทธิให้บริการและข้อกำหนดที่เกี่ยวข้องด้วยตนเองก่อนทำรายการ **การแสดงข้อมูลไม่ได้เป็นคำแนะนำให้สมัครหรือเทรดกับ Bitget** ระบบนี้ไม่มี Private API, เลเวอเรจ, การสั่งซื้อ หรือการติดตาม PnL ในบัญชีจริง

**ห้ามสับสน:** Bitget LONG/SHORT เป็นสัญญาณจากราคา Bitget Futures เท่านั้น ไม่ใช่สัญญาณ Binance Global; BTC/ETH/PEPE/DOGE อาจมีราคา Spread และค่าธรรมเนียมคนละชุดกับตลาดที่คุณใช้งานจริง
