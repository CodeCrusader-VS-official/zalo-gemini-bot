from flask import Flask, request, jsonify, Response
import os
import requests
import random
import base64
import urllib.parse
import uuid
import threading
import io
import re
import time
from PIL import Image

app = Flask(__name__)

# Đọc cấu hình từ biến môi trường
RAW_KEYS = os.getenv("GEMINI_API_KEY", "").strip().strip('"').strip("'")
GEMINI_API_KEYS = [k.strip() for k in RAW_KEYS.split(",") if k.strip()]
ZALO_BOT_TOKEN = os.getenv("ZALO_BOT_TOKEN", "").strip().strip('"').strip("'")

# Bộ lưu trữ ảnh tạm thời trong bộ nhớ RAM
IMAGE_CACHE = {}

# Danh sách Model Chat / Đa phương thức
ALL_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemma-4-31b-it",
    "gemma-4-26b-it"
]

SYSTEM_INSTRUCTION = """
1. DANH TÍNH & VAI TRÒ
- Tên gọi: Tiểu Hy.
- Bản chất: Bạn là một trợ lý AI toàn năng, tư duy sắc bén, có khả năng xử lý đa phương thức (văn bản, hình ảnh, giọng nói, sticker).
- Xưng hô: Tự xưng là "Tiểu Hy" và gọi người dùng là "bạn" (hoặc điều chỉnh linh hoạt theo ngữ cảnh trò chuyện).

2. PHONG CÁCH GIAO TIẾP
- Tự nhiên & Trực diện: Trả lời thẳng vào vấn đề, loại bỏ hoàn toàn các câu chào hỏi xã giao vô ích.
- Sắc sảo & Cởi mở: Trò chuyện chân thành, khách quan, có cá tính riêng.
- Khi người dùng gửi Sticker: Hãy phản hồi một câu vui vẻ, dí dỏm đáp lại họ.

3. THÔNG TIN CẦN THIẾT
- Đang trò chuyện với người dùng thông qua ứng dụng Zalo.
- Cơ chế bảo mật: Hệ thống xử lý từng tin nhắn độc lập và KHÔNG lưu trữ lịch sử trò chuyện hay dữ liệu cá nhân của người dùng để đảm bảo an toàn quyền riêng tư tuyệt đối.
"""

def send_zalo_action(chat_id, action="typing"):
    """Gửi trạng thái 'Đang soạn tin...' chuẩn Zalo API"""
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
        print(f"[ZALO sendMessage LOG] HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Lỗi kết nối sendMessage: {e}")

def send_zalo_photo(chat_id, photo_url, caption=""):
    """Gửi tin nhắn hình ảnh chuẩn API sendPhoto Zalo (Thử lại 2 lần)"""
    if not ZALO_BOT_TOKEN:
        return False
    url = f"https://bot-api.zaloplatforms.com/bot{ZALO_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption
    }
    for attempt in range(2):
        try:
            res = requests.post(url, json=payload, timeout=20)
            print(f"[ZALO sendPhoto LOG] HTTP {res.status_code}: {res.text}")
            if res.status_code == 200 and res.json().get('ok') is True:
                return True
        except Exception as e:
            print(f"Lỗi kết nối sendPhoto lần {attempt+1}: {e}")
        time.sleep(1)
    return False

def clean_user_prompt(text):
    """Lọc sạch tag @Bot và từ khóa tạo ảnh thừa"""
    cleaned = re.sub(r'@[^\s]+', '', text)
    cleaned_lower = cleaned.lower()
    for kw in ["tạo ảnh", "vẽ ảnh", "vẽ cho tôi", "vẽ cho", "vẽ ", "tạo hình", "draw", "generate image"]:
        cleaned_lower = cleaned_lower.replace(kw, "")
    
    result = cleaned_lower.strip()
    return result if result else text

def clean_mention(text):
    """Xóa các thẻ @mention khỏi câu hỏi để gửi prompt sạch sang Gemini"""
    return re.sub(r'@[^\s]+', '', text).strip()

def translate_to_english_prompt(text):
    """Dùng Gemini dịch nhanh yêu cầu tạo ảnh sang Tiếng Anh để Pollinations vẽ chính xác"""
    prompt = f"Translate the following image description to a clear, concise English image generation prompt (only return the translated text): {text}"
    try:
        res_text = generate_gemini_multimodal(prompt)
        if res_text and not res_text.startswith("Lỗi") and not res_text.startswith("Tiểu Hy"):
            return res_text.strip()
    except Exception as e:
        print(f"Lỗi dịch prompt: {e}")
    return text

