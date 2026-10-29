# ตั้งค่า Orbit v4.1 — Telegram แจ้งสัญญาณ PEPE / BTC / DOGE ทุก 15 นาที (วิธีฟรี)

เวอร์ชันนี้มี **2 ส่วนแยกกัน**:

1. **เว็บ Orbit** บน Streamlit ใช้เลือกเหรียญ ล็อก Entry Zone และอ่านหลักฐานตลาด
2. **ตัวตรวจ GitHub Actions** รันตามเวลาโดยไม่ต้องเปิดเว็บ แล้วส่ง Telegram เมื่อสถานะสำคัญเปลี่ยน

> **ข้อจำกัด:** GitHub Actions เป็นตัวตั้งเวลาแบบ *best effort* อาจเลื่อนหรือข้ามรอบ จึงไม่ใช่แจ้งเตือนเรียลไทม์หรือรับประกันว่าเข้าซื้อทัน. ไม่มีการส่งคำสั่ง Exchange และไม่มีการรับประกันผลตอบแทน

## ขั้นที่ 1 — อัปโหลดโปรแกรมใหม่ขึ้น GitHub

1. ดาวน์โหลด ZIP v4.1 แล้วแตกไฟล์ **อย่าอัปโหลด ZIP ทั้งก้อน**
2. เปิด Repository GitHub เดิมที่มี `app.py` ของ Orbit (ไม่จำเป็นต้องสร้าง Repo ใหม่)
3. นำไฟล์ทั้งหมดภายใน `orbit_crypto_signal_lab` ไปไว้ที่ **root ของ Repository เดิม**: `app.py`, `monitor_engine.py`, `monitor_alerts.py`, `monitor_delivery.py`, `alert_monitor.py`, `monitor_config.json`, `monitor_coinglass_manual.json`, `monitor_requirements.txt`, `watch_plans.py` และไฟล์เก่าทั้งหมด
4. **สำคัญที่สุด:** ต้องมีไฟล์ `.github/workflows/orbit-telegram-monitor.yml` ตามพาธนี้ **เป๊ะ** (โฟลเดอร์ `.github` อาจถูกซ่อนใน Windows; GitHub Desktop ฟรีช่วยอัปโหลดทั้งโฟลเดอร์ได้ง่ายกว่า)
5. กด **Commit changes** และรอ Streamlit โหลดเวอร์ชันใหม่ เว็บจะขึ้น **Orbit v4.1** และมีแท็บ **📡 Telegram แจ้งเตือน**

หากอัปโหลดผ่านหน้าเว็บ GitHub แล้วหา `.github` ไม่เจอ ให้ใช้ **Add file → Create new file** ตั้งชื่อไฟล์เป็น `.github/workflows/orbit-telegram-monitor.yml` แล้วนำข้อความจากไฟล์ชื่อเดียวกันใน ZIP ไปวาง จากนั้นกด Commit. GitHub ต้องเห็นไฟล์นี้อยู่บน **default branch** เช่น `main` จึงจะตั้งเวลารันได้

## ขั้นที่ 2 — สร้าง Telegram Bot (ใช้ฟรี)

1. เปิด Telegram ในมือถือ → ค้นหา **@BotFather** ซึ่งเป็นบอททางการของ Telegram
2. ส่ง `/newbot` แล้วตั้งชื่อบอท เช่น `Orbit Crypto Signals`
3. ตั้ง Username ลงท้ายด้วย `bot` เช่น `orbit_signal_example_bot` (ต้องไม่ซ้ำชื่อคนอื่น)
4. BotFather จะส่ง **Bot Token** ให้ เก็บไว้ส่วนตัว ห้ามส่ง Token มาใน ChatGPT, LINE, Screenshot หรือใส่ในไฟล์ GitHub
5. เปิดแชตบอทที่เพิ่งสร้าง แล้วกด **Start** หรือส่ง `/start` เพราะบอทส่วนตัวไม่สามารถเริ่มส่งข้อความหาเราได้เอง

### หา Telegram Chat ID ของตัวเอง

วิธีใช้ Telegram Bot API ทางการ:

1. หลังส่ง `/start` ให้บอทแล้ว เปิดเบราว์เซอร์ส่วนตัว
2. ไปที่ URL `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` โดยแทน `<YOUR_BOT_TOKEN>` ด้วย Token จริงของคุณ **ในเบราว์เซอร์ตัวเองเท่านั้น**
3. มองหาข้อความ `"chat":{"id":123456789,...}` แล้วจดตัวเลข `id` ซึ่งเป็น **Chat ID** (ของคุณอาจไม่ใช่เลขนี้)
4. ระวัง: URL นี้มี Token อยู่ในประวัติเบราว์เซอร์ จึงควรปิดแท็บและลบจากประวัติภายหลัง; ห้ามแชร์ลิงก์หรือภาพหน้าเว็บดังกล่าว

