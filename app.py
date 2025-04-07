from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import os
import sqlite3
import joblib
from datetime import datetime

app = Flask(__name__)

DB_NAME = "messages.db"

model = joblib.load("intent_model.pkl")
vectorizer = joblib.load("vectorizer.pkl")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        message TEXT,
        date TEXT
    )''')
    conn.commit()
    conn.close()

RESPONSES = {
    "طلب": "يرجى تزويدنا برقم الطلب للمتابعة. شكرًا لك! 🙏",
    "فرع": "لدينا فروع في عمان داخل وخارج المول: السيتي سنتر، الموالح، والعذيبة. 🌸",
    "ترحيب": "مرحباً بك في الوداد للعطور! 🌹 كيف أقدر أساعدك؟",
    "خدمات": "يمكنك الطلب من خلال موقعنا الإلكتروني أو زيارتنا بالفروع مباشرةً.",
    "مساعدة": "يسعدنا مساعدتك! ما هو الشيء الذي ترغب بمعرفته؟",
    "منتج": "نُقدّم أفخم أنواع العطور بتشكيلة واسعة تناسب كل الأذواق.",
    "تواصل": "تقدر تتواصل معنا عبر الموقع الرسمي أو على حساباتنا بالسوشال ميديا.",
    "وظائف": "نحن نوفر فرص عمل داخل وخارج سلطنة عُمان. قم بزيارة قسم الوظائف."
}

@app.route("/bot", methods=["POST"])
def bot():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    print("📩 Received message:", incoming_msg)

    # تحديد نوع الرسالة بناءً على التحية مباشرةً
    if incoming_msg.lower() in ["السلام عليكم", "هلا", "مرحبا"]:
        reply = RESPONSES.get("ترحيب")
    else:
        # توقّع النية باستخدام النموذج الاصطناعي
        X = vectorizer.transform([incoming_msg])
        predicted_intent = model.predict(X)[0]
        print("🧠 Intent identified:", predicted_intent)
        reply = RESPONSES.get(predicted_intent, "كيف أقدر أساعدك؟")

    # إعداد الرد 💬
    resp = MessagingResponse()
    msg = resp.message()
    msg.body(reply)

    # حفظ البيانات في قاعدة البيانات 🗃️
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender, message, date) VALUES (?, ?, ?)",
              (sender, incoming_msg, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
