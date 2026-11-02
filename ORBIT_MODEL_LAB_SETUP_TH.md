# Orbit Model Lab — ติดตั้งบน Streamlit (แอปทดลองแยก)

สถานะ: โค้ดอยู่ใน branch `experiment/orbit-model-lab` และยังต้อง Deploy + ทดสอบก่อนถือว่าพร้อมใช้งาน

## เปิดแอปแยกบน Streamlit Community Cloud
1. เข้า https://share.streamlit.io/ และลงชื่อเข้าใช้ด้วย GitHub
2. กด Create app / Deploy app และเลือก Existing app from GitHub
3. Repository: `Punnipah/orbit-crypto-signal-lab`
4. Branch: `experiment/orbit-model-lab`
5. Main file path: `orbit_model_lab.py`
6. เลือก URL ใหม่ (ห้ามใช้ URL แอป Orbit หลัก) และกด Deploy
7. รอให้หน้าเว็บขึ้นชื่อ **Orbit Model Lab — Paper Research**

## วิธีทดสอบ
- อัปโหลดไฟล์ CSV ที่มีคอลัมน์ `timestamp,open,high,low,close,volume` อย่างน้อย 120 แท่ง
- ข้อมูลต้องเรียงตามเวลาและราคา OHLC เป็นบวก
- ตรวจตาราง Train 70% และ Holdout 30% ของ 2 โมเดล
- หากไม่มีธุรกรรมในช่วงทดสอบ ค่าผลลัพธ์บางช่องจะว่าง ซึ่งเป็นพฤติกรรมที่ถูกต้อง

## ข้อจำกัด
- เป็น Paper Research ไม่ส่งออร์เดอร์และไม่ส่ง Telegram
- ยังไม่มี Walk-forward, full order-book/funding/slippage model หรือการตรวจคุณภาพกลยุทธ์ครบถ้วน
- ผลตอบแทนเป็นผลตอบแทนรวมต่อธุรกรรมแบบง่าย ไม่ใช่ผลตอบแทนพอร์ต
- ห้ามนำผลนี้ไปตีความว่าเป็นคำแนะนำซื้อขายหรือโมเดลเอาชนะตลาด

## ความปลอดภัย
- อย่าใส่ API keys หรือ GitHub tokens ใน CSV หรือซอร์สโค้ด
- แอปเดิมบน branch main ไม่ถูกแก้ไข
