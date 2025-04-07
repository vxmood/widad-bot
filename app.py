from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import os
import sqlite3
from datetime import datetime
import joblib

app = Flask(__name__)

# تحميل نموذج الذكاء الاصطناعي وأداة تحويل الكلمات
model = joblib.load("intent_model.pkl")
vectorizer = joblib.load("vectorizer.pkl")

# إعداد قاعدة البيانات
DB_NAME = 'widad.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            message TEXT,
            date TEXT
        )''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            sender TEXT PRIMARY KEY,
            state TEXT
        )''')
    conn.commit()
    conn.close()

init_db()

RESPONSES = {
    "تتبع طلب": "يرجى تزويدنا برقم الطلب للمتابعة.",
    "طلب جديد": "يمكنك الطلب من خلال موقعنا الإلكتروني أو تزويدنا بتفاصيل المنتج الذي ترغب به.",
    "استفسار عن منتج": "يسعدنا مساعدتك! ما هو المنتج الذي ترغب بمعرفة المزيد عنه؟",
    "شكوى": "نأسف لسماع ذلك، يرجى تزويدنا بتفاصيل المشكلة وسنتابع معك فوراً.",
    "شحن وتوصيل": "نعم، نوفر خدمة الشحن داخل وخارج عمان. هل ترغب بمعرفة تفاصيل الشحن؟"
}

@app.route("/bot", methods=['POST'])
def bot():
    incoming_msg = request.values.get('Body', '').strip()
    sender = request.values.get('From', '')
    print("📥 Received message:", incoming_msg)

    # توقع النية باستخدام النموذج
    X = vectorizer.transform([incoming_msg])
    predicted_intent = model.predict(X)[0]
    print("🤖 Intent identified:", predicted_intent)

    # إعداد الرد
    resp = MessagingResponse()
    msg = resp.message()

    reply = RESPONSES.get(predicted_intent, "كيف أقدر أساعدك؟")
    msg.body(reply)

    # حفظ الرسالة في قاعدة البيانات
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
