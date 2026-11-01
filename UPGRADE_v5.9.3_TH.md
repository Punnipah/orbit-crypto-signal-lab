# Orbit v5.9.3 — Signal Recovery

อัปเดตแกน Scalp ของ v5.9.2 โดย **ไม่เปลี่ยน Stop Loss / ทุน / Risk Management / ค่าตั้งใน scalp_config.json / Telegram เดิม**.

## สิ่งที่แก้จริง

1. `scalp_engine.py`: เมื่อ 15m เป็นเทรนด์และไม่มี 5m Breakout อนุญาตให้ประเมินรูปแบบ **5m Pullback Rejection**; ใช้แท่งปิดและ Volume เกณฑ์เดิม แล้วรอแท่ง 1m ปิดที่ผ่าน Volume/Directional Flow เช่นเดิม. หากค่าธรรมเนียม/Spread/Order Book/SL/Net R:R ไม่ผ่าน ระบบยังขึ้น `RISK_BLOCK`.
2. `scalp_bitget.py`: เมื่อประวัติ 100 ธุรกรรมไม่พอ จะลอง API ประวัติสาธารณะ Bitget สูงสุด 3 หน้า (1,000 รายการ/หน้า). ต้องมีธุรกรรมครอบคลุมแท่งครบช่วงเวลาและรวมปริมาณได้ใกล้ 1m candle volume ±5%. ถ้าไม่ได้จะ **ไม่เดา** directional Flow.
3. `futures_data_health.py`, `scalp_marketdata.py`: แยกสถานะ `FLOW_UNAVAILABLE` / `FUTURES_FLOW_VERIFIED`; ติดตามว่าตัวแปร flow ถูก reconcile จริงหรือไม่.
4. `mobile_ui.py`: ข้อความและสถานะชัดขึ้น; เมื่อเข้า Scalp ครั้งแรกจะใช้เหรียญที่เลือกจาก Spot ก่อนหน้า ถ้ารองรับ; ไม่บังคับเปลี่ยนเหรียญเมื่อเลือกเองแล้ว.

## วิธีอัปเดต GitHub / Streamlit

1. สำรองไฟล์ v5.9.2 ที่ใช้งานอยู่ก่อน (เช่น ดาวน์โหลด ZIP ของ Repository หรือใช้ Git commit ที่ยังย้อนกลับได้).
2. แตก `Orbit_v5.9.3_Signal_Recovery.zip` **บนเครื่องก่อน**. ไฟล์ในแพตช์จะอยู่ใต้โฟลเดอร์ `orbit_crypto_signal_lab/`.
3. ใน GitHub Repository ที่ Deploy Streamlit ให้วางหรืออัปโหลดไฟล์ชื่อเดียวกันใน **ตำแหน่ง root จริงของ repo** (ถ้า repo เดิมมี `app.py` อยู่ระดับบนสุด ให้เอาไฟล์จากข้างในโฟลเดอร์นั้นขึ้นไปวางคู่กับ `app.py`). อย่าเพิ่มโฟลเดอร์ซ้อนใหม่โดยไม่ตั้งใจ.
4. Commit การเปลี่ยนแปลงและรอ Streamlit redeploy. เปิดแอปแล้วเช็กหัวแอป `V5.9.3` และหน้า Scalp `v5.9.3`. จากนั้นลองสลับ Spot PEPE / Futures Bitget และกดตรวจตลาดล่าสุด.
5. ทดสอบกับเงินจำลองก่อน และบันทึก `READY / WATCH / RISK_BLOCK / DATA_UNAVAILABLE` กับราคาหลังแท่งปิดต่อเนื่อง เพื่อดูว่าการเพิ่มจุดเข้าช่วยจริงหรือเพิ่มสัญญาณผิด.

## สิ่งที่ยัง *ไม่* สามารถรับประกัน

- ไม่ได้ข้ามข้อจำกัด HTTP 451/403 ของ Binance Global/Bybit. หากข้อมูล Futures ตลาดนั้นเข้าไม่ได้ ยังไม่มีสัญญาณ `READY` จากตลาดนั้น.
- ราคา Spot ของ Binance TH ไม่ใช่ราคา Futures ของ Bitget/Binance Global. ห้ามใช้แผนคนละตลาดแทนกัน.
- Bitget public `side=buy/sell` เป็นปริมาณซื้อขายสาธารณะตามทิศทางที่ API ให้มา ไม่ใช่ certified aggressor flow. หากไม่ตรงกับ OHLC volume จะไม่ผ่าน.
- 3,000 รายการอาจยังไม่พอสำหรับเหรียญที่ซื้อขายหนาแน่น; แสดง `FLOW_UNAVAILABLE` ได้ ซึ่งเป็นการป้องกันข้อมูลเท็จ.
- `PULLBACK_REJECTION` ยังไม่ผ่านการพิสูจน์ผลตอบแทน Out-of-sample หลังค่าธรรมเนียม/Slippage/Funding/Fill และยังไม่ใช่คำแนะนำเข้าเทรดเงินจริง.

## ตรวจโค้ดโดยไม่ต้องเชื่อม Exchange

จากโฟลเดอร์โปรเจกต์ที่มี `app.py`:

```bash
python -m unittest discover -s tests -q
```

แหล่ง API: https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market (Get History Transactions)
