from flask import Flask, request, jsonify
import os
import requests
import google.generativeai as genai

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "").strip().strip('"').strip("'")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

@app.route('/', methods=['GET'])
def home():
    return "Zalo Gemini Bot is running!"

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return "Webhook active", 200

    data = request.get_json() or {}
    
    # Trích xuất chính xác ID người gửi và tin nhắn từ cấu trúc JSON của Zalo
    msg_obj = data.get('message', {})
    sender_id = msg_obj.get('from', {}).get('id') or msg_obj.get('chat', {}).get('id')
    user_message = msg_obj.get('text', '')

    if sender_id and user_message:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(user_message)
            reply_text = response.text if response.text else "AI không trả lời."
        except Exception as e:
            print(f"Lỗi Gemini API: {e}")
            reply_text = "Lỗi kết nối AI Gemini."

        send_zalo_message(sender_id, reply_text)

    return jsonify({"status": "success"}), 200

def send_zalo_message(recipient_id, message_text):
    url = "https://openapi.zalo.me/v2.0/oa/message"
    headers = {
        "Content-Type": "application/json",
        "access_token": ZALO_BOT_TOKEN
    }
    payload = {
        "recipient": {"user_id": recipient_id},
        "message": {"text": message_text}
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=5)
    except Exception as e:
        print(f"Lỗi gửi Zalo API: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
