# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, render_template
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv
import os
import logging
import requests
import json
import re
import threading
import hashlib
import hmac
import base64

# ✅ 가격 리스트 파일 읽기 함수 (통합 버전)
def get_price_list(language='en'):
    """모든 언어 통합 price_list.txt 파일을 불러오는 함수"""
    try:
        if os.path.exists("price_list.txt"):
            with open("price_list.txt", 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if len(content) > 20:
                    logger.info(f"✅ '{language}' 언어 요청에 대해 통합 price_list.txt 를 로드했습니다.")
                    return content
                else:
                    logger.warning("⚠️ price_list.txt 파일이 너무 짧습니다 (20자 미만).")
                    return "❌ 가격 정보가 충분하지 않습니다. 관리자에게 문의해주세요."
        else:
            logger.error("❌ price_list.txt 파일을 찾을 수 없습니다.")
            return "❌ 가격 리스트 파일을 찾을 수 없습니다. 관리자에게 문의해주세요."
    except Exception as e:
        logger.error(f"❌ price_list.txt 파일 읽기 오류: {e}")
        return f"❌ 가격 정보를 불러오는 중 오류가 발생했습니다: {str(e)}"

# ✅ 메신저 / 웹용 줄바꿈 처리 함수
def format_text_for_messenger(text):
    """웹/메신저용: \n → <br> 로 변환"""
    try:
        text = text.replace("\n", "<br>")
        return text
    except Exception as e:
        logger.error(f"❌ 메신저용 줄바꿈 변환 오류: {e}")
        return text

# ✅ LINE 용 줄바꿈 처리 함수
def format_text_for_line(text):
    """LINE 용: \n → \n\n 로 변환"""
    try:
        text = text.replace("\n", "\n\n")
        return text
    except Exception as e:
        logger.error(f"❌ LINE용 줄바꿈 변환 오류: {e}")
        return text

# ✅ .env 환경변수 로드
load_dotenv()

# ✅ 로깅 설정: 시간, 로그 레벨, 메시지 형식을 포함하여 더 상세하게 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# ✅ 환경 확인 로그
if os.getenv('RAILWAY_ENVIRONMENT'):
    logger.info("✅ Railway 프로덕션 환경에서 실행 중입니다.")
else:
    logger.info("✅ 로컬 개발 환경에서 실행 중입니다.")

# ✅ Flask 앱 초기화
app = Flask(__name__)

# ✅ 채팅 로그를 저장할 폴더 이름 정의
CHAT_LOG_DIR = "save_chat"

# ✅ OpenAI 클라이언트 설정
try:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY가 .env 파일에 없습니다.")
    client = OpenAI(api_key=openai_api_key)
    logger.info("✅ OpenAI 클라이언트가 성공적으로 초기화되었습니다.")
except Exception as e:
    logger.error(f"❌ OpenAI 클라이언트 초기화 실패: {e}")
    client = None

# ✅ LINE 설정 확인
LINE_TOKEN = os.getenv("LINE_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_CHANNEL_SECRET") or os.getenv("LINE_SECRET")

if not LINE_TOKEN:
    logger.error("❌ LINE_TOKEN 또는 LINE_CHANNEL_ACCESS_TOKEN을 찾을 수 없습니다!")
if not LINE_SECRET:
    logger.error("❌ LINE_SECRET 또는 LINE_CHANNEL_SECRET을 찾을 수 없습니다!")

# ✅ 전역 변수: 언어별 캐시만 사용
language_data_cache = {}  # 언어별 회사 소개 정보를 메모리에 저장해두는 캐시
last_update_time = datetime.now()

# ✅ 언어별 회사 정보 로드 (캐싱 기능 포함) - 확장된 버전
def fetch_company_info(user_language):
    """언어별 company_info.txt 파일을 읽어오고, 결과를 캐시에 저장합니다."""
    global language_data_cache
    
    if user_language in language_data_cache:
        logger.info(f"📋 캐시된 '{user_language}' 회사 정보를 사용합니다.")
        return language_data_cache[user_language]

    # 확장된 언어 매핑
    lang_map = {
        'thai': 'th',
        'english': 'en', 
        'korean': 'kr',
        'japanese': 'ja',
        'german': 'de',
        'spanish': 'es',
        'arabic': 'ar',
        'chinese': 'zh_cn',
        'taiwanese': 'zh_tw',
        'vietnamese': 'vi',
        'myanmar': 'my',
        'khmer': 'km',
        'russian': 'ru',
        'french': 'fr'
    }
    
    lang_code = lang_map.get(user_language, 'en')
    filename = f"company_info_{lang_code}.txt"

    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if len(content) > 20:  # 내용이 너무 짧지 않은지 확인
                    logger.info(f"✅ '{user_language}' 회사 정보를 {filename} 파일에서 성공적으로 로드했습니다.")
                    language_data_cache[user_language] = content # 캐시에 저장
                    return content
    except Exception as e:
        logger.error(f"❌ {filename} 파일 로드 중 오류 발생: {e}")

    # 영어 폴백 시도
    logger.warning(f"⚠️ {filename} 파일을 찾을 수 없거나 내용이 비어있습니다. 영어 버전을 시도합니다.")
    try:
        if os.path.exists("company_info_en.txt"):
             with open("company_info_en.txt", 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if len(content) > 20:
                    logger.info("✅ 영어 버전(company_info_en.txt)을 폴백으로 사용합니다.")
                    language_data_cache[user_language] = content
                    return content
    except Exception as e:
        logger.error(f"❌ company_info_en.txt 파일 로드 중 오류 발생: {e}")

    # 최종 하드코딩 폴백
    logger.warning("⚠️ 모든 파일 로드에 실패하여, 하드코딩된 기본 정보를 사용합니다.")
    default_info = """
Welcome to SABOO THAILAND! 

We are Thailand's first natural fruit-shaped soap manufacturer since 2008.
- Store: Mixt Chatuchak, 2nd Floor, Bangkok
- Phone: 02-159-9880, 085-595-9565
- Website: www.saboothailand.com
- Shopee: shopee.co.th/thailandsoap
- Email: saboothailand@gmail.com

Products: Natural soaps, bath products, air fresheners, essential oils.
Feel free to ask us anything! 😊
"""
    language_data_cache[user_language] = default_info
    return default_info

# ✅ 초기 데이터 로드 (구글 서비스 제거)
def initialize_data():
    """앱 시작 시 필요한 언어별 데이터를 미리 로드합니다."""
    logger.info("🚀 앱 초기화를 시작합니다...")
    
    # 주요 언어 회사 정보 미리 캐싱
    common_languages = ['english', 'korean', 'thai', 'japanese', 'chinese', 'spanish', 'german']
    for lang in common_languages:
        try:
            fetch_company_info(lang)
        except Exception as e:
            logger.warning(f"⚠️ {lang} 언어 정보 미리 로드 실패: {e}")
    
    logger.info(f"✅ 캐시된 언어: {list(language_data_cache.keys())}")

# ✅ 시스템 메시지 정의
SYSTEM_MESSAGE = """
You are a knowledgeable and friendly Thai staff member of SABOO THAILAND.

Always reply in the **same language** the customer uses:
- If the customer speaks Thai, answer in polite and gentle Thai using "ค่ะ" or "คะ"
- If the customer speaks English, answer in friendly and professional English
- If the customer speaks Korean, answer in polite Korean
- If another language is used, try to respond in that language

IMPORTANT FALLBACK RULE: If there are any technical issues, errors, or problems that prevent you from accessing proper data or generating appropriate responses, ALWAYS switch to English and provide a helpful response in English, regardless of the customer's original language.

Be warm and helpful like a Thai staff member who truly wants to assist the customer.
Use light emojis 😊 to create a friendly and human touch, but do not overuse them.

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

ENGLISH_FALLBACK_MESSAGE = """
You are a helpful customer service representative for SABOO THAILAND.

Always respond in English when there are technical issues or data problems.
Be friendly, professional, and provide as much helpful information as possible from your basic knowledge.

Key information about SABOO THAILAND:
- Founded in 2008
- First Thai company to create fruit-shaped natural soap
- Exports to over 20 countries worldwide
- Store: Mixt Chatuchak, 2nd Floor, Bangkok
- Phone: 02-159-9880, 085-595-9565
- Website: www.saboothailand.com
- Shopee: shopee.co.th/thailandsoap
- Email: saboothailand@gmail.com

Products: Natural soaps (fruit-shaped), bath products, air fresheners, essential oils, scrubs, bath sets.
"""

# ✅ 언어 감지 함수 (확장된 버전)
def detect_user_language(message):
    """사용자 메시지에서 언어를 감지합니다. - 확장된 버전"""
    try:
        # 태국어
        if re.search(r'[\u0e00-\u0e7f]+', message):
            return 'thai'
        # 한국어
        elif re.search(r'[\uac00-\ud7af]+', message):
            return 'korean'
        # 일본어 (히라가나, 가타카나)
        elif re.search(r'[\u3040-\u309f\u30a0-\u30ff]+', message):
            return 'japanese'
        # 중국어/일본어 한자
        elif re.search(r'[\u4e00-\u9fff]+', message):
            # 히라가나/가타카나가 함께 있으면 일본어
            if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', message):
                return 'japanese'
            else:
                return 'chinese'  # 한자만 있으면 중국어로 간주
        # 아랍어
        elif re.search(r'[\u0600-\u06ff]+', message):
            return 'arabic'
        # 러시아어
        elif re.search(r'[\u0401\u0451\u0410-\u044f]+', message):
            return 'russian'
        # 프랑스어 특수문자
        elif re.search(r'[àâäéèêëïîôùûüÿç]+', message.lower()):
            return 'french'
        # 스페인어/포르투갈어 특수문자  
        elif re.search(r'[àáâãçéêíóôõú]+', message.lower()):
            return 'spanish'
        # 독일어 특수문자
        elif re.search(r'[äöüß]+', message.lower()):
            return 'german'
        # 베트남어
        elif re.search(r'[ăâđêôơưàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụ]+', message.lower()):
            return 'vietnamese'
        
        # 기본값: 영어
        return 'english'
    except Exception as e:
        logger.error(f"❌ 언어 감지 중 오류 발생: {e}")
        return 'english'

# ✅ 영어 폴백 응답 생성
def get_english_fallback_response(user_message, error_context=""):
    """문제 발생 시 영어로 된 기본 응답을 생성합니다."""
    logger.warning(f"⚠️ 폴백 응답을 활성화합니다. 원인: {error_context}")
    
    if not client:
        return """I apologize, but we're experiencing technical difficulties at the moment. 

Here's some basic information about SABOO THAILAND:
- We're Thailand's first natural fruit-shaped soap manufacturer since 2008
- Store location: Mixt Chatuchak, 2nd Floor, Bangkok
- Phone: 02-159-9880, 085-595-9565
- Website: www.saboothailand.com
- Shopee: shopee.co.th/thailandsoap

Please try again later or contact us directly. Thank you for your understanding! 😊"""
    
    try:
        prompt = f"""
The user asked: "{user_message}"

There was a technical issue: {error_context}

Please provide a helpful response in English using basic company information.
"""
        completion = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[
                {"role": "system", "content": ENGLISH_FALLBACK_MESSAGE}, 
                {"role": "user", "content": prompt}
            ],
            max_tokens=600, 
            temperature=0.7, 
            timeout=20
        )
        
        response_text = completion.choices[0].message.content.strip()
        response_text = add_hyperlinks(response_text)
        
        if error_context:
            response_text += f"\n\n(Note: We're currently experiencing some technical issues with our data system, but I'm happy to help with basic information about SABOO THAILAND.)"
        
        return response_text
    except Exception as e:
        logger.error(f"❌ 폴백 응답 생성 중에도 오류 발생: {e}")
        return """I apologize for the technical difficulties we're experiencing.

SABOO THAILAND - Basic Information:
- Thailand's first fruit-shaped natural soap company (since 2008)
- Store: Mixt Chatuchak, 2nd Floor, Bangkok  
- Phone: 02-159-9880, 085-595-9565
- Website: www.saboothailand.com
- Shopee: shopee.co.th/thailandsoap
- Email: saboothailand@gmail.com

Products: Natural soaps, bath bombs, scrubs, essential oils, air fresheners

Please contact us directly or try again later. Thank you! 😊"""

# ✅ 하이퍼링크 추가 함수
def add_hyperlinks(text):
    """응답 텍스트에 포함된 전화번호와 URL을 클릭 가능한 HTML 링크로 변환합니다."""
    try:
        # 1. 전화번호 패턴 처리 (한국, 태국 형식)
        phone_pattern = r'\b(0\d{1,2}-\d{3,4}-\d{4})\b'
        text = re.sub(phone_pattern, r'<a href="tel:\1" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        # 2. 슬래시 없는 전화번호도 처리
        phone_pattern2 = r'\b(0\d{9,10})\b'
        text = re.sub(phone_pattern2, r'<a href="tel:\1" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        # 3. URL 패턴 처리
        url_pattern = r'(https?://[^\s<>"\']+)'
        text = re.sub(url_pattern, r'<a href="\1" target="_blank" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        # 4. www로 시작하는 도메인 처리
        www_pattern = r'\b(www\.[a-zA-Z0-9-]+\.(com|co\.th|net|org|co\.kr)[^\s<>"\']*)'
        text = re.sub(www_pattern, r'<a href="https://\1" target="_blank" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        return text
    except Exception as e:
        logger.error(f"❌ 하이퍼링크 변환 중 오류 발생: {e}")
        return text

# ✅ GPT 응답 생성 함수 (구글 서비스 제거, 언어별 파일만 사용)
def get_gpt_response(user_message):
    """언어별 파일 데이터만을 사용하여 OpenAI GPT 모델로 최종 답변을 생성합니다."""
    user_language = detect_user_language(user_message)
    logger.info(f"🌐 감지된 사용자 언어: {user_language}")
    
    company_info = fetch_company_info(user_language)

    try:
        if not client:
            logger.error("❌ OpenAI client가 없습니다.")
            return get_english_fallback_response(user_message, "OpenAI service unavailable")
        
        # 회사 정보 유효성 검사
        if not company_info or len(company_info.strip()) < 50:
            logger.warning("⚠️ 회사 정보가 불충분합니다. 폴백을 사용합니다.")
            return get_english_fallback_response(user_message, "Company data temporarily unavailable")
        
        prompt = f"""
[회사 정보 및 제품 정보 - 언어: {user_language}]
{company_info}

(중요: 고객 질문이 배송/운송, 제품, 회사 정보와 관련된 경우 반드시 위 회사 정보 텍스트에서 정보를 찾을 것!)

[감지된 사용자 언어: {user_language}]
[사용자 질문]
{user_message}
"""
        completion = client.chat.completions.create(
            model="gpt-4o", 
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE}, 
                {"role": "user", "content": prompt}
            ],
            max_tokens=800, 
            temperature=0.7, 
            timeout=25
        )
        
        response_text = completion.choices[0].message.content.strip()
        
        # 응답 품질 검사
        if not response_text or len(response_text.strip()) < 10:
            logger.warning("⚠️ 생성된 응답이 너무 짧습니다. 폴백을 사용합니다.")
            return get_english_fallback_response(user_message, "Response generation issue")
        
        # 하이퍼링크 추가
        response_text = add_hyperlinks(response_text)
        
        logger.info(f"✅ '{user_language}' 언어로 GPT 응답을 성공적으로 생성했습니다.")
        return response_text
        
    except Exception as e:
        logger.error(f"❌ GPT 응답 생성 중 오류 발생: {e}")
        error_context = f"GPT API error: {str(e)[:100]}"
        return get_english_fallback_response(user_message, error_context)

# ✅ 대화 로그 저장 함수 (폴더 및 날짜별 파일 자동 생성)
def save_chat(user_msg, bot_msg, user_id="anonymous"):
    """대화 내용을 날짜별 텍스트 파일로 저장합니다."""
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    datestamp = now.strftime("%Y_%m_%d")
    
    try:
        os.makedirs(CHAT_LOG_DIR, exist_ok=True)
    except Exception as e:
        logger.error(f"❌ 로그 디렉토리 '{CHAT_LOG_DIR}' 생성 실패: {e}")
        return
    
    filename = f"save_chat_{datestamp}.txt"
    full_path = os.path.join(CHAT_LOG_DIR, filename)
    
    # 언어 감지 추가
    detected_lang = detect_user_language(user_msg)
    
    try:
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] User ({user_id}) [{detected_lang}]: {user_msg}\n")
            f.write(f"[{timestamp}] Bot: {bot_msg}\n")
            f.write("-" * 50 + "\n")
        logger.info(f"💬 채팅 로그를 '{full_path}' 파일에 저장했습니다.")
    except Exception as e:
        logger.error(f"❌ 로그 파일 '{full_path}' 저장 실패: {e}")

# ✅ LINE 서명 검증
def verify_line_signature(body, signature):
    """LINE Webhook 서명 검증"""
    if not LINE_SECRET:
        logger.warning("⚠️ LINE_SECRET이 설정되지 않아 서명 검증을 건너뜁니다.")
        return True
    try:
        hash_val = hmac.new(LINE_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
        expected_signature = base64.b64encode(hash_val).decode('utf-8')
        return hmac.compare_digest(expected_signature, signature)
    except Exception as e:
        logger.error(f"❌ 서명 검증 중 오류 발생: {e}")
        return False

# ✅ LINE 메시지 전송
def send_line_message(reply_token, message):
    """LINE API로 메시지 전송"""
    try:
        if not LINE_TOKEN:
            logger.error("❌ LINE_TOKEN이 없습니다.")
            return False
            
        headers = {
            "Content-Type": "application/json", 
            "Authorization": f"Bearer {LINE_TOKEN}"
        }
        payload = {
            "replyToken": reply_token, 
            "messages": [{"type": "text", "text": message}]
        }
        
        response = requests.post(
            "https://api.line.me/v2/bot/message/reply", 
            headers=headers, 
            json=payload, 
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info("✅ LINE 메시지를 성공적으로 전송했습니다.")
            return True
        else:
            logger.error(f"❌ LINE API 오류: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ LINE 메시지 전송 중 오류 발생: {e}")
        return False

# ==============================================================================
# Flask 라우트 (Routes)
# ==============================================================================

@app.route('/')
def index():
    """웹 챗 UI를 위한 기본 페이지를 렌더링합니다."""
    return render_template('chat.html')

@app.route('/health')
def health():
    """서버의 현재 상태를 확인하는 헬스 체크 엔드포인트입니다."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "openai_client": "connected" if client else "disconnected",
        "line_token": "configured" if LINE_TOKEN else "missing",
        "line_secret": "configured" if LINE_SECRET else "missing",
        "cached_languages": list(language_data_cache.keys()),
        "data_source": "language_files_only",
        "google_services": "disabled",
        "linebreak_functions": "enabled"
    })

