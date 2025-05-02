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

# إعدادات التطبيق
DB_NAME = "widad_conversations_v2.db"
TRAINING_DB = "widad_training_v2.db"

RESPONSES = {
    "ترحيب": "مرحباً بك في متاجر الوداد للعطور! 🌹\nكيف يمكنني مساعدتك اليوم؟",
    "طلب": "لمتابعة طلبك، يرجى إرسال رقم الطلب المكون من 5 أرقام أو أكثر.",
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
    "default": "عذراً لم أفهم طلبك. الرجاء اختيار:\n1. متابعة طلب\n2. مواقع الفروع\n3. أسئلة عامة"
}

# ثوابت التحكم
MIN_CONFIDENCE = 0.65
GREETINGS = ["السلام عليكم", "مرحبا", "اهلا", "هلا", "السلام"]
TWILIO_SANDBOX_MSGS = ["You are all set!", "Twilio Sandbox:"]

# تهيئة قواعد البيانات
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            phone TEXT PRIMARY KEY,
            last_intent TEXT,
            created_at TEXT,
            updated_at TEXT
        )''')
    
    with sqlite3.connect(TRAINING_DB) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            message TEXT,
            intent TEXT,
            confidence REAL,
            created_at TEXT
        )''')

init_db()

# تحسين معالجة النص
def clean_text(text):
    text = re.sub(r'[^\w\s]', '', text)  # إزالة علامات الترقيم
    return text.strip()

# تحليل النية المحسنة
def predict_intent(text):
    try:
        cleaned_text = clean_text(text)
        X = vectorizer.transform([cleaned_text])
        proba = model.predict_proba(X)[0]
        max_proba = max(proba)
        intent = model.predict(X)[0]
        return intent, float(max_proba)
    except Exception as e:
        print(f"⚠️ Prediction error: {e}")
        return "default", 0.0

# إدارة المحادثة
def handle_conversation(phone, message):
    # تجاهل رسائل ساندبوكس تويليو
    if any(sandbox_msg in message for sandbox_msg in TWILIO_SANDBOX_MSGS):
        return None
        
    # تنظيف رقم الهاتف
    phone = re.sub(r'\D', '', phone)[-9:]
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        
        # التحقق من وجود المستخدم
        user = cursor.execute('''SELECT last_intent FROM users WHERE phone = ?''', (phone,)).fetchone()
        
        # معالجة التحية الأولى
        if not user or any(text.lower() in message.lower() for text in GREETINGS):
            cursor.execute('''INSERT OR REPLACE INTO users 
                           (phone, last_intent, created_at, updated_at)
                           VALUES (?, ?, ?, ?)''',
                        (phone, "ترحيب", datetime.now(), datetime.now()))
            conn.commit()
            return RESPONSES["ترحيب"]
        
        # تحليل النية
        intent, confidence = predict_intent(message)
        
        # معالجة خاصة لأنواع الطلبات
        if "فرع" in message or (intent == "فرع" and confidence >= MIN_CONFIDENCE):
            response = RESPONSES["فرع"]
            new_intent = "فرع"
        elif "طلب" in message or (intent == "طلب" and confidence >= MIN_CONFIDENCE):
            response = RESPONSES["طلب"]
            new_intent = "طلب"
        else:
            response = RESPONSES["default"]
            new_intent = "default"
        
        # تحديث سجل المستخدم
        cursor.execute('''UPDATE users 
                         SET last_intent = ?, updated_at = ?
                         WHERE phone = ?''',
                      (new_intent, datetime.now(), phone))
        conn.commit()
        
        # تسجيل التدريب
        with sqlite3.connect(TRAINING_DB) as training_conn:
            training_conn.execute('''INSERT INTO messages 
                                   (phone, message, intent, confidence, created_at)
                                   VALUES (?, ?, ?, ?, ?)''',
                                (phone, message, intent, confidence, datetime.now()))
        
        return response

@app.route("/bot", methods=["POST"])
def whatsapp_bot():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    
    print(f"📩 رسالة جديدة من {sender[:10]}...: {incoming_msg}")
    
    response = handle_conversation(sender, incoming_msg)
    
    if not response:
        return "", 200  # تجاهل رسائل الساندبوكس
    
    twiml_response = MessagingResponse()
    twiml_response.message(response)
    
    return str(twiml_response)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
