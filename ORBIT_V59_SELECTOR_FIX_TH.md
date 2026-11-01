# Orbit v5.9 — Menu Contrast Fix (Verified DOM selectors)

ตรวจสอบจาก Streamlit ที่ Deploy จริงพบปุ่มของแถวเมนูเป็น `button[data-variant="segmented_control"]` และแถวเหรียญเป็น `button[data-variant="pills"]` ซึ่งตัวเลือก CSS จากแพตช์ก่อนหน้าไม่ตรงกับ Streamlit เวอร์ชันที่ใช้อยู่

แพตช์นี้แก้ `mobile_ui.py` เพียงไฟล์เดียว:

- ปุ่มทุกอันใช้พื้นน้ำเงินเข้มและข้อความขาว (ไม่เกิด white-on-white)
- ปุ่มที่ถูกเลือกมีพื้นเขียวเข้มและข้อความขาว
- กำหนดสีสำหรับข้อความลูก `<p>` และ `<span>` ของปุ่มให้ชัด

อัปโหลด `mobile_ui.py` ไปที่ root ของ GitHub repository `Punnipah/orbit-crypto-signal-lab` สาขา `main` แล้ว Commit รอ Streamlit redeploy

ไม่มีการแก้เงื่อนไขเทรดและความเสี่ยงใด ๆ
