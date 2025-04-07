from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import os
import sqlite3
from datetime import datetime

app = Flask(__name__)

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
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# رسائل الترحيب
WELCOME_MESSAGES = {
    'ar': "مرحباً بك في الوداد للعطور! 🌹",
    'en': "Welcome to Widad Perfumes! 🌹"
}

HELP_MESSAGES = {
    'ar': "كيف أقدر أساعدك؟",
    'en': "How can I help you?"
}

ORDER_REQUEST_MESSAGES = {
    'ar': "يرجى تزويدنا برقم الطلب للمتابعة. شكراً لك!",
    'en': "Please provide your order number so we can follow up. Thank you!"
}

ORDER_LOOKUP_RESPONSES = {
    'ar': "رقم الطلب تم إرساله لك عبر البريد الإلكتروني. إذا لم يصلك أي بريد، يرجى تزويدي برقم الهاتف المسجّل أثناء الطلب وسأساعدك في المتابعة.",
    'en': "Your order number was sent to your email. If you didn't receive it, please send me the phone number used in the order and I’ll help you further."
}

@app.route("/bot", methods=['POST'])
def bot():
    print("🚀 /bot endpoint was hit")
    incoming_msg = request.values.get('Body', '').strip()
    sender = request.values.get('From', '')
    print("📥 Received message:", incoming_msg)

    lang = 'ar' if any(word in incoming_msg for word in ['طلب', 'رقم', 'مرحبا', 'هلا']) else 'en'

    resp = MessagingResponse()
    msg = resp.message()

    # رد خاص لسؤال رقم الطلب
    if any(phrase in incoming_msg.lower() for phrase in ['رقم الطلب', 'وين رقم الطلب', 'كيف أطلع رقم', 'وين طلبي']):
        msg.body(ORDER_LOOKUP_RESPONSES[lang])
    elif incoming_msg.lower() in ['hi', 'hello', 'مرحبا', 'السلام عليكم']:
        msg.body(f"{WELCOME_MESSAGES[lang]}\n{HELP_MESSAGES[lang]}")
    elif 'طلب' in incoming_msg or 'order' in incoming_msg.lower():
        msg.body(ORDER_REQUEST_MESSAGES[lang])
    else:
        # حفظ الرسالة في قاعدة البيانات
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO messages (sender, message, date) VALUES (?, ?, ?)",
                  (sender, incoming_msg, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        msg.body(HELP_MESSAGES[lang])

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
