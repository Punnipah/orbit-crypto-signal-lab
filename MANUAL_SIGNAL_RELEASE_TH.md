# Orbit Crypto Signal Lab — Live On-Page Signal Release (31 ต.ค. 2026)

## วัตถุประสงค์

เว็บสำหรับ **เปิดดู Spot/Futures แล้วข้อมูลและสัญญาณอัปเดตทุกประมาณ 60 วินาทีขณะหน้า Scalp เปิดอยู่** โดยไม่ต้องกดปุ่มทุกครั้ง ไม่มีการเปิดคำสั่งซื้อขายจริง และไม่ต้องเปิด Scheduler หรือ Telegram

## สิ่งที่ปรับปรุง

1. หน้า Scalp เป็น `LIVE SIGNAL` พร้อมรีเฟรชทุก ~60 วินาทีเมื่อเปิดหน้าเว็บอยู่ และปุ่ม **ตรวจข้อมูลตลาดล่าสุด** ยังใช้เมื่อต้องการตรวจทันทีได้
2. แสดงหลักฐาน 15m Trend, 5m ATR, 1m Volume/Flow และ Spread แยกจากสัญญาณหลัก โดยไม่ตีความจำนวนเครื่องหมายถูกเป็นโอกาสชนะ
3. `EARLY BUY WATCH` เป็นข้อมูลเฝ้าดูเท่านั้น ไม่ยกระดับ `WAIT` หรือ `RISK_BLOCK` เป็น `READY`
4. แก้กรณี PEPE/USDT ที่ Spread ขั้นต่ำ 1 Tick ของตลาดจริงสูงกว่าเพดานเปอร์เซ็นต์: อนุญาตช่วง Spread ขั้นต่ำประมาณ 1 Tick ไม่เกิน 25 bps และ **ยังคิด Spread เต็มใน Net R:R**; 2 Tick ยังถูกบล็อก
5. คงคำสั่งซื้อขายจริงเป็นศูนย์ (`PAPER ONLY`) และคงข้อจำกัดข้อมูล Binance Global Futures HTTP 451 โดยไม่สลับข้อมูลข้ามตลาด

## วิธีใช้งานบน Streamlit

1. อัปโหลดไฟล์โปรเจกต์ทั้งหมดจาก ZIP ไปยัง GitHub Repository `Punnipah/orbit-crypto-signal-lab` โดยรักษาโครงสร้างไฟล์เดิม (ไฟล์ `app.py` ต้องอยู่ที่ root)
2. เปิด Streamlit app เดิม (Entry point = `app.py`) รอจน Deploy เสร็จ
3. เลือกแท็บ `Scalp` → `Spot · Binance TH` → `PEPEUSDT` ระบบจะอัปเดตเองทุก ~60 วินาทีขณะเปิดหน้าไว้; กด `ตรวจข้อมูลตลาดล่าสุด` เมื่อต้องการรีเฟรชทันที
4. อ่านสถานะหลัก `READY/WATCH/WAIT/RISK_BLOCK/EXIT_WATCH` ก่อนเสมอ แล้วกด `ตรวจหลักฐานของสัญญาณ` เพื่อดูเงื่อนไขแต่ละข้อ
5. หากขึ้น `EARLY BUY WATCH` แต่สถานะหลัก `RISK_BLOCK` หมายถึง **ยังไม่ผ่านเกณฑ์เข้า** ไม่ใช่ให้ซื้อทันที
6. ตรวจ BTC/ETH/DOGE และ Bitget Futures ด้วยวิธีเดียวกัน; Binance Global Futures อาจเป็น `DATA_UNAVAILABLE` เมื่อ API ปฏิเสธสิทธิ์ตามภูมิภาค

ไม่ต้องสร้าง cron-job.org, GitHub Token หรือเปิด Telegram เพื่อใช้หน้า Scalp แบบ Live On-Page การปิดหน้าเว็บจะไม่สแกนต่อเบื้องหลัง หากใน GitHub มี workflow เดิมที่ตั้ง Schedule ไว้และไม่ต้องการให้ทำงาน สามารถ Disable workflow นั้นแยกจากการใช้งาน Streamlit ได้

## การตรวจสอบก่อนเผยแพร่

- `python -m unittest discover -s tests -p 'test_*.py' -q`
- `python -m py_compile app.py mobile_ui.py scalp_engine.py scalp_marketdata.py scalp_bitget.py`
- ผลการทดสอบ 252 รายการ: ผ่าน 249, ข้าม 3, ไม่ผ่าน 0

## สิ่งที่ผลทดสอบ **ยังไม่ได้** ยืนยัน

- ไม่มีการรับประกัน Win Rate, TP หรือกำไร
- การ Replay 30 วัน PEPE ที่ทำก่อนหน้านี้ใช้สมมติฐาน Bid/Ask และต้นทุน จึงไม่ใช่ผลการ Fill จริง และพบว่า Early Reversal แบบยังไม่ยืนยันทำกำไรสุทธิเฉลี่ยไม่ได้
- ยังไม่มีข้อมูลย้อนหลัง Bid/Ask/Depth ครบทุกวินาทีสำหรับ Backtest FULL READY ทั้งระบบ
- เวอร์ชันนี้เลือก **รักษาเกณฑ์ความเสี่ยง** ไม่เพิ่มสัญญาณ BUY เพียงเพื่อให้ระบบดูตอบสนองเร็วขึ้น

## ไฟล์ของโครงการ

- `app.py`: Streamlit entry point
- `mobile_ui.py`: หน้า Spot, Futures, Scalp, Alerts, Lab
- `scalp_engine.py`: เงื่อนไข Scalp และหลักฐานสัญญาณ
- `scalp_marketdata.py`, `scalp_bitget.py`: ข้อมูลตลาดเฉพาะ Exchange
- `scalp_config.json`: ทุนจำลองและตัวกรองความเสี่ยง
- `tests/`: Unit tests และไฟล์วิจัยที่เกี่ยวข้อง (ไม่จำเป็นต้องรันเพื่อเปิดเว็บ)

**หมายเหตุ:** GitHub Actions ใน Repository จริงเป็นคนละระบบกับเว็บ Streamlit และไม่ได้จำเป็นสำหรับการกดวิเคราะห์เอง
