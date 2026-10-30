# นำ Orbit Crypto Signal Lab ขึ้นมือถือฟรี — ทีละขั้น

ชุดนี้พร้อมนำไปใช้กับ **Streamlit Community Cloud** โดยไม่ต้องมีคอมพิวเตอร์เปิดโปรแกรมตลอดเวลา
แต่ต้องใช้บัญชี **GitHub** และ **Streamlit Community Cloud** ของคุณเองเพื่อเผยแพร่แอป

## อัปเดตเว็บเดิมเป็น Orbit v4.1 (ล็อกแผน + Telegram แจ้งเตือน)

1. ดาวน์โหลด ZIP **Orbit Crypto Signal Lab v4.1** แล้วแตกไฟล์ในคอมพิวเตอร์ก่อน
2. เปิด GitHub repository เดิมที่พรรณใช้ เช่น `Punnipah/orbit-crypto-signal-lab`
3. อัปโหลด **ไฟล์ทั้งหมด** ในโฟลเดอร์ `orbit_crypto_signal_lab` ไปไว้ที่ **root ของ repository เดิม** โดยเฉพาะ `app.py`, `watch_plans.py`, `alert_monitor.py`, `monitor_engine.py`, `monitor_alerts.py`, `monitor_delivery.py`, `monitor_config.json`, `monitor_coinglass_manual.json`, `monitor_requirements.txt`, `requirements.txt` และ **`.github/workflows/orbit-telegram-monitor.yml`** ห้ามอัปโหลดแค่ ZIP ก้อนเดียว
4. กด `Commit changes` แล้วรอ Streamlit Community Cloud ดึง commit ใหม่/รีสตาร์ตแอป
5. รีเฟรชหน้าเว็บและดูบรรทัดใต้ชื่อแอปว่าขึ้น **`Orbit v4.1`**; เปิดแท็บ **🎯 สัญญาณ MTF รวม** ไม่ต้องสร้างแอปใหม่หรือเปลี่ยน Main file path (`app.py`)
6. อ่าน `WATCH_PLAN_GUIDE_TH.md` เพื่อทดลองล็อกโซนและบันทึกลิงก์แผนบนมือถือ

**ระบบ Telegram ไม่เปิดเองทันทีหลัง Deploy:** อ่าน `MONITOR_TELEGRAM_SETUP_TH.md` เพื่อตั้ง BotFather, GitHub Secrets, ทดสอบ Telegram และเพิ่ม Frozen Watch Links; GitHub Actions รันแยกจาก Streamlit Cloud และสามารถทำงานเมื่อปิดเว็บ

**ข้อควรระวัง:** GitHub `Add file → Upload files` ไม่สามารถเขียนทับไฟล์เดิมในทุกกรณีได้ด้วยการลากวางแบบเดียวกัน หากเว็บแจ้งชื่อไฟล์ซ้ำ/ไม่ยอมอัปโหลด ให้เปิดไฟล์นั้นใน GitHub → ไอคอนดินสอ `Edit` → วางเนื้อหาใหม่ → `Commit changes` ทีละไฟล์ หรือใช้ GitHub Desktop (ฟรี) เพื่อ commit โฟลเดอร์ทั้งหมดในครั้งเดียว อย่าลบ repository หรือ Streamlit app เดิมเพื่ออัปเดต

## A. เตรียมไฟล์บนคอมพิวเตอร์

1. แตกไฟล์ ZIP ก่อน อย่าอัปโหลด ZIP ทั้งก้อนเข้า GitHub
2. เปิดโฟลเดอร์ `orbit_crypto_signal_lab` ที่มี `app.py` และ `requirements.txt`
3. ใช้ไฟล์ทุกไฟล์ในโฟลเดอร์นี้ รวมทั้งโฟลเดอร์ `.streamlit` (โฟลเดอร์ที่ขึ้นต้นด้วยจุดอาจถูก Windows ซ่อนไว้)
4. **ห้ามอัปโหลด** `.venv`, `__pycache__`, `.streamlit/secrets.toml`, รหัสผ่าน หรือ API key ใด ๆ

## B. อัปโหลดขึ้น GitHub

