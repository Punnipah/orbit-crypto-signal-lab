# Orbit Crypto Signal Lab v4.1 — Telegram 15m Monitor + Frozen Watch Plan + MTF

โปรแกรมวิเคราะห์สัญญาณคริปโตแบบอ่านข้อมูลอย่างเดียว ใช้เครื่องมือฟรี ไม่เชื่อมบัญชีซื้อขาย **ไม่ต้องใช้ API Key ของกระดานเทรด** และไม่มีคำสั่งส่งออเดอร์ (ระบบ Telegram ใช้ Bot Token ส่วนตัวใน GitHub Secrets)

## ใหม่ v4.1 — ระบบแจ้งเตือน Telegram โดยไม่ต้องเปิดหน้าเว็บค้างไว้

1. **GitHub Actions Schedule**: ประเมิน `PEPEUSDT`, `BTCUSDT`, `DOGEUSDT` ทุก 15 นาที (UTC นาที :02/:17/:32/:47; อาจรันช้าหรือข้ามรอบได้)
2. **ใช้กฎ MTF เดิม**: อ่านแท่งปิด 15m/1h/4h/1d และเช็ก Futures, Order Book/Aggressor Trades, BTC Regime, Taker Buy, ความเบี่ยงเบน Bybit เมื่อข้อมูลมี, R:R หลังค่าธรรมเนียม ไม่มี Futures/Spot/Book ที่จำเป็นแล้วไม่ส่ง BUY
3. **รองรับแผนที่ล็อกไว้**: นำลิงก์ `?watch=` ของแต่ละเหรียญไปเก็บใน GitHub Secret `ORBIT_WATCH_LINKS` เพื่อให้ตัวตรวจใช้ Entry Zone/SL/TP เดิม แม้ปิดเว็บ (ไม่ย้ายโซนอัตโนมัติเมื่อแผนหมดอายุ)
4. **ถ้ายังไม่มีแผนล็อก**: ตัวตรวจยังแจ้งสถานะ `MTF_READY` ของเหรียญนั้นได้ แต่ระบุชัดว่าเป็น MTF สด ไม่ใช่จุดซื้อจาก Frozen Watch
5. **แจ้งเฉพาะเหตุสำคัญ**: READY_NOW, MTF_READY, INVALIDATED, PASSED, EXPIRED, สัญญาณ READY หลุด และข้อมูลขาด/Manual CoinGlass หมดอายุ พร้อม Outbox และการกันข้อความซ้ำที่บันทึกแยก GitHub Branch `orbit-alert-state`
6. **Telegram Token/Chat ID อยู่ใน GitHub Secrets** เท่านั้น ไม่อยู่ใน Repository หรือไฟล์ ZIP; โหมดดูราคา/วิเคราะห์ยังใช้ฟรีเหมือนเดิม ไม่มีการเชื่อมบัญชี Exchange
7. **CoinGlass ยังเป็นข้อมูลกรอกมือ**: เว็บไม่ซิงก์ข้อมูลเซสชันไป GitHub โดยอัตโนมัติ; หากต้องการใส่ในตัวแจ้งเตือนให้คัดลอกค่าจริงไป `monitor_coinglass_manual.json` ซึ่งจะ veto เมื่อเก่า/ผิดเกณฑ์

**เริ่มต้น:** อ่าน **`MONITOR_TELEGRAM_SETUP_TH.md`** แล้วทำตาม 6 ขั้นตอน. การอัปโหลด ZIP อย่างเดียว **ยังไม่เปิด Telegram Monitor**; ต้องสร้าง Bot, Secrets และ GitHub Actions Workflow ก่อน. กฎ v4.1 รวมทุกแหล่งยัง **ไม่ได้ผ่าน Full Backtest/Walk-forward**, การแจ้งเตือนไม่ใช่คำสั่งซื้อ และอาจมาช้ากว่าจุดเข้า

## v4.0 ที่ยังคงอยู่ใน v4.1 — รอเข้าซื้อจากแผนเดิมให้เป็นระบบ

จุดเปลี่ยนที่ผู้ใช้ต้องการ: **แตะ Entry Zone ไม่ถือเป็นสัญญาณซื้อ** และ **เปิดหน้าเว็บใหม่แล้วโซนที่กำลังเฝ้ารอไม่ควรถูกแทนที่โดยแผนสด**

1. **🧷 Frozen Watch Plan**: ผู้ใช้เลือกเหรียญเพียงตัวเดียว กด "ล็อก Entry Zone ปัจจุบัน" เพื่อเก็บ Entry Low/High, SL, TP1/TP2, ต้นทุนจำลอง และเวลาหมดอายุเป็นข้อมูลที่ **ไม่เลื่อนตามราคาสด** (แยกจากแผน MTF สดที่ยังอัปเดตเสมอ)
2. **บันทึกผ่าน URL `?watch=`**: Bookmark/Copy Link จากแถบที่อยู่ไว้; เมื่อเปิดลิงก์นั้นบนมือถืออีกครั้ง ระบบดึงแผนเดิมกลับมาและพยายามเลือกเหรียญเดิมอัตโนมัติ ไม่ต้องใช้ฐานข้อมูลหรือบัญชีเสียเงิน **แต่ถ้าเข้าเว็บจากลิงก์หน้าหลักที่ไม่ติด `?watch=` จะไม่เห็นแผนที่ล็อกไว้**
3. **ตรวจย้อนหลังด้วยแท่ง 15m ที่ปิดจริง**: WAIT_ZONE → WAIT_RECLAIM → WAIT_BREAK → READY_NOW หรือ INVALIDATED / PASSED / EXPIRED. ระบบแยกจุดราคาแตะโซนออกจากการปิดแท่งฟื้นตัวและยืนยัน Break/Retest หลังจากนั้น
4. **ยกเลิกแผนทันทีเมื่อราคาแตะ Stop Loss หรือปิด 15m ต่ำกว่าขอบล่างโซนสองแท่งติด**; หากข้อมูลแท่งขาด, ราคาสดหาย, MTF/Futures ไม่ผ่าน, แผนหมดอายุ หรือราคาไล่ไปแล้ว จะแสดง WAIT/PASSED แทน READY
5. **ตรวจราคาปัจจุบันและ R:R อีกครั้ง**: READY_NOW ใช้ราคา Spot ล่าสุดซึ่งอยู่ใกล้โซนและต้องไม่เกินขีดจำกัดไล่ราคา; R:R สุทธิถึง TP2 ต้องผ่านเกณฑ์เดิมอีกครั้ง **ไม่อ้างว่าราคาเข้าโซนเดิมยังซื้อได้หลังตลาดวิ่งออกไปไกล**
6. **เฝ้าอัตโนมัติเมื่อเปิดเว็บอยู่**: Streamlit รีเฟรชผลทั้งแอปราวทุก 3 นาทีเมื่อ URL มีแผนล็อก ไม่ใช่การติดตามทุกวินาที; **เว็บเองไม่ส่ง Push เมื่อปิด** แต่ v4.1 เพิ่ม **GitHub Actions + Telegram ที่ต้องเปิดใช้งานแยกต่างหาก**
7. **เวลาหมดอายุ 12/24/48/72 ชั่วโมง**; ข้อมูลของแผนเป็น URL แบบเข้ารหัสเพื่อพกพา (ไม่ได้ปกปิดความลับ ไม่ใช่การเซ็นรับรอง) ไม่บันทึกบัญชีหรือข้อมูลส่วนตัว

