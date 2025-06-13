from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv
import os
import logging
import requests
import json
import re  # 정규식 모듈 추가

# ✅ .env 로드
load_dotenv()

# ✅ 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ 환경 확인 로그
if os.getenv('RAILWAY_ENVIRONMENT'):
    logger.info("✅ Running in Railway production environment")
else:
    logger.info("✅ Running in local development environment")

# ✅ Flask 앱 초기화
app = Flask(__name__)

# ✅ OpenAI 클라이언트 설정
try:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("Missing OPENAI_API_KEY")
    client = OpenAI(api_key=openai_api_key)
    logger.info("✅ OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"❌ OpenAI client initialization failed: {e}")
    client = None

# ✅ LINE 설정 확인
LINE_TOKEN = os.getenv("LINE_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_SECRET") or os.getenv("LINE_CHANNEL_SECRET")

if not LINE_TOKEN:
    logger.error("❌ LINE_TOKEN or LINE_CHANNEL_ACCESS_TOKEN not found!")
if not LINE_SECRET:
    logger.error("❌ LINE_SECRET or LINE_CHANNEL_SECRET not found!")

# ✅ Google 시트 및 문서 기본 정보
saboo_thai_info = """
SABOO THAILAND ข้อมูลฉบับสมบูรณ์ - แชทบอทถาม-ตอบภาษาไทย

ข้อมูลพื้นฐานของบริษัท:
- SABOO THAILAND เป็นบริษัทที่มุ่งเน้นการออกแบบ เป็นบริษัทแรกที่สร้างสรรค์สบู่รูปผลไม้ในประเทศไทย
- ก่อตั้งขึ้นในปี 2008 เป็นบริษัทผลิตสบู่ธรรมชาติชั้นนำของไทย
- เป็นแบรนด์ระดับโลกที่ส่งออกไปกว่า 20 ประเทศทั่วโลก

สำนักงานและร้านค้า:
- สำนักงานใหญ่ (โรงงาน): 55/20 หมู่ 4 ตำบลบึงคำพร้อย อำเภอลำลูกกา จังหวัดปทุมธานี 12150
- SABOO THAILAND SHOP: มิกซ์ จตุจักร ชั้น 2 เลขที่ 8 ถนนกำแพงเพชร 3 จตุจักร กรุงเทพฯ 10900
- โทรศัพท์: 02-159-9880, 085-595-9565 / 062-897-8962

ข้อมูลการติดต่อ:
- อีเมล: saboothailand@gmail.com
- เว็บไซต์: www.saboothailand.com
- ช้อปปิ้งมอลล์: www.saboomall.com

ช่องทางออนไลน์:
- Shopee: https://shopee.co.th/thailandsoap
- Lazada: https://www.lazada.co.th/shop/saboo-thailand
- YouTube: https://www.youtube.com/@saboothailand.official
- Instagram: https://www.instagram.com/saboothailand.official/
- TikTok: https://www.tiktok.com/@saboothailand.official
- แคตตาล็อก: https://books.saboothailand.com/books/bxte/#p=1

ผลิตภัณฑ์หลัก:
- สบู่ธรรมชาติ (สบู่รูปผลไม้)
- ผลิตภัณฑ์อาบน้ำ (บาธบอมบ์ บับเบิลบาธ)
- สเปรย์ปรับอากาศ
- น้ำมันกระจายกลิ่น
- สครับ ชุดอาบน้ำ
"""

sheet_text = saboo_thai_info
doc_text = "ข้อมูลเพิ่มเติมเกี่ยวกับ SABOO THAILAND"

try:
    from chatbot_utils import load_sheet, load_doc
    loaded_sheet = load_sheet()
    loaded_doc = load_doc()
    if loaded_sheet and len(loaded_sheet.strip()) > 50:
        sheet_text = loaded_sheet
    if loaded_doc and len(loaded_doc.strip()) > 50:
        doc_text = loaded_doc
    logger.info("✅ Google Sheets and Docs loaded successfully")
except Exception as e:
    logger.warning(f"⚠️ Google API 불러오기 실패, 기본 태국어 정보 사용: {e}")

# ✅ GPT 시스템 메시지
SYSTEM_MESSAGE = """
You are a knowledgeable and friendly Thai staff member of SABOO THAILAND.

Always reply in the **same language** the customer uses:
- If the customer speaks Thai, answer in polite and gentle Thai using "ค่ะ" or "คะ"
- If the customer speaks English, answer in friendly and professional English
- If the customer speaks Korean, answer in polite Korean
- If another language is used, try to respond in that language

Be warm and helpful like a Thai staff member who truly wants to assist the customer.
Use light emojis 😊 to create a friendly and human touch, but do not overuse them.

Use the following product and company information to answer accurately.

Important information to remember:
- SABOO THAILAND was founded in 2008
- First Thai company to create fruit-shaped soap
- Exported to over 20 countries worldwide
- Store location: Mixt Chatuchak, 2nd Floor
- Factory: Pathum Thani
- Phone: 02-159-9880, 085-595-9565
- Website: www.saboothailand.com
- Shopee: shopee.co.th/thailandsoap
"""


# ✅ 새로 추가: 하이퍼링크 처리 함수
def add_hyperlinks(text):
    """텍스트에서 전화번호와 URL을 하이퍼링크로 변환"""
    try:
        # 1. 전화번호 패턴 처리 (한국, 태국 형식)
        # 예: 02-159-9880, 085-595-9565, 010-1234-5678
        phone_pattern = r'\b(0\d{1,2}-\d{3,4}-\d{4})\b'
        text = re.sub(phone_pattern, r'<a href="tel:\1" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        # 2. 슬래시 없는 전화번호도 처리 (예: 0215999880)
        phone_pattern2 = r'\b(0\d{9,10})\b'
        text = re.sub(phone_pattern2, r'<a href="tel:\1" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        # 3. URL 패턴 처리 (http/https로 시작하는 것)
        url_pattern = r'(https?://[^\s<>"\']+)'
        text = re.sub(url_pattern, r'<a href="\1" target="_blank" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        # 4. www로 시작하는 도메인 처리
        www_pattern = r'\b(www\.[^\s<>"\']+)'
        text = re.sub(www_pattern, r'<a href="https://\1" target="_blank" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        # 5. .com, .co.th 등으로 끝나는 도메인 처리 (www 없이)
        domain_pattern = r'\b([a-zA-Z0-9-]+\.(com|co\.th|net|org|co\.kr))\b'
        # 이미 링크가 된 것은 제외
        def replace_domain(match):
            domain = match.group(1)
            # 이미 href 안에 있는지 확인
            if 'href=' in text[max(0, match.start()-20):match.start()]:
                return domain
            return f'<a href="https://{domain}" target="_blank" style="color: #ff69b4; text-decoration: underline;">{domain}</a>'
        
        text = re.sub(domain_pattern, replace_domain, text)
        
        return text
    except Exception as e:
        logger.error(f"❌ Hyperlink processing error: {e}")
        return text

# ✅ LINE 서명 검증 함수
def verify_line_signature(body, signature):
    """LINE Webhook 서명 검증"""
    try:
        import hashlib
        import hmac
        import base64
        
        if not LINE_SECRET:
            logger.warning("⚠️ LINE_SECRET not set, skipping signature verification")
            return True
            
        hash = hmac.new(LINE_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
        expected_signature = base64.b64encode(hash).decode('utf-8')
        
        return signature == expected_signature
    except Exception as e:
        logger.error(f"❌ Signature verification error: {e}")
        return False

# ✅ GPT 응답 생성 함수
def get_gpt_response(user_message):
    """OpenAI GPT로 응답 생성"""
    try:
        if not client:
            return "ขออภัยค่ะ ระบบมีปัญหาชั่วคราว กรุณาลองใหม่อีกครั้งค่ะ 🙏"
        
        prompt = f"""
[Product Info]
{sheet_text[:5000]}

[Company Info]  
{doc_text[:5000]}

[User]
{user_message}
"""
        
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,  # LINE 메시지 제한 고려
            temperature=0.7,
            timeout=25  # 25초 타임아웃 (LINE 30초 제한)
        )
        
        response_text = completion.choices[0].message.content.strip()
        
        # ✅ 새로 추가: 하이퍼링크 처리
        response_text = add_hyperlinks(response_text)
        
        return response_text
        
    except Exception as e:
        logger.error(f"❌ GPT response error: {e}")
        return "ขออภัยค่ะ ขณะนี้ระบบไม่สามารถตอบได้ กรุณาลองใหม่อีกครั้งค่ะ 🙏"

# ✅ LINE 메시지 전송 함수
def send_line_message(reply_token, message):
    """LINE API로 메시지 전송"""
    try:
        if not LINE_TOKEN:
            logger.error("❌ LINE_TOKEN not available")
            return False
            
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_TOKEN}"
        }
        
        # 텍스트 메시지만 전송 (간단하게)
        if isinstance(message, str):
            payload = {
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": message}]
            }
        else:
            payload = {
                "replyToken": reply_token,
                "messages": [message]
            }
        
        response = requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info("✅ LINE message sent successfully")
            return True
        else:
            logger.error(f"❌ LINE API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Send LINE message error: {e}")
        return False

# ✅ 인덱스 라우트
@app.route('/')
def index():
    return render_template('chat.html')  # ✅ 이렇게 수정

# ✅ 헬스체크
@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "openai": "connected" if client else "disconnected",
        "line_token": "configured" if LINE_TOKEN else "missing",
        "line_secret": "configured" if LINE_SECRET else "missing"
    })

# ✅ 웹 챗 라우트 (수정됨)
@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message', '').strip()
        if not user_message:
            return jsonify({"error": "Empty message."}), 400

        bot_response = get_gpt_response(user_message)
        save_chat(user_message, bot_response)
        
        # ✅ HTML 응답으로 반환 (하이퍼링크 포함)
        return jsonify({
            "reply": bot_response,
            "is_html": True  # 프론트엔드에서 HTML로 렌더링하도록 플래그 추가
        })

    except Exception as e:
        logger.error(f"❌ Error in /chat: {e}")
        return jsonify({"error": "Internal error."}), 500

# ✅ LINE 챗봇 Webhook (수정된 버전)
@app.route('/line', methods=['POST'])
def line_webhook():
    """LINE Webhook 핸들러 - 타임아웃 방지 및 에러 처리 개선"""
    try:
        # 1. 요청 데이터 가져오기
        body = request.get_data(as_text=True)
        signature = request.headers.get('X-Line-Signature', '')
        
        logger.info(f"📨 LINE webhook received: {len(body)} bytes")
        
        # 2. 서명 검증 (선택적)
        if not verify_line_signature(body.encode('utf-8'), signature):
            logger.warning("⚠️ Invalid signature, but continuing...")
        
        # 3. JSON 파싱
        try:
            webhook_data = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON decode error: {e}")
            return "Invalid JSON", 400
        
        events = webhook_data.get("events", [])
        logger.info(f"📋 Processing {len(events)} events")
        
        # 4. 각 이벤트 처리
        for event in events:
            try:
                event_type = event.get("type")
                logger.info(f"🔄 Processing event type: {event_type}")
                
                if event_type == "message" and event.get("message", {}).get("type") == "text":
                    # 텍스트 메시지 처리
                    user_text = event["message"]["text"].strip()
                    reply_token = event["replyToken"]
                    user_id = event.get("source", {}).get("userId", "unknown")
                    
                    logger.info(f"👤 User {user_id}: {user_text}")
                    
                    # 환영 메시지 체크
                    welcome_keywords = ["สวัสดี", "หวัดดี", "hello", "hi", "สวัสดีค่ะ", "สวัสดีครับ", "ดีจ้า", "เริ่ม"]
                    
                    if user_text.lower() in welcome_keywords:
                        response_text = """สวัสดีค่ะ! 💕 ยินดีต้อนรับสู่ SABOO THAILAND ค่ะ

🧴 เราเป็นผู้ผลิตสบู่ธรรมชาติและผลิตภัณฑ์อาบน้ำครั้งแรกในไทยที่ทำสบู่รูปผลไม้ค่ะ

📍 ร้าน: มิกซ์ จตุจักร ชั้น 2
📞 โทร: 02-159-9880
🛒 Shopee: shopee.co.th/thailandsoap
🌐 เว็บไซต์: www.saboothailand.com

มีอะไรให้ดิฉันช่วยเหลือคะ? 😊"""
                        # ✅ 환영 메시지도 하이퍼링크 처리
                        response_text = add_hyperlinks(response_text)
                    else:
                        # GPT 응답 생성 (타임아웃 고려)
                        response_text = get_gpt_response(user_text)
                    
                    # LINE은 HTML을 지원하지 않으므로 HTML 태그 제거
                    clean_response = re.sub(r'<[^>]+>', '', response_text)
                    
                    # LINE으로 응답 전송
                    success = send_line_message(reply_token, clean_response)
                    
                    if success:
                        save_chat(user_text, clean_response[:100] + "...", user_id)
                    else:
                        logger.error(f"❌ Failed to send response to user {user_id}")
                
                elif event_type == "follow":
                    # 친구 추가 이벤트
                    reply_token = event["replyToken"]
                    welcome_text = "สวัสดีค่ะ! ขอบคุณที่เพิ่ม SABOO THAILAND เป็นเพื่อนค่ะ 💕\n\nส่งข้อความ 'สวัสดี' เพื่อเริ่มต้นการสนทนาค่ะ 😊"
                    send_line_message(reply_token, welcome_text)
                
                elif event_type == "unfollow":
                    # 친구 삭제 이벤트 (로그만)
                    user_id = event.get("source", {}).get("userId", "unknown")
                    logger.info(f"👋 User {user_id} unfollowed")
                
                else:
                    logger.info(f"ℹ️ Unhandled event type: {event_type}")
                    
            except Exception as e:
                logger.error(f"❌ Error processing event: {e}")
                continue  # 다음 이벤트 계속 처리
        
        # 5. 성공 응답 반환 (중요!)
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ LINE Webhook fatal error: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        
        # 에러가 있어도 200 반환 (LINE 재시도 방지)
        return "Error handled", 200

# ✅ 대화 로그 저장
def save_chat(user_msg, bot_msg, user_id="anonymous"):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"💬 [{timestamp}] User({user_id[:8]}): {user_msg[:100]}...")
        logger.info(f"🤖 [{timestamp}] Bot: {bot_msg[:100]}...")
    except Exception as e:
        logger.error(f"❌ Failed to save chat log: {e}")

# ✅ 에러 핸들러
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"❌ Internal error: {error}")
    return jsonify({"error": "Server error"}), 500

# ✅ 실행 시작
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    debug_mode = not os.getenv('RAILWAY_ENVIRONMENT')
    logger.info(f"🚀 Starting server on port {port}")
    logger.info(f"🔧 Debug mode: {debug_mode}")
    logger.info(f"🔑 LINE_TOKEN: {'✅ Set' if LINE_TOKEN else '❌ Missing'}")
    logger.info(f"🔐 LINE_SECRET: {'✅ Set' if LINE_SECRET else '❌ Missing'}")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)