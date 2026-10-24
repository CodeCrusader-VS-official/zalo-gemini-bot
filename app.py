from flask import Flask, request, jsonify
import os
import requests
import google.generativeai as genai

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "").strip().strip('"').strip("'")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def get_working_model():
    """Tự động lấy danh sách model hỗ trợ chat thực tế từ API Key"""
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        print(f"-> Danh sách Model khả dụng cho Key của bạn: {available_models}")
        
        if available_models:
            # Ưu tiên lấy model flash nếu có
            for model_name in available_models:
                if 'flash' in model_name:
                    return model_name
            return available_models[0]
    except Exception as e:
        print(f"Lỗi truy vấn danh sách Model từ Gemini API: {e}")
    return None

def generate_gemini_response(prompt):
    model_name = get_working_model()
    if not model_name:
        return "Lỗi: GEMINI_API_KEY không hợp lệ hoặc chưa được cấp quyền truy cập AI."
    
    try:
        print(f"-> Đang xử lý bằng model: {model_name}")
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        if response and response.text:
            return response.text
    except Exception as e:
        print(f"Lỗi khi tạo phản hồi với model {model_name}: {e}")
    return "Lỗi: Không thể tạo câu trả lời từ AI Gemini."

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
