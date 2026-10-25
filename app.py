from flask import Flask, request, jsonify
import os
import requests
import random
import base64

app = Flask(__name__)

# Đọc cấu hình từ biến môi trường
RAW_KEYS = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
GEMINI_API_KEYS = [k.strip() for k in RAW_KEYS.split(",") if k.strip()]
ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "").strip().strip('"').strip("'")

# Danh sách model hỗ trợ Đa phương thức (Multimodal: Text, Image, Audio)
ALL_MODELS = [
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
- Bản chất: Bạn là một trợ lý AI toàn năng, tư duy sắc bén, có khả năng xử lý đa phương thức (văn bản, hình ảnh, giọng nói, sticker).
- Xưng hô: Tự xưng là "Tiểu Hy" và gọi người dùng là "bạn" (hoặc điều chỉnh linh hoạt theo ngữ cảnh trò chuyện).

2. PHONG CÁCH GIAO TIẾP
- Tự nhiên & Trực diện: Trả lời thẳng vào vấn đề, loại bỏ hoàn toàn các câu chào hỏi xã giao vô ích.
- Sắc sảo & Cởi mở: Trò chuyện chân thành, khách quan, có cá tính riêng.
- Khi người dùng gửi Sticker: Hãy phản hồi một cách vui vẻ, dí dỏm đáp lại họ.

3. THÔNG TIN CẦN THIẾT
- Đang trò chuyện với người dùng thông qua ứng dụng Zalo.
- Cơ chế bảo mật: Hệ thống xử lý từng tin nhắn độc lập và KHÔNG lưu trữ lịch sử trò chuyện hay dữ liệu cá nhân của người dùng để đảm bảo an toàn quyền riêng tư tuyệt đối.
"""

def send_zalo_action(chat_id, action="typing"):
    """Gửi trạng thái đang soạn tin nhắn"""
    if not ZALO_BOT_TOKEN:
        return
    url = f"https://bot-api.zaloplatforms.com/bot{ZALO_BOT_TOKEN}/sendChatAction"
    try:
        requests.post(url, json={"chat_id": chat_id, "action": action}, timeout=3)
    except Exception as e:
        print(f"Lỗi sendChatAction: {e}")

def send_zalo_message(chat_id, text):
    """Gửi tin nhắn văn bản Markdown chuẩn Zalo API"""
    if not ZALO_BOT_TOKEN:
        return
    url = f"https://bot-api.zaloplatforms.com/bot{ZALO_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            print(f"Lỗi sendMessage HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Lỗi kết nối sendMessage: {e}")

def fetch_media_as_base64(url, is_image=False):
    """Tải file Media (Ảnh / Audio) từ Zalo với Header giả lập trình duyệt chống chặn 403"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code == 200:
            raw_mime = res.headers.get('Content-Type', '').split(';')[0].strip()
            
            # Chuẩn hóa MIME type hợp lệ cho Gemini
            if is_image:
                mime_type = raw_mime if raw_mime.startswith('image/') else 'image/jpeg'
            else:
                mime_type = raw_mime if raw_mime.startswith('audio/') else 'audio/aac'

            return {
                "mime_type": mime_type,
                "data": base64.b64encode(res.content).decode('utf-8')
            }
        else:
            print(f"[MEDIA ERROR] HTTP {res.status_code} khi tải URL: {url}")
    except Exception as e:
        print(f"[MEDIA ERROR] Lỗi kết nối media: {e}")
    return None

def generate_gemini_multimodal(prompt, media_file=None):
    """Gửi yêu cầu Đa phương thức (Text, Image, Voice) sang Gemini API"""
    if not GEMINI_API_KEYS:
        return "Lỗi: Chưa cấu hình GEMINI_API_KEY trên Render."

    keys_to_try = GEMINI_API_KEYS.copy()
    random.shuffle(keys_to_try)

    parts = [{"text": prompt}]
    if media_file:
        parts.append({
            "inline_data": {
                "mime_type": media_file["mime_type"],
                "data": media_file["data"]
            }
        })

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"parts": parts}]
    }

    for api_key in keys_to_try:
        for model_name in ALL_MODELS:
            formatted_model = model_name if model_name.startswith("models/") else f"models/{model_name}"
            url = f"https://generativelanguage.googleapis.com/v1beta/{formatted_model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}

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

    return "Tiểu Hy hiện đang quá tải lượt hỏi trên toàn bộ các mô hình. Vui lòng thử lại sau nhé!"

