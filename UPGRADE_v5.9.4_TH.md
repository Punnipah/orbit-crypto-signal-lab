# Orbit v5.9.4 — Spot Range Bounce Intelligence

## จุดประสงค์

สำหรับการซื้อ Spot ในกรอบ Sideways เช่นซื้อใกล้แนวรับเพื่อรอเด้ง โดยไม่ลดเกณฑ์ BUY ของ MTF เดิม.

| หน้าจอ Spot | ข้อมูล | ความหมาย |
|---|---|---|
| MTF BUY เดิม | Binance Global Spot + context เดิม | ยังคง WAIT/READY และ Stop Loss เดิมทุกข้อ |
| Spot Range Bounce ใหม่ | Binance TH Spot เท่านั้น | โอกาสซื้อแนวรับในกรอบ Sideways, PAPER ONLY |

## สถานะ Range

- `NO_RANGE`: กรอบ 1H ไม่ผ่าน ADX/ความกว้าง
- `RANGE_DETECTED`: พบกรอบ แต่ราคายังไม่ใกล้แนวรับ
- `NEAR_SUPPORT`: ราคาใกล้แนวรับ ยังไม่มีแท่ง 5m ปิดกลับตัวพร้อม Volume
- `REBOUND_WATCH`: กำลังรอ Buy Flow ของแท่ง 1m ที่ปิดแล้ว หรือรอราคา reclaim แนวรับ
- `RANGE_READY`: ผ่านแท่ง 5m, 1m, Spread, Stop Loss, Net R:R ถึง TP1, ค่า Fee/Slippage, Order Book Depth, ขนาดการซื้อจำลอง; แสดงราคา/ระดับเป็น **PAPER ONLY**
- `RANGE_BROKEN`: ปิดหลุดแนวรับ ไม่อ้างกรอบเก่าเพื่อซื้อ
- `RISK_BLOCK`: มีรูปแบบราคาแต่ต้นทุน/ความเสี่ยงไม่ผ่าน
- `DATA_UNAVAILABLE`: ข้อมูลไม่ครบ/เก่า/ดึงไม่ได้; ไม่เดา READY

## ติดตั้งบน GitHub ที่ใช้งาน v5.9.3 อยู่แล้ว

1. สำรองไฟล์เดิม `mobile_ui.py` ก่อน
2. นำ `spot_range_bounce.py` (ไฟล์ใหม่) และ `mobile_ui.py` จากแพตช์นี้ไปวางทับในโฟลเดอร์หลักของโปรเจกต์ที่ GitHub
3. อัปเดต `README.md` ได้ตามต้องการ; เพิ่ม `tests/test_spot_range_v594.py` เพื่อเก็บ regression test
4. **ห้ามลบหรือเปลี่ยน** `scalp_config.json`, `spot_engine.py`, `scalp_engine.py`, GitHub Actions/Secrets หรือระบบ Telegram เดิม
5. รอ Streamlit redeploy แล้วเปิด Spot → เลือกเหรียญที่ Binance TH รองรับ → เลื่อนลงใต้แผน MTF จะเห็นการ์ด Range ใหม่

ระบบไม่เชื่อมบัญชี Exchange ไม่มี API trading key และไม่ส่งคำสั่งซื้อเอง. ไม่สามารถรับประกันโอกาสกำไร; ทดสอบแบบ Paper ก่อนใช้เงินจริง และจำนวนเหตุการณ์ที่มองย้อนหลังว่าเด้งสำเร็จไม่ใช่ผลทดสอบ Walk-forward.
