# Orbit v5.9 — Menu Text Visibility Hotfix

แก้ปัญหาเมนู Spot / Futures / Scalp / Alerts / Lab และปุ่ม BTCUSDT / PEPEUSDT / DOGEUSDT / ETHUSDT / SOLUSDT แสดงพื้นขาวแต่ตัวหนังสือสีขาวจนอ่านไม่เห็น

## วิธีแก้

อัปโหลด `mobile_ui.py` ไฟล์เดียว ทับไฟล์ชื่อเดียวกันที่ root ของ GitHub `Punnipah/orbit-crypto-signal-lab` branch `main` แล้ว Commit ให้ Streamlit redeploy

สิ่งที่ปรับเป็น CSS เท่านั้น:

- ปุ่มเลือกเมนูและเหรียญทุกสถานะใช้พื้นน้ำเงินเข้มและตัวหนังสือสีขาว
- ปุ่มที่ถูกเลือกยังแยกด้วยพื้นเขียวเข้ม
- ตัวอักษรภายในปุ่ม รวมถึง span และ p ไม่ถูกกลบด้วยสีจาก Streamlit

ไม่ได้แก้สูตรวิเคราะห์, Stop Loss, Risk, Whale, Scalp, TP หรือ Alerts

หลัง Deploy ให้ตรวจทั้งบนมือถือและ Desktop ว่าเมนูทุกปุ่มเห็นชื่อชัดเจน
