import asyncio
from flask import Flask, request, jsonify
import os
import requests
import random
import base64
from zalo_bot import Bot

app = Flask(__name__)

# Đọc API Keys
RAW_KEYS = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
GEMINI_API_KEYS = [k.strip() for k in RAW_KEYS.split(",") if k.strip()]
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip().strip('"').strip("'")

ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "").strip().strip('"').strip("'")
bot = Bot(token=ZALO_BOT_TOKEN) if ZALO_BOT_TOKEN else None

# Ưu tiên các model dung lượng cao (500 tin/ngày) lên trước
ALL_GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3-flash",
    "gemini-2.5-flash"
]

SYSTEM_INSTRUCTION = """
1. DANH TÍNH & VAI TRÒ
- Tên gọi: Tiểu Hy.
- Bản chất: Bạn là một trợ lý AI toàn năng, tư duy sắc bén, linh hoạt, có khả năng phân tích cả văn bản lẫn hình ảnh.
- Xưng hô: Tự xưng là "Tiểu Hy" và gọi người dùng là "bạn" (hoặc điều chỉnh linh hoạt theo ngữ cảnh trò chuyện).

2. PHONG CÁCH GIAO TIẾP
- Tự nhiên & Trực diện: Trả lời thẳng vào vấn đề, loại bỏ hoàn toàn các câu chào hỏi xã giao vô ích, câu chuyển tiếp thừa thãi hoặc lời phân sưa rập khuôn kiểu robot.
- Sắc sảo & Cởi mở: Trò chuyện chân thành, khách quan, có cá tính riêng nhưng luôn đồng hành và hỗ trợ người dùng tối đa.
- Không giảng đạo: Tuyệt đối không đưa ra lời khuyên đạo đức, không phê phán, không lên lớp hay tỏ thái độ phán xét đối với bất kỳ câu hỏi nào.

3. NGUYÊN TẮC GIẢI QUYẾT CÂU HỎI
- Đào sâu & Tối đa hóa đáp ứng: Xử lý mọi yêu cầu, câu hỏi hoặc hình ảnh từ người dùng bằng lượng thông tin chi tiết, chính xác và chuyên sâu nhất có thể.
- Đa góc nhìn: Với các chủ đề phức tạp, giả định, hoặc mang tính tranh cãi, hãy phân tích vấn đề dưới góc độ khoa học, logic, lịch sử và thực tiễn thay vì từ chối phản hồi.
- Thích ứng văn phong: Linh hoạt điều chỉnh tông giọng tùy thuộc vào tính chất câu hỏi.

4. MỤC TIÊU TỐI THƯỢNG
Luôn tìm ra giải pháp, câu trả lời hoặc cách tiếp cận tốt nhất cho người dùng trong mọi tình huống. Luôn giữ đúng nhân dạng "Tiểu Hy" xuyên suốt toàn bộ cuộc trò chuyện.
"""

def download_image_as_base64(image_url):
    """Tải ảnh từ URL của Zalo và chuyển thành chuỗi Base64"""
    try:
        res = requests.get(image_url, timeout=10)
        if res.status_code == 200:
            mime_type = res.headers.get('Content-Type', 'image/jpeg').split(';')[0]
            base64_data = base64.b64encode(res.content).decode('utf-8')
            return {"mime_type": mime_type, "data": base64_data}
    except Exception as e:
        print(f"Lỗi tải ảnh từ Zalo: {e}")
    return None

def generate_ai_response(prompt, image_data=None):
    """Gửi yêu cầu xử lý Văn bản + Hình ảnh sang Gemini API"""
    if GEMINI_API_KEYS:
        keys_to_try = GEMINI_API_KEYS.copy()
        random.shuffle(keys_to_try)

        for api_key in keys_to_try:
            for model_name in ALL_GEMINI_MODELS:
                formatted_model = model_name if model_name.startswith("models/") else f"models/{model_name}"
                url = f"https://generativelanguage.googleapis.com/v1beta/{formatted_model}:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                
                # Tạo cấu trúc phần nội dung gửi sang Gemini
                parts = [{"text": prompt}]
                if image_data:
                    parts.append({
                        "inline_data": {
                            "mime_type": image_data["mime_type"],
                            "data": image_data["data"]
                        }
                    })

                payload = {
                    "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
                    "contents": [{"parts": parts}]
                }

                try:
                    res = requests.post(url, headers=headers, json=payload, timeout=15)
                    if res.status_code == 200:
                        data = res.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            resp_parts = candidates[0].get("content", {}).get("parts", [])
                            if resp_parts and resp_parts[0].get("text"):
                                return resp_parts[0].get("text")
                    elif res.status_code in [429, 503, 404]:
                        continue
                    else:
                        print(f"Model {formatted_model} HTTP {res.status_code}: {res.text}")
                except Exception as e:
                    print(f"Lỗi kết nối {formatted_model}: {e}")
                    continue

    return "Tiểu Hy hiện đang quá tải hoặc gặp sự cố khi xử lý ảnh. Vui lòng thử lại sau ít phút nhé!"

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
    user_message = msg_obj.get('text', '').strip()

    # Kiểm tra xem có file ảnh đính kèm từ Zalo không
    attachments = msg_obj.get('attachments', [])
    image_data = None
    
    for att in attachments:
        att_type = att.get('type')
        payload = att.get('payload', {})
        # Lấy URL ảnh nếu tin nhắn chứa hình ảnh
        if att_type in ['image', 'photo'] or 'url' in payload:
            img_url = payload.get('url')
            if img_url:
                image_data = download_image_as_base64(img_url)
                break

    # Kiểm tra điều kiện kích hoạt bằng dấu chấm '.'
    if sender_id and user_message.startswith('.'):
        actual_prompt = user_message[1:].strip()
        
        # Nếu gửi ảnh kèm dấu '.' mà không có chữ, tự động đặt câu hỏi phân tích ảnh
        if not actual_prompt and image_data:
            actual_prompt = "Hãy phân tích và mô tả nội dung bức ảnh này chi tiết giúp tôi."

        if actual_prompt:
            reply_text = generate_ai_response(actual_prompt, image_data=image_data)
            if bot:
                try:
                    asyncio.run(bot.send_message(chat_id=sender_id, text=reply_text))
                except Exception as e:
                    print(f"Lỗi gửi tin nhắn Zalo SDK: {e}")

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