**สำคัญ:** กฎ Trigger และวินัยรอหลังแตะโซนของ v4.0 **ยังไม่ได้ผ่าน Backtest/Walk-forward แบบเต็มกฎ** ไม่ควรแปล READY_NOW เป็นคำยืนยันว่าจะกำไรหรือเป็นคำสั่งซื้อ ต้องใช้เงินทดลอง/Paper Trade ก่อน ดูคู่มือ `WATCH_PLAN_GUIDE_TH.md` สำหรับวิธีใช้งานบนมือถือ.

## Orbit Professional v3.0 — หลักฐานตลาดที่ยังคงอยู่ใน v4.1

**เลือกคู่เหรียญครั้งเดียว** แล้วดูสัญญาณ 15m + 1h + 4h + 1d รวมหนึ่งผล พร้อม Entry Zone, Stop Loss, TP1, TP2, เวลาเฝ้ารอ และเหตุผลทุกข้อ. เปิดบน Streamlit Community Cloud ด้วยมือถือได้ ไม่ต้องส่งคำสั่งซื้อขายอัตโนมัติ

เพิ่มจาก v2.7:

1. **Spot CVD / Aggressor Evidence**: คำนวณ Delta จำนวนเหรียญจาก Binance taker-buy volume บน 20 แท่งที่ปิดแล้ว, เทียบแรงซื้อ 5 แท่งกับ 20 แท่ง, ไม่สมมติค่าที่ขาด
2. **Candle VWAP + Volume Profile POC (ประมาณเท่านั้น)**: คำนวณจากราคากลางแท่งเทียนถ่วงน้ำหนักปริมาณ; ไม่ปลอมเป็น Tick-level Footprint หรือราคาที่ซื้อขายทุกดีล
3. **Cross-exchange Evidence (Bybit ฟรี)**: ดึง Public Spot Order Book/Trades และ **แยก** USDT Linear Futures OI 24h/Funding โดยระบุขอบเขตตลาดและสถานะที่ขาด; ถ้า API ของ Bybit ไม่รองรับเหรียญหรือถูกจำกัดจะแสดง `MISSING`
4. **Macro Liquidity จาก DefiLlama Free API**: Stablecoin Circulation และ DeFi TVL ย้อนหลัง 7 วันเมื่อมีข้อมูลใหม่พอ; เป็นข้อมูลภาพรวม ไม่ใช่ Whale wallet/Exchange Netflow
5. **Net Reward-to-Risk Audit**: ประเมิน R:R ถึง TP1 และ TP2 จากขอบบน Entry Zone รวมค่าธรรมเนียม/Slippage แบบจำลอง โดย TP2 ต้องผ่านเกณฑ์ที่เลือก (เริ่ม 1.5R) ก่อนผลรวมมีสิทธิ์ READY
6. **Data Source Audit**: นับหลักฐานหลักและเสริมแยกกัน แสดงว่าแหล่งใดใหม่/ขาด/ไม่รองรับ; จำนวนแหล่งไม่ใช่อัตราชนะ
7. **Paper Journal นำกลับเข้าได้ + ตรวจเส้นทางราคาสมมติ**: ดาวน์โหลด CSV เก็บบนมือถือ/คอมฯ และนำเข้าใหม่ในเซสชันถัดไป; สำหรับ READY ที่บันทึกจะตรวจราคาเปิดแท่ง 1h ถัดไปในโซน แล้วตาม Stop/TP2 สูงสุด 48 แท่งโดยถือว่า Stop เกิดก่อนเมื่อชนพร้อมกัน — **ไม่ใช่การยืนยันว่าซื้อหรือขายจริง**
8. **ทดสอบด้วย Streamlit จริงแบบข้อมูลจำลองและกรณีแหล่งข้อมูลล้มเหลว** เพิ่มจาก Unit Tests เดิม (ไม่ใช่ผลชนะตลาด)

### ลำดับความน่าเชื่อถือของข้อมูล

