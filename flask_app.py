from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv
import os
import logging

# ✅ .env 로드 (가장 먼저 실행)
load_dotenv()

# ✅ 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ Railway 배포 시 환경 확인
if os.getenv('RAILWAY_ENVIRONMENT'):
    logger.info("✅ Running in Railway production environment")
else:
    logger.info("✅ Running in local development environment")

# ✅ Flask 앱 초기화
app = Flask(__name__)

# ✅ OpenAI 클라이언트 설정 (최신 버전 호환)
try:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        logger.error("❌ OPENAI_API_KEY not found in environment variables")
        raise ValueError("Missing OPENAI_API_KEY")
    
    # OpenAI 최신 버전 호환 초기화
    client = OpenAI(api_key=openai_api_key)
    logger.info("✅ OpenAI client initialized successfully")
except Exception as e:
    logger.error(f"❌ OpenAI client initialization failed: {e}")
    client = None

# ✅ 구글 문서와 시트 로딩 (안전한 방식으로)
sheet_text = "⚠️ Google Sheets 연결이 설정되지 않았습니다."
doc_text = "⚠️ Google Docs 연결이 설정되지 않았습니다."

try:
    from chatbot_utils import load_sheet, load_doc
    sheet_text = load_sheet()
    doc_text = load_doc()
    logger.info("✅ Google Sheets and Docs loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ chatbot_utils import failed: {e}")
    # 기본 제품 정보로 대체
    sheet_text = """
    Saboo Thailand 제품 정보:
    - 산업용 장비 및 솔루션 제공
    - 고품질 제품 라인업
    - 전문 기술 지원 서비스
    - 태국 전역 서비스 지원
    """
    doc_text = """
    Saboo Thailand 회사 정보:
    - 태국의 선도적인 산업 솔루션 제공업체
    - 다년간의 업계 경험
    - 고객 맞춤형 솔루션 제공
    - 전문 엔지니어링 팀
    """
except Exception as e:
    logger.error(f"❌ Google API 연결 오류: {e}")

# ✅ GPT 시스템 프롬프트
SYSTEM_MESSAGE = """
You are a multilingual product expert for Saboo Thailand.
You must respond in the same language used by the user. Do not switch languages.
Use the provided product information to answer questions.
Be clear, concise, and helpful.

If specific product information is not available, provide general helpful information about Saboo Thailand's services and suggest contacting the company directly for detailed specifications.
"""

