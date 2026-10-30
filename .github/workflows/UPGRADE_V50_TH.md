# Orbit Crypto Signal Lab v5.0 Ultimate — คู่มืออัปเดตแบบไม่ทำ Spot เดิมเสีย

## ภาพรวม

v5.0 รวม v4.2 Rally, v4.3 Mobile/Futures, Futures symbol resolution และ Paper Tracker. อัปเดตได้จาก v4.1 โดยไม่ต้องลง v4.2 และ v4.3 แยกทีละรอบ. เป็นระบบ **อ่านข้อมูลอย่างเดียว** ไม่มี API Key สำหรับส่งคำสั่งเทรดและไม่มี Auto Trading.

> อย่าใช้สัญญาณ Futures ด้วยเงินจริงโดยอ้างว่า Backtest ผ่านแล้ว: v5.0 ยังไม่มีหลักฐาน Full Futures Walk-forward/Paper Forward จำนวนมาก. หน้า Lab มี Historical **Technical Proxy** เท่านั้น.

## ชุดไฟล์ที่ต้องวางใน GitHub

เปิด Repository `Punnipah/orbit-crypto-signal-lab` → Code → Add file → Upload files และเลือกไฟล์ที่แตกจาก ZIP แล้ว. ใช้โฟลเดอร์ให้ตรง path จาก ZIP, ห้ามอัปโหลด ZIP เปล่า ๆ แล้วหวังว่า GitHub จะเปิดใช้โค้ดใน ZIP.

| กลุ่ม | ไฟล์ |
|---|---|
| UI/App | `app.py`, `mobile_ui.py`, `mobile_logic.py`, `futures_symbols.py` |
| Futures | `futures_daytrade.py`, `futures_daytrade_runner.py`, `futures_paper.py`, `futures_research.py` |
| Spot Rally v4.2 | `rally_watch.py`, `monitor_engine.py`, `monitor_alerts.py`, `alert_monitor.py` |
| Config Futures | `futures_daytrade_config.json` — **ถ้าเคยตั้งทุนและความเสี่ยงไว้ ให้เก็บของเดิม** |
| Theme | `.streamlit/config.toml` |
| New Workflow | `.github/workflows/orbit-futures-daytrade.yml` |

ถ้าอัปเดตจาก v4.3 ที่ใช้งานแล้ว ส่วนใหญ่ใช้เฉพาะ UI/App, Futures และไฟล์ใหม่ทั้งสาม; ไม่ต้องเปลี่ยน Spot secrets.

**สำคัญ:** ไม่จำเป็นต้องลบหรือเขียนทับ `.github/workflows/orbit-telegram-monitor.yml`, `monitor_config.json`, `ORBIT_WATCH_LINKS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` หรือ GitHub state branches เดิม.

บน iPhone ถ้า GitHub Mobile ไม่มี Upload/Settings ให้เปิด `github.com` ผ่าน Safari → Request Desktop Website. สำหรับไฟล์ใน `.github/workflows` และ `.streamlit` อาจต้องกด Add file → Create new file และระบุ path ด้วยตัวเอง. ห้ามใส่ Telegram Token ลงใน Code หรือ Config ของ Repository.

## ตรวจสอบหลังอัปเดต

1. เปิด Streamlit App แล้วกด Reload. ตรวจหัวข้อ **ULTIMATE SIGNAL · V5.0**, มีปุ่ม Spot/Futures/Alerts/Lab.
2. เลือก Futures → `PEPE`. ระบบต้องแสดงชื่อสัญญาจริง `1000PEPEUSDT` และอธิบายตัวคูณ 1,000 ชัดเจน หาก Public API ใช้งานได้ในภูมิภาคนั้น.
3. GitHub → Actions → `Orbit Futures Day Trade (Long & Short)` → Run workflow → `send_test=false` → Run. ต้องขึ้นสีเขียวและอ่าน log ได้ว่า `FUTURES run complete`.
4. เมื่อส่ง Telegram จาก Futures ระบบจะเขียน branch `orbit-futures-state` ไฟล์ `.orbit-futures/daytrade-alerts.json` schema 2 โดยโยกสถานะ schema 1 เดิมให้อัตโนมัติ ไม่ลบ sent alert IDs.
5. ไป Alerts: ถ้า Repository public จะอ่านข้อมูลจาก branch อัตโนมัติเมื่อเข้าถึงได้. ถ้า private ให้ดาวน์โหลดไฟล์ State JSON (ไม่ใช่ Secret) มาอัปโหลดในหน้า Alerts.
6. ตอนเริ่มต้น **ไม่มีผล Paper ย้อนหลัง** — จะเก็บเฉพาะสัญญาณ READY ใหม่ตั้งแต่เปิดใช้ v5 และแท่งที่ปิดหลังเวลานั้น ไม่ปั้นสถิติย้อนหลังจาก Telegram เดิม.

