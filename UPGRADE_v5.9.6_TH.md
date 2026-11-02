# Orbit v5.9.6 — Institutional-style Flow & Liquidity Radar

**เผยแพร่แพตช์สำหรับติดตั้งเอง — ยังไม่ได้อัปเดตเว็บ Streamlit ของคุณโดยอัตโนมัติ**

## ทำไมไม่ทำให้ BUY ทุกวัน

โมเดลที่ใช้ในตลาดจริงมีหลายชนิด: บางตัววัดแรงคำสั่งซื้อขาย, บางตัวเป็นระบบจัดวาง Bid/Ask ของ Market Maker, บางตัวใช้เฉลี่ยต้นทุนในการส่งคำสั่งขนาดใหญ่. ไม่มีหลักฐานว่าเทรดเดอร์รายย่อยสามารถระบุได้ว่าเจ้ามือหรือวาฬคนไหนกำลังทำอะไรจากแท่งเทียนกับ Order Book แค่ภาพเดียว. การเร่งให้มี BUY รายวันโดยลดข้อจำกัด Spread/SL/ค่าธรรมเนียม/Net R:R อาจเพิ่มจำนวนไม้ที่ไม่คุ้มต้นทุน.

งานวิจัยสาธารณะที่ใช้เป็นพื้นฐาน:

1. **Cont, Kukanov & Stoikov (2014), *The Price Impact of Order Book Events*.** Order Flow Imbalance ใช้การเปลี่ยนแปลงคำสั่งที่ Best Bid/Ask ตามเวลา; Orbit ยังไม่มี L2 event stream จึง **ห้าม** อ้างว่า Bid Depth Share snapshot คือ OFI: https://academic.oup.com/jfec/article-abstract/12/1/47/816163
2. **Avellaneda & Stoikov (2008), *High-frequency Trading in a Limit Order Book*.** แบบจำลอง Market Maker ที่บริหารความเสี่ยงจากราคา/Inventory และ Bid/Ask; ใช้เป็นหลักคิดสภาพคล่องเท่านั้น ไม่ใช่ BUY indicator: https://doi.org/10.1080/14697680701381228
3. **Almgren & Chriss (2001), *Optimal Execution of Portfolio Transactions*.** เน้นต้นทุน, Volatility และ Market Impact จากการซื้อขาย; Orbit จึงรักษา Cost/Risk Gate: https://doi.org/10.21314/JOR.2001.041
4. **Binance Spot API — Market Data / Kline / Depth.** ข้อมูลแท่งเทียนมีช่อง Taker Buy Base Volume; สามารถดู Snapshot Depth แต่ข้อมูลนี้ไม่อ้างตัวตนคนซื้อ: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md

## รูปแบบที่เปิดให้ดูในหน้า Scalp

| โมเดลทดลอง | ระดับเฝ้าดู | เงื่อนไขจากแท่งปิดแล้ว | เงื่อนไขที่อาจบล็อก |
|---|---|---|---|
| Liquidity Sweep → Reclaim | Low/High 20×5m ก่อนหน้า | แทงทะลุขอบกรอบ แต่ปิดกลับพร้อม Volume | Buy/Sell Flow 1m, ราคาไม่ยืนขอบ, ต้นทุน/Net R:R |
| Breakout → Retest | ขอบกรอบ 20×5m ก่อนแท่ง Breakout | Breakout ปิดผ่านขอบ แล้วแท่งถัดไปรีเทสต์/ปิดยืน | Volume ของแท่งทะลุและแท่งรีเทสต์, Flow, ต้นทุน |
| Rolling VWAP Reclaim | VWAP จากราคากลางแท่ง 48×5m ถ่วง Volume | แท่งก่อนหน้าอยู่ผิดฝั่ง VWAP แล้วแท่งล่าสุดปิดกลับ | Flow, Volume, Spread, Stop และ Net R:R |

**หมายเหตุ:** สถานะ `SETUP WATCH` แปลว่าเงื่อนไขการสังเกตตรงและตรวจบาง Cost/Risk เบื้องต้นแล้ว แต่ **ไม่ใช่ READY**. Stop/TP/Entry ที่เห็นเป็นแผนทฤษฎี ไม่ได้คำนวณขนาดออร์เดอร์, วงเงินรายวัน, slippage จากสภาพตลาดจริง ณ เวลาส่งคำสั่ง และไม่ได้ผ่านการทดสอบ Out-of-Sample. Spot ขาลงแสดง `EXIT WATCH` ไม่เปิด SHORT.

