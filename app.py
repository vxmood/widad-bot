from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import joblib
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)

model = joblib.load("intent_model.pkl")
vectorizer = joblib.load("vectorizer.pkl")
DB_NAME = "widad_messages.db"
TRAINING_DB = "widad_training.db"

RESPONSES = {
    "سلام": "مرحباً بك في الوداد للعطور! 🌹 كيف أقدر أساعدك؟",
    "طلب": "يرجى تزويدنا برقم الطلب للمتابعة. شكرًا لك!",
    "ماعندي_رقم_طلب": "رقم الطلب تم إرساله عبر الإيميل. إذا لم يصلك، يرجى تزويدنا برقم الهاتف المسجل في الطلب للمتابعة.",
    "وين_أحصل_رقم_طلب": "يمكنك العثور على رقم الطلب في الإيميل الذي استخدمته أثناء الطلب. إذا لم يصلك، تواصل معنا برقم الهاتف المسجل وسنساعدك!",
    "فرع": "تفضل بزيارتنا إلى أقرب فرع لديك 🚗 :\n\n• سوق بركاء\n- سيتي سنتر مسقط (الموالح)\n• الموالح (بجانب سيتي سنتر بمحطة شل)\n• مسقط مول\n• العذيبة (بعد أبراج الصحوة بجانب كنتاكي)\n- نزوى جراند مول\n- عمان مول\n• السويق\n\n⏰ أوقات العمل:\nطيلة أيام الأسبوع ما عدا الجمعة\n10 ص إلى 1:30 م\n4:30 م إلى 10:00 م\n\nيوم الجمعة:\n4:30 م إلى 10:00 م\n\nالمجمعات التجارية:\nطيلة أيام الأسبوع\n10:00 ص إلى 10:00 م\nالخميس و الجمعة\n10:00 إلى 12:00 بعد منتصف الليل",
    "default": "كيف أقدر أساعدك؟"
}

GREETINGS = ["السلام عليكم", "هلا", "مرحبا", "أهلاً", "هلا!", "مرحبا!"]

def log_training_data(phone, message, predicted_intent):
    try:
        conn = sqlite3.connect(TRAINING_DB)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS training_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT,
                message TEXT,
                predicted_intent TEXT,
                timestamp TEXT
            )
        ''')
        c.execute('''
            INSERT INTO training_data (phone, message, predicted_intent, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (phone, message, predicted_intent, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        print("✅ Training data logged.")
    except Exception as e:
        print("❌ Error logging training data:", e)

@app.route("/bot", methods=["POST"])
def bot():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    print("📩 Received message:", incoming_msg)

    if incoming_msg.lower() in GREETINGS:
        reply = RESPONSES["سلام"]
        predicted_intent = "سلام"
    elif "رقم" in incoming_msg and "طلب" in incoming_msg and any(word in incoming_msg for word in ["ماعندي", "ما عندي رقم"]):
        reply = RESPONSES["ماعندي_رقم_طلب"]
        predicted_intent = "ماعندي_رقم_طلب"
    elif any(phrase in incoming_msg for phrase in ["وين طلبي", "وين ألقى رقمي", "وين احصل رقم طلب", "ماوصلني رقم"]):
        reply = RESPONSES["وين_أحصل_رقم_طلب"]
        predicted_intent = "وين_أحصل_رقم_طلب"
    elif any(word in incoming_msg for word in ["فرع", "وين الفرع", "الفروع"]):
        reply = RESPONSES["فرع"]
        predicted_intent = "فرع"
    elif "طلب" in incoming_msg:
        reply = RESPONSES["طلب"]
        predicted_intent = "طلب"
    else:
        X = vectorizer.transform([incoming_msg])
