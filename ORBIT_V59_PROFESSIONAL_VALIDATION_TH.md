# Orbit v5.9 — Professional Validation (Paper Evidence Only)

**ขอบเขต:** เพิ่มระบบตรวจสอบผลสัญญาณและเก็บประวัติจริงบน v5.8.5
โดย **ไม่แก้ `scalp_engine.py`, `scalp_fixed_tp.py`, `scalp_config.json`,
Stop Loss, Risk per Trade, Take Profit, Telegram หรือ Workflow เดิม**

## เพิ่มอะไร

| ส่วน | การทำงานจริง |
| --- | --- |
| Signal Journal | บันทึกสถานะ READY / WATCH / WAIT / RISK_BLOCK / DATA_UNAVAILABLE และเหตุผลทุกประมาณ 5 นาที |
| Paper Outcome | เริ่มสมมติที่ **ราคาเปิดแท่ง 1m ถัดจากเวลาสแกนจริง**; ไม่ใช้ราคาในอดีตไปเติมสัญญาณ |
| Cost Model | หัก Fee ทั้งสองข้าง, Spread ณ เวลาสแกน, Slippage สมมติจาก config เดิม |
| TP Choices | แยกผล TP1, TP2 และ PEPE +10 จุด (เฉพาะที่แผนผ่าน `ALTERNATIVE_READY`) |
| Ambiguous Candle | หาก SL และ TP ถูกแตะในแท่ง 1 นาทีเดียวกัน ให้ **SL ก่อน** เป็นค่าประเมินแบบระวัง |
| Data Gaps | ขาดแท่ง 1m หรือข้อมูลตลาดผิดจะ **ไม่เดา** ว่ากำไร/ขาดทุน |
| Paper Dashboard | แสดง Win Rate, Expectancy (R), Net USDT, Profit Factor, Max Drawdown, MFE/MAE |
| Missed Opportunity | วัดการขยับราคาไปในทิศทางที่เคยเฝ้าดู ภายใน 30 นาที เมื่อแท่งปิดครบเท่านั้น |
| Walk-Forward Report | เปรียบเทียบช่วง 7 วันแรกกับ 7 วันถัดไปแบบเลื่อนหน้าต่างตามเวลา; **ไม่ได้ฝึกโมเดลหรือปรับพารามิเตอร์** |
| Data Coverage | แยกจำนวนข้อมูลที่ตรวจได้ / API ล่ม / รอบที่ขาดช่วงในช่วงประวัติที่มีบันทึก |

## ข้อควรเข้าใจตรงกัน

1. นี่คือ **Paper Simulation** ไม่ใช่คำสั่งซื้อขายหรือผลบัญชีจริง ไม่มีการเชื่อม Private API,
   การตรวจยอด Position จริง, Partial Fill, Liquidity Impact หรือ Futures Funding ในผลลัพธ์
2. **ไม่อาจวัด Win Rate จริงทันที:** ต้องรอเริ่มบันทึกและให้เกิดสัญญาณ READY
   พร้อมข้อมูลแท่งในอนาคตครบเท่านั้น; อย่าสรุปจากตัวอย่างไม่กี่ไม้
3. การสแกน Workflow Validation แยกจาก Telegram จึงอาจเกิดต่างเวลาและไม่ตรงทุกสัญญาณ
4. เงื่อนไข Paper Entry: ต้องมีแท่ง 1m ถัดไปภายใน **180 วินาที** และ Open อยู่ห่าง
   Entry แผนไม่เกิน **0.3%**; เลียนแบบ Fill จริงไม่ได้และห้ามใช้แทนราคา Execution
5. Paper SL/TP ถูกตรวจจาก High/Low ของแท่ง **ที่ปิดแล้ว**; กรณีทั้งคู่เกิดในนาทีเดียว
   จะสมมติ Stop ก่อน ส่วนระยะที่เกิน 60 นาทีให้จำลอง Time Exit เฉพาะข้อมูลครบ
6. Missed Opportunity ไม่ใช่กำไรที่พลาด: มีเพียงการวัดว่า *ราคาเคยไปถึงระยะหนึ่ง*
   ไม่ยืนยันว่า Limit Order จะ Fill, Stop ไม่โดนก่อน หรือสุทธิหลังต้นทุนได้กำไร
7. Walk-Forward 7/7 วัน **เป็นรายงานตามลำดับเวลาเท่านั้น**
   ไม่ใช่หลักฐานความได้เปรียบเชิงสถิติและไม่ใช่ Backtest แบบปรับกลยุทธ์หลายรอบ
8. การปิดไม้ `Daily PEPE 10 จุด` บนหน้า Scalp เดิมยังเป็น checkbox เฉพาะ session;
   ระบบใหม่นี้ไม่เชื่อมยอดเงิน 100,000 บาทหรือแก้โหมดจำลองทุน `80 USDT` ของ Scalp
9. กราฟข้อมูลครั้งแรก **ไม่เติมย้อนหลังจำลอง** ต้องเริ่มเก็บด้วย Workflow ก่อน

