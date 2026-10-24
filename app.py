import asyncio
from flask import Flask, request, jsonify
import os
import requests
from zalo_bot import Bot

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "").strip().strip('"').strip("'")

# Khởi tạo Bot instance từ SDK python-zalo-bot
bot = Bot(token=ZALO_BOT_TOKEN) if ZALO_BOT_TOKEN else None

PREFERRED_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash"
]

def generate_gemini_response(prompt):
    if not GEMINI_API_KEY:
        return "Lỗi: Chưa cấu hình GEMINI_API_KEY trên Render."

    for model_name in PREFERRED_MODELS:
        formatted_model = model_name if model_name.startswith("models/") else f"models/{model_name}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{formatted_model}:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=10)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        reply_text = parts[0].get("text", "")
                        if reply_text:
                            return reply_text
            else:
                print(f"Model {formatted_model} HTTP {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Lỗi kết nối {formatted_model}: {e}")
            continue

    return "Lỗi: Không thể kết nối tới AI Gemini. Vui lòng kiểm tra lại GEMINI_API_KEY."

@app.route('/', methods=['GET'])
def home():
    return "Zalo Gemini Bot is running!"

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return "Webhook active", 200

    data = request.get_json() or {}
    print(f"=== Webhook receive: {data}")
    
    msg_obj = data.get('message', {})
    sender_id = msg_obj.get('from', {}).get('id') or msg_obj.get('chat', {}).get('id')
    user_message = msg_obj.get('text', '')

    if sender_id and user_message:
        reply_text = generate_gemini_response(user_message)
        
        if bot:
            try:
                # Tận dụng phương thức async send_message từ SDK python-zalo-bot
                asyncio.run(bot.send_message(chat_id=sender_id, text=reply_text))
                print(f"-> Gửi thành công qua SDK tới chat_id: {sender_id}")
            except Exception as e:
                print(f"Lỗi gửi tin nhắn qua SDK python-zalo-bot: {e}")
        else:
            print("Lỗi: Chưa cấu hình ZALO_BOT_TOKEN.")

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