## ความหมายสถานะ Futures / Paper

| ข้อความ | ความหมาย |
|---|---|
| `WATCH_LONG/SHORT` | รอ Retest ห้ามไล่ราคา |
| `READY_LONG/SHORT` | ผ่านกฎ setup + ราคาอยู่ใน zone; ยังไม่ใช่ fill |
| `PAPER_ENTRY` | แท่งหลัง READY แตะโซนตามกฎจำลอง ไม่ใช่คำสั่งซื้อจริง |
| `TP1`, `TP2`, `STOP` | ประเมินจากราคาสูงต่ำของแท่ง Futures ที่ปิดแล้ว; แท่งเดียวทั้ง TP/SL นับ SL ก่อน |
| `NO_FILL_EXPIRED` | แผนหมดอายุก่อนเข้าโซนบนแท่งที่ตรวจครบ ไม่ถูกนับเป็นดีล |
| `TIME_EXIT` | ถือสถานะจำลองนานเกินเวลาและปิดตามราคาปิดแบบจำลอง |
| `DOWN/DEGRADED` | Futures Market Data ไม่ครบ ระบบไม่แทนค่าขึ้นมาเอง |

**ตัวเลขผลตอบแทน:** ใช้ R แบบสมมติและต้นทุนคงที่ ไม่รวม Funding จริง, Liquidation จริง, Spread ขณะ fill และปัจจัยคำสั่งตลาด. หากดูผล Paper ที่มีไม่ถึง 100 ดีลจะมีป้ายเตือนว่าไม่พอประเมินความแม่นยำ. ไม่สามารถสรุปกำไรจริงของพรรณได้.

## การตรวจย้อนหลังใน Lab

ไป Lab → `Futures Technical Research` → เลือก 30/45/60 วัน → `วิเคราะห์ข้อมูลย้อนหลัง`. ระบบใช้เฉพาะแท่ง 15m/1h/4h ที่ปิดจริง ณ เวลาย้อนหลัง และตามด้วย Paper Fill จำลองบนแท่งถัดไป. บันทึกผลแบ่งครึ่งเวลาเป็น early/holdout โดยไม่ใช้ครึ่งหลังปรับเกณฑ์.

ผลนี้ **ไม่ใช่การพิสูจน์ Full Futures Signal** เพราะ historical mark/funding, liquidity/order book และ execution ที่เกิดจริงไม่มีในชุด replay. ถ้าข้อมูล API ขาดหรือประวัติไม่พอ ต้องแสดง error/ไม่สรุปผล.

## ข้อจำกัดที่ต้องทราบก่อนเรียก Production

- GitHub Actions Cron 15 นาทีอาจรันช้าหรือข้ามรอบ จึงไม่เหมาะกับ Scalping ระดับวินาที/1 นาที และไม่ใช่ Stop Loss Server ที่บังคับขายให้.
- ยังไม่ได้ทดสอบ GitHub Actions/Telegram จริงในบัญชีของผู้ใช้งานจากเครื่องพัฒนา; ให้ดู log และทดลองส่งเองก่อน.
- Streamlit บนมือถือได้รับการออกแบบให้เหมาะ แต่ต้อง QA บน iPhone/Safari จริงหลัง Deploy.
- Binance Futures API อาจจำกัดการเข้าถึงตามภูมิภาคหรือเวลาที่ใช้งาน. ไม่ควรหลบข้อจำกัดเหล่านี้.
- Strategy ต้องทดสอบ Forward Paper และ Walk-forward ครบแหล่งข้อมูล พร้อม stress test funding/fees/slippage และ margin/liquidation ก่อนตัดสินใจว่ามีความได้เปรียบเชิงสถิติ.

## ทดสอบโค้ดก่อนอัปโหลด (ถ้ามี Python)

```bash
python -m unittest discover -s tests -q
python -m futures_daytrade_runner --validate-config
python -m alert_monitor --validate-config
```

ไฟล์ `Orbit_v5_Ultimate_Mobile_Preview.html` เป็น **ตัวอย่างหน้าจอที่ใช้ตัวเลขสมมติ** ไม่ใช่แอป Streamlit ที่ดึงราคาสด.
