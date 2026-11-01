# Orbit v5.9 — High Contrast Mobile UI Patch

แพตช์นี้แก้เฉพาะ CSS ใน `mobile_ui.py` สำหรับหน้าจอ Spot, Futures, Scalp, Alerts และ Lab

- เพิ่มความสว่างของข้อความรอง คำอธิบาย โซนราคา และป้ายกำกับ
- เพิ่มขนาดและความหนาของตัวหนังสือเล็กเพื่ออ่านบน iPhone ได้ง่ายขึ้น
- ปรับข้อความในส่วน Streamlit Caption/Metric/Control และปุ่ม disabled ให้ชัดขึ้น
- รักษาธีมกรมท่า-เขียว/เหลือง/แดงเดิม และไม่เปลี่ยนข้อความสถานะสัญญาณ

## อัปโหลด

อัปโหลด **เฉพาะ `mobile_ui.py`** ที่ root ของ repository `Punnipah/orbit-crypto-signal-lab` สาขา `main` เพื่อแทนไฟล์เดิม แล้ว Commit รอ Streamlit redeploy

ไม่ต้องเปลี่ยน `scalp_engine.py`, `validation_logic.py`, `whale_footprint.py`, workflows หรือ Config ใด ๆ

## ตรวจสอบ

เปิดบนมือถือและลองแท็บ Spot, Futures, Scalp และ Alerts โดยเฉพาะ:

1. อ่านป้ายชื่อราคาและข้อความเหตุผลของสัญญาณได้ชัด
2. สีแดง/เหลือง/เขียวของสถานะยังสื่อความหมายเดิม
3. รายการยาวและปุ่มบนจอเล็กไม่ทับกัน

**หมายเหตุ:** แพตช์นี้เป็นเฉพาะการแสดงผล ไม่ใช่การปรับกลยุทธ์หรือการรับรองผลกำไร