ถ้า `result` เป็น `[]` ให้กลับไปส่ง `/start` หรือข้อความใหม่ในแชตบอท แล้วลองเปิด URL อีกครั้ง

## ขั้นที่ 3 — ใส่ Telegram Secrets ใน GitHub

ใน Repository ไปที่ **Settings → Secrets and variables → Actions → New repository secret**

สร้าง 2 รายการนี้:

| Name (คัดลอกตรงตัว) | Secret value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token จาก BotFather |
| `TELEGRAM_CHAT_ID` | ตัวเลข Chat ID ที่ได้จาก `getUpdates` |

ห้ามพิมพ์ Token ลงใน `app.py`, `monitor_config.json`, YAML หรือ `README.md` เด็ดขาด. **ไม่ต้องตั้ง Binance API Key, Exchange Account หรือ CoinGlass API Key**

ใน GitHub Repository เดิม ต้องอนุญาต Workflow เขียน State branch อัตโนมัติด้วย `GITHUB_TOKEN`:

- ไปที่ **Settings → Actions → General → Workflow permissions** แล้วเลือก **Read and write permissions** ถ้าตัวเลือกนี้เปิดให้ใช้
- ไฟล์ Workflow ก็ระบุ `permissions: contents: write` ไว้แล้ว แต่บางบัญชี/องค์กรอาจล็อกสิทธิ์จาก Settings ให้แก้ไม่ได้; ถ้า GitHub ปฏิเสธการเขียน State ให้หยุดและตรวจสิทธิ์ ไม่ต้องใส่ Personal Access Token เพิ่ม

## ขั้นที่ 4 — กดส่งข้อความทดสอบก่อน

1. ใน GitHub เปิดแท็บ **Actions**
2. เลือก **Orbit Telegram Signal Monitor**
3. กด **Run workflow** → ติ๊ก **Send one Telegram TEST message** → กด Run
4. รอสักครู่แล้วเปิด Telegram จะเห็นข้อความ `✅ Orbit v4.1 Telegram Test สำเร็จ`
5. ถ้า Run สีแดง ให้เปิดรายละเอียด Steps ที่ล้มเหลว (อย่าส่ง Screenshot ที่มี Token); ตรวจ `/start`, Secret names และ Chat ID

หลังทดสอบผ่าน GitHub จะตรวจ **PEPEUSDT, BTCUSDT, DOGEUSDT** เป็นรอบ ๆ ตามตาราง `:02, :17, :32, :47` ของทุกชั่วโมง **UTC** (เวลาไทย +7 ชั่วโมง) โดยอาศัยแท่ง 15 นาทีที่ปิดแล้ว

## ขั้นที่ 5 — เปิดระบบ Frozen Watch Plan (สำคัญ)

ถ้าไม่ตั้งค่าส่วนนี้ ระบบ **ยังตรวจ MTF สด** ของ PEPE/BTC/DOGE และแจ้งสถานะ `MTF_READY` ได้ แต่ **ยังไม่ใช่การยืนยันแผนโซนเดิมที่ล็อกไว้**

หากต้องการให้ Telegram ติดตามราคาเดิมที่ตั้งใจรอ:

1. เปิดเว็บ Orbit v4.1 → เลือกเหรียญ `PEPE` → แท็บ **🎯 สัญญาณ MTF รวม**
2. กด **🧷 ล็อก Entry Zone ปัจจุบันเป็นแผนเฝ้าดู** และเลือกระยะเวลา 12/24/48/72 ชั่วโมง
3. เปิดแท็บ **📡 Telegram แจ้งเตือน** แล้วกด Copy บรรทัดที่เตรียมให้ เช่น `PEPEUSDT=https://ชื่อเว็บ.streamlit.app/?watch=...` (ค่าจริงจะยาวกว่านี้)
4. กลับ GitHub **Settings → Secrets and variables → Actions → New repository secret** แล้วสร้าง Secret ชื่อ **`ORBIT_WATCH_LINKS`**
5. วางบรรทัด PEPE ที่คัดลอกไว้ลงใน Secret นั้น หากมี BTC และ DOGE ให้เพิ่มใน Secret **เดียวกัน** แยกแต่ละเหรียญขึ้นบรรทัดใหม่:

   ```text
   PEPEUSDT=https://.../?watch=TOKEN_FROM_ORBIT_PEPE
   BTCUSDT=https://.../?watch=TOKEN_FROM_ORBIT_BTC
   DOGEUSDT=https://.../?watch=TOKEN_FROM_ORBIT_DOGE
   ```

   **ข้อความนี้เป็นเพียงรูปแบบตัวอย่าง ไม่ใช่ Token ใช้งานจริง**. ใส่เฉพาะเหรียญที่ล็อกแผนแล้วก็ได้ อีกเหรียญจะยังเป็น MTF สด

