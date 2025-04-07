
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

@app.route("/bot", methods=['POST'])
def bot():
    incoming_msg = request.values.get('Body', '').strip()
    resp = MessagingResponse()
    msg = resp.message()

    if incoming_msg.lower() in ['hi', 'hello', 'مرحبا', 'السلام عليكم']:
        msg.body("مرحباً بك في الوداد للعطور! 🌹\nكيف أقدر أساعدك؟")
    elif 'طلب' in incoming_msg or 'order' in incoming_msg.lower():
        msg.body("يرجى تزويدنا برقم الطلب للمتابعة. شكراً لك!")
    else:
        msg.body("كيف أقدر أساعدك؟")

    return str(resp)

if __name__ == "__main__":
    app.run(debug=True)
