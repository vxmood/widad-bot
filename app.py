from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import joblib
import sqlite3
from datetime import datetime
import re
from difflib import SequenceMatcher
import os

app = Flask(__name__)

# تحميل النماذج
try:
    model = joblib.load("intent_model.pkl")
    vectorizer = joblib.load("vectorizer.pkl")
except Exception as e:
    print(f"❌ Error loading models: {e}")
    raise

# إعداد قواعد البيانات
DB_NAME = "widad_conversations.db"
TRAINING_DB = "widad_training.db"

RESPONSES = {
    "ترحيب": "مرحباً بك في الوداد للعطور! 🌹 كيف أقدر أساعدك اليوم؟",
    "طلب": "للمساعدة في متابعة طلبك، يرجى إرسال رقم الطلب.",
    "ماعندي_رقم_طلب": "يمكنك العثور على رقم الطلب في رسالة التأكيد المرسلة إليك. إذا لم تصلك، يرجى إرسال رقم هاتفك المسجل وسنساعدك.",
    "وين_أحصل_رقم_طلب": "رقم الطلب موجود في:\n1. رسالة التأكيد على الإيميل\n2. رسالة SMS إن كنت مسجلاً بالواتساب\n3. في تطبيقنا إذا كنت تستخدمه",
    "فرع": """أقرب فروعنا لك 🚗:

📍 مسقط:
• سيتي سنتر (الموالح)
• مسقط مول
• العذيبة (بجانب كنتاكي)

📍 خارج مسقط:
• نزوى جراند مول
• السويق
• سوق بركاء

⏰ أوقات العمل:
الأحد-الخميس: 10 ص - 10 م
الجمعة: 4 م - 10 م""",
    "شكر": "شكراً لثقتك بنا 🌹 نرحب بك دائماً في متاجر الوداد للعطور.",
    "default": "عذراً، لم أفهم استفسارك. يمكنك اختيار:\n1. متابعة طلب\n2. معرفة الفروع\n3. أسئلة عامة"
}

# أنماط الكلام
GREETINGS = ["السلام عليكم", "هلا", "مرحبا", "أهلاً", "السلام"]
THANKS = ["شكرا", "شكرًا", "مشكور", "يعطيك العافية"]
ORDER_PATTERNS = [
    r"رقم الطلب",
    r"الطلب رقم",
    r"طلب رقم",
    r"رقم\s*\d+"
]

# تهيئة قواعد البيانات
def init_databases():
    for db_name in [DB_NAME, TRAINING_DB]:
        conn = sqlite3.connect(db_name)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS conversations (
            phone TEXT PRIMARY KEY,
            last_intent TEXT,
            last_message TEXT,
            timestamp TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS training_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            message TEXT,
            intent TEXT,
            confidence REAL,
            timestamp TEXT
        )''')
        
        conn.commit()
        conn.close()

init_databases()

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

# مقارنة النصوص
def text_similarity(a, b, threshold=0.7):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold

# إدارة المحادثة
def get_conversation(phone):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''SELECT last_intent, last_message FROM conversations WHERE phone = ?''', (phone,))
    result = c.fetchone()
    conn.close()
    return result if result else (None, None)

def update_conversation(phone, intent, message):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO conversations 
                 (phone, last_intent, last_message, timestamp)
                 VALUES (?, ?, ?, ?)''',
              (phone, intent, message, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

# تسجيل التدريب
def log_interaction(phone, message, intent, confidence):
    conn = sqlite3.connect(TRAINING_DB)
    c = conn.cursor()
    c.execute('''INSERT INTO training_logs 
                 (phone, message, intent, confidence, timestamp)
                 VALUES (?, ?, ?, ?, ?)''',
              (phone, message, intent, confidence, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

# معالجة الطلبات
def handle_order_request(phone, message):
    order_num = re.search(r'\d{5,}', message)
    if order_num:
        update_conversation(phone, "طلب", f"order_{order_num.group()}")
        return "تم استلام رقم الطلب. سيصلك تحديث الحالة خلال 24 ساعة."
    return RESPONSES["طلب"]

@app.route("/bot", methods=["POST"])
def bot():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    phone = re.sub(r'\D', '', sender)[-9:]  # أخذ آخر 9 أرقام
    
    print(f"📩 رسالة من {phone}: {incoming_msg}")
    
    # استعادة آخر محادثة
    last_intent, last_message = get_conversation(phone)
    
    # التحقق من التحية
    if (not last_intent) or any(text_similarity(incoming_msg, g) for g in GREETINGS):
        update_conversation(phone, "ترحيب", incoming_msg)
        return str(MessagingResponse().message(RESPONSES["ترحيب"]))
    
    # تحليل النية
    intent, confidence = predict_intent(incoming_msg)
    
    # معالجة خاصة لأنواع الطلبات
    if any(re.search(p, incoming_msg) for p in ORDER_PATTERNS):
        reply = handle_order_request(phone, incoming_msg)
    elif any(text_similarity(incoming_msg, t) for t in THANKS):
        reply = RESPONSES["شكر"]
        intent = "شكر"
    elif intent == "فرع" or "فرع" in incoming_msg:
        reply = RESPONSES["فرع"]
    else:
        reply = RESPONSES.get(intent, RESPONSES["default"])
    
    # منع التكرار غير الضروري
    if last_intent == intent and intent in ["فرع", "طلب"]:
        reply = "لا تزال المعلومات نفسها. هل لديك استفسار آخر؟"
    
    # تحديث المحادثة
    update_conversation(phone, intent, incoming_msg)
    log_interaction(phone, incoming_msg, intent, confidence)
    
    # إعداد الرد
    resp = MessagingResponse()
    msg = resp.message()
    
    # تحسين الردود العامة
    if intent == "default":
        suggestions = "\n\nيمكنك اختيار:\n1. متابعة طلب\n2. مواقع الفروع\n3. التوصيل والشحن"
        msg.body(reply + suggestions)
    else:
        msg.body(reply)
    
    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
