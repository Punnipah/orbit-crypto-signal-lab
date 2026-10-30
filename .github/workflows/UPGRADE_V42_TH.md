# คู่มืออัปเกรด Orbit v4.1 → v4.2 (ไม่ต้องตั้ง Telegram ใหม่)

สำหรับผู้ที่ **GitHub Actions ส่ง Test Telegram ได้แล้ว** และใน Logs เห็น `Frozen links 1/3` หรือ `3/3` ตามจำนวนแผนที่ล็อก

## 1. สำรองแผนก่อน

- คัดลอก Secret `ORBIT_WATCH_LINKS` ต้นฉบับที่เก็บส่วนตัวไว้ (GitHub ไม่แสดงค่า Secret เก่าที่บันทึกไปแล้ว) **ไม่ต้องเปลี่ยน Secret นี้** สำหรับการอัปเกรด
- เก็บ Bookmark URL `?watch=` ของ PEPE/BTC/DOGE; หากแผนหมดอายุ ต้องล็อกใหม่และแก้ Secret ด้วยตนเองตามปกติ
- **ไม่ลบ Branch `orbit-alert-state`** เพราะบันทึกสถานะกันแจ้งซ้ำของ v4.1 ไว้แล้ว

## 2. อัปโหลด 5 ไฟล์ที่ต้องใช้จริง

เปิด GitHub Repository เดิม → **Code → Add file → Upload files** → ลากไฟล์จาก ZIP ที่ *แตกแล้ว* ไปยัง root (ชั้นเดียวกับ `app.py` เดิม):

| ไฟล์ | บทบาท |
|---|---|
| `rally_watch.py` | **ไฟล์ใหม่**: กฎตรวจราคาเหนือ Frozen Zone จากแท่งปิด + Volume + ATR ก่อนล็อก |
| `monitor_engine.py` | เชื่อมกฎใหม่กับ MTF/Futures และสถานะของแต่ละเหรียญ |
| `monitor_alerts.py` | ข้อความ Telegram ใหม่และกันแจ้งซ้ำต่อ Frozen Plan |
| `alert_monitor.py` | แสดง `rally=...` ใน GitHub Actions Log |
| `app.py` | หน้าเว็บแสดงคำเตือนราคาออกห่างแผนเดิม |

