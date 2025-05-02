from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
import torch
from functools import lru_cache
import sqlite3
from datetime import datetime
import re
import os
import logging

# تهيئة التطبيق
app = Flask(__name__)

# 1. إعداد التسجيل (Logging)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. تحميل نموذج الذكاء الاصطناعي (مع التخزين المؤقت)
@lru_cache(maxsize=1)
def load_ai_model():
    try:
        model_name = "aubmindlab/bert-base-arabertv02-twitter"  # نسخة خفيفة
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            device_map="auto",
            load_in_8bit=True,  # تقليل استخدام الذاكرة
            torch_dtype=torch.float16
            low_cpu_mem_usage=True 
        )
        
        return pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            device=0 if torch.cuda.is_available() else -1
        )
    except Exception as e:
        logger.error(f"Failed to load AI model: {e}")
        raise

# تعطيل الحسابات التلقائية لتوفير الذاكرة
torch.set_grad_enabled(False)
ai_model = load_ai_model()

# 3. إعداد قاعدة البيانات
DB_PATH = os.getenv("DB_PATH", "conversations.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            user_id TEXT PRIMARY KEY,
            context TEXT,
            last_updated TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            message TEXT,
            response TEXT,
            timestamp TEXT
        )
        """)

init_db()

# 4. فئات مساعدة لإدارة المحادثة
class ConversationManager:
    def __init__(self, db_path):
        self.db_path = db_path
    
    def get_context(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT context FROM conversations WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def update_context(self, user_id, context):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO conversations VALUES (?, ?, ?)",
                (user_id, context, datetime.now().isoformat())
            )
    
    def log_message(self, user_id, message, response):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO messages VALUES (NULL, ?, ?, ?, ?)",
                (user_id, message, response, datetime.now().isoformat())
            )

conversation_mgr = ConversationManager(DB_PATH)

# 5. معالجة الرسائل الواردة
def preprocess_text(text):
    """تنظيف النص المدخل"""
    text = re.sub(r'[^\w\s\u0600-\u06FF]', '', text)  # إزالة غير الأحرف العربية
    return text.strip()

def should_ignore(message):
    """تجاهل رسائل النظام"""
    ignore_phrases = [
        "Twilio Sandbox:",
        "You are all set!",
        "رسالة نظام"
    ]
    return any(phrase in message for phrase in ignore_phrases)

def generate_ai_response(prompt, context=None):
    """توليد رد باستخدام الذكاء الاصطناعي"""
    try:
        full_prompt = f"المحادثة السابقة:\n{context}\n\nالسؤال: {prompt}\nالجواب:" if context else prompt
        
        response = ai_model(
            full_prompt,
            max_length=150,
            num_return_sequences=1,
            temperature=0.7,
            top_p=0.9,
            do_sample=True
        )
        
        return response[0]['generated_text'].split("الجواب:")[-1].strip()
    except Exception as e:
        logger.error(f"AI generation error: {e}")
        return "عذرًا، حدث خطأ في معالجة طلبك. يرجى المحاولة لاحقًا."

# 6. واجهة واتساب الرئيسية
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        # استقبال البيانات
        incoming_msg = request.values.get("Body", "").strip()
        sender = request.values.get("From", "")
        
        logger.info(f"رسالة من {sender[:10]}...: {incoming_msg}")
        
        # تجاهل الرسائل غير المرغوب فيها
        if should_ignore(incoming_msg):
            return "", 200
        
        # تنظيف رقم الهاتف
        user_id = re.sub(r'\D', '', sender)[-9:]  # أخذ آخر 9 أرقام
        
        # الحصول على السياق السابق
        context = conversation_mgr.get_context(user_id)
        
        # توليد الرد
        cleaned_msg = preprocess_text(incoming_msg)
        bot_response = generate_ai_response(cleaned_msg, context)
        
        # تحديث السياق
        new_context = f"{context or ''}\nالمستخدم: {cleaned_msg}\nالبوت: {bot_response}"
        conversation_mgr.update_context(user_id, new_context[-1000:])  # حفظ آخر 1000 حرف
        
        # تسجيل التفاعل
        conversation_mgr.log_message(user_id, incoming_msg, bot_response)
        
        # إرسال الرد
        resp = MessagingResponse()
        resp.message(bot_response)
        return str(resp)
    
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": "Internal Server Error"}), 500

# 7. نقاط نهاية مساعدة
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "model_loaded": ai_model is not None,
        "timestamp": datetime.now().isoformat()
    })

@app.route("/logs", methods=["GET"])
def get_logs():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT 10")
        logs = cursor.fetchall()
    return jsonify(logs)

# 8. التشغيل الرئيسي
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)  # debug=False للإنتاج
