# Orbit Crypto Signal Lab v2.1 — Windows + มือถือผ่านเว็บ

โปรแกรมวิเคราะห์สัญญาณคริปโตแบบอ่านข้อมูลอย่างเดียว ใช้เครื่องมือฟรี ไม่เชื่อมบัญชีซื้อขาย ไม่มี API Key หรือคำสั่งส่งออเดอร์

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

| รายการ | สถานะ v2.0 |
|---|---|
| ค้นหาคู่เหรียญ Spot ที่อยู่ใน Binance Public Catalog | ได้ (รหัสเหรียญ / ชื่อสามัญบางเหรียญ) |
| ดึงข้อมูลราคาแบบไม่ต้องมีบัญชีหรือ API Key | ได้ผ่าน Binance public market-data-only API |
| วิเคราะห์ EMA20/50/200, RSI14, MACD, ADX, ATR, Volume Breakout | ได้ |
| วิเคราะห์หลาย Timeframe | 15m→1h, 1h→4h, 4h→1d, 1d ไม่มีการยืนยันซ้ำ |
| Confirmed Pivots, BOS, CHoCH, Liquidity Sweep | ได้ (เป็นกฎเชิงปริมาณเบื้องต้น) |
| คำนวณ SL/TP/ขนาดสถานะ | ได้เมื่อ BUY ผ่าน CoinGlass |
| Backtest แบบ Long-only Spot พร้อมค่าธรรมเนียม/Slippage | ได้ — **เฉพาะกลยุทธ์เทคนิค** |
| Walk-forward ปรับเกณฑ์คะแนนบน Train แล้วทดสอบช่วงถัดไป | ได้ — **เฉพาะกลยุทธ์เทคนิค** |
| CoinGlass Funding/OI/Long-Short/Liquidations | กรอกเองใน Dashboard |
| Final BUY/SELL/WAIT เมื่อข้อมูล CoinGlass สดและผ่านกฎ | ได้ |
| Auto Telegram / Auto Trading | ไม่มี |

## แหล่งข้อมูลและความถูกต้อง

- ข้อมูลราคาใหม่/ย้อนหลังใช้ **Binance Spot public market-data-only endpoints**: `https://data-api.binance.vision/api/v3` (ใช้ `/exchangeInfo`, `/klines` อย่างเดียว)
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

**ข้อจำกัด:** Backtest/Walk-forward ของ v2.0 ยังคงไม่รวม CoinGlass เพราะยังไม่มีชุดข้อมูล CoinGlass ย้อนหลังที่ได้รับสิทธิ์มาอย่างถูกต้อง จึงห้ามอ้างว่าผลของ Full Signal ที่รวม CoinGlass ผ่าน Backtest แล้ว

## CoinGlass แบบฟรี — ไม่มีบัญชี/API Key

1. เปิด https://www.coinglass.com/ และดูข้อมูลที่เข้าถึงได้ตามปกติ
2. คัดลอก Funding Rate, OI Change 24h, Long/Short Accounts Ratio และ Liquidations ของ Long/Short ช่วง 24h ที่อยู่ในหน่วยเดียวกัน
3. กรอกค่าพร้อมวันและเวลาไทยในหัวข้อ CoinGlass ของแดชบอร์ด และยืนยันความถูกต้อง
4. Final Signal จะเป็น BUY/SELL ได้ต่อเมื่อสัญญาณเทคนิคและข้อมูล CoinGlass ที่ใหม่พอสอดคล้องกัน มิฉะนั้น WAIT

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

โปรแกรมนี้เป็นเครื่องมือวิจัย/สนับสนุนการตัดสินใจ ไม่ใช่คำแนะนำการลงทุนเฉพาะบุคคล
