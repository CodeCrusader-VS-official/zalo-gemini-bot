from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "").strip().strip('"').strip("'")

# Danh sách tên Model Gemini thế hệ mới được Google hỗ trợ cho API Key của bạn
PREFERRED_MODELS = [
    "gemini-3.8-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
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
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ]
        }

        try:
            print(f"-> Đang gửi yêu cầu tới Gemini ({formatted_model})...")
            res = requests.post(url, headers=headers, json=payload, timeout=10)
            
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        reply_text = parts[0].get("text", "")
                        if reply_text:
                            print(f"-> Phản hồi thành công từ model: {formatted_model}")
                            return reply_text
            else:
                print(f"Model {formatted_model} trả về lỗi HTTP {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Lỗi kết nối tới model {formatted_model}: {e}")
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
    
    msg_obj = data.get('message', {})
    sender_id = msg_obj.get('from', {}).get('id') or msg_obj.get('chat', {}).get('id')
    user_message = msg_obj.get('text', '')

    if sender_id and user_message:
        reply_text = generate_gemini_response(user_message)
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
        res = requests.post(url, headers=headers, json=payload, timeout=5)
        print(f"-> Kết quả gửi Zalo API: Status {res.status_code}")
    except Exception as e:
        print(f"Lỗi gửi Zalo API: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