1. เข้า https://github.com/ แล้วสมัครหรือเข้าสู่ระบบ (บัญชีฟรี)
2. กด `+` → `New repository`
3. ตั้งชื่อ `orbit-crypto-signal-lab` เลือก `Private` ถ้าต้องการจำกัดผู้เข้าชม หรือ `Public` ถ้าตั้งใจเผยแพร่สาธารณะ แล้วกด `Create repository`
4. ในหน้า repository เลือก `Add file` → `Upload files`
5. **ลากเนื้อหาทั้งหมดของโฟลเดอร์ `orbit_crypto_signal_lab`** ลงไป โดยให้ `app.py` และ `requirements.txt` อยู่ที่ราก repository (ไม่อยู่ในโฟลเดอร์ซ้อน)
6. ตรวจว่ามี `app.py`, `requirements.txt`, **`watch_plans.py`**, `binance_data.py`, `analysis_engine.py`, `research_engine.py`, `market_structure.py`, `backtest_engine.py`, `coinglass_overlay.py`, `public_derivatives.py`, `display_format.py`, `entry_planner.py`, `multi_timeframe.py`, `confluence.py`, `market_microstructure.py`, `btc_market.py`, `mtf_research.py`, `advanced_evidence.py`, `bybit_intelligence.py`, `macro_liquidity.py`, `risk_audit.py`, `journal_utils.py`, `signal_outcomes.py` ครบ
7. กด `Commit changes`

> หมายเหตุ: อัปโหลดผ่านเว็บ GitHub บางกรณีโฟลเดอร์ `.streamlit` ที่ซ่อนอาจไม่ถูกเลือกหรืออัปโหลด ไม่เป็นไร แอปยังรันได้ด้วยค่าเริ่มต้นของ Streamlit; ธีมอาจต่างเล็กน้อย

## C. เปิดแอปออนไลน์ฟรี

1. เข้า https://share.streamlit.io/ และเลือกเข้าสู่ระบบด้วย GitHub
2. อนุญาตให้ Streamlit เข้าถึง repository ที่ต้องใช้ (หากเลือก Private อาจต้องอนุญาตเพิ่มเติม)
3. คลิก `Create app` → `Yup, I have an app`
4. เลือก Repository: `ชื่อผู้ใช้ GitHub/orbit-crypto-signal-lab`
5. Branch: `main` (หรือชื่อ branch ที่ GitHub แสดง)
6. Main file path: **`app.py`**
7. ถ้ามีตัวเลือก Python version ให้เลือก **3.12**
8. เลือก App URL ตามต้องการ (หากชื่อยังว่าง) แล้วกด `Deploy`
9. รอติดตั้ง dependencies และเริ่มรัน จากนั้นจะได้ URL รูปแบบ `https://ชื่อแอป.streamlit.app`

## D. ใช้บน iPhone/Android

