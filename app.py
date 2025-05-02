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
import psutil
import time
from threading import Lock

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DB_PATH = os.getenv("DB_PATH", "conversations.db")
MODEL_NAME = "aubmindlab/aragpt2-base"  # نموذج مخصص للتوليد
MAX_CONTEXT_LENGTH = 1000  # عدد الأحرف الأقصى للسياق
MAX_RESPONSE_TIME = 10  # ثواني

# Lock for thread-safe model access
model_lock = Lock()

@lru_cache(maxsize=1)
def load_ai_model():
    try:
        logger.info("Loading AI model...")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
        
        device = 0 if torch.cuda.is_available() else -1
        if device == 0:
            logger.info("Using GPU acceleration")
            model = model.to('cuda')
        else:
            logger.info("Using CPU")
            
        return pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            device=device
        )
    except Exception as e:
        logger.error(f"Failed to load AI model: {e}", exc_info=True)
        raise

# Initialize model
torch.set_grad_enabled(False)
ai_model = load_ai_model()

def init_db():
    try:
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
                timestamp TEXT,
                intent TEXT
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON messages (user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON messages (timestamp)")
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        raise

init_db()

class ConversationManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.lock = Lock()

    def get_context(self, user_id):
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT context FROM conversations WHERE user_id = ?", (user_id,))
                    result = cursor.fetchone()
                    return result[0] if result else ""
            except Exception as e:
                logger.error(f"Error getting context: {e}")
                return ""

    def update_context(self, user_id, new_message, bot_response):
        with self.lock:
            try:
                context = self.get_context(user_id)
                new_entry = f"\nالمستخدم: {new_message}\nالبوت: {bot_response}"
                new_context = (context + new_entry)[-MAX_CONTEXT_LENGTH:]
                
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO conversations VALUES (?, ?, ?)",
                        (user_id, new_context, datetime.now().isoformat())
                    )
            except Exception as e:
                logger.error(f"Error updating context: {e}")

    def log_message(self, user_id, message, response, intent):
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "INSERT INTO messages VALUES (NULL, ?, ?, ?, ?, ?)",
                        (user_id, message, response, datetime.now().isoformat(), intent)
                    )
            except Exception as e:
                logger.error(f"Error logging message: {e}")

conversation_mgr = ConversationManager(DB_PATH)

def detect_intent(message):
    message = message.lower()
    intent_patterns = {
        "طلب": ["طلب", "أبي", "ابي", "اشتري", "شرا", "ابغى", "أريد", "اريد", "كم سعر", "كم توصل", "ارسل لي"],
        "تتبع طلب": ["وين", "وين الطلب", "رقم الطلب", "وصل", "تتبع", "tracking"],
        "شكوى": ["شكوى", "ما عجبني", "غير راضي", "سيئ", "رديء", "خربان"],
        "شكر": ["شكرا", "يعطيك العافية", "مشكور", "تسلم"],
        "تحية": ["مرحبا", "السلام عليكم", "اهلا", "هلا"]
    }
    
    for intent, patterns in intent_patterns.items():
        if any(pattern in message for pattern in patterns):
            return intent
    return "عام"

def preprocess_text(text):
    text = re.sub(r'[^\w\s؀-ۿ]', '', text)
    return text.strip()

def should_ignore(message):
    ignore_phrases = ["Twilio Sandbox:", "You are all set!", "رسالة نظام"]
    return any(phrase in message for phrase in ignore_phrases)

def generate_ai_response(prompt, context=None):
    try:
        start_time = time.time()
        
        if context:
            full_prompt = f"""المحادثة السابقة:
{context}

السؤال: {prompt}
الجواب:"""
        else:
            full_prompt = prompt

        with model_lock:
            response = ai_model(
                full_prompt,
                max_length=60,
                num_return_sequences=1,
                temperature=0.7,
                top_k=30,
                top_p=0.9,
                do_sample=True,
                max_time=MAX_RESPONSE_TIME
            )
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        text = response[0]['generated_text']
        
        # استخراج الجزء الأخير فقط إذا كان هناك "الجواب:"
        if "الجواب:" in text:
            text = text.split("الجواب:")[-1].strip()
        
        # تنظيف الإجابة النهائية
        text = text.split("\n")[0].strip()
        
        logger.info(f"Generation took {time.time() - start_time:.2f} seconds")
        return text
    except Exception as e:
        logger.error(f"AI generation error: {e}", exc_info=True)
        return "عذرًا، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى لاحقًا."

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    duration = time.time() - request.start_time
    logger.info(f"Request {request.path} took {duration:.2f} seconds")
    return response

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.values.get("Body", "").strip()
        sender = request.values.get("From", "")
        
        if not incoming_msg:
            return "", 400

        logger.info(f"📩 رسالة من {sender[:10]}...: {incoming_msg}")

        if should_ignore(incoming_msg):
            return "", 200

        user_id = re.sub(r'\D', '', sender)[-9:]
        cleaned_msg = preprocess_text(incoming_msg)
        intent = detect_intent(cleaned_msg)
        
        # ردود سريعة للنوايا المحددة
        if intent == "تحية":
            bot_response = "أهلاً وسهلاً بك! كيف يمكنني مساعدتك اليوم؟"
        elif intent == "شكر":
            bot_response = "العفو! لا تتردد في طلب المساعدة إذا احتجت أي شيء آخر."
        else:
            context = conversation_mgr.get_context(user_id)
            bot_response = generate_ai_response(cleaned_msg, context)

        if not bot_response:
            bot_response = "أهلاً بك! كيف يمكنني مساعدتك اليوم؟"

        conversation_mgr.update_context(user_id, cleaned_msg, bot_response)
        conversation_mgr.log_message(user_id, incoming_msg, bot_response, intent)

        resp = MessagingResponse()
        resp.message(bot_response)
        return str(resp)
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({"error": "Internal Server Error"}), 500

@app.route("/", methods=["GET"])
def index():
    return "Widad Bot is up and running!"

@app.route("/health", methods=["GET"])
def health():
    mem_info = psutil.Process().memory_info()
    return jsonify({
        "status": "ok",
        "model_loaded": ai_model is not None,
        "memory_usage": f"{mem_info.rss / 1024**2:.2f} MB",
        "active_connections": len(psutil.Process().connections()),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/messages/<user_id>", methods=["GET"])
def get_user_messages(user_id):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT message, response, timestamp, intent 
                FROM messages 
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 20
            """, (user_id,))
            messages = cur.fetchall()
        return jsonify(messages)
    except Exception as e:
        logger.error(f"Error fetching messages: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
