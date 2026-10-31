# Orbit Crypto Signal Lab v5.8.2 — Scalp TP ระยะราคา 10 USDT

## อัปเดต

- หน้า **Scalp** มีตัวเลือก `🎯 TP ระยะราคา 10 USDT` และ `TP ตามแผนเดิม`
- แสดง **ราคาปลายทาง TP** แม้ยังอยู่ในสถานะ `WAIT` แต่เป็นเพียง *ตัวอย่างราคาอ้างอิง* ไม่ใช่สัญญาณเข้า
- เมื่อโซนผ่านสัญญาณ `READY` ระบบประเมิน TP ทางเลือกด้วยจุดเข้า, Stop Loss, ปริมาณ, ค่าธรรมเนียม, Spread, Slippage และ Net Risk/Reward
- ระงับ TP ทางเลือกเมื่อราคาไม่สมเหตุสมผล, ปลายทางต่ำกว่าศูนย์, หลังต้นทุนไม่เหลือกำไร หรือ Risk/Reward ไม่ผ่าน
- Spot ใช้ LONG เท่านั้น; Futures ประเมิน LONG และ SHORT ตามสัญญาณ
- แผน TP1/TP2 เดิมไม่ถูกลบ ไม่ส่งคำสั่งซื้อขาย (PAPER ONLY)

## ตัวอย่างการตีความ

- BTC ราคา 77,000 USDT เปิด LONG → TP ราคา 77,010 USDT (ก่อนปัดตาม tick ของตลาด)
- BTC ราคา 77,000 USDT เปิด SHORT → TP ราคา 76,990 USDT
- ไม่ได้หมายถึงกำไร 10 USDT ของทั้งไม้: กำไรต่อไม้ขึ้นอยู่กับขนาดสัญญาและค่าใช้จ่าย
- PEPE ราคาใกล้ 0.000005 USDT ไม่เหมาะกับการตั้งเป้าราคาห่าง 10 USDT ระบบจะแสดงสถานะไม่ผ่าน

## วิธีติดตั้งใน GitHub

1. แตกไฟล์ `ORBIT_V582_TP10_GITHUB_2_FILES.zip` จะได้ `mobile_ui.py` และ `scalp_fixed_tp.py`
2. เปิด repository `Punnipah/orbit-crypto-signal-lab` > **Add file** > **Upload files**
3. ลาก **ทั้งสองไฟล์** ไปไว้ที่ root ของ repository ไม่ใช่ในโฟลเดอร์ใหม่
4. กด **Commit changes** ให้ทับ `mobile_ui.py` เดิม และเพิ่ม `scalp_fixed_tp.py`
5. เมื่อ Streamlit Cloud อัปเดตแล้วตรวจหัวแอปเป็น **V5.8.2** และเลือกหน้า **Scalp**

## การทดสอบ

ทดสอบ Python syntax และ automated tests ทั้งหมด 281 รายการผ่าน (ข้าม 3 รายการเนื่องจากสภาพแวดล้อมไม่มี Streamlit/Plotly) การทดสอบดังกล่าวไม่ใช่การรับประกันผลกำไรหรือการตรวจหน้าเว็บ live หลัง commit
