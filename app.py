from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from transformers import pipeline, AutoTokenizer
import torch
from functools import lru_cache
import sqlite3
from datetime import datetime
import re
import os

app = Flask(__name__)

# 1. تحميل نموذج الذكاء الاصطناعي
@lru_cache(maxsize=1)
def load_ai_model():
    model_name = "aubmindlab/bert-base-arabertv02-twitter"  # نسخة أخف
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map="auto",
        load_in_8bit=True  # تقليل استخدام الذاكرة
    )
    return pipeline("text-generation", model=model, tokenizer=tokenizer)
    )
    return qa_pipeline

ai_model = load_ai_model()

# 2. إعداد قواعد البيانات
DB_NAME = "conversations_ai.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS conversations (
            user_id TEXT PRIMARY KEY,
            context TEXT,
            last_interaction TEXT,
            created_at TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            message TEXT,
            response TEXT,
            timestamp TEXT
        )''')

init_db()

# 3. نظام إدارة المحادثة
class ConversationManager:
    def __init__(self, db_name):
        self.db_name = db_name
    
    def get_context(self, user_id):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''SELECT context FROM conversations WHERE user_id = ?''', (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def update_context(self, user_id, new_context):
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT OR REPLACE INTO conversations 
                            (user_id, context, last_interaction, created_at)
                            VALUES (?, ?, ?, ?)''',
                         (user_id, new_context, now, now))
    
    def log_message(self, user_id, message, response):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''INSERT INTO messages 
                          (user_id, message, response, timestamp)
                          VALUES (?, ?, ?, ?)''',
                       (user_id, message, response, datetime.now().isoformat()))

conversation_mgr = ConversationManager(DB_NAME)

# 4. معالجة الرسائل الواردة
def should_ignore(message):
    ignore_phrases = [
        "Twilio Sandbox:",
        "You are all set!",
        "رسالة نظام"
    ]
    return any(phrase in message for phrase in ignore_phrases)

def clean_phone_number(phone):
    return re.sub(r'\D', '', phone)[-9:]

# 5. توليد الردود الذكية
def generate_response(user_input, user_id):
    # الخطوة 1: الحصول على السياق السابق
    context = conversation_mgr.get_context(user_id) or ""
    
    # الخطوة 2: توليد الرد باستخدام الذكاء الاصطناعي
    prompt = f"المحادثة السابقة:\n{context}\n\nالسؤال الجديد: {user_input}\nالرد:"
    
    try:
        response = ai_model(
            prompt,
            max_length=200,
            num_return_sequences=1,
            temperature=0.7,
            top_p=0.9,
            do_sample=True
        )[0]['generated_text']
        
        # استخراج الجزء الأكثر صلة من الرد
        generated_response = response.split("الرد:")[-1].strip()
        
        # الخطوة 3: تحديث السياق
        new_context = f"{context}\nالمستخدم: {user_input}\nالبوت: {generated_response}"
        conversation_mgr.update_context(user_id, new_context[-1000:])  # حفظ آخر 1000 حرف فقط
        
        # الخطوة 4: تسجيل التفاعل
        conversation_mgr.log_message(user_id, user_input, generated_response)
        
        return generated_response
    
    except Exception as e:
        print(f"⚠️ Error generating response: {e}")
        return "عذرًا، حدث خطأ في معالجة طلبك. يرجى المحاولة لاحقًا."

# 6. واجهة واتساب الرئيسية
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    # استقبال البيانات الواردة
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "")
    
    print(f"📩 رسالة من {sender[:10]}...: {incoming_msg}")
    
    # تجاهل الرسائل غير المرغوب فيها
    if should_ignore(incoming_msg):
        return "", 200
    
    # تنظيف رقم الهاتف
    user_id = clean_phone_number(sender)
    
    # توليد الرد
    bot_response = generate_response(incoming_msg, user_id)
    
    # إرسال الرد
    resp = MessagingResponse()
    resp.message(bot_response)
    return str(resp)

# 7. واجهة الصحة للتأكد من عمل السيرفر
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