6. กด Save. รอบถัดไปตัวตรวจจะใช้ **ราคา Entry/SL/TP เดิมจากแต่ละลิงก์** และสถานะ `WAIT_ZONE → WAIT_RECLAIM → WAIT_BREAK → READY_NOW` ตามกฎ Orbit v4.0/4.1

**แผนล็อกไม่ต่ออายุเอง** เมื่อครบกำหนดหรือถูก INVALIDATED/PASSED จะแจ้งเหตุสำคัญหนึ่งครั้ง. หากต้องการเฝ้าต่อ ให้ล็อกแผนใหม่ในเว็บแล้ว **อัปเดต Secret `ORBIT_WATCH_LINKS`** แทนบรรทัดเก่า มิฉะนั้นระบบจะไม่ย้ายไปใช้โซนใหม่โดยพลการ

## ขั้นที่ 6 — CoinGlass แบบกรอกเอง (ไม่ใช่ API อัตโนมัติ)

- ตัวตรวจใช้ **Public Futures API** จาก Kraken/Binance/Bybit ตามกฎเดิม ไม่ปลอมว่าเป็นข้อมูล CoinGlass
- ถ้าไม่เพิ่ม CoinGlass ในไฟล์ Manual ระบบจะแสดง `NOT_ENTERED` และใช้กฎที่เหลือตามเดิม (CoinGlass เป็น Optional)
- ถ้าพรรณต้องการใช้ CoinGlass ร่วมด้วย: กรอกข้อมูลเหรียญนั้นในแท็บ **📊 สัญญาณละเอียด** ของ Orbit แล้วกลับแท็บ **📡 Telegram แจ้งเตือน** เพื่อคัดลอก JSON
- ใน GitHub เปิด `monitor_coinglass_manual.json` → กด Edit → วางค่าใต้ `snapshots` โดยใช้ข้อมูลจริง พร้อม `observed_at` ที่มี timezone เช่น `+07:00`; ตัวอย่างรูปแบบ (ต้องแทนตัวเลขด้วยค่าที่เห็นใน CoinGlass จริง):

  ```json
  {
    "snapshots": {
      "PEPE": {
        "observed_at": "2026-10-29T15:00:00+07:00",
        "funding_rate_pct": 0.01,
        "oi_change_24h_pct": 2.0,
        "long_short_account_ratio": 1.2,
        "long_liquidations_usd_24h": 1000,
        "short_liquidations_usd_24h": 2000
      }
    }
  }
  ```

- ข้อมูลเหล่านี้เป็น **ตัวเลขสมมติสำหรับสอนรูปแบบเท่านั้น**; ต้องกรอกค่าจริงและอ่านหน่วยให้ถูกต้อง. หากมีหลายเหรียญให้เพิ่ม `BTC`, `DOGE` ภายใต้ `snapshots` เดียวกัน
- เมื่อ CoinGlass ที่กรอก **เก่าเกิน 1 ชั่วโมงสำหรับ 15m** หรือขัดกฎเดิม จะทำให้ผลรวม WAIT และมีข้อความเตือนเมื่อสถานะเปลี่ยน; **โปรแกรมไม่ดึง CoinGlass ให้เอง**. ถ้าต้องการติดตามแบบไม่ต้องอัปเดต CoinGlass ทุกชั่วโมง คงไฟล์เป็น `{"snapshots":{}}` แล้วใช้เป็นตัวกรองเสริมในเว็บเมื่อต้องการ

## ได้รับแจ้งเตือนอะไรบ้าง?

| สถานะ | ส่ง Telegram เมื่อใด |
|---|---|
| `READY_NOW` | Frozen Plan ยืนยันแตะโซน → Reclaim → Break/Retest แล้ว MTF/Futures/R:R ปัจจุบันยังผ่าน |
| `MTF_READY` | MTF สด READY (ใช้กับเหรียญที่ยังไม่ใส่ลิงก์แผนล็อก) และระบุชัดว่าไม่มี Frozen Plan |
| `INVALIDATED` | แผนล็อกถูกยกเลิกจาก SL หรือโครงสร้างหลุด |
| `PASSED` | จังหวะเคยผ่านไปแล้ว ราคาไล่ไม่ได้หรือสัญญาณเกินอายุ |
| `EXPIRED` | แผนล็อกครบอายุ |
| `NO_LONGER_READY` | สัญญาณ READY ที่เคยแจ้งกลับเป็น WAIT |
| `DATA_UNAVAILABLE` | ดึงข้อมูลสำคัญไม่ได้ 2 รอบติด (ไม่ส่ง BUY จากข้อมูลที่หาย) |
| `COINGLASS_STALE` | Manual CoinGlass มีอยู่แต่ไม่ผ่าน/หมดอายุ |