## ไฟล์ใน ZIP อัปเดต

| ไฟล์ | การติดตั้ง |
| --- | --- |
| `mobile_ui.py` | แทนที่ไฟล์เดิมที่ root ของ repo (เฉพาะ UI) |
| `validation_history.py` | เพิ่มไฟล์ใหม่ที่ root |
| `validation_logic.py` | เพิ่มไฟล์ใหม่ที่ root |
| `validation_runner.py` | เพิ่มไฟล์ใหม่ที่ root |
| `.github/workflows/orbit-professional-validation.yml` | เพิ่มไฟล์ใหม่ในโฟลเดอร์ `.github/workflows/` |
| `tests/test_validation_v59.py` | เพิ่ม Test ใหม่ภายใต้ `tests/` |
| `ORBIT_V59_PROFESSIONAL_VALIDATION_TH.md` | คู่มือฉบับนี้ |

## ขั้นตอนใช้งาน

1. เปิด Repository `Punnipah/orbit-crypto-signal-lab` บน GitHub > branch `main`
   สำรอง commit เก่าก่อนอัปโหลด และ **แตก ZIP ออกก่อน** (GitHub ไม่แตก ZIP เอง)
2. อัปโหลด/สร้างไฟล์ตามตำแหน่งในตารางให้ครบ แล้ว Commit
3. รอ Streamlit Redeploy; ในแท็บ Scalp ต้องเห็น `v5.9`
   และกล่อง `🧪 Orbit v5.9 · Professional Validation / Paper Journal`
4. GitHub > Actions > `Orbit v5.9 Professional Validation (Paper Evidence Only)`
   > `Run workflow` > `dry_run` (ไม่เขียนไฟล์/ไม่ส่ง Telegram)
5. ตรวจ log `Verified coverage` มากกว่า 0 จึงถือว่าทดลองดึงตลาดผ่าน
   `HTTP 451/403` หมายถึงตลาดนั้น **ใช้ไม่ได้จริงจาก Runner** ไม่ใช้ข้อมูลตลาดอื่นแทน
6. Run `record` หนึ่งครั้งเพื่อเริ่มเก็บ จากนั้น schedule จะพยายามทำงานทุกประมาณ 5 นาที
7. GitHub จะสร้าง branch ใหม่ `orbit-validation-history` เก็บไฟล์บีบอัด
   `.orbit-validation/days/YYYY-MM-DD.json.gz` (วันที่ตาม UTC)
8. บนหน้า Scalp ขยายกล่อง Validation > ติ๊ก `โหลดประวัติการตรวจสัญญาณ`
   > เลือกย้อนหลัง 1/7/30 วัน / TP1, TP2 หรือ PEPE 10 จุด และ Export CSV

## สิทธิ์และข้อจำกัดการเก็บ

- GitHub > Settings > Actions > General > Workflow permissions >
  **Read and write permissions** เพื่อให้ `GITHUB_TOKEN` เขียน branch ประวัติใหม่ได้
- **ไม่ต้องเพิ่ม Secret ใหม่** และไม่ต้องเปิด API สั่งซื้อขาย
- Workflow ใหม่ไม่อ่าน/เขียน `orbit-scalp-state`, `orbit-whale-history`, branch `main`
  หรือ Telegram state (นอกจากเช็กเอาต์ source สาธารณะตามปกติ)
- เก็บไฟล์วันละไฟล์, UI อ่านได้สูงสุด 30 วันตามที่ผู้ใช้เลือก
  แต่เก็บไฟล์เก่าบน branch ต่อไป ไม่ลบข้อมูลเดิมให้เอง
- GitHub Actions แบบ Schedule เป็น **best effort** ไม่รับประกันตรงรอบหรือ 24/7
  เมื่อมี Data Gap ระบบจะเปิดเผยว่าไม่มีข้อมูลเพียงพอ
- การอัปเกรดรอบนี้เป็น **เฉพาะแพ็กเกจโค้ด** ยังไม่ได้แก้ไข GitHub หรือเปิด Workflow ให้

## ตรวจสอบก่อนใช้

```bash
PYTHONPATH=orbit_crypto_signal_lab python -m unittest discover -s orbit_crypto_signal_lab/tests -q
python -m compileall -q orbit_crypto_signal_lab/validation_logic.py orbit_crypto_signal_lab/validation_history.py orbit_crypto_signal_lab/validation_runner.py orbit_crypto_signal_lab/mobile_ui.py
```

การทดสอบออฟไลน์รวม **329 รายการ ผ่าน** (`skipped=3`) ณ เวลาจัดแพ็กเกจ.
ไม่ได้ทดสอบการแสดงผล Streamlit บน Hosting จริงในเครื่องนี้ (ไม่ติดตั้ง Streamlit)
ต้องทดสอบ `dry_run` ใน GitHub Actions หลัง Deploy และตรวจข้อมูลจริงในแอปอีกครั้ง