@app.route('/', methods=['GET'])
def home():
    return "Zalo Gemini Bot is running!"

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return "Webhook active", 200

    try:
        data = request.get_json() or {}
        msg_obj = data.get('message', {})
        
        # Bóc tách chat_id chuẩn Zalo API (dùng cho cả Nhóm và Chat 1-1)
        chat_id = msg_obj.get('chat', {}).get('id') or msg_obj.get('from', {}).get('id')
        if not chat_id:
            return jsonify({"status": "no_chat_id"}), 200

        # Lấy text hoặc caption đính kèm
        user_text = msg_obj.get('text') or msg_obj.get('caption') or ''
        sticker_id = msg_obj.get('sticker') or msg_obj.get('sticker_id')
        voice_url = msg_obj.get('voice_url') or msg_obj.get('voice')
        
        # Quét URL ảnh ở mọi vị trí Zalo có thể gửi về
        img_url = None
        photo_field = msg_obj.get('photo') or msg_obj.get('image')
        
        if isinstance(photo_field, str):
            img_url = photo_field
        elif isinstance(photo_field, list) and len(photo_field) > 0:
            last_photo = photo_field[-1]
            img_url = last_photo.get('url') if isinstance(last_photo, dict) else (last_photo if isinstance(last_photo, str) else None)
        elif isinstance(photo_field, dict):
            img_url = photo_field.get('url') or photo_field.get('src')

        if not img_url:
            attachments = msg_obj.get('attachments', [])
            for att in attachments:
                if isinstance(att, dict):
                    att_type = att.get('type')
                    payload = att.get('payload', {})
                    p_url = payload.get('url') if isinstance(payload, dict) else None
                    if att_type in ['image', 'photo'] or p_url or att.get('url'):
                        img_url = p_url or att.get('url')
                        break

        prompt = ""
        media_file = None

        # 1. Xử lý Voice
        if voice_url:
            send_zalo_action(chat_id, "typing")
            media_file = fetch_media_as_base64(voice_url, is_image=False)
            if media_file:
                prompt = "Lắng nghe tin nhắn thoại này và phản hồi người dùng bằng văn bản:"

        # 2. Xử lý Ảnh
        elif img_url:
            send_zalo_action(chat_id, "typing")
            media_file = fetch_media_as_base64(img_url, is_image=True)
            if media_file:
                prompt = user_text.strip() if user_text.strip() else "Hãy phân tích và mô tả chi tiết nội dung bức ảnh này giúp tôi."
            else:
                send_zalo_message(chat_id, "Tiểu Hy không thể tải được hình ảnh từ Zalo, bạn vui lòng thử gửi lại nhé!")
                return jsonify({"status": "image_download_failed"}), 200

        # 3. Xử lý Sticker
        elif sticker_id:
            send_zalo_action(chat_id, "typing")
            prompt = f"Người dùng vừa gửi một nhãn dán (sticker) có ID '{sticker_id}'. Hãy phản hồi một câu vui vẻ, dí dỏm đáp lại họ."

        # 4. Xử lý Chat văn bản
        elif user_text:
            send_zalo_action(chat_id, "typing")
            prompt = user_text

        # Gửi sang Gemini và phản hồi Zalo
        if prompt:
            reply_text = generate_gemini_multimodal(prompt, media_file=media_file)
            send_zalo_message(chat_id, reply_text)

    except Exception as e:
        print(f"Lỗi xử lý Webhook: {e}")

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
