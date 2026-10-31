# Orbit Scalp Signal v5.8 — AUTO REGIME

รุ่นนี้เพิ่ม Sideways Range Reversal โดยยังคง Trend Breakout v5.7, แยก Spot Binance TH / Futures Binance Global / Futures Bitget, และ Telegram ผ่าน GitHub Actions ไว้ตามเดิม ระบบส่งเพียงสัญญาณ **PAPER ONLY** ไม่ส่งออร์เดอร์จริง

## วางไฟล์ GitHub

1. เปิด ZIP แล้วอัปโหลด **ไฟล์ Python/JSON 7 ไฟล์และคู่มือนี้** ลงหน้าแรกของ repository (`main`) โดยเลือก Replace เมื่อมีชื่อซ้ำ:
   `scalp_engine.py`, `scalp_runner.py`, `scalp_alerts.py`, `scalp_config.json`, `mobile_ui.py`, `scalp_marketdata.py`, `scalp_bitget.py`, `UPGRADE_V58_AUTO_REGIME_TH.md`
2. อัปโหลด `.github/workflows/orbit-scalp-signal.yml` ไปยังโฟลเดอร์ `.github/workflows` **ไม่ใช่หน้าแรก**
3. อัปโหลด `tests/test_scalp_range_v58.py` ไปยังโฟลเดอร์ `tests` (ส่วน `tests/test_scalp_v56.py` ใช้ไฟล์เดิมได้)
4. ไม่ต้องเปลี่ยน `app.py` หรือ GitHub Secrets เดิม และ **อย่าลบ workflows เก่าที่ใช้งานอยู่**

## ทำหลัง Commit

1. GitHub → Actions → **Orbit Scalp Signal v5.8** → `Run workflow` → `mode=probe`; ตรวจแหล่งข้อมูลที่เข้าถึงได้ตามจริง
2. เลือก `mode=dry_run`; ตรวจว่ามีคำว่า `SIDEWAYS`, `RANGE_REVERSAL`, `READY/WATCH/WAIT` ตามภาวะตลาด (หากตลาดไม่ Sideways อาจไม่ปรากฏ เป็นปกติ)
3. เลือก `mode=live_alerts` เพียงหนึ่งครั้งเพื่อทดสอบการเปลี่ยนสถานะและ Telegram (ไม่มีสัญญาณใหม่จะขึ้น `Telegram sent=0`)
4. รอ Scheduled run: GitHub กำหนดรอบทุก 5 นาที **แบบ best-effort** เริ่มที่นาที `03,08,13,...` (UTC/ไทยนาทีตรงกัน) อาจล่าช้าหรือบางรอบไม่รัน
5. เปิด Streamlit → Scalp → ทดสอบ Binance TH และ Bitget แยกกัน ดู `Market Regime`/`Strategy`

## ข้อจำกัดที่ต้องเข้าใจ

- Trend READY ต้องผ่านแนวโน้ม, Breakout, แท่งปิด 1m, ทุน/ความเสี่ยง/ค่าธรรมเนียม
- Range READY ต้องผ่าน ADX 5m ต่ำ, ช่วงแกว่งเหมาะสม, ราคาแตะขอบกรอบ, 1m กลับตัวพร้อม Volume/Flow ที่ตรวจยืนยันได้, Stop/TP ในกรอบ, Net R:R และกฎตลาดจริง
- Spot ไม่สร้าง Short; Futures Binance Global ที่ตอบ `HTTP 451` จะถูกปิด ไม่ทดแทนด้วยราคาจากอีกตลาด; Bitget ใช้ราคา Bitget เท่านั้น
- ข้อมูล Buy/Sell fills ของ Bitget ไม่ใช่ Taker Flow ที่ exchange รับรอง; หากข้อมูลคลุมแท่งไม่ครบจะไม่ขึ้น READY
- GitHub Actions ไม่ใช่ระบบ streaming วินาทีต่อวินาที จึงอาจพลาดโอกาส Scalp ระหว่างรอบ และการขึ้น READY ไม่ใช่คำรับรองความแม่นยำหรือกำไร
- **ยังไม่มี Walk-forward PnL/Win-rate ที่พิสูจน์แล้วสำหรับ Range Strategy** ควรทดลอง Paper Trade และบันทึกผลจริงก่อนใช้เงิน

## ถ้าไม่มี Scheduled หลังอัปโหลด

ตรวจว่า workflow อยู่บน Default Branch `main`, เปิดใช้งานอยู่, มี `schedule`, และไม่มีปัญหา GitHub Actions ระดับ Repository. การเปลี่ยน Cron ในไฟล์รุ่นนี้ช่วยลงทะเบียนตารางใหม่ แต่ **ไม่รับประกัน** ว่า GitHub จะเริ่มรันตรงเวลา. อย่าเข้าใจว่า Manual run ที่ผ่านคือ Scheduler ผ่าน

## ชุดทดสอบ

คำสั่ง `python -m unittest discover -s tests -q` ครอบคลุมทั้งรุ่นก่อนและทดสอบ Sideways ใหม่ (ข้อมูลตลาดจำลอง ไม่ใช่สถิติผลตอบแทน) และ `python -m scalp_runner --validate-config` ใช้ตรวจ config ก่อน deploy.