เลือก **Commit changes** แล้วรอ Streamlit redeploy. **ไม่ต้องแก้** `.github/workflows/orbit-telegram-monitor.yml`, `monitor_delivery.py`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` หรือ `ORBIT_WATCH_LINKS` ถ้าปัจจุบันใช้งานอยู่แล้ว.

**`monitor_config.json` เป็นไฟล์ทางเลือก:** ไม่จำเป็นต้องทับไฟล์เดิม เพราะโค้ด v4.2 มีเกณฑ์ Rally เริ่มต้นในตัวแล้ว. ถ้าพรรณเคยปรับทุน/ค่าธรรมเนียม/เกณฑ์ความเสี่ยงใน GitHub ให้ **เก็บ config เดิมไว้** และเพิ่มเฉพาะ 5 ช่อง Rally ของตัวอย่างด้านล่างด้วยตนเองเมื่ออยากปรับค่าตั้งต้น.

**เพิ่มเติม (เอกสาร/ทดสอบ):** อัปโหลด `README.md`, `V42_RELEASE_NOTES_TH.md`, `UPGRADE_V42_TH.md`, `tests/test_rally_v42.py` เพื่อให้ repo เก็บคำอธิบายและการทดสอบรุ่นเดียวกัน. หาก Upload ผ่าน GitHub Web โฟลเดอร์ `tests` อาจต้องสร้างพาธ `tests/test_rally_v42.py` ด้วย **Add file → Create new file**.

## 3. ทดสอบหลังอัปเกรด

1. GitHub → **Actions → Orbit Telegram Signal Monitor → Run workflow**
2. **อย่าติ๊ก** `send_test` (คือ `false`) → Run workflow
3. เปิด job `monitor` → ขั้นตอน **Scan PEPE BTC DOGE and notify changes**
4. Log ควรเริ่ม `Orbit v4.2 scanning PEPEUSDT, BTCUSDT, DOGEUSDT ...`
5. ถ้าคุณมีแผน PEPE ล็อกอยู่ Log ควรขึ้นแนวนี้:

   `PEPEUSDT | mode=FROZEN | status=WAIT_ZONE | rally=NONE | futures=OK ...`

6. `rally=NONE` คือยังไม่มีหลักฐานราคาหนีโซน **ไม่ใช่ข้อผิดพลาด**. บางช่วงขึ้น `BREAKOUT_WATCH`, `MISSED_ENTRY` หรือ `NEW_SETUP_CANDIDATE` ได้เมื่อกฎผ่านจริง
7. ในหน้า Actions หากรายการใหม่มาจาก **Schedule** (ไม่ใช่ Manually run) พร้อม ✓ คือ GitHub เริ่มรันตามนัด; ตารางเวลา UTC นาที :02/:17/:32/:47 (เวลาไทยนาทีเดียวกัน) อาจมีดีเลย์หรือข้ามรอบตามภาระระบบ

## 4. ความหมายการแจ้งเตือนเพิ่มเติม

| Telegram / Log | ความหมาย | ทำอะไรต่อ |
|---|---|---|
| `BREAKOUT_WATCH` | ราคาเหนือ Frozen Zone และแท่ง 15m + Volume ผ่าน | เฝ้าดู ไม่ไล่ซื้อ |
| `MISSED_ENTRY` | ราคาวิ่งหนีโซนเกินเกณฑ์ความเสี่ยง | ไม่ย้ายราคาเดิมขึ้น; รอวิเคราะห์ใหม่ |
| `NEW_SETUP_CANDIDATE` | MTF สด READY และมีโซนใหม่ที่ผ่านตัวกรอง | เปิดเว็บไปตรวจใหม่; ถ้าพอใจจึงล็อกแผนเอง |
| `NONE` | ไม่มีเหตุใหม่ / หลักฐานไม่ครบ / แผนยังรอ | รอรอบถัดไป |

การที่ `status=WAIT_ZONE` พร้อม `rally=BREAKOUT_WATCH` **ไม่ขัดกัน**: สถานะแรกหมายถึง *แผนซื้อที่ล็อกยังไม่เข้า*, สถานะที่สองหมายถึง *ราคาเริ่มวิ่งหนีแผน*. ไม่ว่าจะมี Rally Alert หรือไม่ Entry/SL/TP ของ Frozen Plan **ยังคงเดิม**.

## 5. ปรับเกณฑ์ได้ (ถ้าต้องการ)

เปิด `monitor_config.json` ใน GitHub และแก้ค่าอย่างมีเหตุผล:

```json
"rally_watch_above_zone_pct": 3.0,
"rally_missed_above_zone_pct": 8.0,
"rally_confirmation_bars": 2,
"rally_min_volume_ratio": 0.8,
"rally_candidate_max_above_new_zone_pct": 1.0
```

- เปอร์เซ็นต์ 3/8 เป็น **ขั้นต่ำ**: ระบบใช้ค่าที่สูงกว่าเมื่อ 15m ATR *ก่อนล็อกแผน* ชี้ว่าความผันผวนเดิมสูง (`1.5× ATR` สำหรับ Breakout Watch; `3× ATR` สำหรับ Missed Entry)
- ต้องมีแท่ง 15m ปิดอย่างน้อย 2 แท่งเหนือเกณฑ์, แท่งล่าสุดยังสด, ไม่มีช่องว่าง, Volume ≥0.8× ค่าเฉลี่ยย้อนหลังที่ไม่ใช้ข้อมูลอนาคต, ราคาสดคงอยู่เหนือเกณฑ์
- เกณฑ์ Confirm ปรับได้ 2–4 แท่ง; ความเข้มงวดมากขึ้นลดแจ้งเตือน แต่จะช้าขึ้น
- **ไม่รับประกันว่า Telegram จะส่งทันก่อนราคาขยับ**; scheduled GitHub Actions best-effort, ค่าธรรมเนียมและ slippage จริงอาจสูงกว่าโมเดล

## 6. ฟีเจอร์เก่าที่ยังอยู่

- MTF 15m / 1h / 4h / 1d, Futures Public, Spot Book/Trades, BTC Regime, Bybit เสริม
- Frozen Watch + Entry/SL/TP + `READY_NOW`, `INVALIDATED`, `PASSED`, `EXPIRED`
- CoinGlass Manual (`monitor_coinglass_manual.json`) **ไม่ดึงเอง ไม่ปลอมข้อมูล**
- Backtest / Walk-forward เดิม และ Paper Journal (ยังไม่ใช่ผลทดสอบกฎรวมทั้งหมด)
- ส่งแจ้งเตือนเฉพาะเหตุสำคัญ ไม่ส่งทุก 15 นาที และไม่เปิดออเดอร์โดยอัตโนมัติ

> กฎ Rally Escape เป็น heuristic ใหม่ที่ยังไม่มีการพิสูจน์กำไรจาก Walk-forward แบบครบชุด. ไม่ใช่สัญญาณเข้าซื้อ ควรทดสอบบนกระดาษก่อนใช้เงินจริง.
