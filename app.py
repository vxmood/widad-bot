from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import joblib
import sqlite3
from datetime import datetime, timedelta
import os

app = Flask(__name__)

model = joblib.load("intent_model.pkl")
vectorizer = joblib.load("vectorizer.pkl")
DB_NAME = "widad_messages.db"
TRAINING_DB = "widad_training.db"

RESPONSES = {
    "ترحيب": "مرحباً بك في الوداد للعطور! 🌹 كيف أقدر أساعدك؟",
    "طلب": "يرجى تزويدنا برقم الطلب للمتابعة. شكرًا لك!",
    "ماعندي_رقم_طلب": "رقم الطلب تم إرساله عبر الإيميل. إذا لم يصلك، يرجى تزويدنا برقم الهاتف المسجل في الطلب للمتابعة.",
    "وين_أحصل_رقم_طلب": "يمكنك العثور على رقم الطلب في الإيميل الذي استخدمته أثناء الطلب. إذا لم يصلك، تواصل معنا برقم الهاتف المسجل وسنساعدك!",
    "فرع": "تفضل بزيارتنا إلى أقرب فرع لديك 🚗 :\n\n• سوق بركاء\n- سيتي سنتر مسقط (الموالح)\n• الموالح (بجانب سيتي سنتر بمحطة شل)\n• مسقط مول\n• العذيبة (بعد أبراج الصحوة بجانب كنتاكي)\n- نزوى جراند مول\n- عمان مول\n• السويق\n\n⏰ أوقات العمل:\nطيلة أيام الأسبوع ما عدا الجمعة\n10 ص إلى 1:30 م\n4:30 م إلى 10:00 م\n\nيوم الجمعة:\n4:30 م إلى 10:00 م\n\nالمجمعات التجارية:\nطيلة أيام الأسبوع\n10:00 ص إلى 10:00 م\nالخميس و الجمعة\n10:00 إلى 12:00 بعد منتصف الليل",
    "شكر": "شكرًا لتواصلك معنا في الوداد للعطور 🌹 نحن دائماً في خدمتك. إذا احتجت أي مساعدة لا تتردد في مراسلتنا.",
    "default": "كيف أقدر أساعدك؟"
}

GREETINGS = ["السلام عليكم", "هلا", "مرحبا", "أهلاً", "هلا!", "مرحبا!"]
THANKS = ["شكرا", "شكرًا", "مشكووور", "مشكور"]

# تخزين بيانات التدريب
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

# تخزين آخر تفاعل لكل زبون
def update_last_interaction(phone):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (phone TEXT PRIMARY KEY, last_seen TEXT)''')
    c.execute('''REPLACE INTO sessions (phone, last_seen) VALUES (?, ?)''', (phone, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

# التحقق من وجود محادثة سابقة
def is_first_message(phone):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (phone TEXT PRIMARY KEY, last_seen TEXT)''')
    result = c.execute('''SELECT last_seen FROM sessions WHERE phone = ?''', (phone,)).fetchone()
    conn.close()
    return result is None

@app.route("/bot", methods=["POST"])
def bot():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    print("📩 Received message:", incoming_msg)

    reply = RESPONSES["default"]
    predicted_intent = ""

    if is_first_message(sender):
        reply = RESPONSES["ترحيب"]
        predicted_intent = "ترحيب"
    elif incoming_msg.lower() in GREETINGS:
        reply = RESPONSES["ترحيب"]
        predicted_intent = "ترحيب"
    elif any(thx in incoming_msg.lower() for thx in THANKS):
        reply = RESPONSES["شكر"]
        predicted_intent = "شكر"
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
        predicted_intent = model.predict(X)[0]
        reply = RESPONSES.get(predicted_intent, RESPONSES["default"])

    # تخزين التفاعل
    log_training_data(sender, incoming_msg, predicted_intent)
    update_last_interaction(sender)

    # إرسال الرد
    resp = MessagingResponse()
    msg = resp.message()
    msg.body(reply)
    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