| ชั้นหลักฐาน | การใช้งาน |
|---|---|
| **Mandatory / Veto** | ประวัติแท่งปิด 4 กรอบ, Spot Quote, Futures สาธารณะที่ใช้กฎเดิม, Binance Book/Trades, BTC Regime, Taker Buy ล่าสุด, แผน Entry และ R:R หลังต้นทุนจำลอง: ขาดหรือไม่ผ่าน = WAIT |
| **Optional / Independent** | Bybit Spot + Futures, DefiLlama Stablecoin/TVL และ CVD/VWAP/POC เป็นหลักฐานเสริม; ขาด = ระบุ MISSING ไม่แต่งค่าและไม่ทำให้ผ่านมากขึ้น |
| **Optional / Manual** | CoinGlass ต้องกรอกเองและยืนยันค่า; เมื่อกรอกแล้วไม่ผ่าน/เก่า/ผิดเหรียญ = WAIT |
| **Unavailable on no-key free plan** | การระบุตัว Whale จริง, Liquidation Heatmap จากทุก Exchange, ประวัติ L2 Book แบบ Tick, Token Unlock/ETF Flow ครบทุกเหรียญ และ Macro Event API ที่เชื่อถือได้พร้อมข้อมูลเก่าเท่ากันทุกตลาด |

**ข้อจำกัดที่สำคัญที่สุด:** Full Final Strategy ยัง **ไม่ได้ผ่านการพิสูจน์ผลตอบแทน Out-of-sample แบบครบกฎ**; `MTF Research` ทดสอบเฉพาะข้อมูล Spot/Entry บางส่วน (ไม่รวม Futures, CVD จาก Tick, Book History, Bybit, DefiLlama และ CoinGlass ย้อนหลัง). แผนใด ๆ อาจขาดทุนได้และไม่มีข้อมูลฟรีที่รับประกันว่าจะเล่นฝั่งเดียวกับเจ้ามือได้จริง. Streamlit Cloud ฟรีไม่ใช่บริการเก็บ Order Book ความถี่สูง 24/7; ต้องเก็บ CSV Paper Journal เอง.

### วิธีอัปเดต GitHub / ใช้บนมือถือ

แตก ZIP → เข้าโฟลเดอร์ `orbit_crypto_signal_lab` → อัปโหลด **ไฟล์ภายในทั้งหมด รวม `.github/workflows/orbit-telegram-monitor.yml`** ไปที่ root ของ GitHub repository เดิมให้ `app.py` อยู่ระดับเดียวกับ `requirements.txt` → Commit → รอ Streamlit Cloud อัปเดต → เปิด URL เดิมบน iPhone/Android. ดู `MONITOR_TELEGRAM_SETUP_TH.md` สำหรับระบบแจ้งเตือน และ `DEPLOY_MOBILE_TH.md` สำหรับเว็บ

**ไฟล์ใหม่สำคัญของ v4.0:** `watch_plans.py`, `WATCH_PLAN_GUIDE_TH.md`, `tests/test_watch_plans.py` และไฟล์จาก v3.0 (`advanced_evidence.py`, `bybit_intelligence.py`, `macro_liquidity.py`, `risk_audit.py`, `journal_utils.py`, `signal_outcomes.py`) ต้องอัปโหลดด้วย โดยเฉพาะ `watch_plans.py` **ต้องอยู่ระดับเดียวกับ `app.py`**