1. เปิด URL ที่ได้รับบน Safari หรือ Chrome ได้จากทุกเครือข่ายที่เข้าถึงเว็บได้
2. แตะลูกศรเมนูซ้ายบนเพื่อเปิดแถบ `ค้นหาเหรียญ`
3. ค้นหา `BTC`, `ETH`, `SOL`, `DOGE` หรือคู่เหรียญอื่นในตลาด Spot ที่ Binance แสดง
4. เลือกคู่เหรียญ และจำนวนแท่งประวัติ; มือถือแนะนำเริ่มที่ **1000–1500 แท่ง** เพราะหน้ารวมต้องเรียกข้อมูลทั้ง 4 ช่วงเวลา
5. เปิดแท็บเริ่มต้น **🎯 สัญญาณ MTF รวม** โปรแกรมวิเคราะห์ 15m, 1h, 4h, 1d อัตโนมัติหลังเลือกเหรียญ แล้วตรวจ **Spot Order Book, Aggressor Trades, Taker Buy Volume, BTC Regime และ Risk:Reward สุทธิ** ร่วมกับ Futures สาธารณะ ก่อนแสดง **สัญญาณรวมหนึ่งค่า** และ **Entry Zone/SL/TP ชุดเดียว** ไม่ต้องเลือก Timeframe ทีละกรอบ
5.1. เมื่อพบแผนที่ต้องการเฝ้าดู ให้เลื่อนลงถึง **🧷 แผนเฝ้าดูที่ล็อกไว้** เลือกระยะเวลา 12/24/48/72 ชั่วโมงแล้วกด **ล็อก Entry Zone ปัจจุบันเป็นแผนเฝ้าดู**; คัดลอก URL ที่มี `?watch=` หรือเพิ่มเป็น Bookmark บนมือถือ **ต้องเปิดจาก URL นี้ครั้งหน้า** จึงจะเห็นโซนเดิม แม้แผนสดเปลี่ยนไป
5.2. อ่านสถานะแผนล็อก: `WAIT_ZONE` (ยังไม่ถึง), `WAIT_RECLAIM` (แตะแล้วรอแท่งปิด), `WAIT_BREAK` (รอยืนยัน), `READY_NOW` (ผ่านเงื่อนไขเชิงทดลอง), `INVALIDATED` / `PASSED` / `EXPIRED` (อย่าเข้าตามแผนเดิม) **แตะ Entry Zone ไม่ใช่คำสั่งซื้อ**
6. ในแท็บ **📊 สัญญาณละเอียด** ดูกราฟและแหล่ง Kraken/Binance/Bybit Futures แล้วกรอก CoinGlass เป็นตัวกรองเสริม; วางเลข CoinGlass 5 ค่าในช่องเดียวได้ เมื่อบันทึกแล้วกลับมาดูผล MTF รวม
7. หากขึ้น `MTF BUY BIAS · WAIT FOR ENTRY` หมายถึง **ทิศทางสนับสนุน แต่ยังไม่ถึงเงื่อนไขซื้อ**; กด **ทำไม MTF ยังรอ?** เพื่อดูเหตุผลและเวลาแท่งถัดไป
8. เปิดหัวข้อ **📚 Data Source Audit** และ **🔬 Professional Evidence Desk** เพื่อดู CVD/VWAP/POC, Bybit Spot + Futures, DefiLlama Liquidity และสถานะแหล่งข้อมูล เปิดหัวข้อ **🔎 ทำไม MTF ยังรอ?** เพื่ออ่านเกณฑ์หลักที่ผ่าน/ไม่ผ่าน **ทุกข้อ**
9. กด **💾 บันทึกสัญญาณ MTF นี้** แล้วดาวน์โหลด CSV; ถ้าเปิดเบราว์เซอร์ใหม่ ให้อัปโหลด CSV กลับเข้าแอปในส่วน Paper Journal. มีปุ่มตรวจ Stop/TP2 แบบสมมติหลัง READY จากแท่ง 1h สูงสุด 48 แท่ง (**ไม่ใช่การซื้อขายจริง และไม่ได้ยืนยัน Fill ที่ราคาเปิดแท่ง**)
10. ในแท็บ `Backtest` และ `Walk-forward` ดูผลเฉพาะกฎเทคนิคเดิม ส่วน **📈 MTF Research** กดทดสอบชุดกฎ MTF เฉพาะข้อมูล Spot ย้อนหลังได้ และต้องดูจำนวนดีลก่อนสรุปผล
11. iPhone: Safari → แชร์ → `Add to Home Screen` เพื่อมีไอคอนทางลัด; Android: Chrome → เมนู → `Add to Home screen` หากเบราว์เซอร์รองรับ

## ข้อจำกัดที่ต้องเข้าใจ

