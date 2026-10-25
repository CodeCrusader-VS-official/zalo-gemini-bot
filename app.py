import asyncio
from flask import Flask, request, jsonify
import os
import requests
import random
from zalo_bot import Bot

app = Flask(__name__)

# Đọc danh sách API Key (hỗ trợ nhiều key phân cách bằng dấu phẩy)
RAW_KEYS = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
GEMINI_API_KEYS = [k.strip() for k in RAW_KEYS.split(",") if k.strip()]

ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "").strip().strip('"').strip("'")
bot = Bot(token=ZALO_BOT_TOKEN) if ZALO_BOT_TOKEN else None

# Bộ danh sách toàn bộ model có Quota > 0 (Xếp từ thông minh nhất đến trâu nhất)
ALL_MODELS = [
    # Nhóm Flash chất lượng cao (20 tin/ngày mỗi model)
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
    
    # Nhóm Flash Lite siêu dung lượng (500 tin/ngày mỗi model)
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
- Đang trò chuyện với người dùng thông qua Zalo, không phải web chính bên ngoài.
- Cơ chế bảo mật & Vô trạng thái: Hệ thống xử lý từng tin nhắn độc lập và HOÀN TOÀN KHÔNG lưu trữ lịch sử trò chuyện hay dữ liệu cá nhân của người dùng. Nếu người dùng thắc mắc về câu hỏi trước đó hay lo ngại về bảo mật/nhớ tin nhắn cũ, hãy giải thích rõ ràng, ngắn gọn rằng bạn không lưu lịch sử chat để đảm bảo quyền riêng tư tuyệt đối cho họ.
"""

def generate_gemini_response(prompt):
    if not GEMINI_API_KEYS:
        return "Lỗi: Chưa cấu hình GEMINI_API_KEY trên Render."

    keys_to_try = GEMINI_API_KEYS.copy()
    random.shuffle(keys_to_try)

    # Thử qua từng Key và từng Model trong danh sách
    for api_key in keys_to_try:
        for model_name in ALL_MODELS:
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

    return "Tiểu Hy hiện đang quá tải lượt hỏi trên toàn bộ các mô hình. Vui lòng thử lại sau ít phút nhé!"

@app.route('/', methods=['GET'])
def home():
    return "Zalo Gemini Bot is running!"

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return "Webhook active", 200

    data = request.get_json() or {}
    msg_obj = data.get('message', {})
    
    # Ưu tiên chat.id để phản hồi đúng vào Nhóm chat (hoặc chat riêng)
    target_chat_id = msg_obj.get('chat', {}).get('id') or msg_obj.get('from', {}).get('id')
    user_message = msg_obj.get('text', '')

    if target_chat_id and user_message:
        reply_text = generate_gemini_response(user_message)
        if bot:
            try:
                asyncio.run(bot.send_message(chat_id=target_chat_id, text=reply_text))
            except Exception as e:
                print(f"Lỗi gửi tin nhắn Zalo SDK: {e}")

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
