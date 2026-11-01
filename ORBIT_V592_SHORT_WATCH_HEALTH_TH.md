# Orbit v5.9.2 — SHORT Opportunity Watch + Futures Data Health

อัปเดตแบบต่อยอดจาก v5.9.1 โดย **ไม่แก้เครื่องยนต์ส่งสัญญาณเข้า** และไม่เปลี่ยนค่าความเสี่ยงเดิม เหมาะกับกรณีที่มองเห็น PEPE อ่อนตัวลงบน TradingView แต่หน้า Orbit ยังขึ้น `WAIT` หรือ `DATA UNAVAILABLE` ต้องการรู้ *ทำไมยังไม่ SHORT* โดยไม่มีการฝืนกฎความปลอดภัย

## สิ่งที่เพิ่ม

### 1. SHORT Opportunity Watch — อ่านโอกาส ไม่ใช่คำสั่งเปิดสถานะ

- แสดงบนหน้า **Scalp Signal** สำหรับตลาดที่ดึง Snapshot ได้จริง โดยอ่านแท่ง **ปิดแล้ว** ของ `1H`, `15m`, `5m`, `1m` และข้อมูล Taker Flow จากตลาดที่เลือก
- ตรวจบริเวณแนวต้านย้อนหลัง 1H หรือจุดที่เพิ่งหลุดกรอบ 5 นาทีโดยไม่ไล่ราคาเกิน 0.4%, สัญญาณแนวโน้ม 15 นาที, แรงขาย 5 นาที, แท่งแดง 1 นาที และแรงขายของผู้ทำรายการ (Taker Sell)
- สถานะ `SHORT_WATCH` หมายถึง *มีองค์ประกอบที่ควรเฝ้าดู* ไม่ใช่เปิด Short ได้ทันที; `EARLY_WATCH` คือยังต้องรอ; `NO_SETUP` และ `INSUFFICIENT_DATA` อธิบายความไม่พร้อม
- กดแสดงรายละเอียดได้ว่าข้อสังเกตใดผ่านหรือไม่ผ่าน แยกจากกฎอนุมัติคำสั่งทั้งหมด

**ข้อสำคัญ:** การผ่าน 3/5 ใน Watch **ไม่ใช่การลดเกณฑ์ READY** ไม่ใช่ Win Rate และไม่คำนวณ Entry, Stop, TP หรือขนาดสัญญา ข้อมูล Spot ใช้เฝ้าดูราคาขาลงได้ แต่ **ห้ามเปิด SHORT Spot** และห้ามยกระดับ Spot เป็นสัญญาณ Futures

### 2. Futures Data Health — แยกเหตุขัดข้องจากกลยุทธ์

ในหน้า Scalp มีส่วน `Futures Data Health` บอกสถานะตามตลาดที่ผู้ใช้เลือก:

| สถานะ | ความหมาย | อนุมัติ SHORT ได้เลยหรือไม่ |
| --- | --- | --- |
| `ACCESS_BLOCKED` | Exchange ตอบ HTTP 403/451; ตลาดนั้นไม่พร้อมใช้งานจากสภาพแวดล้อมที่รัน | ไม่ได้ |
| `RATE_LIMITED` | API ตอบ HTTP 429 จำกัดจำนวนคำขอ | ไม่ได้ |
| `NETWORK_ERROR` | เชื่อมต่อ/หมดเวลา | ไม่ได้ |
| `SYMBOL_UNAVAILABLE` | คู่เหรียญไม่พร้อมในตลาดนั้น | ไม่ได้ |
| `DATA_UNAVAILABLE` / `STALE_DATA` | ไม่มี Snapshot ที่ยืนยันได้ / ข้อมูลเก่า | ไม่ได้ |
| `SPOT_ONLY` | มีข้อมูล Binance TH Spot | ไม่ได้สำหรับ SHORT Futures |
| `WATCH_ONLY` | มีข้อมูล Bitget Futures แต่ขาด Taker Flow ตามกฎเดิม | ไม่ได้ |
| `API_REACHABLE` | ตรวจผ่านเฉพาะ Exchange Catalog | ไม่ได้ |
| `FUTURES_DATA_READY` | ดึง Binance Global Futures Snapshot ตามการตรวจต้นทางได้ | **ยังไม่ได้** — ต้องผ่านเกณฑ์เทรดทั้งหมดแยกต่างหาก |