ข้อมูลราคา/Volume ต้องเป็นของตลาดเดียวกันที่เลือก; Bitget หากไม่สามารถยืนยันข้อมูล Buy/Sell Flow ได้ ระบบแสดง `FLOW BLOCK`; HTTP 451/403 หรือข้อมูล Futures ไม่ครบยังเป็น `DATA UNAVAILABLE` ตามเดิม. ไม่ใช้ข้อมูล Spot ทดแทน Futures.

## ตรวจความถี่พื้นฐานบน PEPE Binance TH

ใช้ไฟล์ราคา PEPE 5m/1m ที่มีในชุดทดสอบ `tests/pepe_binanceth_30d_data` ตั้งแต่ **29 ก.ย. 2026 เวลา 21:00 UTC ถึง 31 ต.ค. 2026 เวลา 08:55 UTC** จำนวน **9,072 แท่ง 5m**. ใช้เงื่อนไขการตรวจ Pattern + Volume 1.10x และคำนวณ Buy Flow จาก 1m ปิด 3 แท่งในช่วงประมาณ 2 นาทีหลังแท่ง 5m ปิด; ไม่มีข้อมูล Bid/Ask, Spread, Depth แบบย้อนหลังครบสำหรับตรวจ Risk Gate จริง.

| รูปแบบซื้อ (Long Spot) | พบ Pattern+Volume | บวก Flow Buy 1m และระดับยังยืน | ข้อควรทราบ |
|---|---:|---:|---|
| Sweep/Reclaim | 33 | 16 | ก่อน SL/TP, Spread และค่าธรรมเนียม |
| Rolling VWAP Reclaim | 83 | 46 | ก่อน SL/TP, Spread และค่าธรรมเนียม |

**ห้ามเรียกตารางนี้ว่า Backtest หรืออัตราชนะ**: เป็นเพียงจำนวนเหตุการณ์ย้อนหลัง; หลายเหตุการณ์อาจทับซ้อนหรือเป็นโอกาสที่ไม่มีทางเข้าซื้อได้จริง. ก่อนใช้เงินจริงต้องทำ walk-forward, paper trade พร้อม bid/ask, การปัด tick/qty, stop-first ในแท่งเดียวกัน, fee/slippage และ market-impact ที่สมจริง.

## ติดตั้งลง GitHub / Streamlit

1. สำรองไฟล์ `mobile_ui.py` ที่อยู่บน GitHub ปัจจุบันไว้ก่อน.
2. หากยังไม่ติดตั้ง **v5.9.5**, ต้องเพิ่ม `model_radar.py` ด้วย (v5.9.6 เรียกใช้โมดูลนี้). ถ้าติดตั้งแล้วไม่ต้องแก้อะไรในไฟล์นี้.
3. เพิ่มไฟล์ใหม่ `institutional_radar.py` และวางทับ `mobile_ui.py` จากแพตช์นี้. ปรับ `README.md` และเพิ่มคู่มือไฟล์นี้ถ้าต้องการ.
4. **ไม่ต้องแก้** `scalp_config.json`, `scalp_engine.py`, `spot_range_bounce.py`, `.github/workflows`, Telegram secrets หรือส่วน MTF/Futures เดิม.
5. รอ Streamlit Deploy แล้วเปิด **Scalp → Spot Binance TH → PEPEUSDT**. หลัง Hero ของ Scalp จะเห็น `Model Radar` เดิมและ `Institutional-style Radar` ใหม่ด้านล่าง. กดปุ่ม **ตรวจข้อมูลตลาดล่าสุด**.
6. ทดสอบออฟไลน์ได้ด้วย `python -m unittest discover -s tests -q`.

## ข้อจำกัดการใช้งาน

- Radar ทำงานเฉพาะช่วงที่เปิดหน้า Scalp; ไม่ได้ส่ง Alert อัตโนมัติ 24 ชั่วโมง. การเพิ่ม Telegram ต้องสร้างขั้นตอนทดสอบและความเสี่ยงแยกต่างหาก.
- ห้ามนำรูปแบบราคาแบบ `Liquidity Sweep` ไปกล่าวว่าเป็นการจงใจล่าจุด Stop โดยเจ้ามือ เพราะ Order Book สาธารณะไม่ยืนยันเจตนาหรือตัวตน.
- โมเดลเหล่านี้เป็น **แนวคิดปรับใช้จากงานวิจัยสาธารณะและเทคนิค Price Action** ไม่ใช่ซอร์สโค้ดที่คัดลอกจากผู้เขียนคนอื่นหรือระบบลับจากสถาบัน.
- ไม่มีโมเดลใดรับประกันกำไร หรือทำให้ต้องเกิดสัญญาณซื้อทุกวัน; หาก Risk Gate ไม่ผ่าน การแสดง WAIT/BLOCK คือพฤติกรรมที่ถูกต้อง.