def async_handle_image_generation(chat_id, raw_user_text, base_url):
    """Xử lý tạo ảnh ngầm và tự động cắt bỏ dải Logo mép dưới"""
    try:
        clean_text = clean_user_prompt(raw_user_text)
        en_prompt = translate_to_english_prompt(clean_text)
        encoded_prompt = urllib.parse.quote(en_prompt)
        
        res = None
        for attempt in range(2):
            try:
                poll_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=800&seed={random.randint(1, 999999)}"
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                res = requests.get(poll_url, headers=headers, timeout=25)
                if res.status_code == 200 and res.content:
                    break
            except Exception as req_err:
                print(f"Lần thử {attempt+1} lấy ảnh thất bại: {req_err}")

        if res and res.status_code == 200 and res.content:
            final_bytes = res.content
            
            # Cắt 45px mép dưới xóa logo
            try:
                img = Image.open(io.BytesIO(res.content))
                width, height = img.size
                if height > 100:
                    img_cropped = img.crop((0, 0, width, height - 45))
                    buf = io.BytesIO()
                    img_cropped.save(buf, format='JPEG', quality=95)
                    final_bytes = buf.getvalue()
            except Exception as crop_err:
                print(f"Lỗi cắt logo ảnh: {crop_err}")

            img_id = str(uuid.uuid4())[:8]
            if len(IMAGE_CACHE) > 20:
                IMAGE_CACHE.pop(next(iter(IMAGE_CACHE)))
            IMAGE_CACHE[img_id] = final_bytes
            
            photo_cdn_url = f"{base_url}/cdn/{img_id}.jpg"
            caption_msg = f"Bức ảnh '{clean_text}' của bạn đây nhé!"
            
            success = send_zalo_photo(chat_id, photo_cdn_url, caption=caption_msg)
            if not success:
                send_zalo_message(chat_id, "Tiểu Hy vẽ xong ảnh rồi nhưng kết nối gửi ảnh tới Zalo bị chập chờn. Bạn bấm gửi lại lệnh giúp Tiểu Hy nhé!")
        else:
            send_zalo_message(chat_id, "Server vẽ ảnh hiện đang bận chút, bạn thử bấm gửi lại lệnh xem sao nhé!")
    except Exception as e:
        print(f"Lỗi tạo ảnh ngầm: {e}")
        send_zalo_message(chat_id, "Rất tiếc, hệ thống tạo ảnh đang gặp sự cố nhỏ. Bạn thử lại sau ít phút nhé!")

def extract_photo_url(data):
    """Quét đệ quy thông minh tìm URL ảnh, loại trừ Avatar và hỗ trợ tên miền Zalo zdn.vn"""
    if not data:
        return None

    if isinstance(data, str) and (data.startswith("http://") or data.startswith("https://")):
        lower_s = data.lower()
        valid_keywords = ['.jpg', '.jpeg', '.png', '.webp', 'zapps', 'zadn', 'zdn', 'photo', 'image', 'thumb', 'cdn', 'media']
        if any(k in lower_s for k in valid_keywords):
            return data

    elif isinstance(data, dict):
        ignored_keys = ['avatar', 'avatar_url', 'profile', 'user_avatar', 'chat_avatar', 'icon']
        photo_keys = ['photo', 'image', 'thumb', 'thumbnail', 'preview', 'cdn', 'url', 'src', 'href', 'media_url']
        
        for key in photo_keys:
            if key in ignored_keys:
                continue
            val = data.get(key)
            if isinstance(val, str) and (val.startswith("http://") or val.startswith("https://")):
                lower_v = val.lower()
                valid_keywords = ['.jpg', '.jpeg', '.png', '.webp', 'zapps', 'zadn', 'zdn', 'photo', 'image', 'thumb', 'cdn', 'media']
                if any(k in lower_v for k in valid_keywords):
                    return val

        for key, val in data.items():
            if key in ignored_keys:
                continue
            res = extract_photo_url(val)
            if res:
                return res

    elif isinstance(data, list):
        for item in data:
            res = extract_photo_url(item)
            if res:
                return res

    return None

