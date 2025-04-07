import os
import sqlite3
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import joblib
from datetime import datetime

app = Flask(__name__)
DB_NAME = "messages.db"

model = joblib.load("intent_model.pkl")
vectorizer = joblib.load("vectorizer.pkl")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            sender TEXT,
            message TEXT,
            date TEXT
        )
    """)
    conn.commit()
    conn.close()

RESPONSES = {
    "طلب": "يرجى تزويدنا برقم الطلب للمتابعة.",
    "وين": "يمكنك الطلب من خلال موقعنا الإلكتروني أو زيارتنا بأقرب فرع 🛍️.",
    "مساعدة": "سعدنا مساعدتك! ما هي الخدمة التي ترغب في معرفتها؟",
    "فرع": "لدينا فروع في مسقط داخل وخارج السلطنة. خبرني أقرب ولاية لك ❤️",
    "موقع": "تقدر تشوف فروعنا على خرائط جوجل بكتابة 'الوداد للعطور'."
}

@app.route("/bot", methods=["POST"])
def bot():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    print("💬 Received message:", incoming_msg)

    # تحديد الرد بناءً على التحية مباشرةً
    if incoming_msg.lower() in ["السلام عليكم", "هلا", "مرحبا"]:
        reply = "مرحباً بك في الوداد للعطور! كيف أقدر أساعدك؟"
    else:
        # تنبؤ بالنية واستخدام الذكاء الاصطناعي
        X = vectorizer.transform([incoming_msg])
        predicted_intent = model.predict(X)[0]
        print("🔮 Intent identified:", predicted_intent)
        reply = RESPONSES.get(predicted_intent, "كيف أقدر أساعدك؟")

    # إعداد الرد
    resp = MessagingResponse()
    msg = resp.message()
    msg.body(reply)

    # حفظ البيانات في قاعدة البيانات
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender, message, date) VALUES (?, ?, ?)",
              (sender, incoming_msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    return str(resp)

if __name__ == "__main__":
    init_db()  # ← هذا السطر هو المهم لإنشاء الجدول
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

