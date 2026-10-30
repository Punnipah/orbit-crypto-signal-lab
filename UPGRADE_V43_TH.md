# Orbit v4.3 — อัปเกรดจาก v4.1/v4.2 เป็น Mobile App UI + Futures Long/Short

## สิ่งที่ได้

1. **Spot**: หน้าใหม่แบบแอปมือถือ แสดงสถานะจริงจากกฎ Spot v4.2, Entry/SL/TP, Frozen Watch และ Rally Escape ในหน้าเดียว
2. **Futures**: หน้าใหม่แบบแอปมือถือ รองรับ Long/Short จาก Binance USD-M Futures public API แยกจากราคา Spot, พร้อม Stop/TP และกราฟ 15m
3. **Lab**: หน้าวิเคราะห์ MTF, ล็อกแผน, CoinGlass, Backtest/Walk-forward, Data Evidence, Telegram Setup เดิมยังครบ
4. **Telegram**: Workflow Spot เดิมทำต่อ; เพิ่ม Workflow Futures แบบแยกและใช้ Secrets ตัวเดิมได้

ไม่มีการซื้อขายจริง ไม่มีการใช้ Exchange API Key หรือส่งออร์เดอร์ ผู้ใช้ต้องตรวจราคาและความเสี่ยงเองเสมอ

## อัปโหลดบน GitHub (รวม v4.2 มาแล้ว)

เปิด Repository `Punnipah/orbit-crypto-signal-lab` แล้วแตกไฟล์ ZIP **ก่อน** อัปโหลด

**ไฟล์ root (10 ไฟล์):**

```
app.py
mobile_ui.py
mobile_logic.py
rally_watch.py
monitor_engine.py
monitor_alerts.py
alert_monitor.py
futures_daytrade.py
futures_daytrade_runner.py
futures_daytrade_config.json
```

เข้า `Code → Add file → Upload files` เลือกทั้ง 10 ไฟล์จาก ZIP (ไม่ใช่ ZIP ทั้งก้อน); กด Commit changes. ไฟล์ชื่อเดิมให้แทนที่บน main; ไฟล์ใหม่จะเพิ่มเข้ามา.

**ไฟล์ในโฟลเดอร์ (2 ไฟล์):**

```
.streamlit/config.toml
.github/workflows/orbit-futures-daytrade.yml
```

ต้องเก็บ path ตรงตามนี้: ถ้าอัปโหลดจากเว็บ GitHub แล้วไม่คงโฟลเดอร์ ให้เปิด/สร้างไฟล์ตาม path ด้วย `Add file → Create new file` และคัดลอกเนื้อหาเดิม. อย่าสร้างไฟล์ YAML ไว้ที่ root เพราะ GitHub Actions จะไม่เห็น.

**ห้ามทับ/แก้สิ่งเหล่านี้:**

- `monitor_config.json` ของ Spot ที่พรรณตั้งไว้
- `ORBIT_WATCH_LINKS` (Frozen plans เดิมยังอยู่ แต่แผนที่ INVALIDATED ต้องล็อกใหม่)
- `TELEGRAM_BOT_TOKEN` และ `TELEGRAM_CHAT_ID` GitHub Secrets
- `.github/workflows/orbit-telegram-monitor.yml` และ GitHub state branch เดิมของ Spot

เอกสาร `README.md` กับไฟล์ทดสอบใน ZIP เป็นไฟล์เสริม ไม่จำเป็นสำหรับการเปิดระบบ

## เปิดหน้าแอปมือถือ

เมื่อ Streamlit Cloud นำโค้ดจาก main ไป Deploy แล้ว ให้เปิดลิงก์เว็บเดิมได้เลย:

1. `🎯 Spot` — อ่านสถานะและ Entry/SL/TP แบบการ์ด ไม่มีคำอธิบายยาวหน้าแรก
2. `⚡ Futures` — อ่านสถานะ Long/Short, Entry/Stop/TP และกราฟจากตลาด Futures โดยตรง
3. `🔬 Lab` — รายละเอียดเชิงลึก, ล็อก Frozen Plan, CoinGlass, Backtest, รายงานและคู่มือ

การเลือกเหรียญใช้ปุ่ม BTC / PEPE / DOGE / ETH / SOL หรือ `🔎 อื่น ๆ` แล้วพิมพ์รหัส USDT เช่น XRP, BONK, Bitcoin; ตลาดที่ไม่มีสัญญาจะถูกระบุว่าไม่พร้อม ไม่สร้างสัญญาณปลอม

## เปิด Telegram Futures (ทำแยกเพิ่ม)

1. เข้า GitHub → Actions → `Orbit Futures Day Trade (Long & Short)`
2. กด `Run workflow` แล้วเลือก `send_test=true` **เฉพาะหากต้องการทดสอบช่องทาง Telegram**
3. ทดสอบการสแกนจริง ให้ `send_test=false` (ไม่ต้องติ๊ก)
4. อ่าน Log: `Orbit FUTURES Day Trade scanning ...` และ `... Futures | status=...`
5. GitHub ตั้ง Cron ตรวจตอนนาที :07, :22, :37, :52 ของทุกชั่วโมง UTC (นาทีตรงกันในไทย) หลังแท่ง 15m ปิด 7 นาที แต่ Scheduled Actions อาจดีเลย์หรือข้ามรอบได้
6. สถานะ `WATCH_LONG/SHORT` = *ห้ามเข้า ยังรอ Retest*; `READY_LONG/SHORT` = สัญญาณให้พิจารณาเท่านั้น; ไม่ส่งทุก 15 นาทีหากสถานะไม่เปลี่ยน

ข้อความ Futures มีหัว `Orbit FUTURES DAY TRADE` แยกจาก Spot และใช้ GitHub State Branch `orbit-futures-state` แยกกัน ไม่มีการลบสถานะ Spot

## ความเสี่ยงและข้อจำกัด

- ค่าเริ่มต้น Futures `capital_usdt=1000` เป็นเพียง **ทุนสมมติ**; ปรับได้ที่ `futures_daytrade_config.json` สำหรับ Telegram หรือในหน้า Futures สำหรับการจำลองเฉพาะหน้านั้น (ไม่ซิงก์ไป GitHub)
- การคำนวณ TP1/TP2 เป็นเป้าหมายคณิตศาสตร์ตาม R ไม่ได้รับรองว่าจะถึงแนวราคาเหล่านั้น
- ค่าธรรมเนียม/Slippage/Funding/Mark-Last spread/ความเสี่ยง Liquidation ทำให้กำไรจริงต่างจากตัวอย่างอย่างมาก
- **ยังไม่ได้พิสูจน์กลยุทธ์ Futures ด้วย Backtest, Walk-forward หรือ Paper Trading แบบนอกตัวอย่าง**; อย่าใช้สัญญาณเป็นคำสั่งเปิดสถานะอัตโนมัติ
- การสแกน 15 นาทีไม่ใช่แบบ Real-Time และอาจพลาดจังหวะราคาวิ่งเร็ว; ไม่ไล่ Entry ถ้าราคาออกนอกโซน
- หาก API ใดไม่พร้อม แสดง DATA_UNAVAILABLE ไม่ตีความว่า READY

## ตรวจสอบก่อนอัปโหลด

```
python -m futures_daytrade_runner --validate-config
python -m alert_monitor --validate-config
python -m unittest discover -s tests
```

การทดสอบ offline ไม่ได้ยืนยันว่า GitHub Actions/Telegram/เว็บ Streamlit ของบัญชีผู้ใช้ Deploy สำเร็จจนกว่าจะรันจริง
