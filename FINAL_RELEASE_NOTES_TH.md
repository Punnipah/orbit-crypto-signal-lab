# Orbit Professional Signal Lab — Final Release v3.0

วันที่เตรียมชุดส่งมอบ: 28 ตุลาคม 2026 (เวลาไทย)

## ใช้ได้อย่างไร

- เลือกเหรียญหนึ่งคู่ (เช่น BTCUSDT / PEPEUSDT) แล้วเปิด `🎯 สัญญาณ MTF รวม` เพื่อดูผลรวมหนึ่งชุด พร้อมแผน Entry Zone / Stop Loss / Take Profit 1–2 และเงื่อนไขเชิงทดลองที่ต้องผ่าน
- หลักฐาน Spot: 15m + 1h + 4h + 1d, pivots/BOS/sweep, RSI/ADX/EMA/Volume, Binance Spot Book, Aggressive Trades, Taker Buy, CVD, VWAP/POC จากแท่งโดยประมาณ
- หลักฐาน Futures สาธารณะ: Kraken → Binance → Bybit fallback เดิม โดยใช้แหล่งเดียวต่อการประเมิน Futures; เพิ่ม Bybit Spot Book/Trades และ Bybit Linear Perpetual OI/Funding เป็น **หลักฐานประกอบแยกตลาด** เท่านั้น
- BTC macro regime 4h/1d; DefiLlama Free market-level USD-pegged Stablecoin Market Value และ DeFi TVL เมื่อข้อมูลพร้อม; CoinGlass เป็นตัวกรองกรอกเอง
- Risk:Reward สุทธิตาม fee/slippage จำลองต้องผ่านเกณฑ์ที่ตั้งไว้ก่อน READY; มี source audit และแสดงกรณีข้อมูลหาย ไม่ปลอมข้อมูล
- `📈 MTF Research` ทดสอบข้อมูล Spot ย้อนหลังบางส่วน, `📝 Paper Journal` บันทึกสัญญาณ CSV, นำเข้าไฟล์กลับได้, ประเมินการชน Stop/TP2 หลัง READY **แบบสมมติ** จากแท่ง 1h ถัดไปสูงสุด 48 แท่ง

## การทดสอบก่อนส่งมอบ

- Unit/Regression + Streamlit AppTest รวม **107 กรณีผ่าน** เมื่อรันทดสอบใน Python 3.12 พร้อม Streamlit 1.66.1, pandas 3.1 และ Plotly 7.1 (รวมกรณีข้อมูลสาธารณะขาดและพร้อมแบบ mock)
- ทดสอบ Public API สดจากสภาพแวดล้อมพัฒนา: **Binance BTCUSDT Spot** (250 แท่งและ 500 Aggregate Trades), **Kraken Futures BTC** (Funding/OI/L-S snapshot), **DefiLlama Stablecoin Charts และ DeFi TVL** ส่งข้อมูลสำเร็จ
- **Bybit API ใช้งานไม่ได้จากเครือข่ายทดสอบในครั้งนี้** จึงเป็นข้อมูลเสริม `MISSING` โดยไม่ปนค่าจากตลาดอื่น; การเข้าถึงของ Streamlit Cloud อาจต่างออกไป
- **ยังไม่ได้ทดสอบการ deploy บน Streamlit Cloud ของผู้ใช้จริง** และยังไม่ได้พิสูจน์ Full Signal v3.0 แบบครบทุกชั้นใน Backtest/Walk-forward

## สิ่งที่เป็นไปไม่ได้จะไม่อ้างว่ามี

1. ไม่ระบุตัวเจ้ามือหรือผู้ถือรายใหญ่จาก Order Book/Taker Trades และไม่รู้คำสั่งที่ถูกซ่อนหรือถูกถอน
2. ไม่ได้แสดง Liquidation Heatmap, Whale Wallet Labels, Token Unlock และ ETF Flow ครบทุกเหรียญแบบ Public API ฟรี
3. CoinGlass API ทางการต้องใช้ Key และแพ็กเกจที่รองรับ; ไม่มีการข้ามข้อจำกัดสิทธิ์หรือ Scrape เว็บ
4. แหล่ง Public Futures มีข้อจำกัดคู่เหรียญ หน่วยสัญญา อายุข้อมูล และการเข้าถึงเครือข่าย; Futures ไม่พร้อม = Final WAIT
5. ไม่เก็บความลึก Order Book ต่อเนื่องตลอด 24 ชม. บนโฮสต์ฟรี; ข้อมูล Journal อยู่ใน Session จนกว่าจะดาวน์โหลด CSV
6. ผลย้อนหลังจำลองไม่ใช่ผลซื้อขายจริง และไม่ยืนยัน Win Rate, ความสามารถทำกำไร หรือความเหนือกว่าตลาด

## อัปเดต GitHub

แตก ZIP → เปิดโฟลเดอร์ `orbit_crypto_signal_lab` → อัปโหลด **ทุกไฟล์ด้านใน** ไปยัง root ของ Repository เดิม (ให้ `app.py` และ `requirements.txt` อยู่ระดับหลักเดียวกัน) → Commit → รอ Streamlit Cloud อัปเดต → เปิด URL เดิมบนมือถือ. ไม่ต้องสร้างบัญชี Exchange หรือใช้ API Key สำหรับ Public Market Data

โปรดดู `DEPLOY_MOBILE_TH.md` และ `README.md` สำหรับรายละเอียดทั้งหมด
