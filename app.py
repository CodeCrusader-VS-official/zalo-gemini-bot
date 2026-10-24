import requests
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# --- Điền Key của bạn vào 2 dòng bên dưới ---
ZALO_BOT_TOKEN = "DÁN_ZALO_BOT_TOKEN_CỦA_BẠN_VÀO_ĐÂY"
GEMINI_API_KEY = "DÁN_GEMINI_API_KEY_VỪA_COPIED_VÀO_ĐÂY"

# Cấu hình Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

def send_zalo_message(chat_id, text):
    url = f"https://bot-api.zalo.me/bot{ZALO_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    
    if data and "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"].get("text", "")
        
        if user_text:
            try:
                # Gửi câu hỏi sang Gemini
                response = model.generate_content(user_text)
                bot_reply = response.text
            except Exception as e:
                bot_reply = "Xin lỗi, hiện tại tôi gặp sự cố khi xử lý dữ liệu."
            
            # Gửi phản hồi lại cho người dùng Zalo
            send_zalo_message(chat_id, bot_reply)
            
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(port=5000)