- แพ็กเกจโฮสต์ Community Cloud ฟรีอยู่ภายใต้นโยบายโควต้า/ทรัพยากรของผู้ให้บริการ อาจพักแอปหรือใช้เวลาปลุกแอปเมื่อไม่ได้เปิดนาน
- **แผนที่ล็อกไว้เดินทางไปกับ URL `?watch=` ไม่ได้บันทึกในฐานข้อมูล**: Bookmark นี้เป็นข้อมูลตัวเลขแผน ไม่ใช่ข้อมูลลับหรือ URL ที่ลงลายเซ็น; เปลี่ยนมือถือได้เมื่อคัดลอกลิงก์ครบ ห้ามเข้าเว็บจากลิงก์หน้าแรกเปล่าแล้วคาดว่าจะเห็นแผนเดิม
- **ตัวเว็บรีเฟรชราว 3 นาทีเฉพาะตอนเปิดพร้อมแผนล็อก**; เมื่อปิดเว็บจะไม่มี Push จากตัว Streamlit เอง. v4.1 เพิ่ม GitHub Actions + Telegram **เมื่อพรรณตั้งค่าตามคู่มือแยกแล้ว** ซึ่งอาจเลื่อน/ข้ามรอบได้; ไม่ใช่ราคาตลาด Tick-by-tick
- **กฎ Trigger v4.0 ยังไม่ผ่าน Backtest/Walk-forward แบบครบทุกแหล่งข้อมูล**; สถานะ READY_NOW เป็นข้อเสนอให้ตรวจสอบเอง ไม่ใช่โอกาสชนะที่รับรองและไม่ใช่ราคาที่รับประกันว่าจะซื้อได้
- URL ใช้ได้จากทุกที่ **เมื่อแอปออนไลน์และเครือข่ายเข้าถึงบริการได้**; ไม่ใช่การยืนยันว่าแอปทำงานตลอด 24 ชั่วโมง
- Repository `Public` = โค้ดเปิดเผย; แอปอาจเปิดเผยแก่ทุกคนที่มีลิงก์ด้วย ตั้งค่า Private ตามความเหมาะสมและตรวจสิทธิ์บน Streamlit อีกครั้ง
- ข้อมูล CoinGlass ที่กรอกอยู่ใน Streamlit session ของอุปกรณ์/เบราว์เซอร์ ไม่ซิงก์ข้ามเครื่อง และอาจหายเมื่อเซสชันสิ้นสุด อย่ากรอกข้อมูลส่วนตัวหรือรหัสผ่าน
- CoinGlass ไม่เชื่อม API ฟรีอัตโนมัติ; หากต้องการตัวกรอง CoinGlass ต้องกรอก Funding / OI / Long-Short / Liquidations เองและยืนยัน หากกรอกแล้วไม่ผ่านจะทำให้ WAIT
- **Order Book เป็นภาพ ณ ขณะร้องขอ ไม่ใช่ข้อมูลคำสั่งซื้อย้อนหลังหรือหลักฐานระบุตัวเจ้ามือ:** คำสั่งใน Book อาจถูกยกเลิก/ทำ Spoofing ได้; `aggTrades` และ Taker Buy เป็นธุรกรรมแบบไม่ระบุตัวตน จึงบอกไม่ได้ว่าเงินของรายใหญ่รายใดกำลังเข้าซื้อจริง
- ข้อมูลใหม่ของรุ่น Final: CVD จากแท่งปิดและ Candle VWAP/POC เป็นการประมาณ ไม่ใช่ Footprint Tick-level; Bybit Spot และ Bybit Futures แยกตลาดกันเสมอ; DefiLlama เป็นภาพรวม Stablecoin/DeFi ไม่ใช่ Exchange Whale Flows
- **แหล่งเสริมที่ดึงไม่ได้ไม่ถูกเติมด้วยตัวเลขสมมติ** และจะแสดงไม่พร้อมใน Data Source Audit; สัญญาณ READY ยังต้องผ่านแหล่งหลักและ Risk:Reward สุทธิตามเกณฑ์ทดลอง
- ค่าเกณฑ์ Spread, Bid Share, Aggressive Buy และ BTC Regime เป็น **heuristic ทดลอง** ยังไม่ได้พิสูจน์ประสิทธิภาพโดยการทดสอบ Full Signal จึงไม่ใช่คะแนนความแม่นยำที่ตรวจสอบแล้ว
- Auto Futures ลอง Kraken ก่อน (ทดสอบสด BTC และ PEPE ผ่านแล้ว) หากไม่พร้อมจึงใช้ Binance/Bybit โดยใช้ข้อมูลตลาดเดียวต่อครั้ง ไม่ผสมกัน; HTTP 451/403 และเครือข่ายโฮสต์อาจทำให้เป็น WAIT
- Backtest/Walk-forward เดิม **ไม่ได้** ทดสอบ Entry Zone/SL/TP1–TP2 ใหม่, กฎ Futures หรือ CoinGlass ย้อนหลัง; **MTF Research** เพิ่มการทดสอบ MTF/Entry แบบ Spot-only โดยยัง **ไม่รวม historical Order Book/Aggressor Trades/BTC Regime/Futures/Bybit/DefiLlama/CoinGlass หรือ Frozen Watch Trigger** ผลทุกส่วนจึงยังไม่รับรอง Full Signal v4.1
- `READY` เป็นเพียงการผ่านเกณฑ์ของแท่งที่ปิดแล้ว ต้องตรวจราคาที่ซื้อจริงและเงื่อนไขกระดาน; แม้จะมี Telegram แจ้งเตือนเมื่อเปิด GitHub Actions แล้วก็ไม่มีการซื้อขายอัตโนมัติ
- READY ยังต้องอาศัยราคา Spot ล่าสุดจาก Binance `ticker/price`; API นี้ไม่บอกเวลาของดีลล่าสุด จึงไม่ใช่คำรับรองว่าสามารถซื้อได้ที่ราคาเดียวกัน และหน้าเว็บไม่ได้อัปเดตเองทุกวินาที หากดึงไม่ได้จะเป็น `WAIT_LIVE_QUOTE`
- ระบบไม่ส่งคำสั่งซื้อขาย ไม่เชื่อม Exchange Account หรือเก็บ API key
- Binance public market API อาจถูกจำกัดตามภูมิภาคหรือเครือข่ายของโฮสต์ และอาจทำให้แอปโหลดข้อมูลไม่ได้
- Single MTF ใช้การเรียกแท่งเทียนทั้ง 4 กรอบมากกว่ารุ่นก่อน อาจใช้เวลารอเพิ่ม; หากบางกรอบล้มเหลว ระบบจะแสดง `WAIT` ไม่สร้างสัญญาณรวมหรือคะแนนแทนข้อมูลที่ขาด