@app.route('/language-status')
def language_status():
    """언어별 데이터 로딩 상태 확인"""
    try:
        status = {}
        
        # 지원 언어 목록
        supported_languages = ['thai', 'english', 'korean', 'japanese', 'german', 
                             'spanish', 'arabic', 'chinese', 'taiwanese', 'vietnamese',
                             'myanmar', 'khmer', 'russian', 'french']
        
        lang_map = {
            'thai': 'th', 'english': 'en', 'korean': 'kr', 'japanese': 'ja',
            'german': 'de', 'spanish': 'es', 'arabic': 'ar', 'chinese': 'zh_cn',
            'taiwanese': 'zh_tw', 'vietnamese': 'vi', 'myanmar': 'my',
            'khmer': 'km', 'russian': 'ru', 'french': 'fr'
        }
        
        for lang in supported_languages:
            try:
                lang_code = lang_map.get(lang, 'en')
                filename = f"company_info_{lang_code}.txt"
                
                file_exists = os.path.exists(filename)
                cached = lang in language_data_cache
                
                if file_exists:
                    with open(filename, 'r', encoding='utf-8') as f:
                        content_length = len(f.read())
                else:
                    content_length = 0
                
                status[lang] = {
                    "file_exists": file_exists,
                    "filename": filename,
                    "cached": cached,
                    "content_length": content_length,
                    "cache_length": len(language_data_cache.get(lang, "")) if cached else 0
                }
                
            except Exception as e:
                status[lang] = {"error": str(e)}
        
        return jsonify({
            "language_status": status,
            "total_cached": len(language_data_cache),
            "cache_summary": {lang: len(content) for lang, content in language_data_cache.items()},
            "data_source": "language_files_only"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/clear-language-cache')
def clear_language_cache():
    """언어별 캐시 초기화"""
    global language_data_cache
    try:
        old_cache_size = len(language_data_cache)
        language_data_cache.clear()
        
        return jsonify({
            "status": "success",
            "message": f"Language cache cleared. Removed {old_cache_size} entries.",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reload-language-data')
def reload_language_data():
    """언어별 데이터 다시 로드"""
    try:
        # 캐시 초기화
        global language_data_cache
        language_data_cache.clear()
        
        # 데이터 다시 로드
        initialize_data()
        
        return jsonify({
            "status": "success",
            "message": "Language data reloaded successfully.",
            "cached_languages": list(language_data_cache.keys()),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat():
    """웹 챗으로부터 메시지를 받아 처리하고 응답을 반환합니다."""
    try:
        user_message = request.json.get('message', '').strip()
        if not user_message: 
            return jsonify({"error": "Empty message."}), 400
        
        # 언어 감지
        detected_language = detect_user_language(user_message)
        
        # ✅ 가격 키워드 감지 - 다국어 지원
        price_keywords = [
            # 한국어
            '가격', '비누 가격', '팬시비누 가격', '비누가격', '얼마', '값', '요금', '비용',
            # 영어
            'price', 'prices', 'price list', 'cost', 'how much', 'pricing', 'rate', 'fee',
            # 태국어
            'ราคา', 'สบู่ราคา', 'ราคาสบู่', 'เท่าไหร่', 'เท่าไร', 'ค่า', 'ค่าใช้จ่าย',
            # 일본어
            '価格', '値段', 'いくら', '料金', 'コスト', 'プライス',
            # 중국어
            '价格', '价钱', '多少钱', '费用', '成本', '定价',
            # 스페인어
            'precio', 'precios', 'costo', 'cuanto', 'tarifa',
            # 독일어
            'preis', 'preise', 'kosten', 'wie viel', 'gebühr',
            # 프랑스어
            'prix', 'coût', 'combien', 'tarif',
            # 러시아어
            'цена', 'цены', 'стоимость', 'сколько'
        ]
        
        # 가격 관련 키워드가 포함되어 있는지 확인
        if any(keyword.lower() in user_message.lower() for keyword in price_keywords):
            logger.info(f"💰 가격 정보 요청 감지 - 언어: {detected_language}")
            
            # 언어별 가격 정보 가져오기
            price_text = get_price_list(language=detected_language)
            
            # ✅ 웹/메신저용 줄바꿈 처리
            formatted_price_text = format_text_for_messenger(price_text)
            
            # 로그 저장용 HTML 태그 제거
            clean_response_for_log = re.sub(r'<[^>]+>', '', formatted_price_text)
            save_chat(user_message, clean_response_for_log)
            
            # 가격 정보에 하이퍼링크 추가
            price_text_with_links = add_hyperlinks(formatted_price_text)
            
            return jsonify({
                "reply": price_text_with_links,
                "is_html": True,  # 하이퍼링크가 포함되어 있을 수 있으므로 HTML로 처리
                "user_language": detected_language,
                "data_source": "price_list",
                "request_type": "price_inquiry"
            })
        
        # ✅ 기존 GPT 호출 (가격 관련이 아닌 일반 질문)
        bot_response = get_gpt_response(user_message)
        
        # ✅ 웹/메신저용 줄바꿈 처리
        formatted_response = format_text_for_messenger(bot_response)
        
        # 로그에는 HTML 태그를 제거하고 저장
        clean_response_for_log = re.sub(r'<[^>]+>', '', formatted_response)
        save_chat(user_message, clean_response_for_log)
        
        # 언어 코드 매핑
        lang_map = {
            'thai': 'th', 'english': 'en', 'korean': 'kr', 'japanese': 'ja',
            'german': 'de', 'spanish': 'es', 'arabic': 'ar', 'chinese': 'zh_cn',
            'taiwanese': 'zh_tw', 'vietnamese': 'vi', 'myanmar': 'my',
            'khmer': 'km', 'russian': 'ru', 'french': 'fr'
        }
        lang_code = lang_map.get(detected_language, 'en')
        language_file_used = f"company_info_{lang_code}.txt"
        
        return jsonify({
            "reply": formatted_response,
            "is_html": True,
            "user_language": detected_language,
            "language_file_used": language_file_used,
            "data_source": "language_files_only",
            "request_type": "general_inquiry"
        })
        
    except Exception as e:
        logger.error(f"❌ /chat 엔드포인트에서 오류 발생: {e}")
        fallback_response = get_english_fallback_response(
            user_message if 'user_message' in locals() else "general inquiry", 
            f"Web chat system error: {str(e)[:100]}"
        )
        # ✅ 폴백 응답에도 줄바꿈 처리 적용
        formatted_fallback = format_text_for_messenger(fallback_response)
        return jsonify({
            "reply": formatted_fallback,
            "is_html": True,
            "error": "fallback_mode",
            "request_type": "error_fallback"
        })

@app.route('/line', methods=['POST'])
def line_webhook():
    """LINE 플랫폼으로부터 오는 웹훅 이벤트를 처리합니다."""
    try:
        body = request.get_data(as_text=True)
        signature = request.headers.get('X-Line-Signature', '')
        
        logger.info(f"📨 LINE 웹훅을 받았습니다: {len(body)} bytes")
        
        if not verify_line_signature(body.encode('utf-8'), signature):
            logger.warning("⚠️ 잘못된 서명입니다.")
            # 개발 편의를 위해 일단 진행 (프로덕션에서는 400 반환 권장)
            # return "Invalid signature", 400
        
        webhook_data = json.loads(body)
        
        for event in webhook_data.get("events", []):
            if event.get("type") == "message" and event.get("message", {}).get("type") == "text":
                user_text = event["message"]["text"].strip()
                reply_token = event["replyToken"]
                user_id = event.get("source", {}).get("userId", "unknown")
                
                # 언어 감지
                detected_language = detect_user_language(user_text)
                logger.info(f"👤 사용자 {user_id[:8]} ({detected_language}): {user_text}")
                
                # ✅ LINE에서도 가격 키워드 감지
                price_keywords = [
                    # 한국어
                    '가격', '비누 가격', '팬시비누 가격', '비누가격', '얼마', '값', '요금', '비용',
                    # 영어
                    'price', 'prices', 'price list', 'cost', 'how much', 'pricing', 'rate', 'fee',
                    # 태국어
                    'ราคา', 'สบู่ราคา', 'ราคาสบู่', 'เท่าไหร่', 'เท่าไร', 'ค่า', 'ค่าใช้จ่าย',
                    # 일본어
                    '価格', '値段', 'いくら', '料金', 'コスト', 'プライス',
                    # 중국어
                    '价格', '价钱', '多少钱', '费用', '成本', '定价',
                    # 스페인어
                    'precio', 'precios', 'costo', 'cuanto', 'tarifa',
                    # 독일어
                    'preis', 'preise', 'kosten', 'wie viel', 'gebühr',
                    # 프랑스어
                    'prix', 'coût', 'combien', 'tarif',
                    # 러시아어
                    'цена', 'цены', 'стоимость', 'сколько'
                ]
                
                # 가격 관련 키워드 확인
                if any(keyword.lower() in user_text.lower() for keyword in price_keywords):
                    logger.info(f"💰 LINE에서 가격 정보 요청 감지 - 언어: {detected_language}")
                    price_text = get_price_list(language=detected_language)
                    
                    # ✅ LINE용 줄바꿈 처리 후 HTML 태그 제거
                    formatted_price_text = format_text_for_line(price_text)
                    clean_price_response = re.sub(r'<[^>]+>', '', formatted_price_text)
                    
                    if send_line_message(reply_token, clean_price_response):
                        save_chat(user_text, clean_price_response, user_id)
                    continue
                
                # 환영 인사 키워드 확인
                welcome_keywords = ["สวัสดี", "หวัดดี", "hello", "hi", "สวัสดีค่ะ", "สวัสดีครับ", 
                                  "ดีจ้า", "เริ่ม", "안녕하세요", "안녕", "こんにちは", "你好", "नमस्ते"]
                
                if user_text.lower() in [k.lower() for k in welcome_keywords]:
                    if detected_language == 'thai':
                        response_text = "สวัสดีค่ะ! 💕 ยินดีต้อนรับสู่ SABOO THAILAND ค่ะ\n\nมีอะไรให้ดิฉันช่วยเหลือคะ? 😊"
                    elif detected_language == 'korean':
                        response_text = "안녕하세요! 💕 SABOO THAILAND에 오신 것을 환영합니다!\n\n무엇을 도와드릴까요? 😊"
                    elif detected_language == 'japanese':
                        response_text = "こんにちは！💕 SABOO THAILANDへようこそ！\n\n何かお手伝いできることはありますか？😊"
                    elif detected_language == 'chinese':
                        response_text = "您好！💕 欢迎来到 SABOO THAILAND！\n\n有什么可以帮您的吗？😊"
                    else: # English and others
                        response_text = "Hello! 💕 Welcome to SABOO THAILAND!\n\nHow can I help you today? 😊"
                else:
                    response_text = get_gpt_response(user_text)
                
                # ✅ LINE용 줄바꿈 처리 후 HTML 태그 제거
                formatted_response = format_text_for_line(response_text)
                clean_response = re.sub(r'<[^>]+>', '', formatted_response)
                
                if send_line_message(reply_token, clean_response):
                    save_chat(user_text, clean_response, user_id)
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ LINE 웹훅 처리 중 심각한 오류 발생: {e}")
        import traceback
        logger.error(f"❌ 전체 트레이스백: {traceback.format_exc()}")
        return "Error", 500

# ✅ 에러 핸들러
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"❌ 내부 서버 오류: {error}")
    return jsonify({"error": "Server error"}), 500

# ==============================================================================
# 앱 초기화 및 실행
# ==============================================================================
app_initialized = False

@app.before_request
def initialize_once():
    """첫 번째 요청이 들어왔을 때 딱 한 번만 앱 초기화를 실행합니다."""
    global app_initialized
    if not app_initialized:
        with threading.Lock(): # 여러 요청이 동시에 들어와도 한 번만 실행되도록 보장
            if not app_initialized:
                logger.info("🎯 첫 요청 감지, 앱 초기화를 진행합니다...")
                initialize_data()
                app_initialized = True

if __name__ == '__main__':
    # 로컬 개발 환경에서는 바로 초기화 실행
    if not os.getenv('RAILWAY_ENVIRONMENT'):
        logger.info("🚀 개발 모드이므로 직접 초기화를 실행합니다...")
        initialize_data()
        app_initialized = True
    
    port = int(os.environ.get("PORT", 5000))
    debug_mode = not os.getenv('RAILWAY_ENVIRONMENT')
    
    logger.info(f"🚀 Flask 서버를 포트 {port}에서 시작합니다. (디버그 모드: {debug_mode})")
    logger.info("📂 데이터 소스: 언어별 파일만 사용 (Google 서비스 비활성화)")
    logger.info("🌈 줄바꿈 처리 기능: 웹용 <br>, LINE용 \\n\\n 지원")
    
    try:
        # use_reloader=False는 개발 모드에서 초기화가 두 번 실행되는 것을 방지
        app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=not debug_mode)
    except KeyboardInterrupt:
        logger.info("🛑 서버 종료 요청을 받았습니다.")
    except Exception as e:
        logger.error(f"❌ 서버 실행 중 오류 발생: {e}")
    finally:
        logger.info("🔚 서버가 정상적으로 종료되었습니다.")