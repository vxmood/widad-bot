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

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def load_ai_model():
    try:
        model_name = "aubmindlab/bert-base-arabertv02-twitter"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(model_name)
        return pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            device=0 if torch.cuda.is_available() else -1
        )
    except Exception as e:
        logger.error(f"Failed to load AI model: {e}")
        raise

torch.set_grad_enabled(False)
ai_model = load_ai_model()

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


def detect_intent(message):
    message = message.lower()
    if any(x in message for x in ["طلب", "أبي", "ابي", "اشتري", "شرا", "ابغى", "أريد", "اريد", "كم سعر", "كم توصل", "ارسل لي"]):
        return "طلب"
    if any(x in message for x in ["وين", "وين الطلب", "رقم الطلب", "وصل", "تتبع", "tracking"]):
        return "تتبع طلب"
    if any(x in message for x in ["شكوى", "ما عجبني", "غير راضي", "سيئ", "رديء", "خربان"]):
        return "شكوى"
    if any(x in message for x in ["شكرا", "يعطيك العافية", "مشكور", "تسلم"]):
        return "شكر"
    return "عام"


class ConversationManager:
    def __init__(self, db_path):
        self.db_path = db_path

    def get_context(self, user_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT context FROM conversations WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else ""

    def update_context(self, user_id, context):
        context = context[-500:] if context else ""
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

def preprocess_text(text):
    text = re.sub(r'[^\w\s؀-ۿ]', '', text)
    return text.strip()

def should_ignore(message):
    return any(x in message for x in ["Twilio Sandbox:", "You are all set!", "رسالة نظام"])

def generate_ai_response(prompt, context=None):
    try:
        if context:
            full_prompt = f"""المحادثة السابقة:
{context}

السؤال: {prompt}
الجواب:"""
        else:
            full_prompt = prompt

        response = ai_model(
            full_prompt,
            max_length=40,
            num_return_sequences=1,
            temperature=0.7,
            top_k=30,
            do_sample=True
        )
        text = response[0]['generated_text']
        if "الجواب:" in text:
            return text.split("الجواب:")[-1].strip()
        return text.strip()
    except Exception as e:
        logger.error(f"AI generation error: {e}")
        return "عذرًا، حدث خطأ أثناء توليد الرد."

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.values.get("Body", "").strip()
        sender = request.values.get("From", "")
        logger.info(f"📩 رسالة من {sender[:10]}...: {incoming_msg}")

        if should_ignore(incoming_msg):
            return "", 200

        user_id = re.sub(r'\D', '', sender)[-9:]
        context = conversation_mgr.get_context(user_id)
        cleaned_msg = preprocess_text(incoming_msg)
        bot_response = generate_ai_response(cleaned_msg, context)

        if not bot_response:
            bot_response = "أهلاً وسهلاً بك في الوداد للعطور! كيف أقدر أساعدك اليوم؟"

        new_context = f"{context}
المستخدم: {cleaned_msg}
البوت: {bot_response}"
        conversation_mgr.update_context(user_id, new_context)
        conversation_mgr.log_message(user_id, incoming_msg, bot_response)

        resp = MessagingResponse()
        resp.message(bot_response)
        return str(resp)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": "Internal Error"}), 500

@app.route("/", methods=["GET"])
def index():
    return "Widad Bot is up!"

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "model_loaded": ai_model is not None,
        "memory": f"{psutil.Process().memory_info().rss / 1024**2:.2f} MB",
        "time": datetime.now().isoformat()
    })

@app.route("/logs", methods=["GET"])
def get_logs():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT 10")
        return jsonify(cur.fetchall())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
