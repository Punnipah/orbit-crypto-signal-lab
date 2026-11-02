# อัปเกรด Orbit v5.9.5 — Model Radar (ยังไม่ใช่ระบบปล่อยสัญญาณอัตโนมัติ)

## ตรวจพบสาเหตุที่ v5.9.4 ไม่มีสัญญาณบ่อย

วันที่ 2 พฤศจิกายน 2026 (เวลาไทย) ตรวจบนเว็บ Streamlit ที่กำลังเผยแพร่:

1. **Futures Day Trade:** Binance Global USD-M ตอบ `HTTP 451`, Bybit `HTTP 403` จึงใช้ Kraken USD Perpetual สำรองแบบ WATCH ONLY โดยไม่มีข้อมูล Taker Flow ที่ตรวจสอบให้เป็น READY ได้. ต้องมีตลาด Futures ที่เข้าถึงได้และข้อมูลจำเป็นครบก่อน; การเพิ่มกลยุทธ์อย่างเดียวไม่แก้จุดนี้.
2. **Binance TH Spot / PEPE Scalp:** พบ SIDEWAYS แต่ Net R:R ประมาณ `0.47:1` หลังต้นทุนจึงเป็น `RISK BLOCK`, ไม่ใช่ข้อผิดพลาดที่ควรเลี่ยง.
3. **Bitget Futures:** มีแท่ง ราคา และ Spread ได้ แต่ข้อมูล buy/sell flow บางช่วงไม่ครบ; ระบบยังต้องใช้การตรวจสอบข้อมูลให้ผ่านตามเดิม.

## หลักการที่ศึกษาและนำมาดัดแปลง

| แหล่ง | แนวคิด | สิ่งที่ทำใน Model Radar |
|---|---|---|
| QuantConnect | Bollinger Mean Reversion | 5m ปิดกลับเข้า BB20 หลังหลุดขอบโดยใช้ 15m ADX คัดกรองไม่สวนเทรนด์แรง |
| TradingView | Bollinger Bands Directed Long/Short | ด้าน Short ใช้เฉพาะ Futures ไม่ให้ Spot เปิด Short |
| Freqtrade / Jesse | Backtest, Dry Run, ห้ามมองเห็นแท่งอนาคต | อ่านเฉพาะ Closed Candles และแยก Watch จาก READY ที่ผ่าน Risk Gate เต็ม |

แหล่งอ่าน: https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/behavioral-finance

https://www.tradingview.com/support/solutions/43000599826-bollinger-bands-strategy-directed/

https://www.freqtrade.io/en/stable/strategy-customization/

https://docs.jesse.trade/

## ติดตั้ง

1. ระบบ GitHub เดิมควรอยู่ `v5.9.4` แล้ว; เก็บสำเนา `mobile_ui.py` เดิมก่อนอัปเดต.
2. วางทับ `mobile_ui.py`; เพิ่มไฟล์ใหม่ `model_radar.py` ในโปรเจกต์เดียวกัน.
3. เก็บไฟล์ทดสอบ `tests/test_model_radar_v595.py` และปรับ `README.md` ได้ตามต้องการ.
4. **ไม่ต้องแก้** `scalp_config.json`, `.github/workflows`, Telegram Secrets, `scalp_engine.py`, `spot_range_bounce.py`, หรือไฟล์เฝ้าตลาด Futures เดิม.
5. เมื่อ Streamlit โหลดสำเร็จ เปิด `Scalp → PEPEUSDT` จะเห็น `Model Radar` ถัดจากสถานะหลัก.

## ข้อจำกัดสำคัญ

- `MODEL WATCH` คือ **สัญญาณวิจัย** ไม่ใช่ `READY` และไม่ส่ง Telegram/ออร์เดอร์. หากราคาไปไกลแล้ว ระบบอาจแสดง NO PATTERN เพราะไม่ไล่ย้อนหลัง.
- ค่าราคา Stop/Target ของโมเดลเป็นระดับจำลอง ไม่ผ่าน Order Book, Flow, Daily Risk Budget และเงื่อนไข READY เดิมโดยอัตโนมัติ.
- แนวคิดจากตัวอย่างผู้พัฒนาอื่นไม่สามารถอ้าง Win Rate ของสินทรัพย์หรือ Timeframe ต้นฉบับมาใช้กับ PEPE ได้. ต้องทดสอบ Out-of-Sample / Walk-forward พร้อม Spread จริงและค่าใช้จ่ายก่อนใช้งานจริง.
- ห้ามนำ Kraken USD Perpetual ไปแทน Binance USDT-M โดยตรง; อย่าใช้ VPN หลบข้อจำกัดตลาด/API.
