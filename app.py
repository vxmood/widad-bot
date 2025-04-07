from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import os

app = Flask(__name__)

# رسائل الترحيب
WELCOME_MESSAGES = {
    'ar': "مرحباً بك في الوداد للعطور! 🌹",
    'en': "Welcome to Widad Perfumes! 🌹"
}

# السؤال عن المساعدة
HELP_MESSAGES = {
    'ar': "كيف أقدر أساعدك؟",
    'en': "How can I help you?"
}

# طلب رقم الطلب
ORDER_REQUEST_MESSAGES = {
    'ar': "يرجى تزويدنا برقم الطلب للمتابعة. شكراً لك!",
    'en': "Please provide your order number so we can follow up. Thank you!"
}

# حفظ البيانات بشكل بسيط
messages_store = []

@app.route("/bot", methods=['POST'])
def bot():
    incoming_msg = request.values.get('Body', '').strip()
    print("📥 Received message:", incoming_msg)

    lang = 'ar' if any(word in incoming_msg for word in ['طلب', 'رقم', 'مرحبا']) else 'en'

    resp = MessagingResponse()
    msg = resp.message()

    # الترحيب + سؤال المساعدة
    if incoming_msg.lower() in ['hi', 'hello', 'مرحبا', 'السلام عليكم']:
        msg.body(f"{WELCOME_MESSAGES[lang]}\n{HELP_MESSAGES[lang]}")
    elif 'طلب' in incoming_msg or 'order' in incoming_msg.lower():
        msg.body(ORDER_REQUEST_MESSAGES[lang])
    else:
        # حفظ الرسالة
        messages_store.append({
            'message': incoming_msg,
            'language': lang
        })
        msg.body(HELP_MESSAGES[lang])

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