ไม่ส่งข้อความทุก 15 นาทีเพราะราคาไม่เปลี่ยนสถานะ. เก็บสถานะข้ามรอบใน GitHub Branch ชื่อ `orbit-alert-state` ซึ่งระบบสร้างเองและ **ไม่มี Bot Token, Chat ID หรือ watch token ใน State**. อย่าลบ Branch นี้ถ้าต้องการคงระบบป้องกันข้อความซ้ำ

## ข้อจำกัดและค่าใช้จ่าย

- GitHub Actions บน **Public Repository ใช้ Runner มาตรฐานได้ฟรีตามนโยบายปัจจุบัน**; Private Repository มีโควตานาทีใช้ฟรีตามแพ็กเกจ และอาจมีค่าบริการหากใช้เกิน. ถ้าตั้ง Billing ไว้ให้ตรวจ Usage เอง
- Scheduled workflows อาจรันช้า/ข้ามรอบ และใน Public Repository ที่ไม่มีความเคลื่อนไหว 60 วัน อาจถูกปิดอัตโนมัติ. **ไม่มี SLA แจ้งเตือนภายใน 15 นาที**
- หาก Binance หรือ Futures APIs บล็อก GitHub Runner ตามภูมิภาคหรือ Rate Limit ระบบจะ **WAIT/DATA_UNAVAILABLE** ไม่แต่งค่าหรือหลีกเลี่ยงข้อจำกัด
- หาก Telegram ส่งสำเร็จแต่ GitHub บันทึกผลตอบกลับไม่สำเร็จ อาจเกิดข้อความซ้ำในรอบถัดไปได้; เป็นการส่งแบบพยายามไม่ให้ตกหล่น ไม่ใช่รับประกัน Exactly Once
- ผู้ที่เข้าถึง Public Repository อาจเห็น `monitor_coinglass_manual.json` และ **State Branch ที่เก็บสถานะ/ข้อความเตือนรวมทั้งระดับราคา** ได้ แต่ **Secrets และ Frozen Watch Token ไม่ถูกฝังใน Git**. อย่านำข้อมูลส่วนตัวหรือข้อมูลบัญชีไปใส่ไฟล์ JSON; หากต้องการปกปิดระดับราคาให้เลือก Private Repository แล้วตรวจโควต้า Actions ฟรี
- ไม่เปิดคำสั่งซื้อขาย ไม่ใช้ Leverage ไม่มี API Key ของกระดาน และไม่สามารถรู้ได้ว่าเจ้ามือรายใดเข้าซื้อจริง
- กฎ Entry Trigger/Full MTF รวม Futures, Book และ CoinGlass **ยังไม่ผ่าน Walk-forward แบบครบชุด**; แจ้งเตือนเป็นสัญญาณเฝ้าดู ไม่ใช่คำสั่งซื้อหรือการรับประกันกำไร

## ตรวจปัญหาเบื้องต้น

| อาการ | วิธีแก้ |
|---|---|
| ไม่มี Workflow ในแท็บ Actions | ตรวจ `.github/workflows/orbit-telegram-monitor.yml` ว่าอยู่ default branch จริง |
| Test ไม่ส่ง Telegram | กด `/start` ในแชต Bot; เช็ก Secret Name/Token/Chat ID โดยไม่แชร์ค่า |
| `GitHub State API HTTP 403` | ตรวจ Settings → Actions → Workflow permissions และสิทธิ์ Repository; ไม่ต้องสร้าง PAT ใหม่ |
| `Data unavailable` | ดู GitHub Actions Logs; API สาธารณะอาจถูกจำกัด หากมีข้อมูลขาดจะไม่มี READY |
| Telegram ไม่มี READY นาน | ดูผล Scan ว่ายัง WAIT หรือไม่, แผนหมดอายุหรือไม่, CoinGlass Manual เก่าหรือไม่; นี่ไม่ใช่เหตุให้ซื้อทันที |
| Frozen Link แจ้งว่าไม่ตรงเหรียญ | เลือกลิงก์แผนล็อกคู่ USDT ให้ตรงกับชื่อก่อนเครื่องหมาย `=` |
| ค่า CoinGlass เก่า | อัปเดต timestamp/ตัวเลขจาก CoinGlass จริงหรือเอารายการนั้นออกจาก Manual เพื่อกลับเป็น optional |
| Workflow ถูกหยุดหลังไม่ใช้ repo นาน | เปิด GitHub Actions และตรวจ Scheduled workflow เพื่อเปิดใช้งานอีกครั้ง |

เอกสารทางการ: [GitHub Actions Schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [GitHub Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets), [Telegram Bot API](https://core.telegram.org/bots/api)
