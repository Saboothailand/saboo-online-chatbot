from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv
import os
import logging

# ✅ .env 로드 (가장 먼저 실행)
load_dotenv()

# ✅ 로깅 설정 (Railway 환경에서 더 나은 디버깅)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ Railway 배포 시 환경 확인
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
        logger.error("❌ OPENAI_API_KEY not found in environment variables")
        raise ValueError("Missing OPENAI_API_KEY")
    
    client = OpenAI(api_key=openai_api_key)
    logger.info("✅ OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"❌ OpenAI client initialization failed: {e}")
    client = None

# ✅ 구글 문서와 시트 로딩
try:
    from chatbot_utils import load_sheet, load_doc
    sheet_text = load_sheet()
    doc_text = load_doc()
    logger.info("✅ Google Sheets and Docs loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ chatbot_utils import failed: {e}")
    sheet_text = "⚠️ 시트 연결 모듈을 찾을 수 없습니다."
    doc_text = "⚠️ 문서 연결 모듈을 찾을 수 없습니다."
except Exception as e:
    logger.error(f"❌ Google API 연결 오류: {e}")
    sheet_text = "⚠️ 시트를 불러올 수 없습니다."
    doc_text = "⚠️ 문서를 불러올 수 없습니다."

# ✅ GPT 시스템 프롬프트
SYSTEM_MESSAGE = """
You are a multilingual product expert for Saboo Thailand.
You must respond in the same language used by the user. Do not switch languages.
Use only the product sheet and documentation to answer the question.
Be clear, concise, and helpful.
"""

@app.route('/')
def index():
    try:
        return render_template('chat.html')
    except Exception as e:
        logger.error(f"❌ Template rendering error: {e}")
        return f"<h1>Saboo Thailand Chatbot</h1><p>Template error: {e}</p>", 500

@app.route('/chat', methods=['POST'])
def chat():
    try:
        if not client:
            return jsonify({"error": "OpenAI client not initialized. Please check API key."}), 500
            
        user_message = request.json.get('message', '').strip()
        if not user_message:
            return jsonify({"error": "Empty message."}), 400

        prompt = f"""
[Product Sheet]
{sheet_text[:2000]}

[Documentation]
{doc_text[:2000]}

[User Question]
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

        return jsonify({
            "reply": bot_response
        })

    except Exception as e:
        logger.error(f"❌ Error in chat route: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500


def save_chat(user_msg, bot_msg):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Railway에서는 파일 시스템이 임시적이므로 로깅만
        logger.info(f"[CHAT] {timestamp} - User: {user_msg[:50]}...")
        logger.info(f"[CHAT] {timestamp} - Bot: {bot_msg[:50]}...")
        
        # 로컬에서만 파일 저장
        if not os.getenv('RAILWAY_ENVIRONMENT'):
            try:
                with open("chat_log.txt", "a", encoding='utf-8') as f:
                    f.write(f"[{timestamp}]\n")
                    f.write(f"User: {user_msg}\n")
                    f.write(f"Bot: {bot_msg}\n")
                    f.write("-" * 50 + "\n\n")
            except Exception as file_error:
                logger.warning(f"⚠️ Local file save failed: {file_error}")
                
    except Exception as e:
        logger.error(f"❌ Log save error: {e}")

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "environment": "production" if os.getenv('RAILWAY_ENVIRONMENT') else "development",
        "openai": "connected" if client else "error",
        "google_sheets": "connected" if "시트를 불러올 수 없습니다" not in sheet_text else "error",
        "google_docs": "connected" if "문서를 불러올 수 없습니다" not in doc_text else "error"
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"❌ Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # Railway에서 제공하는 PORT 환경변수 사용
    port = int(os.environ.get("PORT", 5001))
    # 프로덕션에서는 debug=False
    debug_mode = not os.getenv('RAILWAY_ENVIRONMENT')
    
    logger.info(f"🚀 Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)