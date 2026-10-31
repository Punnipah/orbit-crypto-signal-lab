# Orbit Scalp v5.8 · MICRO_TREND Patch (31 ต.ค. 2026)

## เปลี่ยนอะไร

- เมื่อ 15m **ยังไม่ยืนยันแนวโน้ม** ระบบสามารถประเมินทิศทางสั้นจาก EMA9/21 และ ADX ของ 5m ได้ โดยแสดง `Strategy: MICRO_TREND` และ `Market Regime: SHORT_TERM_MOMENTUM`.
- ยังคงต้องผ่าน **Breakout แท่ง 5m ที่ปิดแล้ว + Volume**, **ยืนยันแท่ง 1m**, และตัวกรอง Spread, ATR, Depth, ขนาดคำสั่งขั้นต่ำ, Stop Loss, Net R:R ก่อน `READY`.
- 5m ที่สวนกับ 15m ขาขึ้น/ลงชัดเจนไม่สามารถใช้ทางลัดนี้ได้.
- กลยุทธ์ Range Reversal และ Early Buy Watch เดิมยังทำงานตามเดิม. Early Buy Watch เป็นเพียงเฝ้าดู ไม่ใช่คำแนะนำซื้อ.
- Binance TH Spot ไม่เปิด Short, ไม่มีการส่งคำสั่งซื้อขายจริง และระบบไม่ต้องใช้ API Key ส่วนตัว.

## ข้อจำกัด

การปรับนี้เพิ่มช่องทาง **ตรวจจับ** ที่เดิมถูก 15m บล็อก แต่ **ไม่ได้รับประกันจำนวน BUY/READY หรือกำไร**. ยังไม่มีผลทดสอบย้อนหลังแบบเต็มของ MICRO_TREND; ห้ามตีความว่าผ่านการพิสูจน์กำไรแล้ว. ผลลัพธ์ `WAIT` ยังเป็นเรื่องปกติเมื่อไม่มี Breakout/Flow หรือความเสี่ยงไม่ผ่าน.

## ตรวจสอบ

`PYTHONPATH=. python -m unittest discover -s tests -q` (254 tests, ผ่าน 251, skipped 3 ณ วันที่จัดทำ)

## นำขึ้นเว็บ

อัปโหลดไฟล์ชุดนี้ทับไฟล์ใน GitHub repository ที่ Streamlit ใช้ (โดยเฉพาะ `scalp_engine.py`, `tests/test_scalp_v56.py`); รอ Streamlit redeploy. หน้าแอปยังใช้ชื่อ `LIVE SIGNAL` เดิม แต่เมื่อพบโอกาสแบบใหม่จะปรากฏ `Strategy: MICRO_TREND`. การเห็นหัวข้อ LIVE SIGNAL เพียงอย่างเดียวไม่ยืนยันว่า patch นี้ deploy แล้ว.
