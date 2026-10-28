# นำ Orbit Crypto Signal Lab ขึ้นมือถือฟรี — ทีละขั้น

ชุดนี้พร้อมนำไปใช้กับ **Streamlit Community Cloud** โดยไม่ต้องมีคอมพิวเตอร์เปิดโปรแกรมตลอดเวลา
แต่ต้องใช้บัญชี **GitHub** และ **Streamlit Community Cloud** ของคุณเองเพื่อเผยแพร่แอป

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
6. ตรวจว่ามี `app.py`, `requirements.txt`, `binance_data.py`, `analysis_engine.py`, `research_engine.py`, `market_structure.py`, `backtest_engine.py`, `coinglass_overlay.py` ครบ
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
4. เลือกคู่เหรียญ, Timeframe, จำนวนแท่งประวัติ; มือถือแนะนำเริ่มที่ **1000–1500 แท่ง** เพื่อลดเวลารอ
5. ในแท็บ `สัญญาณ` กรอกตัวเลข CoinGlass **ด้วยตัวเอง** เพื่อขอ Final BUY/SELL/WAIT
6. ในแท็บ `Backtest` และ `Walk-forward` ดูผลเฉพาะกฎเทคนิค โดยตรวจจำนวนเทรดก่อนเชื่อถือผล
7. iPhone: Safari → แชร์ → `Add to Home Screen` เพื่อมีไอคอนทางลัด; Android: Chrome → เมนู → `Add to Home screen` หากเบราว์เซอร์รองรับ

## ข้อจำกัดที่ต้องเข้าใจ

- แพ็กเกจโฮสต์ Community Cloud ฟรีอยู่ภายใต้นโยบายโควต้า/ทรัพยากรของผู้ให้บริการ อาจพักแอปหรือใช้เวลาปลุกแอปเมื่อไม่ได้เปิดนาน
- URL ใช้ได้จากทุกที่ **เมื่อแอปออนไลน์และเครือข่ายเข้าถึงบริการได้**; ไม่ใช่การยืนยันว่าแอปทำงานตลอด 24 ชั่วโมง
- Repository `Public` = โค้ดเปิดเผย; แอปอาจเปิดเผยแก่ทุกคนที่มีลิงก์ด้วย ตั้งค่า Private ตามความเหมาะสมและตรวจสิทธิ์บน Streamlit อีกครั้ง
- ข้อมูล CoinGlass ที่กรอกอยู่ใน Streamlit session ของอุปกรณ์/เบราว์เซอร์ ไม่ซิงก์ข้ามเครื่อง และอาจหายเมื่อเซสชันสิ้นสุด อย่ากรอกข้อมูลส่วนตัวหรือรหัสผ่าน
- CoinGlass ไม่เชื่อม API ฟรีอัตโนมัติ ต้องกรอก Funding / OI / Long-Short / Liquidations เอง; ข้อมูลขาดหรือเก่า = WAIT
- Backtest/Walk-forward **ไม่** ได้ทดสอบกฎ CoinGlass ย้อนหลัง ผลทดสอบไม่ได้ยืนยันว่าเทรดทำกำไรจริง
- ระบบไม่ส่งคำสั่งซื้อขาย ไม่เชื่อม Exchange Account หรือเก็บ API key
- Binance public market API อาจถูกจำกัดตามภูมิภาคหรือเครือข่ายของโฮสต์ และอาจทำให้แอปโหลดข้อมูลไม่ได้

## แก้ปัญหาที่พบบ่อย

| อาการ | วิธีตรวจ |
|---|---|
| `ModuleNotFoundError` | `requirements.txt` ต้องอยู่ใน repo และ `app.py` ต้องอยู่ระดับเดียวกับโมดูล Python |
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
