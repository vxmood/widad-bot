from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import joblib
import sqlite3
from datetime import datetime, timedelta
import os
import re
from difflib import SequenceMatcher

app = Flask(__name__)

# تحميل النماذج
try:
    model = joblib.load("intent_model.pkl")
    vectorizer = joblib.load("vectorizer.pkl")
except Exception as e:
    print(f"❌ Error loading models: {e}")
    raise

# إعداد قواعد البيانات
DB_NAME = "widad_messages.db"
TRAINING_DB = "widad_training.db"

RESPONSES = {
    "ترحيب": "مرحباً بك في الوداد للعطور! 🌹 كيف أقدر أساعدك؟",
    "طلب": "يرجى تزويدنا برقم الطلب للمتابعة. شكرًا لك!",
    "ماعندي_رقم_طلب": "رقم الطلب تم إرساله عبر الإيميل. إذا لم يصلك، يرجى تزويدنا برقم الهاتف المسجل في الطلب للمتابعة.",
    "وين_أحصل_رقم_طلب": "يمكنك العثور على رقم الطلب في الإيميل الذي استخدمته أثناء الطلب. إذا لم يصلك، تواصل معنا برقم الهاتف المسجل وسنساعدك!",
    "فرع": """تفضل بزيارتنا في أقرب فرع لديك 🚗:
    
• سوق بركاء
• سيتي سنتر مسقط (الموالح)
• الموالح (بجانب سيتي سنتر بمحطة شل)
• مسقط مول
• العذيبة (بعد أبراج الصحوة بجانب كنتاكي)
• نزوى جراند مول
• عمان مول
• السويق

⏰ أوقات العمل:
طيلة أيام الأسبوع ما عدا الجمعة
10 ص إلى 1:30 م | 4:30 م إلى 10:00 م

يوم الجمعة:
4:30 م إلى 10:00 م

المجمعات التجارية:
طيلة أيام الأسبوع 10:00 ص إلى 10:00 م
الخميس والجمعة حتى 12:00 بعد منتصف الليل""",
    "شكر": "شكرًا لتواصلك معنا في الوداد للعطور 🌹 نحن دائماً في خدمتك.",
    "default": "كيف أقدر أساعدك؟"
}

# أنماط الكلام
GREETINGS = ["السلام عليكم", "هلا", "مرحبا", "أهلاً"]
THANKS = ["شكرا", "شكرًا", "مشكووور", "مشكور"]
ORDER_PATTERNS = [
    r"رقم الطلب",
    r"الطلب رقم",
    r"طلب رقم",
    r"رقم\s*\d+"
]

# تحسين قاعدة البيانات
def init_db():
    for db_name in [DB_NAME, TRAINING_DB]:
        conn = sqlite3.connect(db_name)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS sessions (
            phone TEXT PRIMARY KEY, 
            last_seen TEXT,
            context TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS training_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            message TEXT,
            predicted_intent TEXT,
            confidence REAL,
            timestamp TEXT
        )''')
        conn.commit()
        conn.close()

init_db()

# تحليل النية مع الثقة
def predict_intent(text):
    try:
        X = vectorizer.transform([text])
        proba = model.predict_proba(X)[0]
        max_proba = max(proba)
        intent = model.predict(X)[0]
        return intent, float(max_proba)
    except Exception as e:
        print(f"⚠️ Prediction error: {e}")
        return "default", 0.0

# ذاكرة المحادثة
def get_context(phone):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    context = c.execute('''SELECT context FROM sessions WHERE phone = ?''', (phone,)).fetchone()
    conn.close()
    return context[0] if context else None

def update_context(phone, context):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO sessions (phone, last_seen, context) 
                 VALUES (?, ?, ?)''', 
              (phone, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), context))
    conn.commit()
    conn.close()

# معالجة الطلبات
def handle_order_request(phone, message):
    order_num = re.search(r'\d{5,}', message)
    if order_num:
        update_context(phone, f"order_{order_num.group()}")
        return f"تم تسجيل طلبك رقم {order_num.group()}. سيتم متابعته خلال 24 ساعة."
    return RESPONSES["طلب"]

# تحسين التعرف على الكلام
def text_similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

@app.route("/bot", methods=["POST"])
def bot():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    print(f"📩 {sender[:5]}...: {incoming_msg}")

    # تحديد الهوية
    phone = re.sub(r'\D', '', sender)[-9:]  # أخر 9 أرقام

    # التحقق من المحادثات السابقة
    context = get_context(phone)
    
    # معالجة خاصة بناءً على السياق
    if context and context.startswith("order_"):
        order_num = context.split("_")[1]
        update_context(phone, None)
        return str(MessagingResponse().message(
            f"شكرًا لمتابعة طلبك رقم {order_num}. تم تحديث حالة الطلب."
        ))

    # تحليل النية
    intent, confidence = predict_intent(incoming_msg)
    reply = RESPONSES.get(intent, RESPONSES["default"])

    # معالجة خاصة للطلبات
    if any(re.search(pattern, incoming_msg) for pattern in ORDER_PATTERNS):
        reply = handle_order_request(phone, incoming_msg)
    elif any(text_similarity(incoming_msg, g) > 0.8 for g in GREETINGS):
        reply = RESPONSES["ترحيب"]
        intent = "ترحيب"
    elif any(text_similarity(incoming_msg, t) > 0.7 for t in THANKS):
        reply = RESPONSES["شكر"]
        intent = "شكر"

    # تسجيل البيانات
    try:
        conn = sqlite3.connect(TRAINING_DB)
        c = conn.cursor()
        c.execute('''INSERT INTO training_data 
                    (phone, message, predicted_intent, confidence, timestamp)
                    VALUES (?, ?, ?, ?, ?)''',
                 (phone, incoming_msg, intent, confidence, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Database error: {e}")

    # الرد الذكي
    resp = MessagingResponse()
    msg = resp.message()
    
    # إضافة اقتراحات إن كانت الإجابة عامة
    if intent == "default":
        msg.body(reply + "\n\nيمكنك طرح:\n- أسئلة عن الطلبات\n- استفسارات عن الفروع\n- أو أي استفسار آخر")
    else:
        msg.body(reply)
    
    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