## แก้ปัญหาที่พบบ่อย

| อาการ | วิธีตรวจ |
|---|---|
| `ModuleNotFoundError` | `requirements.txt` ต้องอยู่ใน repo และ `app.py` ต้องอยู่ระดับเดียวกับโมดูล Python |
| `No module named 'multi_timeframe'` หรือ `confluence` | อัปโหลด `multi_timeframe.py` และ `confluence.py` ไปที่ root ของ repo ระดับเดียวกับ `app.py` แล้วรีสตาร์ตแอป |
| `No module named 'market_microstructure'`, `btc_market`, `mtf_research`, `advanced_evidence`, `bybit_intelligence`, `macro_liquidity`, `risk_audit`, `journal_utils`, `watch_plans` หรือ `alert_monitor` | ยังไม่ได้อัปโหลดโมดูล Python ให้ครบ; คัดลอกจาก ZIP v4.1 ไปไว้ระดับเดียวกับ `app.py` |
| เปิดแอปใหม่แล้วโซนเปลี่ยน | นั่นคือ **แผน MTF สด**; ต้องเปิดจาก Bookmark URL ที่มี `?watch=` เพื่อเรียก **แผนล็อก**; ถ้าไม่มี URL ต้องล็อกแผนใหม่ |
| โซนแตะแล้วแต่ยังไม่ขึ้น READY | เป็นเจตนา: ต้องให้แท่ง 15m ปิดกลับเหนือโซน ตามด้วย Break/Retest และ MTF/Futures/R:R สดผ่าน; ถ้าข้อมูลขาดจะไม่ออก READY |
| MTF `WAIT` ทั้งที่กราฟ Spot เป็นขาขึ้น | คลิก **ทำไม MTF ยังรอ?** — ข้อมูล Futures, Order Book, Taker Flow, BTC, CoinGlass (ถ้ากรอก) หรือความสดอาจไม่ผ่าน; ระบบไม่เติมค่าปลอม |
| `File not found: app.py` | ตรวจ Main file path และโครงสร้าง repo (อย่าใส่ชื่อโฟลเดอร์เพิ่มถ้าไฟล์อยู่ root) |
| ไม่เจอเหรียญ | เปลี่ยนสกุลราคาเป็น `ทั้งหมด` หรือค้นรหัส เช่น `ETH` |
| Binance API ใช้ไม่ได้ | ดูข้อความ error; ถ้าโฮสต์ถูกจำกัด API ให้รอ/ลองใหม่ โดยไม่พยายามเลี่ยงข้อจำกัด |
| โหลดนาน/แอปเริ่มใหม่ | ลดแท่งเหลือ 1000–1500 และรอให้แอปตื่นจากการพัก |
| CoinGlass กลับเป็นค่าว่าง | ต้องกรอกใหม่ในเซสชันมือถือ; ไม่ได้เก็บกลางระบบ |

## ลิงก์ทางการ

- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app
- https://docs.streamlit.io/deploy/streamlit-community-cloud/status
- https://github.com/
- https://share.streamlit.io/
