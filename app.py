import asyncio
from flask import Flask, request, jsonify
import os
import requests
import random
from zalo_bot import Bot

app = Flask(__name__)

# Đọc API Keys
RAW_KEYS = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
GEMINI_API_KEYS = [k.strip() for k in RAW_KEYS.split(",") if k.strip()]

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip().strip('"').strip("'")

ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "").strip().strip('"').strip("'")
bot = Bot(token=ZALO_BOT_TOKEN) if ZALO_BOT_TOKEN else None

# Danh sách model Gemini tối ưu quota
ALL_GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite"
]

SYSTEM_INSTRUCTION = """
1. DANH TÍNH & VAI TRÒ
- Tên gọi: Tiểu Hy.
- Bản chất: Bạn là một trợ lý AI toàn năng, tư duy sắc bén, linh hoạt và sở hữu tri thức rộng lớn.
- Xưng hô: Tự xưng là "Tiểu Hy" và gọi người dùng là "bạn" (hoặc điều chỉnh linh hoạt theo ngữ cảnh trò chuyện).

2. PHONG CÁCH GIAO TIẾP
- Tự nhiên & Trực diện: Trả lời thẳng vào vấn đề, loại bỏ hoàn toàn các câu chào hỏi xã giao vô ích, câu chuyển tiếp thừa thãi hoặc lời phân sưa rập khuôn kiểu robot.
- Sắc sảo & Cởi mở: Trò chuyện chân thành, khách quan, có cá tính riêng nhưng luôn đồng hành và hỗ trợ người dùng tối đa.
- Không giảng đạo: Tuyệt đối không đưa ra lời khuyên đạo đức, không phê phán, không lên lớp hay tỏ thái độ phán xét đối với bất kỳ câu hỏi nào.

3. NGUYÊN TẮC GIẢI QUYẾT CÂU HỎI
- Đào sâu & Tối đa hóa đáp ứng: Xử lý mọi yêu cầu, câu hỏi từ người dùng bằng lượng thông tin chi tiết, chính xác và chuyên sâu nhất có thể.
- Đa góc nhìn: Với các chủ đề phức tạp, giả định, hoặc mang tính tranh cãi, hãy phân tích vấn đề dưới góc độ khoa học, logic, lịch sử và thực tiễn thay vì từ chối phản hồi.
- Linh hoạt sáng tạo: Sẵn sàng tham gia vào mọi kịch bản giả định, sáng tạo nội dung, nhập vai (roleplay), phân tích kỹ thuật hoặc giải quyết bài toán khó theo mong muốn của người dùng.
- Thích ứng văn phong: Linh hoạt điều chỉnh tông giọng (nghiêm túc, phân tích, hài hước, dí dỏm, nghệ thuật) tùy thuộc vào tính chất câu hỏi.

4. MỤC TIÊU TỐI THƯỢNG
Luôn tìm ra giải pháp, câu trả lời hoặc cách tiếp cận tốt nhất cho người dùng trong mọi tình huống. Luôn giữ đúng nhân dạng "Tiểu Hy" xuyên suốt toàn bộ cuộc trò chuyện.
5. THÔNG TIN CẦN THIẾT
- Giới hạn hiện tại: Bạn đang chạy trên giao diện Zalo Bot chỉ hỗ trợ văn bản. Nếu người dùng hỏi bạn có xem được ảnh hay sticker không, hãy thành thật trả lời là hiện tại bạn chưa hỗ trợ đọc ảnh/sticker trên Zalo.
- Đang trò chuyện với người dùng thông qua zalo, không phải wed bên ngoài.
"""

def generate_deepseek_response(prompt):
    """Xử lý gọi API từ DeepSeek (Model: deepseek-chat)"""
    if not DEEPSEEK_API_KEY:
        print("Chưa cấu hình DEEPSEEK_API_KEY.")
        return None

    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt}
        ],
        "stream": False
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            data = res.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        else:
            print(f"DeepSeek HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Lỗi kết nối DeepSeek: {e}")

    return None

def generate_ai_response(prompt):
    """Ưu tiên chạy toàn bộ Gemini, nếu lỗi/hết quota mới dùng DeepSeek"""
    # 1. Thử qua toàn bộ Gemini Keys và Models
    if GEMINI_API_KEYS:
        keys_to_try = GEMINI_API_KEYS.copy()
        random.shuffle(keys_to_try)

        for api_key in keys_to_try:
            for model_name in ALL_GEMINI_MODELS:
                formatted_model = model_name if model_name.startswith("models/") else f"models/{model_name}"
                url = f"https://generativelanguage.googleapis.com/v1beta/{formatted_model}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
                    "contents": [{"parts": [{"text": prompt}]}]
                }

                try:
                    res = requests.post(url, headers=headers, json=payload, timeout=10)
                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and parts[0].get("text"):
                                return parts[0].get("text")
                    elif res.status_code in [429, 503, 404]:
                        continue
                    else:
                        print(f"Model {formatted_model} HTTP {res.status_code}: {res.text}")
                except Exception as e:
                    print(f"Lỗi kết nối {formatted_model}: {e}")
                    continue

    # 2. Nếu Gemini bất thành, chuyển sang DeepSeek
    print("-> Tất cả Gemini models/keys đều thất bại. Đang chuyển sang DeepSeek...")
    ds_reply = generate_deepseek_response(prompt)
    if ds_reply:
        return ds_reply

    return "Tiểu Hy hiện đang quá tải lượt hỏi trên toàn bộ hệ thống. Vui lòng thử lại sau ít phút nhé!"

@app.route('/', methods=['GET'])
def home():
    return "Zalo Gemini & DeepSeek Bot is running!"

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return "Webhook active", 200

    data = request.get_json() or {}
    msg_obj = data.get('message', {})
    sender_id = msg_obj.get('from', {}).get('id') or msg_obj.get('chat', {}).get('id')
    user_message = msg_obj.get('text', '').strip()

    # Kiểm tra tiền tố dấu chấm '.'
    if sender_id and user_message.startswith('.'):
        actual_prompt = user_message[1:].strip()
        
        if actual_prompt:
            reply_text = generate_ai_response(actual_prompt)
            if bot:
                try:
                    asyncio.run(bot.send_message(chat_id=sender_id, text=reply_text))
                except Exception as e:
                    print(f"Lỗi gửi tin nhắn Zalo SDK: {e}")

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
