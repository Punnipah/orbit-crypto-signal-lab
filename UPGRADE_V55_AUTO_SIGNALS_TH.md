# Orbit v5.5 — Auto BUY / LONG / SHORT โดยไม่ต้อง Save แผน

## สิ่งที่เปลี่ยน

- **Spot LIVE MTF:** ตรวจ PEPEUSDT, BTCUSDT, DOGEUSDT อัตโนมัติทุกครั้งที่ GitHub Actions ทำงาน โดยไม่ต้องสร้าง Entry Zone ที่ล็อกไว้หรือใส่ `ORBIT_WATCH_LINKS`
- ถ้ามีลิงก์ `ORBIT_WATCH_LINKS` เดิม ระบบจะอ่าน **ทั้ง** สัญญาณ MTF สด **และ** แผนล็อกเก่าในรอบเดียวกัน; สถานะของแผนเก่า (เช่น `INVALIDATED`) ไม่บังสัญญาณสด (`MTF_READY`)
- ข้อมูลราคา/แท่งเทียนสำหรับ Live + Frozen ของเหรียญเดียวกันจะดึงและประมวลผลเพียงหนึ่งครั้งต่อรอบ
- แยกประวัติ Telegram ของสองโหมด ไม่แจ้ง READY ซ้ำทุก 15 นาที และทิ้ง READY ที่ค้างส่งเมื่อเงื่อนไขไม่ผ่านแล้ว
- แผนล็อกที่มีปัญหาไม่ทำให้สัญญาณสดหยุด และลิงก์ Save ที่ผิดรูปแบบจะถูกข้าม ไม่หยุดสแกนสด
- แท็บ Telegram ในหน้า Lab อธิบายชัดว่า Save เป็นทางเลือก ไม่ใช่เงื่อนไขของ Auto Scan
- **Futures LONG / SHORT** ยังใช้ workflow แยกที่ติดตั้งแล้ว; ไม่ต้องสร้างแผนล็อก โดย Binance Futures ให้ READY ได้เฉพาะเมื่อข้อมูลยืนยันครบ ส่วน fallback Bybit/Kraken ที่ขาด historical taker flow เป็น `WATCH ONLY` และ **ไม่แสดง READY**

## ติดตั้งจากมือถือ / GitHub

1. เปิด Repository `Punnipah/orbit-crypto-signal-lab` → แท็บ **Code**
2. เลือก **Add file → Upload files**
3. อัปโหลด **4 ไฟล์ `.py` ลง root ของ Repository** (โฟลเดอร์เดียวกับ `app.py` เดิม):
   - `app.py`
   - `alert_monitor.py`
   - `monitor_engine.py`
   - `monitor_alerts.py`
4. เลือก **Commit changes** เพื่อแทนไฟล์เดิม 4 ไฟล์ ไม่ต้องลบหรือแก้ Workflow/Secrets
5. เปิด **Actions → Orbit Telegram Signal Monitor → Run workflow** โดยปล่อย `Send test` เป็น **false** แล้วกด **Run workflow**
6. เปิด log `Scan PEPE BTC DOGE and notify changes` ต้องเห็น `mode=LIVE_MTF` สำหรับทุกคู่; ถ้ายังมี Save เดิมจะเห็น `mode=FROZEN` เพิ่มสำหรับคู่นั้นด้วย
7. ตรวจว่า Workflow สีเขียว; ถ้ายังเป็น `MTF_WAIT` แปลว่าเงื่อนไขซื้อไม่ผ่าน **ไม่ใช่บอทเสีย** และ Telegram จะไม่ส่งข้อความ BUY ปลอม

### Telegram จะเตือนอะไร

- `MTF_READY` = Spot BUY จากแผน MTF สด (ไม่จำเป็นต้องล็อกแผน)
- `READY_NOW` = Trigger ของแผนล็อกเดิม (ถ้ามี)
- `INVALIDATED`, `PASSED`, `EXPIRED` = ปิด/ยกเลิกแผนล็อกเดิม
- Futures `WATCH_LONG` / `WATCH_SHORT` = **เฝ้ารอ ไม่ใช่สัญญาณเข้า**
- Futures `READY_LONG` / `READY_SHORT` = เฉพาะเมื่อมีข้อมูลตลาดและยืนยันตามกฎครบจริง

**สำคัญ:** `ORBIT_WATCH_LINKS` เดิมไม่ต้องคัดลอกใหม่ หากไม่ต้องการแจ้งเตือนแผนล็อกอีก สามารถเอา Secret นี้ออกได้ภายหลังโดยไม่กระทบ LIVE MTF. ห้ามลบ `TELEGRAM_BOT_TOKEN` หรือ `TELEGRAM_CHAT_ID`.

## ความถี่และข้อจำกัด

- Spot GitHub Actions: นาที **:02, :17, :32, :47** ของทุกชั่วโมง (UTC และไทยมีนาทีตรงกัน)
- Futures GitHub Actions: นาที **:07, :22, :37, :52** ของทุกชั่วโมง
- ทั้งคู่ทำงานได้ทั้งกลางวัน/กลางคืนโดยไม่ต้องเปิด Streamlit แต่ GitHub Actions เป็นงานที่รันตามรอบ **ไม่ใช่ Real-time 24/7 ที่รับประกันความตรงเวลา**; ระบบอาจถูกหน่วงหรือข้ามบางรอบ
- ติดตามเพียง 3 คู่ที่ระบุใน Config ตอนนี้ ไม่ได้สแกนเหรียญทุกตัวในกระดานอัตโนมัติ
- สัญญาณทั้งหมดเป็นผลคัดกรองเชิงทดลอง **ไม่มีการส่งคำสั่งซื้อขาย ไม่มีคำรับประกันกำไร**; ต้องตรวจราคา Bid/Ask, Funding และความเสี่ยงเองก่อนตัดสินใจ
- เมื่อ Binance Futures HTTP 451 / Bybit HTTP 403 ยังถูกบล็อกจาก GitHub และ Kraken มีข้อมูลไม่พอ ระบบ Futures จะตรวจเป็น WATCH เท่านั้น—ต้องแก้แหล่งข้อมูลจริงในรุ่นถัดไปจึงจะส่ง READY ได้อย่างน่าเชื่อถือ

## ทดสอบไฟล์ก่อนอัปโหลด

รันจากโฟลเดอร์โครงการ:

```bash
python -m unittest discover -s tests -q
python -m alert_monitor --validate-config
python -m futures_daytrade_runner --validate-config
```

การทดสอบแบบ `--dry-run` จะติดต่อ Public API จริง แต่ไม่ส่ง Telegram และไม่บันทึกสถานะ:

```bash
python -m alert_monitor --dry-run
python -m futures_daytrade_runner --dry-run
```
