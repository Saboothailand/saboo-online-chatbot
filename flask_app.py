from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv
import os
import logging
import requests

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

# ✅ Google 시트 및 문서 기본 정보
sheet_text = "⚠️ Google Sheets 연결이 설정되지 않았습니다."
doc_text = "⚠️ Google Docs 연결이 설정되지 않았습니다."

try:
    from chatbot_utils import load_sheet, load_doc
    sheet_text = load_sheet()
    doc_text = load_doc()
    logger.info("✅ Google Sheets and Docs loaded successfully")
except Exception as e:
    logger.warning(f"⚠️ Google API 불러오기 실패: {e}")
    sheet_text = "Saboo 제품 정보: 다양한 산업 솔루션 제공"
    doc_text = "Saboo 회사 정보: 태국의 선도적인 제조업체"

# ✅ GPT 시스템 메시지
SYSTEM_MESSAGE = """
You are a multilingual product expert for Saboo Thailand.
You must respond in the same language used by the user. Do not switch languages.
Use the provided product information to answer questions.
Be clear, concise, and helpful.
"""

# ✅ 인덱스 라우트
@app.route('/')
def index():
    return "<h1>Saboo Thailand Chatbot is running.</h1>"

# ✅ 웹 챗 라우트
@app.route('/chat', methods=['POST'])
def chat():
    try:
        if not client:
            return jsonify({"error": "OpenAI not available."}), 500

        user_message = request.json.get('message', '').strip()
        if not user_message:
            return jsonify({"error": "Empty message."}), 400

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
            max_tokens=1000,
            temperature=0.7
        )

        bot_response = completion.choices[0].message.content.strip()
        save_chat(user_message, bot_response)

        return jsonify({"reply": bot_response})

    except Exception as e:
        logger.error(f"❌ Error in /chat: {e}")
        return jsonify({"error": "Internal error."}), 500

# ✅ LINE 챗봇 Webhook
@app.route('/line', methods=['POST'])
def line_webhook():
    try:
        body = request.json
        events = body.get("events", [])

        for event in events:
            if event.get("type") == "message":
                user_text = event["message"]["text"]
                reply_token = event["replyToken"]

                prompt = f"""
[Product Info]
{sheet_text[:5000]}

[Company Info]
{doc_text[:5000]}

[User]
{user_text}
"""

                completion = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": SYSTEM_MESSAGE},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1000,
                    temperature=0.7
                )

                bot_response = completion.choices[0].message.content.strip()
                save_chat(user_text, bot_response)

                line_token = os.getenv("LINE_TOKEN", "")
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {line_token}"
                }
                payload = {
                    "replyToken": reply_token,
                    "messages": [{"type": "text", "text": bot_response}]
                }

                requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=payload)

        return "OK", 200
    except Exception as e:
        logger.error(f"❌ LINE Webhook Error: {e}")
        return "Error", 500

# ✅ 대화 로그 저장
def save_chat(user_msg, bot_msg):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[CHAT] {timestamp} - User: {user_msg}")
        logger.info(f"[CHAT] {timestamp} - Bot: {bot_msg}")
    except Exception as e:
        logger.error(f"❌ Failed to save chat log: {e}")

# ✅ 헬스체크
@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "openai": "connected" if client else "disconnected"
    })

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
    app.run(host='0.0.0.0', port=port, debug=debug_mode)