- มีปุ่มตรวจ **Exchange Catalog ทั้ง 3 ตลาด** ตามคำขอเท่านั้น (read-only); ผลสำเร็จแค่บอกว่า API สำหรับรายชื่อคู่เหรียญตอบ ไม่ได้ตรวจแท่ง ราคา Mark/Funding, Order Book หรือความพร้อมจะเทรด
- เมื่อ Futures API ใช้งานไม่ได้ มี **ตัวเลือกแยกต่างหาก** ให้ดู SHORT Watch จาก Binance TH Spot *เพื่อศึกษาเท่านั้น* ติดป้ายแหล่งข้อมูลและคำเตือนชัดเจน **ไม่ส่งข้อมูล Spot เข้าเครื่องยนต์ Futures**
- ไม่สร้างการเชื่อมต่อหลบเลี่ยง HTTP 451/403 และไม่ส่งคำสั่งซื้อขาย

## สิ่งที่คงเดิมทุกข้อ

ไม่มีการแก้ `scalp_engine.py`, `zone_signal.py`, `scalp_config.json`, `scalp_marketdata.py` หรือ workflow แจ้งเตือน/คัดกรองเดิม จึงคงการตรวจ Stop Loss, TP, Risk per Trade, Daily Risk Budget, Spread, Fees, Depth, Net R:R, Confirming/READY, Venue-native และกฎ Bitget Flow ตามเดิม ตัว Tracker **Near Ready/Missed Opportunity** ของ v5.9.1 ก็ยังอยู่ครบ

## Deploy จาก v5.9 หรือ v5.9.1 — แพ็กเดียว

แตก ZIP แล้วอัปโหลดใน GitHub repo เดิม `Punnipah/orbit-crypto-signal-lab` branch `main` โดยรักษาโครงสร้างโฟลเดอร์:

| ตำแหน่ง | การดำเนินการ |
| --- | --- |
| `mobile_ui.py` | **แทนที่ไฟล์เดิม** (รวม Near Ready v5.9.1 และสีเมนูที่อ่านได้) |
| `validation_runner.py` | แทนที่เฉพาะเมื่อยังไม่ได้อัปเกรด v5.9.1 |
| `near_ready_tracker.py`, `near_ready_history.py` | เพิ่มใหม่ถ้ายังไม่มี |
| `short_opportunity.py`, `futures_data_health.py` | เพิ่มใหม่ทั้งคู่ |
| `tests/test_near_ready_v591.py`, `tests/test_short_watch_health_v592.py` | เพิ่มในโฟลเดอร์ `tests/` |

**อย่าแทนที่:** `scalp_engine.py`, `zone_signal.py`, `scalp_config.json`, `scalp_marketdata.py`, ไฟล์อื่นที่ไม่มีในแพ็ก และไฟล์ GitHub Actions Workflow เดิม

หลัง Commit ให้ Streamlit ปรับใช้อัตโนมัติหากผูก branch เดิม; เปิดเมนู `Scalp`, เลือก `Futures · Binance Global` หรือ `Futures · Bitget`, ตรวจ **Data Health** ก่อนอ่าน **SHORT Opportunity Watch** กรณี Futures ติด `ACCESS_BLOCKED` จะไม่มี READY แม้ Spot จะลงแรง

ส่วน Data Health และ Watch บนหน้าเว็บทำงานตามการเปิดหน้า/รีเฟรช ขณะที่ Telegram และ GitHub Actions ยังคงกำหนดรอบแยกตาม workflow เดิม: **แพ็กนี้ไม่ได้เพิ่ม Scheduled Scanner/Telegram Alert ใหม่**

## ทดสอบก่อนส่งมอบ

```bash
python -m py_compile mobile_ui.py short_opportunity.py futures_data_health.py
python -m unittest discover -s tests -q
```

ผลทดสอบฐานโค้ดที่บรรจุแพ็ก: **353 tests OK (3 skipped)** รวม 11 tests ใหม่สำหรับ Watch/Data Health และตรวจว่าเครื่องยนต์สัญญาณเดิมไม่เปลี่ยนผลจากการเรียก Watch การทดสอบหน้าเว็บจริงและข้อจำกัด API ภายหลัง Deploy ยังต้องตรวจจากแอปที่เผยแพร่