**แหล่งอ้างอิงหลัก:** [Binance Market-Data-Only](https://developers.binance.com/en/docs/products/spot/rest-api), [Bybit Public Trades](https://bybit-exchange.github.io/docs/v5/market/recent-trade), [Bybit OI](https://bybit-exchange.github.io/docs/v5/market/open-interest), [DefiLlama Free API](https://github.com/DefiLlama/api-docs/blob/main/llms-free.txt), [CoinGlass API Auth](https://docs.coinglass.com/reference/authentication)

---

## ใหม่ใน v2.7 — ตรวจแรงซื้อเชิงรุกและสภาพคล่องก่อน READY

- **Binance Spot Order Book ฟรี**: Best Bid/Ask, Spread (bps), ปริมาณคำสั่งใกล้ราคาในระยะ ±0.5%, ความไม่สมดุล Bid/Ask และประมาณ Price Impact ของขนาดดีลที่ตั้งไว้ จาก `/ticker/bookTicker` และ `/depth`
- **Anonymous Trade Flow ฟรี**: อ่าน 500 Binance Aggregate Trades ล่าสุดจาก `/aggTrades` แยกผู้ซื้อเชิงรุก/ผู้ขายเชิงรุกตามฟิลด์ buyer-is-maker; เช็กอายุเวลาของรายการเทรดและสัดส่วนแรงซื้อเชิงรุก
- **Taker Buy Volume จากแท่งปิด**: ดึงฟิลด์ที่ Binance ระบุไว้ใน Kline แล้วประเมินอัตราส่วน Buy Volume 20 แท่งย้อนหลังของ 15m และ 1h (ต้อง ≥52% ตามเกณฑ์ทดลอง) ไม่สมมติข้อมูลเมื่อแหล่งไม่ส่งฟิลด์นี้
- **BTC Market Regime**: ตรวจ BTCUSDT 4h และ 1d จาก Binance Spot แม้กำลังวิเคราะห์เหรียญอื่น เพื่อระวังตลาดหลักเป็นขาลง; ข้อมูลไม่พร้อมหรือเป็นลบจะไม่ให้ผลรวม READY
- **Strict Evidence Gate**: ทุกชั้นใหม่เป็น veto อย่างเดียว ไม่เพิ่มความแม่นยำที่ไม่มีหลักฐาน; เมื่อข้อมูลสภาพคล่อง/Trade Flow/BTC ไม่พร้อมจะเป็น MTF WAIT พร้อมเหตุผล
- **📈 MTF Research แบบทดลอง**: ปุ่มรัน Historical Spot-only MTF + Rolling Walk-forward บนแท่งที่ปิดแล้ว ทดสอบช่วง Train/Test แยกกัน และจำลองเข้าที่ราคาเปิดแท่ง 1h ถัดไปเฉพาะเมื่อยังอยู่ในโซน; รวมต้นทุนจำลอง แต่ **ยังไม่รวม Order Book, aggTrades, BTC Regime, Futures และ CoinGlass ย้อนหลัง** จึงไม่ใช่ Backtest ของ Final v2.7
- **Paper Journal**: ปุ่มบันทึกสถานะ MTF/ราคา/โซน/แหล่งข้อมูลไว้ตรวจภายหลัง แล้วดาวน์โหลด CSV (ข้อมูลอยู่ในเซสชันเว็บ ต้องดาวน์โหลดเองก่อนปิด)

**ห้ามตีความว่าโปรแกรมระบุตัวตนเจ้ามือได้**: Book Orders เปลี่ยน/ยกเลิกได้, Trade Flow ไม่แสดงเจ้าของ และข้อมูลจากตลาดหนึ่งไม่ได้แทนตลาดทั้งหมด. เงื่อนไข Spread ≤30 bps, Book Depth ≥5 เท่าของมูลค่าดีล, Estimated Impact ≤25 bps, Aggressive Buy ≥52%, Taker Buy 20 แท่ง ≥52% เป็น heuristic ยังไม่ผ่านการปรับเทียบกับผลจริง; ไม่รับประกันกำไร

## มีอะไรใหม่ใน v2.6.1 — เลือกเหรียญเดียว ได้ผลวิเคราะห์ MTF ชุดเดียว

- แค่ **ค้นหาและเลือกคู่เหรียญหนึ่งครั้ง** เช่น PEPE/USDT แล้วเปิดแท็บเริ่มต้น **🎯 สัญญาณ MTF รวม** ระบบจะดึงและวิเคราะห์ **15m, 1h, 4h, 1d อัตโนมัติ** แต่แสดง **คำตอบรวมเพียงชุดเดียว** ไม่แสดงตาราง/การ์ดสัญญาณแยก 4 ชุดแบบ v2.6 เดิม
- แสดง **MTF Signal = BUY/WAIT**, สถานะ **READY/WAIT ENTRY/WAIT SIGNAL**, คะแนนความสอดคล้อง 0–100 (ไม่ใช่โอกาสทำกำไร), Entry Zone **ชุดเดียว**, Stop Loss, TP1, TP2 และเวลาที่ต้องตรวจแท่งครั้งต่อไป
- กฎทดลอง: **1d 30% + 4h 30% + 1h 25% + 15m 15%** ใช้คะแนนเทคนิคที่ทำให้มีหน่วยเทียบกันได้ก่อนถ่วงน้ำหนัก; ต้อง ≥70/100 พร้อมมีแนวโน้มใหญ่เป็นบวก, 1h/15m Final BUY, แท่ง 15m เขียว + Volume ผ่าน แล้วจึงถือว่าทิศทางซื้อผ่าน; ไม่ใช่การนำระดับราคาเข้าซื้อ 4 กรอบมาเฉลี่ย
- **ระดับ Entry/SL/TP มาจากแผน 1h เท่านั้น** และต้องรอแผน 1h แสดง READY ก่อนผลรวมจะเป็น READY; กรอบ 1d+4h ใช้ดูเทรนด์หลัก, 15m ใช้ดูจังหวะยืนยัน
- Futures Public ชุดเดียวกับเดิม (Kraken/Binance/Bybit fallback แหล่งเดียวต่อครั้ง) และ CoinGlass ที่กรอกเอง (ถ้ามี) ยังสามารถคัดค้านได้; หากข้อมูล 4 กรอบขาด/เก่า/ขัดแย้งจะ **WAIT** พร้อมรายการสาเหตุ
- **ไม่มีความแม่นยำหรือผลตอบแทนที่รับรองจากคะแนน 0–100**; สูตร Multi-Timeframe รวมนี้ **ยังไม่ได้ผ่าน Backtest/Walk-forward ตามกฎรวม** และไม่ใช่คำสั่งซื้อจริง

### วิธีใช้ Single MTF บนมือถือ

1. เลือกคู่เหรียญที่เมนูซ้าย (เช่น `PEPE/USDT`) **ครั้งเดียว**; ช่อง Timeframe ในเมนูมีผลเฉพาะกราฟละเอียดและ Backtest ไม่ได้เปลี่ยนสูตรหน้า MTF
2. เปิดแท็บ **🎯 สัญญาณ MTF รวม** อ่านสัญญาณรวมหนึ่งค่า พร้อม Entry Zone/SL/TP ชุดเดียว
3. ขยายหัวข้อ **ทำไม MTF ยังรอ?** เพื่อดูเหตุผลที่กฎรวมผ่าน/ยังไม่ผ่าน ไม่จำเป็นต้องเปิดทีละ Timeframe
4. ถ้าขึ้น **MTF BUY BIAS · WAIT FOR ENTRY** แปลว่าทิศทางผ่าน แต่ยัง **ไม่ใช่จังหวะซื้อ**; รอ READY และตรวจราคา/คำเสนอขายจริง
5. หากต้องการ CoinGlass ให้กรอกและบันทึกในแท็บ **📊 สัญญาณละเอียด** แล้วกลับมาดูผลรวม
6. กด **🔄 ดึงข้อมูลใหม่** เมื่อจะตรวจแท่งใหม่; โปรแกรมไม่ได้ติดตามราคาเบื้องหลังหรือส่งแจ้งเตือนอัตโนมัติ

## มีอะไรใหม่ใน v2.5

- **Entry Zone ตามเหรียญและ Timeframe ที่เลือก** ใช้แนวรับล่าสุดจาก Pivot ที่ยืนยันแล้ว, Support 50 แท่ง, EMA20/50 หรือ Pivot High ที่ทะลุแล้วสำหรับ Retest; ต้องอยู่ใกล้ราคาในหน่วย ATR จึงจะเสนอแผน ไม่สุ่มโซนซื้อให้ทุกเหรียญ
- **Stop Loss / Take Profit 1 (1.5R) / Take Profit 2 (2.5R)** จากราคาขอบบนของ Entry Zone โดยใช้ ATR และโครงสร้างราคา; แสดงระดับบนกราฟและการกำหนดขนาดสถานะจากทุนจำลอง
- **ระบุสถานะเข้าซื้อและเวลา**: READY เฉพาะ Final BUY + แท่งเขียวปิดในโซนเหนือแนวรับ + Volume ผ่าน; WAIT_RETEST รอย่อ, WAIT_CONFIRMATION รอตัวกรอง, INVALID/NO_SETUP เมื่อข้อมูลหรือโครงสร้างไม่เหมาะ
- เพิ่มราคาซื้อขายล่าสุดจาก Binance Spot Public `ticker/price` (ไม่ต้องมี API Key) เพื่อไม่ให้ขึ้น READY หากราคาที่ร้องขอล่าสุดอยู่นอกโซน; หากดึงราคานี้ไม่ได้จะเป็น `WAIT_LIVE_QUOTE`
- บอกเวลาไทยของแท่งปิดล่าสุด, เวลาตรวจเมื่อแท่งถัดไปปิด และเวลาหมดอายุแผนสมมติ (3 แท่ง); รีเฟรชแอปเพื่อคำนวณใหม่ ไม่ใช่ระบบแจ้งเตือนหรือซื้อขายอัตโนมัติ
- **ช่วงราคาไม่ใช่สัญญาณให้ซื้อทันที** โดยเฉพาะเมื่อ Final Signal เป็น WAIT/SELL; Backtest/Walk-forward รุ่นนี้ยังเป็นของกฎเทคนิคเดิม **ไม่ได้ทดสอบ Entry Zone, SL/TP ใหม่, Futures หรือ CoinGlass ร่วมกัน**

## มีอะไรใหม่ใน v2.4

- ข้อความ **Final Signal** แสดงชื่อผู้ให้ข้อมูล Futures จริงตามที่ได้รับ (Kraken / Binance / Bybit) แก้ปัญหาที่เคยเขียนว่า Binance Futures แม้กำลังใช้ Kraken
- แสดงราคาปิด, Pivot High/Low, ATR, Entry, SL และ TP สำหรับเหรียญทศนิยมเล็กอย่าง PEPE ได้โดยไม่ปัดเป็น `0.00000` (ใช้ความแม่นยำตามขนาดราคา; เมื่อเล็กมากจะแสดงเลขวิทยาศาสตร์แทนศูนย์)
- เมื่อ CoinGlass เป็น `CAUTION` หรือ `INVALID` จะแสดงเหตุผลสำคัญไว้ใต้ Final Signal ทันที รวม **ค่าที่กรอกเทียบเกณฑ์จริง** เช่น `Long/Short Accounts 1.660 > 1.600`
- ย้ำข้อควรระวังเมื่อกรอกค่า CoinGlass ที่มีขอบเขตต่างตลาด (เช่น Funding/Ratio ของ OKX แต่ OI รวมหลายตลาด); ข้อมูลไม่ถูกตรวจสอบความสอดคล้องของแหล่งโดยอัตโนมัติ
- **ไม่เปลี่ยนเกณฑ์ BUY/SELL/WAIT ของ v2.3** และไม่แอบเปิดคำสั่งซื้อขาย; ยังคงใช้ CoinGlass เป็นตัวกรองเสริมที่กรอกเอง

**ชื่อบอทใหม่:** Orbit Crypto Signal Lab (ไม่ใช้ชื่อผู้ใช้)

**ใช้บนมือถือจากทุกที่:** ดูคู่มือ `DEPLOY_MOBILE_TH.md` สำหรับอัปโหลด GitHub และ Deploy ฟรีบน Streamlit Community Cloud (ไม่มีค่าโฮสต์ตามแพ็กเกจฟรี แต่ต้องมีบัญชี GitHub/Streamlit)

## วิธีเปิดโปรแกรม (Windows)

1. ติดตั้ง **Python 3.11 หรือ 3.12** จาก https://www.python.org/downloads/ และเลือก `Add Python to PATH` ตอนติดตั้ง
2. แตก ZIP ทั้งหมด ไม่เปิดไฟล์ `.bat` จากใน ZIP โดยตรง
3. ดับเบิลคลิก `start_windows.bat`
4. ครั้งแรกโปรแกรมจะติดตั้งแพ็กเกจฟรีที่ระบุใน `requirements.txt` ต้องเชื่อมต่ออินเทอร์เน็ต
5. หน้าจอจะเปิดที่ `http://localhost:8501` (หากไม่เปิดเอง ให้คัดลอก Local URL จากหน้าต่าง Command Prompt)
6. ใช้ช่องค้นหาเหรียญทางซ้าย เลือกคู่และ Timeframe เพื่อเริ่มวิเคราะห์

การหยุดโปรแกรม: กลับไปที่หน้าต่าง Command Prompt แล้วกด `Ctrl+C`.

### รันเองเมื่อจำเป็น

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```

## สิ่งที่ทำได้จริง

| รายการ | ความสามารถเดิมที่ยังคงอยู่ใน v4.1 |
|---|---|
| ค้นหาคู่เหรียญ Spot ที่อยู่ใน Binance Public Catalog | ได้ (รหัสเหรียญ / ชื่อสามัญบางเหรียญ) |
| ดึงข้อมูลราคาแบบไม่ต้องมีบัญชีหรือ API Key | ได้ผ่าน Binance public market-data-only API |
| วิเคราะห์ EMA20/50/200, RSI14, MACD, ADX, ATR, Volume Breakout | ได้ |
| วิเคราะห์หลาย Timeframe | 15m→1h, 1h→4h, 4h→1d, 1d ไม่มีการยืนยันซ้ำ |
| **Single MTF Signal (15m+1h+4h+1d)** | **มี** — วิเคราะห์ทั้ง 4 กรอบแต่แสดง BUY/WAIT + Entry/SL/TP รวมชุดเดียว; เกณฑ์ถ่วงน้ำหนักและยืนยันเป็น heuristic ยังไม่ Backtest |
| **Spot Order Book + Best Bid/Ask + Estimated Impact** | **มี** — Binance Public API ฟรี; แสดง WAIT เมื่อไม่พร้อม/ข้อมูลเก่า/สภาพคล่องไม่เพียงพอ |
| **Aggressive Trade Flow + Taker Buy Volume** | **มี** — Aggregate Trades ล่าสุดและ Taker Buy จากแท่งที่ปิดแล้ว; เป็น proxy ของแรงซื้อไม่ใช่ข้อมูลเจ้ามือ |
| **BTC Market Regime 4h+1d** | **มี** — ดึง BTCUSDT Spot เป็น risk veto เพิ่มเมื่อวิเคราะห์ Altcoin |
| **MTF Spot-only Walk-forward Research** | **มีแบบจำกัด** — กฎส่วนย่อยที่มีข้อมูลย้อนหลัง ไม่รวมอนุพันธ์/Order Book/CoinGlass จึงยังไม่พิสูจน์ Full Signal |
| **บันทึก Signal Journal CSV** | **มี** — ผู้ใช้กดบันทึกเองในเซสชันเพื่อทำ Forward Paper Audit |
| Confirmed Pivots, BOS, CHoCH, Liquidity Sweep | ได้ (เป็นกฎเชิงปริมาณเบื้องต้น) |
| แผน Entry Zone / SL / TP1 / TP2 | คำนวณจากแท่งเทียนที่ปิดแล้วสำหรับคู่ที่ค้นหาได้; ถ้าข้อมูลหรือโครงสร้างไม่ดีจะแสดง NO SETUP ไม่ฝืนให้จุดซื้อ |
| ขนาดสถานะและความเสี่ยงเชิงตัวอย่าง | ใช้ราคาขอบบน Entry Zone เผื่อ fee/slippage สองด้านและเพดานเงินต่อดีล; ไม่ใช่คำแนะนำขนาดเงินจริง |
| Backtest แบบ Long-only Spot พร้อมค่าธรรมเนียม/Slippage | ได้ — **เฉพาะกลยุทธ์เทคนิค** |
| Walk-forward ปรับเกณฑ์คะแนนบน Train แล้วทดสอบช่วงถัดไป | ได้ — **เฉพาะกลยุทธ์เทคนิค** |
| CoinGlass Funding/OI/Long-Short/Liquidations | กรอกเองใน Dashboard |
| Auto Futures Funding/OI/Long-Short | ดึงจาก Kraken Futures ก่อน (สำรอง Binance USDⓈ-M และ Bybit USDT Linear Futures) แบบอ่านอย่างเดียว ไม่ใช้ API Key |
| Auto BUY/SELL/WAIT | กรองเพิ่มจากข้อมูล Futures ที่ใหม่และครบ; เป็นเกณฑ์ทดลอง ยังไม่มีผล Backtest ของตัวกรองนี้ |
| CoinGlass แบบเสริม | วางตัวเลข 5 ค่าในช่องเดียวได้บนมือถือ; หากไม่กรอกใช้ผล Auto; หากกรอกแล้วไม่ผ่าน/เก่า/ผิดเหรียญ เปลี่ยนเป็น WAIT |
| Final BUY/SELL/WAIT | ได้เมื่อเทคนิคและ Auto Futures ผ่าน และข้อมูลเสริม CoinGlass (ถ้ามี) ไม่คัดค้าน |
| Auto Telegram / Auto Trading | ไม่มี |

## แหล่งข้อมูลและความถูกต้อง

- ข้อมูลราคาใหม่/ย้อนหลังใช้ **Binance Spot public market-data-only endpoints**: `https://data-api.binance.vision/api/v3` (`/exchangeInfo`, `/klines`, `/ticker/price`)
- นำข้อมูลย้อนหลังแบบแบ่งหน้าโดยส่ง `endTime` และคัดออกแท่งที่ยังไม่ปิด
- ใช้เวลา UTC สำหรับคำนวณ; แสดงเวลาไทยในหน้าจอ
- ยืนยัน Timeframe ใหญ่เฉพาะเมื่อแท่ง Timeframe ใหญ่นั้นปิดจริง
- Pivot ต้องมีแท่งด้านขวาปิดครบตามที่กำหนดก่อนเป็นจุด Pivot ที่ระบบรู้จัก (non-repainting ในกรอบกฎนี้)
- หากพบช่องว่างของแท่งข้อมูล ระบบจะไม่รัน Backtest และ Walk-forward
- ข้อมูลสาธารณะอาจไม่พร้อมใช้งานหรือถูกจำกัดตามภูมิภาค/เครือข่าย; ไม่มีการเลี่ยงข้อจำกัด

## ทำความเข้าใจ Backtest และ Walk-forward

Backtest จำลองการซื้อเมื่อสัญญาณ BUY เกิดหลังแท่งเทียนปิด และซื้อที่ **ราคาเปิดของแท่งถัดไป**. ขายเมื่อพบ SELL, Stop Loss, Target 2R หรือจบช่วงทดสอบ

- ใช้ Spot ฝั่ง Long เท่านั้น ไม่เปิด Short
- คิดค่าธรรมเนียมทั้งตอนซื้อและขาย และจำลอง Slippage ตามค่าที่ผู้ใช้กำหนด
- หากในแท่งเดียวกันแตะทั้ง SL และ TP ระบบนับว่าโดน SL ก่อน (conservative)
- จำกัดสัดส่วนเงินต่อดีล และจำกัดงบความเสี่ยงตามระยะ SL
- หยุดเปิดดีลใหม่เมื่อพบ Drawdown เกินเกณฑ์ที่กำหนด
- Walk-forward เลือกเกณฑ์คะแนน 5/6/7 จากช่วงฝึก แล้วทดสอบช่วงถัดไปโดยไม่ใช้ผลทดสอบมาปรับเกณฑ์ย้อนหลัง
- เมื่อจำนวนดีลน้อย ผลจะถูกระบุว่า "หลักฐานไม่เพียงพอ"; ตัวเลขในอดีตไม่รับประกันอนาคต

**ข้อจำกัด:** Backtest/Walk-forward เดิมยังทดสอบ **เฉพาะเทคนิค Spot** ส่วนแท็บ MTF Research ของ v2.7 ทดสอบเพียง MTF + Taker Buy + แผน Entry 1h จากแท่งปิดและจำลองราคาเปิดแท่งถัดไป **ไม่รวม Order Book/Aggressor Trades/BTC Regime/Futures/CoinGlass ในอดีต** จึงห้ามอ้างว่าผลของ Full Signal v2.7 ผ่าน Backtest แล้ว

## แผนเข้าซื้ออัตโนมัติ — v2.5

1. เลือกคู่เหรียญและ Timeframe จากเมนูซ้าย แล้วดูหัวข้อ **🎯 Entry Zone · SL · TP1 · TP2** ใต้ Final Signal บนหน้า `📊 สัญญาณ`
2. **ENTRY ZONE** เป็นพื้นที่เฝ้ารอราคาย่อหรือ Retest กว้าง `±0.30 ATR` รอบแนวรับที่ยังรู้ได้ ณ แท่งปิดล่าสุด; ถ้าแนวรับไกลกว่าเกณฑ์จะขึ้น `NO VALID SETUP`
3. **READY** ต้องมี `Final BUY`, แท่งเทียนที่ปิดแล้วเป็นแท่งเขียว, ราคาปิดอยู่ในช่วงเหนือแนวรับอ้างอิง, Volume ≥ `0.75×`, และราคาล่าสุดที่ดึงจาก Binance `ticker/price` **ยังอยู่ภายใน Entry Zone**; หาก API ราคาไม่พร้อมจะขึ้น `WAIT_LIVE_QUOTE` โดยไม่สมมติราคา
4. หากราคายังสูงกว่า Entry Zone ให้ **WAIT FOR ENTRY** ไม่ไล่ราคา; หาก Final Signal เป็น WAIT แม้ราคาจะเข้าโซนก็ยัง **WAIT** ไม่ใช่คำแนะนำให้ซื้อทันที
5. Stop Loss วางใต้ขอบล่างของโซนและ Pivot Low ที่อยู่ใกล้ (ถ้ามี), ด้วยระยะตาม ATR; TP1/TP2 เป็นระดับตามสัดส่วนความเสี่ยง **ก่อนต้นทุน** ที่ `1.5R` และ `2.5R` จาก **ขอบบนของโซน** ไม่ใช่ราคาเข้าซื้อจริง
6. ขนาดสถานะคำนวณจากงบเสี่ยงต่อดีลและวงเงินสูงสุดที่ตั้งไว้ รวมค่า fee+slippage ประมาณสองด้าน แต่ **ไม่ได้ตรวจ Lot Size / Min Notional / Tick Size ของกระดาน และไม่ได้รองรับการกระโดดของราคา** ต้องตรวจคำสั่งจริงด้วยตัวเอง
7. แผนออกแบบให้ใช้กับราคาตลาด Spot ที่มีข้อมูลครบ ไม่จำกัดชื่อเหรียญ แต่ **ไม่รับประกันว่าจะมีจุดซื้อที่เหมาะสำหรับทุกคู่**; Futures Auto รองรับเฉพาะคู่ `USDT` ที่มีตลาดในแหล่งสาธารณะ หากไม่พร้อม Final Signal ยังคง WAIT
8. เวลาแผนแสดงเป็นเวลาประเทศไทยจากแท่งเทียนที่ปิดแล้ว; ต้องเปิด/รีเฟรชเว็บอีกครั้งเพื่อรับการประเมินล่าสุด ไม่มีการส่ง Push หรือเฝ้าราคาเบื้องหลัง
9. ราคา Spot ล่าสุดมาจาก endpoint แบบ last-traded price ที่ **ไม่บอกเวลาเทรดจริง** จึงบอกได้เพียงเวลาเมื่อแอปขอข้อมูล (แคชประมาณ 15 วินาทีเมื่อแอปรันซ้ำ); ตลาดที่สภาพคล่องต่ำอาจมีราคาซื้อขายล่าสุดเก่า และราคาที่เข้าซื้อจริงอาจต่างกัน ต้องดู Bid/Ask/Order Book ที่กระดานก่อนทำรายการ

แนวคิดการใช้ ATR เป็นระยะเผื่อความผันผวนอ้างอิงจากหลักการของ Fidelity: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr
**ค่าสัมประสิทธิ์ทั้งหมดในแผนนี้เป็นเกณฑ์ทดลองของโปรแกรม ไม่ใช่เกณฑ์ที่ผ่านการปรับแต่งทางสถิติหรือสัญญาณรับประกันกำไร**

## Futures อัตโนมัติฟรี (v2.5)

1. เลือกคู่เหรียญที่ลงท้ายด้วย `USDT` (เช่น BTCUSDT) และมีตลาด Futures ในแหล่งที่ใช้
2. แอปเรียก Kraken Futures Public REST (`tickers`, `open-interest`, `long-short-ratio`) เป็นอันดับแรกสำหรับ Perpetual `PF_*USD` เช่น BTCUSDT จะจับคู่กับ Kraken `PF_XBTUSD`, PEPEUSDT กับ `PF_PEPEUSD`
3. ถ้า Kraken ไม่มีเหรียญหรือไม่พร้อม จึงลอง Binance USDⓈ-M (`premiumIndex`, `openInterestHist`, `globalLongShortAccountRatio`) และ Bybit Public REST (`tickers`, `open-interest`, `account-ratio`) ตามลำดับ โดยใช้ **ข้อมูลครบจากตลาดเดียวเท่านั้น** ไม่ผสมข้ามตลาด
4. OI Change 24h ของ Binance ใช้มูลค่า OI (USDT), ส่วน Bybit/Kraken ใช้ปริมาณสัญญา; ไม่ควรเทียบการเปลี่ยนแปลงข้ามแหล่งตรง ๆ. ข้อมูล Kraken เป็นตลาด **USD Perpetual** ไม่ใช่ USDT spot เดียวกัน แม้เป็นเหรียญฐานเดียวกัน
5. **Kraken Funding** แสดงค่า raw ของตลาด โดยไม่ตีความเป็นเปอร์เซ็นต์แบบ Binance และยังไม่ใช้ในการตัดสิน crowding เพราะไม่ผ่านการทำหน่วยให้เทียบเท่ากัน; กฎ Auto ของ Kraken ใช้ราคาฝั่ง Spot + OI 24h + Long/Short Ratio เป็นหลัก
6. ต้องมีข้อมูล OI ย้อนหลังอย่างน้อย 24 ชั่วโมง, Funding และสัดส่วน Long/Short ใหม่ตามเกณฑ์ ก่อน Auto Signal ไม่เป็น WAIT
7. หากทุกแหล่งถูกจำกัด จะ **WAIT พร้อมเหตุผล** ไม่บังคับเลี่ยงข้อจำกัดหรือสมมติข้อมูล
8. ไม่มี Liquidation Aggregates แบบ CoinGlass 24h จาก Public API ชุดนี้ จึงไม่ใช้ค่านี้ใน Auto Signal และยังคง CoinGlass เป็นตัวกรองกรอกเอง

**ข้อเท็จจริงจากการทดสอบสดในสภาพแวดล้อมพัฒนา:** Kraken Futures ตอบข้อมูลจริงสำเร็จสำหรับ BTC/PEPE (tickers, OI history, L/S ratio); Binance Futures ตอบ HTTP 451, Bybit HTTP 403 และ OKX HTTP 403. แอปบน Streamlit Cloud อาจมีนโยบายเครือข่ายต่างกัน จึงยังต้องตรวจใช้งานจริงบนเว็บของผู้ใช้. เมื่อไม่สำเร็จจะ WAIT

## CoinGlass แบบฟรี — ไม่มีบัญชี/API Key

1. เปิด https://www.coinglass.com/ และดูข้อมูลที่เข้าถึงได้ตามปกติ
2. คัดลอก Funding Rate, OI Change 24h, Long/Short Accounts Ratio และ Liquidations ของ Long/Short ช่วง 24h ที่อยู่ในหน่วยเดียวกัน
3. กรอกค่าพร้อมวันและเวลาไทยในหัวข้อ CoinGlass ของแดชบอร์ด และยืนยันความถูกต้อง
4. กรอกง่ายบนมือถือ: สามารถวางเลขทั้ง 5 ค่าในช่องเดียว โดยคั่นด้วยคอมมา เช่น `Funding%, OI24h%, Long/Short, LongLiqUSD, ShortLiqUSD` จากนั้นตรวจค่าที่เติมให้และกดยืนยัน
5. CoinGlass เป็นตัวกรองเสริมใน v2.5: ไม่กรอกยังดู Auto Signal ได้ หากกรอกแล้วข้อมูลขัดแย้ง/หมดอายุ/ผิดเหรียญ Final Signal จะ WAIT พร้อมบอกเหตุผลแบบเจาะจงใต้หัวข้อ Final Signal
6. **อย่าใช้ตัวเลขที่มาจากต่างตลาดหรือเวลาห่างกันเป็นหลักฐานยืนยันร่วมที่เชื่อถือได้** แอปไม่สามารถตรวจว่าค่า Funding, OI, Ratio และ Liquidations ที่กรอกเองอ้างถึงตลาดเดียวกันได้; จะแสดงคำเตือนเรื่องนี้ให้เห็น

### ตัวอย่างการอ่าน CAUTION

- `Technical BUY +8/9` หมายถึงกฎกราฟเชิงทดลองให้คะแนนสูง ไม่ใช่คำสั่งซื้อ
- `Kraken Futures: SUPPORTED` หมายถึงเกณฑ์ Auto จาก Kraken ผ่าน ไม่ใช่ Binance และไม่ใช่ CoinGlass
- `CoinGlass: CAUTION` พร้อมเหตุผล `Long/Short Accounts 1.660 > 1.600` คืออัตรา Long/Short จาก CoinGlass ที่กรอกเองสูงกว่าเกณฑ์ระวังในโค้ด จึง **Final WAIT**
- ค่าเกณฑ์ `1.600` นี้เป็น heuristic ป้องกันการไล่ราคา **ยังไม่ผ่านการปรับเทียบและ Backtest แบบรวม Futures/CoinGlass**; ห้ามตีความเป็นโอกาสกำไร/ขาดทุนเชิงสถิติ

CoinGlass API ทางการต้องใช้ API Key และแผนที่แสดงบนหน้าราคา ณ ตุลาคม 2026 เริ่ม $29/เดือน โปรแกรมฟรีนี้จึง **ไม่เชื่อม CoinGlass API อัตโนมัติ** และไม่ทำการสแครปเว็บเพื่อข้ามระบบสิทธิ์ หากข้อมูลหน้าเว็บบางอย่างไม่สามารถเข้าถึงได้ฟรี ก็ไม่สามารถยืนยัน Final Signal ได้

## วิธีตรวจสอบคุณภาพโปรแกรม

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

## แหล่งอ้างอิง

- Binance public market-data endpoint: https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md
- Binance public historical files: https://github.com/binance/binance-public-data
- Streamlit install: https://docs.streamlit.io/get-started/installation/command-line
- CoinGlass API authentication: https://docs.coinglass.com/reference/authentication
- CoinGlass pricing: https://www.coinglass.com/pricing
- Bybit public market tickers: https://bybit-exchange.github.io/docs/v5/market/tickers
- Bybit public OI: https://bybit-exchange.github.io/docs/v5/market/open-interest
- Bybit public Long/Short: https://bybit-exchange.github.io/docs/v5/market/long-short-ratio
- Kraken Futures tickers: https://docs.kraken.com/api-reference/market-data/get-tickers
- Kraken Futures market analytics: https://docs.kraken.com/api/docs/futures-api/charts/market-analytics

โปรแกรมนี้เป็นเครื่องมือวิจัย/สนับสนุนการตัดสินใจ ไม่ใช่คำแนะนำการลงทุนเฉพาะบุคคล
