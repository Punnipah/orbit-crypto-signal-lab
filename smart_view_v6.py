import streamlit as st
import pandas as pd
import random
import math

st.set_page_config(page_title="Orbit V6 Smart View", page_icon="🪐", layout="centered")
st.title("🪐 Orbit V6.0")
st.subheader("Smart View | ห้องเรียนตลาด")
st.info("ข้อมูลจำลองทั้งหมด ไม่เชื่อมต่อราคาจริงหรือบัญชีซื้อขาย")
scenario = st.selectbox("เลือกสถานการณ์เพื่อศึกษา", ["แนวโน้มขึ้น", "แนวโน้มลง", "แกว่งตัว", "ข้อมูลขัดแย้ง"])
seed = st.number_input("ชุดข้อมูลจำลอง", min_value=1, max_value=9999, value=42)
rng = random.Random(int(seed))
drift = {"แนวโน้มขึ้น":0.003,"แนวโน้มลง":-0.003,"แกว่งตัว":0,"ข้อมูลขัดแย้ง":0.003}[scenario]
prices = [100.0]
for i in range(95):
    prices.append(prices[-1]*math.exp(drift+rng.gauss(0,0.006)))
buy = {"แนวโน้มขึ้น":65,"แนวโน้มลง":35,"แกว่งตัว":50,"ข้อมูลขัดแย้ง":32}[scenario]
st.header("ภาพรวม")
st.write("**"+scenario+"**")
st.write("แนวโน้มย้อนหลังและสัดส่วนธุรกรรมอาจไม่สอดคล้องกัน และไม่สามารถรับประกันราคาในอนาคต")
a,b = st.columns(2)
a.metric("ราคาในแบบจำลอง", f"{prices[-1]:.2f}")
b.metric("เปลี่ยนแปลงย้อนหลัง", f"{(prices[-1]/prices[0]-1)*100:.2f}%")
st.subheader("สัดส่วนธุรกรรมสมมติ")
st.progress(buy, text=f"ฝั่งซื้อ {buy}% | ฝั่งขาย {100-buy}%")
st.subheader("กราฟย้อนหลัง")
st.line_chart(pd.DataFrame({"ราคา":prices}), y="ราคา")
with st.expander("อ่านข้อมูลอย่างไร"):
    st.write("แนวโน้มคือการเปลี่ยนแปลงในอดีต ไม่ใช่การทำนาย สัดส่วนธุรกรรมเป็นตัวอย่างที่กำหนดไว้ ไม่ใช่ผลคำนวณจากตลาดจริง")
    st.write("ข้อมูลขัดแย้งเกิดขึ้นได้เมื่อข้อมูลแต่ละชนิดครอบคลุมช่วงเวลาต่างกัน")
with st.expander("คุณภาพและที่มาข้อมูล"):
    st.write("ราคาเกิดจากแบบจำลองสุ่ม 96 จุด ไม่มีข้อมูลตลาดสด ไม่มีการประเมินความแม่นยำของสัญญาณ")
    st.write(f"ค่าต่ำสุด {min(prices):.2f} | ค่าสูงสุด {max(prices):.2f}")
st.download_button("ดาวน์โหลดข้อมูลจำลอง CSV",pd.DataFrame({"step":range(len(prices)),"price":prices}).to_csv(index=False),"orbit_v6_demo.csv","text/csv")
