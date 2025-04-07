from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import joblib
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
DB_NAME = "messages.db"

# دالة إنشاء قاعدة البيانات والجدول
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            sender TEXT,
            message TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

# تشغيل الإنشاء أول ما يشتغل السيرفر
init_db()

# تحميل النموذج
model = joblib.load("intent_model.pkl")
vectorizer = joblib.load("vectorizer.pkl")

# الردود
RESPONSES = {
    "طلب": "يرجى تزويدنا برقم الطلب للمتابعة. شكرًا لك!",
    "فرع": "لدينا فروع في مسقط، السيب، وصلالة.",
    "خدمة": "يمكنك الطلب من خلال موقعنا الإلكتروني أو زيارتنا بأقرب فرع لك.",
    "": "كيف أقدر أساعدك؟"
}

@app.route("/bot", methods=["POST"])
def bot():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")

    print("📩 Received message:", incoming_msg)

    # كلمات ترحيبية
    if incoming_msg.lower() in ["مرحبا", "السلام عليكم", "هلا", "مرحبا!"]:
        reply = "مرحباً بك في الوداد للعطور! 🌹\nكيف أقدر أساعدك؟"
    else:
        # توقّع النية
        X = vectorizer.transform([incoming_msg])
        predicted_intent = model.predict(X)[0]
        print("🔮 Intent identified:", predicted_intent)
        reply = RESPONSES.get(predicted_intent, "كيف أقدر أساعدك؟")

    # إرسال الرد
    resp = MessagingResponse()
    msg = resp.message()
    msg.body(reply)

    # حفظ في قاعدة البيانات
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO messages (sender, message, date) VALUES (?, ?, ?)",
                  (sender, incoming_msg, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
    except Exception as e:
        print("❌ DB Error:", e)

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

