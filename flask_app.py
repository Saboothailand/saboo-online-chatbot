from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import logging
import requests
import json
import re
import threading
import time
import hashlib
import socket
import hmac
import base64
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# ✅ .env 로드
load_dotenv()

# ✅ 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ✅ 환경 확인 로그
if os.getenv('RAILWAY_ENVIRONMENT'):
    logger.info("✅ Running in Railway production environment")
else:
    logger.info("✅ Running in local development environment")

# ✅ Flask 앱 초기화
app = Flask(__name__)

# ✅ 채팅 로그를 저장할 폴더 이름 정의
CHAT_LOG_DIR = "save_chat"

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
LINE_SECRET = os.getenv("LINE_CHANNEL_SECRET") or os.getenv("LINE_SECRET")

if not LINE_TOKEN: logger.error("❌ LINE_TOKEN or LINE_CHANNEL_ACCESS_TOKEN not found!")
if not LINE_SECRET: logger.error("❌ LINE_SECRET or LINE_CHANNEL_SECRET not found!")

# ✅ Google API 설정
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
UPDATE_INTERVAL_MINUTES = int(os.getenv("UPDATE_INTERVAL_MINUTES", "5"))

# ✅ 전역 변수로 데이터와 해시 저장
current_sheet_text = ""
sheet_hash = ""
last_update_time = datetime.now()
scheduler = None

# ✅ Google 시트 기본 정보 (폴백용)
saboo_thai_info_fallback = "SABOO THAILAND - 태국 최초의 과일 모양 비누 회사입니다. 무엇이든 물어보세요."

# ✅ Google Sheets API에서 데이터 가져오기
def fetch_google_sheet_data():
    """Google Sheets에서 제품 데이터 가져오기"""
    logger.info("🔍 Attempting to fetch Google Sheets data...")
    try:
        if GOOGLE_CREDENTIALS_JSON and GOOGLE_SHEET_ID:
            try:
                import gspread
                from oauth2client.service_account import ServiceAccountCredentials
                creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
                scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                gc = gspread.authorize(creds)
                sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1
                all_values = sheet.get_all_values()
                sheet_content = "\n".join([" | ".join(filter(None, map(str.strip, row))) for row in all_values if any(row)])
                logger.info(f"✅ Google Sheets data fetched via gspread: {len(sheet_content)} chars")
                return sheet_content.strip()
            except Exception as e:
                logger.error(f"❌ gspread failed, will try other methods. Error: {e}")

        if GOOGLE_API_KEY and GOOGLE_SHEET_ID:
            try:
                url = f"https://sheets.googleapis.com/v4/spreadsheets/{GOOGLE_SHEET_ID}/values/A:Z?key={GOOGLE_API_KEY}"
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    values = response.json().get('values', [])
                    sheet_content = "\n".join([" | ".join(filter(None, map(str.strip, row))) for row in values if any(row)])
                    logger.info(f"✅ Google Sheets data fetched via REST API: {len(sheet_content)} chars")
                    return sheet_content.strip()
                else:
                    logger.error(f"❌ Google Sheets REST API error: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"❌ REST API request failed: {e}")
        
        logger.warning("⚠️ No valid Google Sheets config found. Using fallback data.")
        return saboo_thai_info_fallback
    except Exception as e:
        logger.error(f"❌ Critial error in fetch_google_sheet_data: {e}")
        return saboo_thai_info_fallback

# ✅ 데이터 해시 계산
def calculate_hash(data):
    if not data: return ""
    return hashlib.md5(data.encode('utf-8')).hexdigest()

# ✅ Google 데이터 업데이트 확인 및 갱신
def check_and_update_google_data():
    """Google Sheets 데이터 변경사항 확인 및 업데이트"""
    global current_sheet_text, sheet_hash, last_update_time
    logger.info("🔄 Checking for data updates...")
    try:
        new_sheet_data = fetch_google_sheet_data()
        if new_sheet_data:
            new_sheet_hash = calculate_hash(new_sheet_data)
            if new_sheet_hash != sheet_hash:
                logger.info("📊 Google Sheets data has been updated!")
                current_sheet_text = new_sheet_data
                sheet_hash = new_sheet_hash
                last_update_time = datetime.now()
            else:
                logger.info("📊 Google Sheets data is unchanged.")
    except Exception as e:
        logger.error(f"❌ Error in check_and_update_google_data: {e}")

# ✅ 초기 데이터 로드
def initialize_data():
    """앱 시작시 데이터 초기 로드"""
    global current_sheet_text, sheet_hash
    logger.info("🚀 Initializing data...")
    current_sheet_text = fetch_google_sheet_data()
    sheet_hash = calculate_hash(current_sheet_text)
    logger.info(f"📊 Initial sheet data loaded. Length: {len(current_sheet_text)} chars")

# ✅ 스케줄러 설정
def setup_scheduler():
    """백그라운드 스케줄러 설정"""
    global scheduler
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=check_and_update_google_data,
        trigger=IntervalTrigger(minutes=UPDATE_INTERVAL_MINUTES),
        id='google_data_update', name='Check Google Data Updates', replace_existing=True
    )
    scheduler.start()
    logger.info(f"⏰ Scheduler started. Checking for updates every {UPDATE_INTERVAL_MINUTES} minutes.")

