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
        )''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            sender TEXT PRIMARY KEY,
            state TEXT
        )''')
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
    'ar': "يرجى تزويدنا برقم الطلب للمتابعة.",
    'en': "Please provide your order number so we can follow up."
}

ORDER_LOOKUP_RESPONSES = {
    'ar': "رقم الطلب تم إرساله لك عبر البريد الإلكتروني. إذا لم يصلك أي بريد، يرجى تزويدي برقم الهاتف المسجّل أثناء الطلب وسأساعدك في المتابعة.",
    'en': "Your order number was sent to your email. If you didn't receive it, please send me the phone number used in the order and I’ll help you further."
}

NO_ORDER_PHRASES = [
    'ما عندي رقم',
    'ما وصلني رقم الطلب',
    'ماوصلني رقم طلب',
    'وين احصل رقم طلب',
    'ما جاني رقم',
    'ما حصلت رقم الطلب',
    'ما شفت رقم الطلب',
    'ما وصلني رقم طلبي',
    'ماوصلني رقم طلبي',
    'ما وصلي رقم طلب',
    'ماوصلي رقم طلب',
    'ما وصلي رقم',
    'ماوصلني رقم'
]

TRACKING_REQUEST_PHRASES = [
    'عندي طلب', 'أريد متابعة', 'ابي اتابع طلبي', 'ابي اعرف طلبي', 'وين طلبي', 'وين طلبي؟', 'وين طلبي الان'
]

@app.route("/bot", methods=['POST'])
def bot():
    print("🚀 /bot endpoint was hit")
    incoming_msg = request.values.get('Body', '').strip()
    sender = request.values.get('From', '')
    print("📥 Received message:", incoming_msg)

    lang = 'ar' if any(word in incoming_msg for word in ['طلب', 'رقم', 'مرحبا', 'هلا']) else 'en'

    resp = MessagingResponse()
    msg = resp.message()

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # حفظ الرسالة
    c.execute("INSERT INTO messages (sender, message, date) VALUES (?, ?, ?)",
              (sender, incoming_msg, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

    # الحصول على حالة الجلسة
    c.execute("SELECT state FROM sessions WHERE sender = ?", (sender,))
    row = c.fetchone()
    state = row[0] if row else None

    # تحديث الحالة والرد حسب الجلسة
    response_sent = False

    if state == "awaiting_order_number":
        if any(phrase in incoming_msg.lower() for phrase in NO_ORDER_PHRASES):
            msg.body(ORDER_LOOKUP_RESPONSES[lang])
            c.execute("DELETE FROM sessions WHERE sender = ?", (sender,))
            response_sent = True
        else:
            msg.body(ORDER_REQUEST_MESSAGES[lang])
            response_sent = True

    if not response_sent:
        if any(phrase in incoming_msg.lower() for phrase in TRACKING_REQUEST_PHRASES):
            msg.body(ORDER_REQUEST_MESSAGES[lang])
            c.execute("INSERT OR REPLACE INTO sessions (sender, state) VALUES (?, ?)", (sender, "awaiting_order_number"))
        elif incoming_msg.lower() in ['hi', 'hello', 'مرحبا', 'السلام عليكم']:
            msg.body(f"{WELCOME_MESSAGES[lang]}\n{HELP_MESSAGES[lang]}")
        else:
            msg.body(HELP_MESSAGES[lang])

    conn.commit()
    conn.close()

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
