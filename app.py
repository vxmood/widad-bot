import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import joblib
import sqlite3
from datetime import datetime

app = Flask(__name__)

# تحميل النموذج والمتجه
model = joblib.load("intent_model.pkl")
vectorizer = joblib.load("vectorizer.pkl")

DB_NAME = "messages.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS messages
        (sender TEXT, message TEXT, date TEXT)"""
    )
    conn.commit()
    conn.close()

RESPONSES = {
    "ترحيب": "مرحباً بك في الوداد للعطور! 🌹 كيف أقدر أساعدك؟",
    "طلب": "يرجى تزويدنا برقم الطلب للمتابعة. شكرًا لك!",
    "طريقة الطلب": "يمكنك الطلب من خلال موقعنا الإلكتروني أو التواصل معنا عبر واتساب.",
    "منتج معين": "سعدنا مساعدتك! ما هو اسم العطر أو نوع المنتج الذي تبحث عنه؟",
    "مشكلة الطلب": "نأسف لسماع ذلك، سيتم تحويلك مباشرةً لخدمة العملاء.",
    "فروعنا": "لدينا فروع في عمان داخل وخارج مسقط، هل ترغب في معرفة موقع معين؟"
}

@app.route("/bot", methods=["POST"])
def bot():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    print("📩 Received message:", incoming_msg)

    # تحديد الرد بناءً على الرسالة مباشرةً
    if incoming_msg.lower() in ["مرحبا", "هلا", "السلام عليكم"]:
        reply = RESPONSES.get("ترحيب")
    else:
        # توقع النية باستخدام الذكاء الاصطناعي
        X = vectorizer.transform([incoming_msg])
        predicted_intent = model.predict(X)[0]
        print("🧠 Intent identified:", predicted_intent)
        reply = RESPONSES.get(predicted_intent, "كيف أقدر أساعدك؟")

    # إعداد الرد
    resp = MessagingResponse()
    msg = resp.message()
    msg.body(reply)

    # حفظ البيانات في قاعدة البيانات
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

