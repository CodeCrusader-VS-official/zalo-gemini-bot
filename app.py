from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "").strip().strip('"').strip("'")

# Danh sách Model Gemini ưu tiên gọi trực tiếp qua HTTP REST
PREFERRED_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-exp"
]

def generate_gemini_response(prompt):
    if not GEMINI_API_KEY:
        return "Lỗi: Chưa cấu hình GEMINI_API_KEY trên Render."

    for model_name in PREFERRED_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ]
        }

        try:
            print(f"-> Đang gửi yêu cầu tới Gemini (Model: {model_name})...")
            res = requests.post(url, headers=headers, json=payload, timeout=8)
            
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        reply_text = parts[0].get("text", "")
                        if reply_text:
                            print(f"-> Phản hồi thành công từ model: {model_name}")
                            return reply_text
            else:
                print(f"Model {model_name} trả về lỗi HTTP {res.status_code}: {res.text}")
        except Exception as e:
            print(f"Lỗi kết nối tới model {model_name}: {e}")
            continue

    return "Lỗi: Không thể kết nối tới AI Gemini. Bạn vui lòng kiểm tra lại GEMINI_API_KEY."

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
