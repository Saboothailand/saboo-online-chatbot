from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv
import os

# ✅ .env 로드 (가장 먼저 실행)
load_dotenv()

# ✅ Railway 배포 시 API 키 디버깅 출력 제거 (보안상)
# 로컬 개발 시에만 출력하도록 수정
if os.getenv('RAILWAY_ENVIRONMENT') != 'production':
    print("✅ Environment loaded")
    # API 키는 보안상 출력하지 않음
    print("✅ GOOGLE_APPLICATION_CREDENTIALS:", os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))

# ✅ Flask 앱 초기화
app = Flask(__name__)

# ✅ OpenAI 클라이언트 설정
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ✅ 구글 문서와 시트 로딩
from chatbot_utils import load_sheet, load_doc
try:
    sheet_text = load_sheet()
    doc_text = load_doc()
    print("✅ Google Sheets and Docs loaded successfully")
except Exception as e:
    print(f"❌ Google API 연결 오류: {e}")
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
    return render_template('chat.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
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
        print(f"❌ Error in chat route: {e}")
        return jsonify({"error": "Server error occurred. Please try again."}), 500


def save_chat(user_msg, bot_msg):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Railway에서는 파일 시스템이 임시적이므로 로깅 방식 변경
        if os.getenv('RAILWAY_ENVIRONMENT') == 'production':
            # 프로덕션에서는 콘솔 로그만
            print(f"[CHAT LOG {timestamp}] User: {user_msg[:50]}...")
        else:
            # 로컬에서는 파일 저장
            with open("chat_log.txt", "a", encoding='utf-8') as f:
                f.write(f"[{timestamp}]\n")
                f.write(f"User: {user_msg}\n")
                f.write(f"Bot: {bot_msg}\n")
                f.write("-" * 50 + "\n\n")
    except Exception as e:
        print(f"❌ Log save error: {e}")

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "google_sheets": "connected" if "시트를 불러올 수 없습니다" not in sheet_text else "error",
        "google_docs": "connected" if "문서를 불러올 수 없습니다" not in doc_text else "error"
    })

if __name__ == '__main__':
    # Railway에서 제공하는 PORT 환경변수 사용
    port = int(os.environ.get("PORT", 5001))
    # 프로덕션에서는 debug=False
    debug_mode = os.getenv('RAILWAY_ENVIRONMENT') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)