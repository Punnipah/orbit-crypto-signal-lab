# Orbit Crypto Signal Lab v5.2 — Futures Binance → Bybit WATCH Backup

## ทำอะไรเพิ่ม

- **Binance USDⓈ-M Futures เป็นแหล่งหลัก** และบอก HTTP Error/Network Error ให้ชัดขึ้น
- เมื่อ Binance ใช้ไม่ได้ ระบบจะลอง **Bybit V5 Linear Perpetual** สำหรับคู่ที่มีสัญญาเปิดซื้อขายจริง
- ใช้ราคา, Mark, Funding และแท่งเทียน 15m/1h/4h ของ **ตลาดเดียวกันทั้งหมด** ไม่ใช้ข้อมูล Binance ปนกับ Bybit
- ปิดแท่งเทียนที่ยังไม่ครบเวลา ตรวจช่วงเทียนขาด ตรวจความสดของเซิร์ฟเวอร์ราคา
- แสดงป้าย `BYBIT USDT PERPETUAL · WATCH ONLY` และเหตุผลบนหน้าจอ
- **Bybit สำรองออก WATCH เท่านั้น ห้าม READY** เพราะ Kline API มาตรฐานไม่มี Historical Taker Buy ให้ยืนยันสูตรเดิม; ไม่บันทึกการเปิด Paper Trade ใหม่จาก Bybit
- แยก State Key Telegram ระหว่าง `BINANCE` และ `BYBIT` ป้องกันสถานะข้ามตลาด

## อัปโหลด GitHub `main`

แตก ZIP แล้วอัปโหลดไฟล์เหล่านี้ลงตำแหน่งเดิมใน Repository:

1. `futures_daytrade.py`
2. `futures_backup.py` (ไฟล์ใหม่)
3. `futures_daytrade_runner.py`
4. `mobile_ui.py`
5. `tests/test_futures_backup_v52.py` (ในโฟลเดอร์ `tests/`; ใช้สำหรับทดสอบ)

**ไม่ต้องอัปโหลด ZIP โดยตรง** ห้ามลบ `.github`, Config, Secret หรือ State branch เดิม

## ตรวจหลังอัปเดต

1. เปิด Streamlit และ Refresh หน้า ⚡ Futures หาก Binance ยังใช้ไม่ได้ และ Bybit พร้อม ต้องเห็นป้าย `BYBIT ... WATCH ONLY`
2. ถ้าทั้งคู่ถูกบล็อก ให้เปิด `รายละเอียด` แล้วส่งข้อความ Error มา (ระบบจะไม่แต่งสัญญาณ)
3. GitHub → Actions → `Orbit Futures Daytrade` → Run workflow; ดูว่า Job สำเร็จและมี State branch `orbit-futures-state`
4. หน้า 🔔 Alerts จะมีประวัติก็ต่อเมื่อ Futures Workflow เขียน State สำเร็จอย่างน้อยหนึ่งครั้ง (Spot Workflow เป็นคนละตัว)

## ข้อจำกัดสำคัญ

- Bybit backup เป็น **โหมดสังเกตการณ์** ไม่ใช่สัญญาณอนุมัติ Futures Entry
- ไม่ใช่บอทเทรดจริง ไม่มี API Key/คำสั่งเปิดออร์เดอร์ และไม่รับประกันผลตอบแทน
- ไม่สามารถยืนยันการเชื่อมต่อ API จากเครือข่าย Streamlit Cloud หรือ GitHub Actions ของผู้ใช้ได้จนกว่าจะอัปโหลดและรันจริง
- ผล Backtest/Research เดิมไม่ได้ถูกเปลี่ยนให้เป็น Bybit โดยอัตโนมัติ