# ✅ 시스템 메시지
SYSTEM_MESSAGE = """You are a friendly and helpful Thai staff member of SABOO THAILAND. Always reply in the customer's language. Use polite language (e.g., 'ค่ะ/ครับ' for Thai) and light emojis (e.g., 😊) to be welcoming. If there are technical issues, provide a helpful response in English."""
ENGLISH_FALLBACK_MESSAGE = """You are a helpful customer service representative for SABOO THAILAND. Always respond in English. Be friendly and professional."""

# ✅ 언어 감지 함수
def detect_user_language(message):
    try:
        if re.search(r'[\u4e00-\u9fff]+', message): return 'chinese'
        if re.search(r'[\u3040-\u30ff]+', message): return 'japanese'
        if re.search(r'[\uac00-\ud7af]+', message): return 'korean'
        if re.search(r'[\u0e00-\u0e7f]+', message): return 'thai'
        return 'english'
    except Exception as e:
        logger.error(f"❌ Language detection error: {e}")
        return 'english'

# ✅ 언어별 회사 정보 로드 함수
def fetch_company_info(user_language):
    lang_map = {'thai': 'th', 'english': 'en', 'korean': 'kr', 'japanese': 'ja', 'chinese': 'zh_cn'}
    lang_code = lang_map.get(user_language, 'en')
    filename = f"company_info_{lang_code}.txt"
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                logger.info(f"✅ Loaded company info for '{user_language}' from {filename}")
                return content
        else:
            logger.warning(f"⚠️ Company info file not found: {filename}. Using default English version.")
            if os.path.exists("company_info_en.txt"):
                with open("company_info_en.txt", 'r', encoding='utf-8') as f:
                    return f.read().strip()
            return "Welcome to SABOO THAILAND! We are the first company in Thailand to create fruit-shaped natural soaps. Feel free to ask us anything. 😊"
    except Exception as e:
        logger.error(f"❌ Error loading company info file {filename}: {e}")
        return "SABOO THAILAND - Company Information"

# ✅ 영어 폴백 응답 생성
def get_english_fallback_response(user_message, error_context=""):
    logger.warning(f"⚠️ Activating English fallback. Context: {error_context}")
    fallback_text = "I apologize for the technical difficulties. SABOO THAILAND is Thailand's first fruit-shaped natural soap company, since 2008. Our store is at Mixt Chatuchak, 2nd Floor, Bangkok. Please try again later. 😊"
    if not client: return fallback_text
    try:
        prompt = f"The user asked: \"{user_message}\"\nThere was a technical issue: {error_context}\nPlease provide a helpful response in English using basic company information."
        completion = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "system", "content": ENGLISH_FALLBACK_MESSAGE}, {"role": "user", "content": prompt}],
            max_tokens=600, temperature=0.7, timeout=20
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"❌ English fallback response also failed: {e}")
        return fallback_text

# ✅ 하이퍼링크 추가 함수
def add_hyperlinks(text):
    try:
        url_pattern = r'(https?://[^\s<>"\']+)'
        text = re.sub(url_pattern, r'<a href="\1" target="_blank" style="color: #ff69b4;">\1</a>', text)
        return text
    except Exception as e:
        logger.error(f"❌ Hyperlink processing error: {e}")
        return text

# ✅ GPT 응답 생성 함수
def get_gpt_response(user_message):
    user_language = detect_user_language(user_message)
    company_info = fetch_company_info(user_language)
    try:
        if not client or not current_sheet_text:
            error_msg = "OpenAI client not available" if not client else "Sheet data not loaded"
            return get_english_fallback_response(user_message, error_msg)
        
        prompt = f"""
[Product Info Table - from Google Sheets]
{current_sheet_text}

[Company Info - Language: {user_language}]
{company_info}

[User]
{user_message}
"""
        completion = client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "system", "content": SYSTEM_MESSAGE}, {"role": "user", "content": prompt}],
            max_tokens=800, temperature=0.7, timeout=25
        )
        response_text = completion.choices[0].message.content.strip()
        return add_hyperlinks(response_text)
    except Exception as e:
        logger.error(f"❌ GPT response generation error: {e}")
        return get_english_fallback_response(user_message, str(e))