@app.route('/')
def index():
    try:
        # 간단한 HTML 템플릿 직접 제공 (템플릿 파일 없어도 작동)
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Saboo Thailand Chatbot</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 0; 
                    padding: 0;
                    background: linear-gradient(135deg, #f5a3c7 0%, #fd9bb5 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .chat-container { 
                    background: white;
                    border-radius: 20px;
                    padding: 20px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                    max-width: 500px;
                    width: 90%;
                    height: 600px;
                    display: flex;
                    flex-direction: column;
                }
                .header {
                    text-align: center;
                    margin-bottom: 20px;
                    background: linear-gradient(135deg, #f5a3c7 0%, #fd9bb5 100%);
                    color: white;
                    padding: 15px;
                    border-radius: 15px;
                    font-size: 24px;
                    font-weight: bold;
                }
                .chat-box { 
                    border: 1px solid #eee; 
                    height: 400px; 
                    overflow-y: auto; 
                    padding: 15px; 
                    margin: 10px 0; 
                    border-radius: 15px;
                    background: #fafafa;
                    flex: 1;
                }
                .input-container { 
                    display: flex; 
                    gap: 10px; 
                    margin-top: 10px;
                }
                input[type="text"] { 
                    flex: 1; 
                    padding: 15px; 
                    border: 2px solid #f5a3c7;
                    border-radius: 25px;
                    outline: none;
                    font-size: 16px;
                }
                button { 
                    padding: 15px 25px; 
                    background: linear-gradient(135deg, #f5a3c7 0%, #fd9bb5 100%);
                    color: white;
                    border: none;
                    border-radius: 25px;
                    cursor: pointer;
                    font-size: 16px;
                    font-weight: bold;
                }
                button:hover {
                    opacity: 0.9;
                }
                .message { 
                    margin: 10px 0; 
                    padding: 12px 15px; 
                    border-radius: 15px; 
                    max-width: 80%;
                    word-wrap: break-word;
                }
                .user { 
                    background: linear-gradient(135deg, #f5a3c7 0%, #fd9bb5 100%); 
                    color: white;
                    margin-left: auto; 
                }
                .bot { 
                    background: #f0f0f0; 
                    color: #333;
                }
                .logo {
                    text-align: center;
                    margin-bottom: 15px;
                    font-size: 18px;
                    color: #666;
                }
            </style>
        </head>
        <body>
            <div class="chat-container">
                <div class="logo">🌸 Saboo Thailand</div>
                <div class="header">Saboo Thailand Chatbot</div>
                <div id="chatBox" class="chat-box"></div>
                <div class="input-container">
                    <input type="text" id="messageInput" placeholder="Type your message..." onkeypress="handleKeyPress(event)">
                    <button onclick="sendMessage()">Send</button>
                </div>
            </div>

            <script>
                function addMessage(message, isUser) {
                    const chatBox = document.getElementById('chatBox');
                    const messageDiv = document.createElement('div');
                    messageDiv.className = 'message ' + (isUser ? 'user' : 'bot');
                    messageDiv.textContent = message;
                    chatBox.appendChild(messageDiv);
                    chatBox.scrollTop = chatBox.scrollHeight;
                }

                function handleKeyPress(event) {
                    if (event.key === 'Enter') {
                        sendMessage();
                    }
                }

                async function sendMessage() {
                    const input = document.getElementById('messageInput');
                    const message = input.value.trim();
                    if (!message) return;

                    addMessage(message, true);
                    input.value = '';

                    try {
                        const response = await fetch('/chat', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ message: message })
                        });

                        const data = await response.json();
                        if (data.reply) {
                            addMessage(data.reply, false);
                        } else {
                            addMessage('Sorry, an error occurred. Please try again.', false);
                        }
                    } catch (error) {
                        addMessage('Connection error occurred.', false);
                    }
                }

                // 초기 메시지
                addMessage('Thank you for visiting Saboo Thailand! I am the Saboo Thailand chatbot here to help you. I can communicate in Korean, English, Thai, Japanese, and Chinese. How can I assist you today?', false);
            </script>
        </body>
        </html>
        """
        return html_content
    except Exception as e:
        logger.error(f"❌ Template rendering error: {e}")
        return f"<h1>Saboo Thailand Chatbot</h1><p>Error: {e}</p>", 500

@app.route('/chat', methods=['POST'])
def chat():
    try:
        if not client:
            return jsonify({"error": "OpenAI service is temporarily unavailable. Please try again later."}), 500
            
        user_message = request.json.get('message', '').strip()
        if not user_message:
            return jsonify({"error": "Please enter a message."}), 400

        prompt = f"""
[Product Information]
{sheet_text[:5000]}

[Company Information]
{doc_text[:5000]}

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
@app.route("/line", methods=["POST"])
def line_webhook():
    try:
        body = request.json
        events = body.get("events", [])

        for event in events:
            if event.get("type") == "message":
                user_text = event["message"]["text"]
                reply_token = event["replyToken"]

                # GPT 응답 생성
                prompt = f"""
[Product Information]
{sheet_text[:5000]}

[Company Information]
{doc_text[:5000]}

[User Question]
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

                # LINE 메시지 전송
                line_token = os.getenv("LINE_TOKEN", "여기에_토큰을_직접_넣을_수_있음")
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
        logger.error(f"❌ LINE webhook error: {e}")
        return "Error", 500

        return jsonify({
            "reply": bot_response
        })

    except Exception as e:
        logger.error(f"❌ Error in chat route: {e}")
        return jsonify({"error": f"Sorry, a temporary error occurred. Please try again."}), 500

def save_chat(user_msg, bot_msg):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[CHAT] {timestamp} - User: {user_msg[:50]}...")
        logger.info(f"[CHAT] {timestamp} - Bot: {bot_msg[:50]}...")
    except Exception as e:
        logger.error(f"❌ Log save error: {e}")

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "environment": "production" if os.getenv('RAILWAY_ENVIRONMENT') else "development",
        "openai": "connected" if client else "error - client initialization failed",
        "google_sheets": "connected" if "시트를 불러올 수 없습니다" not in sheet_text else "warning - using fallback data",
        "google_docs": "connected" if "문서를 불러올 수 없습니다" not in doc_text else "warning - using fallback data"
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"❌ Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    debug_mode = not os.getenv('RAILWAY_ENVIRONMENT')
    
    logger.info(f"🚀 Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug_mode)