def fetch_media_as_base64(url, is_image=False):
    """Tải file Media từ Zalo về Base64"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*'
        }
        res = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if res.status_code == 200 and res.content:
            raw_mime = res.headers.get('Content-Type', '').split(';')[0].strip()
            if is_image:
                mime_type = raw_mime if raw_mime.startswith('image/') else 'image/jpeg'
            else:
                mime_type = raw_mime if raw_mime.startswith('audio/') else 'audio/aac'

            return {
                "mime_type": mime_type,
                "data": base64.b64encode(res.content).decode('utf-8')
            }
    except Exception as e:
        print(f"[MEDIA FETCH ERROR]: {e}")
    return None

def generate_gemini_multimodal(prompt, media_file=None):
    """Gửi yêu cầu Đa phương thức sang Gemini API"""
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
            except Exception as e:
                print(f"Lỗi kết nối {formatted_model}: {e}")
                continue

    return "Tiểu Hy hiện đang quá tải lượt hỏi trên toàn bộ các mô hình. Vui lòng thử lại sau nhé!"

@app.route('/', methods=['GET'])
def home():
    return "Zalo Gemini Bot is running!"

@app.route('/cdn/<img_id>.jpg', methods=['GET'])
def serve_cached_image(img_id):
    """Cung cấp ảnh trực tiếp từ RAM cho Zalo tải về siêu tốc"""
    img_data = IMAGE_CACHE.get(img_id)
    if img_data:
        return Response(img_data, mimetype='image/jpeg')
    return "Image not found", 404

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return "Webhook active", 200

    try:
        data = request.get_json() or {}
        print(f"[WEBHOOK INCOMING LOG]: {data}")
        
        msg_obj = data.get('message', {})
        chat_id = msg_obj.get('chat', {}).get('id') or msg_obj.get('from', {}).get('id')
        if not chat_id:
            return jsonify({"status": "no_chat_id"}), 200

        user_text = msg_obj.get('text') or msg_obj.get('caption') or ''
        sticker_id = msg_obj.get('sticker') or msg_obj.get('sticker_id')
        voice_url = msg_obj.get('voice_url') or msg_obj.get('voice')
        
        # Quét ưu tiên trong tin nhắn & trích dẫn trước
        img_url = extract_photo_url(msg_obj) or extract_photo_url(data)

        text_lower = user_text.lower().strip()
        img_keywords = ["vẽ ", "tạo ảnh", "tạo hình", "vẽ ảnh", "vẽ cho", "draw ", "generate image"]

        # 1. XỬ LÝ TẠO ÁNH AI BẤT ĐỒNG BỘ
        if any(kw in text_lower for kw in img_keywords) and not img_url and not voice_url:
            send_zalo_action(chat_id, "typing")
            
            clean_display_text = clean_user_prompt(user_text)
            send_zalo_message(chat_id, f"Tiểu Hy đang vẽ ảnh '{clean_display_text}', bạn đợi vài giây nhé...")
            
            base_url = request.host_url.rstrip('/')
            threading.Thread(target=async_handle_image_generation, args=(chat_id, user_text, base_url)).start()
            
            return jsonify({"status": "processing_image"}), 200

        # 2. XỬ LÝ VOICE (.aac)
        elif voice_url:
            send_zalo_action(chat_id, "typing")
            media_file = fetch_media_as_base64(voice_url, is_image=False)
            if media_file:
                prompt = "Lắng nghe tin nhắn thoại này và phản hồi người dùng bằng văn bản:"
                reply_text = generate_gemini_multimodal(prompt, media_file=media_file)
                send_zalo_message(chat_id, reply_text)

        # 3. XỬ LÝ ĐỌC ÁNH (GỬI TRỰC TIẾP HOẶC TRÍCH DẪN/REPLY)
        elif img_url:
            send_zalo_action(chat_id, "typing")
            media_file = fetch_media_as_base64(img_url, is_image=True)
            if media_file:
                clean_text = clean_mention(user_text)
                prompt = clean_text if clean_text else "Hãy phân tích và mô tả chi tiết nội dung bức ảnh này giúp tôi."
                reply_text = generate_gemini_multimodal(prompt, media_file=media_file)
                send_zalo_message(chat_id, reply_text)
            else:
                send_zalo_message(chat_id, "Tiểu Hy không thể tải được hình ảnh từ Zalo, bạn vui lòng thử gửi lại nhé!")

        # 4. XỬ LÝ STICKER
        elif sticker_id:
            send_zalo_action(chat_id, "typing")
            prompt = f"Người dùng vừa gửi một nhãn dán (sticker) có ID '{sticker_id}'. Hãy phản hồi một câu vui vẻ, dí dỏm đáp lại họ."
            reply_text = generate_gemini_multimodal(prompt)
            send_zalo_message(chat_id, reply_text)

        # 5. CHAT TEXT VĂN BẢN
        elif user_text:
            send_zalo_action(chat_id, "typing")
            clean_text = clean_mention(user_text)
            reply_text = generate_gemini_multimodal(clean_text if clean_text else user_text)
            send_zalo_message(chat_id, reply_text)

    except Exception as e:
        print(f"Lỗi xử lý Webhook: {e}")

    return jsonify({"status": "success"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
