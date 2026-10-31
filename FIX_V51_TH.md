# Orbit v5.1 · แก้ GitHub Monitor และความคมชัดหน้าจอ

## ไฟล์ที่ให้อัปเดตใน GitHub (branch `main`)

1. `monitor_delivery.py` — ลองเชื่อมต่อ GitHub State API ซ้ำเมื่อ GET ขัดข้องชั่วคราว; แจ้ง HTTP 401/403, 429/5xx และ network/DNS แยกประเภท โดยไม่แสดง Token
2. `mobile_ui.py` — ปรับปุ่มที่เดิมเป็นสีขาว/ตัวอักษรจางให้มีคอนทราสต์อ่านได้
3. `tests/test_monitor_v41.py` — เพิ่มกรณีทดสอบความปลอดภัยของ retry

**อย่าลบไฟล์เดิมทั้ง Repository และอย่าทับไฟล์ตั้งค่า Secrets/Watch Link**

## ตรวจปัญหา Monitor จากภาพ

Log `GitHub State API ติดต่อไม่ได้` คือการเรียก API สำหรับประวัติแจ้งเตือนล้มเหลว ไม่ได้หมายความว่า Binance หรือ Telegram ล้มเหลวเสมอไป

1. เปิด Repository → Settings → Actions → General → Workflow permissions ตรวจว่าอนุญาตการเขียนตามนโยบาย Repository (ไฟล์ Workflow มี `permissions: contents: write` อยู่แล้ว)
2. เปิด Actions → `Orbit Telegram Signal Monitor` → `Run workflow` ใหม่หนึ่งครั้ง
3. ถ้า Error เป็น `HTTP 403` ให้ตรวจสิทธิ์/Branch protection; ถ้าเป็น network/DNS อาจเป็นเหตุขัดข้องชั่วคราว ให้ลองใหม่
4. ตรวจว่ามี branch `orbit-alert-state` และไฟล์ `.orbit-monitor/alert-state.json` หลังรันสำเร็จ
5. สำหรับ Futures ต้องตรวจ Workflow `Orbit Futures Daytrade` แยกต่างหาก โดยผลจะอยู่ใน branch `orbit-futures-state`

## ข้อจำกัด

- แพตช์นี้ **ไม่ได้รับรองว่า GitHub API ภายนอกกลับมาใช้งานได้** และไม่เปลี่ยนสิทธิ์ GitHub โดยอัตโนมัติ
- ไม่แก้สัญญาณให้เกิดขึ้นเมื่อข้อมูล Futures ขาด และไม่มีการสั่งซื้อขายจริง
- หากหน้า Futures ยังขึ้น `NO DATA` กรุณาเปิดกล่อง **รายละเอียด** แล้วส่งข้อความ Error ภายในมาเพื่อวินิจฉัย API เฉพาะจุด
- Log จากภาพยังแสดง `Orbit v4.2` ของ *Spot monitor* ซึ่งเป็นข้อความเวอร์ชันของโมดูลเดิม ไม่ได้ยืนยันว่าเว็บ UI v5.0 ถูกย้อนเวอร์ชัน
