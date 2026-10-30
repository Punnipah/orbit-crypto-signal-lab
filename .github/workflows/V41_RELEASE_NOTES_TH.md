# Orbit Crypto Signal Lab v4.1 — Telegram Scheduled Signal Monitor

วันที่: 29 ตุลาคม 2026

## สิ่งที่เพิ่ม

- ติดตามเหรียญเริ่มต้น **PEPEUSDT, BTCUSDT, DOGEUSDT** และกำหนดเพิ่ม/ลดได้ใน `monitor_config.json` (สูงสุด 10 คู่ USDT)
- GitHub Actions Workflow `.github/workflows/orbit-telegram-monitor.yml` ตรวจทุก 15 นาที โดยเลื่อนเป็น :02/:17/:32/:47 UTC เพื่อเว้นช่วงหลังแท่งปิด
- ตัวประเมินเบื้องหลังไม่ต้องใช้ Streamlit Runtime, มี dependencies แค่ Numpy/Pandas ใน `monitor_requirements.txt`
- ใช้กฎเดิมจาก `build_timeframe_report`, `combine_timeframes`, `microstructure_checks`, `btc_context_checks`, `risk_audit` และ `evaluate_watch` ไม่สร้างกฎซื้อแยกที่ผ่อนปรนโดยพลการ
- รับลิงก์ Frozen Watch ผ่าน GitHub Secret `ORBIT_WATCH_LINKS` (บรรทัด `SYMBOL=URL`) และไม่ส่ง token นี้ไปยัง State branch หรือ Telegram
- หากไม่มี Frozen Link จะตรวจและแจ้ง `MTF_READY` เท่านั้น โดยระบุชัดว่าเป็น **สัญญาณ MTF สด ไม่ใช่แผนล็อก**
- CoinGlass Manual file `monitor_coinglass_manual.json` ไม่เชื่อม API; การมีข้อมูลแล้วเก่า/ผิดเกณฑ์ veto ผลรวมตามกฎเดิม; ไม่เติมค่าที่ขาด
- แยก Telegram Bot Token และ Chat ID ไว้ใน GitHub Repository Secrets พร้อม `workflow_dispatch` ปุ่มทดสอบการส่งหนึ่งข้อความ
- เก็บ last_status, seen event IDs และ pending outbox ใน Branch `orbit-alert-state` เพื่อกันซ้ำและส่งใหม่หาก Telegram ไม่พร้อม; **ทิ้ง pending READY ที่เก่าเมื่อสถานะไม่เป็น READY แล้ว**
- แจ้งเมื่อ READY_NOW/MTF_READY/INVALIDATED/PASSED/EXPIRED/NO_LONGER_READY/CoinGlass invalid/mandatory data unavailable ต่อเนื่อง ไม่ส่ง WAIT ทุกครั้ง
- เพิ่มแท็บ **📡 Telegram แจ้งเตือน** ในเว็บสำหรับ Copy Frozen Link และ CoinGlass JSON ไป GitHub ได้ง่ายขึ้น

## ข้อจำกัดที่ยังมีอยู่

- **ยังไม่ได้เปิดระบบจริงในบัญชี GitHub/Telegram ของผู้ใช้** เพราะต้องให้ผู้ใช้สร้าง Bot และเพิ่ม Secrets ใน GitHub ของตัวเอง
- GitHub Actions Cron ไม่ใช่ SLA; อาจเริ่มช้าหรือถูกข้ามรอบ, และ Public Repo ที่ไม่มี activity นานอาจถูกปิด Scheduled Workflows
- Public API อาจถูกจำกัดบน GitHub-hosted runners โดยเฉพาะ Binance Futures; กรณีข้อมูลหลักไม่ครบจะ WAIT/DATA_UNAVAILABLE และไม่สร้างสัญญาณ BUY
- ข้อมูล Futures และ Spot อาจมาจากคนละ Exchange; คงหลักการระบุแหล่งชัดเจน ไม่รวมข้อมูล OI ข้ามตลาด
- การแจ้งเตือนทุก 15 นาทีไม่ได้แปลว่าแจ้งทันในวินาทีที่ราคาแตะโซน; Trigger READY_NOW อาจหมดความสดระหว่างรอบได้
- **Frozen Watch ที่หมดอายุไม่ต่ออายุอัตโนมัติ**; ต้องล็อกใหม่ในเว็บและอัปเดต Secret `ORBIT_WATCH_LINKS`
- ภายหลังส่ง Telegram สำเร็จแต่การบันทึก ACK ลง GitHub ล้มเหลว อาจเกิดข้อความซ้ำในรอบถัดไปได้ (ไม่สามารถรับประกัน exactly-once ระหว่างสองระบบได้)
- การ์ด CoinGlass เว็บเซสชันไม่ sync เข้าสู่ runner อัตโนมัติ ต้อง Copy JSON เอง; ตัวเลข manual ต้องมี timezone/ยังสดตามกฎ
- เกณฑ์ BUY/READY_NOW เป็น **heuristic ทดลอง** และ **ยังไม่ได้ผ่าน Full Out-of-sample Backtest/Walk-forward ที่รวม Futures, Order Book, CoinGlass และการแจ้งเตือนนี้**; Win Rate ไม่สามารถระบุจากจำนวนการทดสอบซอฟต์แวร์

## การทดสอบ

- Python Syntax/Unit: ตรวจการเข้ารหัส Frozen Link, Symbol USDT Validation, MTF fail-closed, Futures/OrderBook missing, Missing Timeframe, Telegram JSON POST, GitHub State Branch, Dedup, Outbox, Invalidated, Stale/expired data
- Streamlit AppTest: เปิดหน้าเว็บจาก URL มีแผนล็อก, แอปยังแสดง MTF/Futures/CoinGlass เมื่อแหล่งเสริมหายหรือพร้อม
- GitHub API/Telegram จริง: ต้องทดสอบผ่าน `Run workflow → Send test` หลังตั้งค่า Secrets; ไม่มีการส่งทดสอบไป Telegram ของผู้ใช้จากเครื่องสร้างไฟล์

อ่าน `MONITOR_TELEGRAM_SETUP_TH.md` สำหรับคู่มือพร้อมใช้จากมือถือและ GitHub
