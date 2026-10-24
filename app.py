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

# Hồ sơ nhân vật & Hệ quy chuẩn ứng xử của Tiểu Hy
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
"""

def generate_gemini_response(prompt):
    if not GEMINI_API_KEY:
        return "Lỗi: Chưa cấu hình GEMINI_API_KEY trên Render."

    for model_name in PREFERRED_MODELS:
        formatted_model = model_name if model_name.startswith("models/") else f"models/{model_name}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{formatted_model}:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}]
            },
            "contents": [{"parts": [{"text": prompt}]}]
        }

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=12)
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
                asyncio.run(bot.send_message(chat_id=sender_id, text=reply_text))
                print(f"-> Gửi thành công qua SDK tới chat_id: {sender_id}")
            except Exception as e:
                print(f"Lỗi gửi tin nhắn qua SDK python-zalo-bot: {e}")
        else:
            print("Lỗi: Chưa cấu hình ZALO_BOT_TOKEN.")

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
