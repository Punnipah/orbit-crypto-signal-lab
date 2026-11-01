# Orbit v5.9 — Deployment Hotfix (Whale modules)

## สาเหตุ

เว็บ Streamlit แสดง v5.9 แล้ว แต่หน้า Scalp เกิด `ModuleNotFoundError` ที่ `mobile_ui.py` ตอน `from whale_footprint import ...` เพราะ repository ยังไม่มีโมดูล Whale จาก v5.8.5

## ไฟล์ที่ต้องเพิ่ม (เท่านั้น)

อัปโหลดไฟล์ต่อไปนี้โดยรักษาตำแหน่งใน GitHub repository `Punnipah/orbit-crypto-signal-lab` สาขา `main`:

1. `whale_footprint.py` — ที่ root
2. `whale_history.py` — ที่ root
3. `whale_runner.py` — ที่ root
4. `.github/workflows/orbit-whale-footprint.yml` — ที่ path ตามชื่อ

**สำคัญ:** ไม่ต้องอัปโหลด `mobile_ui.py` จากแพ็กเกจ v5.8.5 และไม่ต้องแก้ `scalp_engine.py` เพราะจะเสี่ยงทับ v5.9 / เปลี่ยนกฎ Stop Loss และ risk โดยไม่จำเป็น

## ตรวจสอบหลัง Commit

1. รอ Streamlit redeploy แล้วเปิดแท็บ **Scalp**
2. ตรวจว่ามี Whale Footprint และ Professional Validation โดยไม่มี traceback
3. ใน GitHub Actions เลือก workflow **Orbit v5.8.5 Whale Footprint History (Research Only)** และรัน `mode=dry_run` ก่อนเปิด `record`
4. Whale footprint เป็นการอนุมานจากข้อมูลตลาดสาธารณะ ไม่ได้ยืนยันตัวตนผู้เล่นรายใหญ่ และไม่ใช่สัญญาณกำไรที่รับประกัน

หากหน้า Scalp ยังมี error หลัง Deploy ให้ส่งข้อความ error ล่าสุดก่อนแก้ไฟล์อื่น