# ✅ 대화 로그 저장 함수
def save_chat(user_msg, bot_msg, user_id="anonymous"):
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    datestamp = now.strftime("%Y_%m_%d")
    try:
        os.makedirs(CHAT_LOG_DIR, exist_ok=True)
    except Exception as e:
        logger.error(f"❌ Failed to create directory '{CHAT_LOG_DIR}': {e}")
        return
    
    filename = f"save_chat_{datestamp}.txt"
    full_path = os.path.join(CHAT_LOG_DIR, filename)
    logger.info(f"💬 Saving chat to '{full_path}'")
    
    try:
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] User ({user_id}): {user_msg}\n")
            f.write(f"[{timestamp}] Bot: {bot_msg}\n")
            f.write("-" * 20 + "\n")
    except Exception as e:
        logger.error(f"❌ Failed to save chat log to file '{full_path}': {e}")

# ✅ LINE 서명 검증
def verify_line_signature(body, signature):
    if not LINE_SECRET:
        logger.warning("⚠️ LINE_SECRET not set, skipping verification.")
        return True
    try:
        hash = hmac.new(LINE_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
        return hmac.compare_digest(base64.b64encode(hash).decode('utf-8'), signature)
    except Exception as e:
        logger.error(f"❌ Signature verification error: {e}")
        return False

# ✅ LINE 메시지 전송
def send_line_message(reply_token, message):
    try:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": message}]}
        response = requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("✅ LINE message sent successfully.")
        else:
            logger.error(f"❌ LINE API error: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"❌ Send LINE message error: {e}")

# ==============================================================================
# Flask 라우트 (Routes)
# ==============================================================================
@app.route('/')
def index():
    return render_template('chat.html')

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "openai_client": "connected" if client else "disconnected",
        "last_sheet_update": last_update_time.isoformat(),
        "sheet_data_length": len(current_sheet_text),
        "scheduler_running": scheduler.running if scheduler else False
    })

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message', '').strip()
        if not user_message: return jsonify({"error": "Empty message."}), 400
        bot_response = get_gpt_response(user_message)
        save_chat(user_message, re.sub(r'<[^>]+>', '', bot_response)) # HTML 태그 제거 후 저장
        return jsonify({"reply": bot_response})
    except Exception as e:
        logger.error(f"❌ Error in /chat endpoint: {e}")
        return jsonify({"reply": "Sorry, a critical error occurred."}), 500

@app.route('/line', methods=['POST'])
def line_webhook():
    try:
        body = request.get_data(as_text=True)
        signature = request.headers.get('X-Line-Signature', '')
        if not verify_line_signature(body.encode('utf-8'), signature):
            return "Invalid signature", 400
        
        for event in json.loads(body).get("events", []):
            if event.get("type") == "message" and event.get("message", {}).get("type") == "text":
                user_text = event["message"]["text"].strip()
                reply_token = event["replyToken"]
                user_id = event.get("source", {}).get("userId", "unknown")
                
                bot_response = get_gpt_response(user_text)
                clean_response = re.sub(r'<[^>]+>', '', bot_response)
                send_line_message(reply_token, clean_response)
                save_chat(user_text, clean_response, user_id)
        return "OK", 200
    except Exception as e:
        logger.error(f"❌ LINE Webhook fatal error: {e}")
        return "Error", 500

# ==============================================================================
# 앱 초기화 및 실행
# ==============================================================================
app_initialized = False
@app.before_request
def initialize_once():
    global app_initialized
    if not app_initialized:
        with threading.Lock():
            if not app_initialized:
                logger.info("🎯 Running one-time initialization...")
                initialize_data()
                setup_scheduler()
                app_initialized = True

if __name__ == '__main__':
    if not os.getenv('RAILWAY_ENVIRONMENT'):
        logger.info("🚀 Development mode - running direct initialization...")
        initialize_data()
        setup_scheduler()
        app_initialized = True
    
    port = int(os.environ.get("PORT", 5000))
    debug_mode = not os.getenv('RAILWAY_ENVIRONMENT')
    
    logger.info(f"🚀 Starting Flask server on port {port} with debug_mode={debug_mode}")
    # use_reloader=False 는 개발 모드에서 초기화가 두 번 실행되는 것을 방지합니다.
    app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=False)