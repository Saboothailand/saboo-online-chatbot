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
LINE_SECRET = os.getenv("LINE_CHANNEL_SECRET") or os.getenv("LINE_SECRET")

if not LINE_TOKEN:
    logger.error("❌ LINE_TOKEN or LINE_CHANNEL_ACCESS_TOKEN not found!")
if not LINE_SECRET:
    logger.error("❌ LINE_SECRET or LINE_CHANNEL_SECRET not found!")

# ✅ Google API 설정
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_DOC_ID = os.getenv("GOOGLE_DOC_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
UPDATE_INTERVAL_MINUTES = int(os.getenv("UPDATE_INTERVAL_MINUTES", "5"))

# ✅ 전역 변수로 데이터와 해시 저장
current_sheet_text = ""
current_doc_text = ""
sheet_hash = ""
doc_hash = ""
last_update_time = datetime.now()
scheduler = None

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

# ✅ 사용 가능한 포트 찾기 함수
def find_free_port():
    """사용 가능한 포트 찾기"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    except:
        return 5000

# ✅ Google Sheets API에서 데이터 가져오기 (수정된 버전)
def fetch_google_sheet_data():
    """Google Sheets에서 데이터 가져오기 - 개선된 버전"""
    try:
        logger.info("🔍 Attempting to fetch Google Sheets data...")
        
        # 방법 1: gspread 사용 (서비스 계정 필요)
        if GOOGLE_CREDENTIALS_JSON:
            try:
                import gspread
                from oauth2client.service_account import ServiceAccountCredentials
                
                creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
                scope = ['https://spreadsheets.google.com/feeds',
                        'https://www.googleapis.com/auth/drive']
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                gc = gspread.authorize(creds)
                
                sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1
                all_values = sheet.get_all_values()
                
                # 시트 데이터를 텍스트로 변환
                sheet_content = ""
                for row in all_values:
                    row_text = " | ".join(str(cell) for cell in row if str(cell).strip())
                    if row_text.strip():
                        sheet_content += row_text + "\n"
                
                logger.info(f"✅ Google Sheets data fetched via gspread: {len(sheet_content)} chars")
                logger.info(f"📊 Preview: {sheet_content[:200]}...")
                return sheet_content.strip()
                
            except ImportError:
                logger.warning("⚠️ gspread not installed, trying REST API")
            except Exception as e:
                logger.error(f"❌ gspread failed: {e}")
        
        # 방법 2: REST API 사용 (공개 문서인 경우만)
        if GOOGLE_API_KEY and GOOGLE_SHEET_ID:
            try:
                # 시트를 공개로 설정해야 API 키로 접근 가능
                url = f"https://sheets.googleapis.com/v4/spreadsheets/{GOOGLE_SHEET_ID}/values/A:Z?key={GOOGLE_API_KEY}"
                
                logger.info(f"🌐 Trying REST API: {url}")
                response = requests.get(url, timeout=15)
                
                logger.info(f"📡 API Response Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    values = data.get('values', [])
                    
                    # 시트 데이터를 텍스트로 변환
                    sheet_content = ""
                    for row in values:
                        row_text = " | ".join(str(cell) for cell in row if str(cell).strip())
                        if row_text.strip():
                            sheet_content += row_text + "\n"
                    
                    logger.info(f"✅ Google Sheets data fetched via REST API: {len(sheet_content)} chars")
                    logger.info(f"📊 Preview: {sheet_content[:200]}...")
                    return sheet_content.strip()
                elif response.status_code == 403:
                    logger.error("❌ Google Sheets API - Access denied. Make sure the sheet is publicly accessible")
                    logger.info("💡 To fix: Share the Google Sheet with 'Anyone with the link can view'")
                elif response.status_code == 404:
                    logger.error("❌ Google Sheets API - Sheet not found. Check GOOGLE_SHEET_ID")
                else:
                    logger.error(f"❌ Google Sheets REST API error: {response.status_code}")
                    logger.error(f"❌ Error response: {response.text}")
            except Exception as e:
                logger.error(f"❌ REST API request failed: {e}")
        
        logger.warning("⚠️ No Google Sheets credentials or API key configured, using fallback data")
        return None
            
    except Exception as e:
        logger.error(f"❌ Error fetching Google Sheets data: {e}")
        import traceback
        logger.error(f"❌ Full traceback: {traceback.format_exc()}")
        return None

# ✅ Google Docs 폴백 (간단한 텍스트 파일로 대체)
def fetch_google_doc_data():
    """Google Docs 대신 로컬 파일이나 기본 데이터 사용"""
    try:
        logger.info("🔍 Loading document data...")
        
        # 로컬 파일이 있다면 사용
        if os.path.exists('company_info.txt'):
            with open('company_info.txt', 'r', encoding='utf-8') as f:
                content = f.read().strip()
                logger.info(f"✅ Local document file loaded: {len(content)} chars")
                return content
        
        # 기본 회사 정보 반환
        default_info = """
SABOO THAILAND - เพิ่มเติม

ประวัติความเป็นมา:
- ก่อตั้งในปี 2008 โดยมีวิสัยทัศน์ในการสร้างผลิตภัณฑ์สบู่ธรรมชาติที่มีคุณภาพ
- เป็นผู้บุกเบิกการผลิตสบู่รูปผลไม้ครั้งแรกในประเทศไทย
- ได้รับการยอมรับในระดับสากลและส่งออกไปทั่วโลก

คุณภาพและมาตรฐาน:
- ผลิตด้วยวัตถุดิบธรรมชาติ 100%
- ไม่มีสารเคมีที่เป็นอันตราย
- ผ่านมาตรฐานความปลอดภัยระดับสากล
- เป็นมิตรกับสิ่งแวดล้อม

การบริการ:
- จัดส่งทั่วประเทศไทย
- รับสั่งผลิตตามความต้องการ (OEM/ODM)
- บริการหลังการขายที่เป็นเลิศ
- คำปรึกษาผลิตภัณฑ์ฟรี
"""
        logger.info(f"✅ Using default document info: {len(default_info)} chars")
        return default_info.strip()
            
    except Exception as e:
        logger.error(f"❌ Error loading document data: {e}")
        return "ข้อมูลเพิ่มเติมเกี่ยวกับ SABOO THAILAND"

# ✅ 데이터 해시 계산
def calculate_hash(data):
    """데이터의 MD5 해시 계산"""
    if not data:
        return ""
    return hashlib.md5(data.encode('utf-8')).hexdigest()

# ✅ Google 데이터 업데이트 확인 및 갱신
def check_and_update_google_data():
    """Google Sheets/Docs 데이터 변경사항 확인 및 업데이트"""
    global current_sheet_text, current_doc_text, sheet_hash, doc_hash, last_update_time
    
    try:
        logger.info("🔄 Checking for data updates...")
        update_occurred = False
        
        # Sheets 데이터 확인
        try:
            new_sheet_data = fetch_google_sheet_data()
            if new_sheet_data and len(new_sheet_data.strip()) > 50:
                new_sheet_hash = calculate_hash(new_sheet_data)
                if new_sheet_hash != sheet_hash:
                    logger.info("📊 Google Sheets data updated!")
                    current_sheet_text = new_sheet_data
                    sheet_hash = new_sheet_hash
                    update_occurred = True
                else:
                    logger.info("📊 Google Sheets data unchanged")
            else:
                logger.info("📊 Using existing sheet data")
        except Exception as e:
            logger.error(f"❌ Error checking Google Sheets: {e}")
        
        # Docs 데이터 확인
        try:
            new_doc_data = fetch_google_doc_data()
            if new_doc_data and len(new_doc_data.strip()) > 20:
                new_doc_hash = calculate_hash(new_doc_data)
                if new_doc_hash != doc_hash:
                    logger.info("📄 Document data updated!")
                    current_doc_text = new_doc_data
                    doc_hash = new_doc_hash
                    update_occurred = True
                else:
                    logger.info("📄 Document data unchanged")
        except Exception as e:
            logger.error(f"❌ Error checking document: {e}")
        
        if update_occurred:
            last_update_time = datetime.now()
            logger.info(f"✅ Data update completed at {last_update_time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            logger.info(f"ℹ️ No data changes detected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        logger.error(f"❌ Error in check_and_update_google_data: {e}")

# ✅ 초기 데이터 로드
def initialize_google_data():
    """앱 시작시 데이터 초기 로드"""
    global current_sheet_text, current_doc_text, sheet_hash, doc_hash
    
    logger.info("🚀 Initializing data...")
    
    # 기본값 설정
    current_sheet_text = saboo_thai_info
    current_doc_text = "ข้อมูลเพิ่มเติมเกี่ยวกับ SABOO THAILAND"
    
    # 환경 변수 확인 및 로그
    logger.info(f"🔧 Environment check:")
    logger.info(f"   - GOOGLE_SHEET_ID: {'✅' if GOOGLE_SHEET_ID else '❌'}")
    logger.info(f"   - GOOGLE_DOC_ID: {'✅' if GOOGLE_DOC_ID else '❌'}")
    logger.info(f"   - GOOGLE_API_KEY: {'✅' if GOOGLE_API_KEY else '❌'}")
    logger.info(f"   - GOOGLE_CREDENTIALS_JSON: {'✅' if GOOGLE_CREDENTIALS_JSON else '❌'}")
    
    # Google API로 데이터 가져오기 시도
    try:
        sheet_data = fetch_google_sheet_data()
        if sheet_data and len(sheet_data.strip()) > 50:
            current_sheet_text = sheet_data
            logger.info("✅ Google Sheets data loaded successfully")
        else:
            logger.info("ℹ️ Using fallback sheet data")
        
        doc_data = fetch_google_doc_data()
        if doc_data and len(doc_data.strip()) > 20:
            current_doc_text = doc_data
            logger.info("✅ Document data loaded successfully")
        else:
            logger.info("ℹ️ Using fallback document data")
    except Exception as e:
        logger.error(f"❌ Error during data initialization: {e}")
        logger.info("ℹ️ Continuing with fallback data")
    
    # 초기 해시 계산
    sheet_hash = calculate_hash(current_sheet_text)
    doc_hash = calculate_hash(current_doc_text)
    
    logger.info(f"📊 Final sheet data length: {len(current_sheet_text)} chars")
    logger.info(f"📄 Final doc data length: {len(current_doc_text)} chars")

# ✅ 스케줄러 설정
def setup_scheduler():
    """백그라운드 스케줄러 설정"""
    global scheduler
    try:
        if scheduler and scheduler.running:
            scheduler.shutdown()
            
        scheduler = BackgroundScheduler(daemon=True)
        
        scheduler.add_job(
            func=check_and_update_google_data,
            trigger=IntervalTrigger(minutes=UPDATE_INTERVAL_MINUTES),
            id='google_data_update',
            name='Check Google Data Updates',
            replace_existing=True,
            max_instances=1
        )
        
        scheduler.start()
        logger.info(f"⏰ Scheduler started - checking every {UPDATE_INTERVAL_MINUTES} minutes")
        
        return scheduler
    except Exception as e:
        logger.error(f"❌ Failed to setup scheduler: {e}")
        return None

# ✅ GPT 시스템 메시지
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

# ✅ 영어 폴백 시스템 메시지
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

# ✅ 언어 감지 함수
def detect_user_language(message):
    """사용자 메시지의 언어 감지"""
    try:
        # 태국어 문자 패턴
        thai_pattern = r'[\u0E00-\u0E7F]'
        # 한국어 문자 패턴  
        korean_pattern = r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]'
        
        if re.search(thai_pattern, message):
            return 'thai'
        elif re.search(korean_pattern, message):
            return 'korean'
        else:
            return 'english'  # 기본값
    except Exception as e:
        logger.error(f"❌ Language detection error: {e}")
        return 'english'  # 에러 시 영어로 폴백

# ✅ 영어 폴백 응답 생성
def get_english_fallback_response(user_message, error_context=""):
    """문제 발생 시 영어로 폴백 응답 생성"""
    try:
        logger.warning(f"⚠️ Activating English fallback. Context: {error_context}")
        
        if not client:
            return """I apologize, but we're experiencing technical difficulties at the moment. 

Here's some basic information about SABOO THAILAND:
- We're Thailand's first natural fruit-shaped soap manufacturer since 2008
- Store location: Mixt Chatuchak, 2nd Floor, Bangkok
- Phone: 02-159-9880, 085-595-9565
- Website: www.saboothailand.com
- Shopee: shopee.co.th/thailandsoap

Please try again later or contact us directly. Thank you for your understanding! 😊"""
        
        prompt = f"""
The user asked: "{user_message}"

There was a technical issue: {error_context}

Please provide a helpful response in English using basic company information.
"""
        
        completion = client.chat.completions.create(
            model="gpt-4o",
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
        logger.error(f"❌ English fallback response error: {e}")
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

def add_hyperlinks(text):
    """텍스트에서 전화번호와 URL을 하이퍼링크로 변환"""
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
        logger.error(f"❌ Hyperlink processing error: {e}")
        return text

# ✅ LINE 서명 검증 함수
def verify_line_signature(body, signature):
    """LINE Webhook 서명 검증"""
    try:
        if not LINE_SECRET:
            logger.warning("⚠️ LINE_SECRET not set, skipping signature verification")
            return True
            
        hash = hmac.new(LINE_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
        expected_signature = base64.b64encode(hash).decode('utf-8')
        
        return hmac.compare_digest(expected_signature, signature)
    except Exception as e:
        logger.error(f"❌ Signature verification error: {e}")
        return False

# ✅ GPT 응답 생성 함수 (업데이트된 데이터 사용 + 영어 폴백) - ⭐️ 수정된 부분 ⭐️
def get_gpt_response(user_message):
    """OpenAI GPT로 응답 생성 - 최신 데이터 사용 + 영어 폴백"""
    user_language = detect_user_language(user_message)
    
    try:
        if not client:
            logger.error("❌ OpenAI client not available")
            return get_english_fallback_response(user_message, "OpenAI service unavailable")
        
        # 데이터 유효성 검사
        if not current_sheet_text or len(current_sheet_text.strip()) < 50:
            logger.warning("⚠️ Sheet data seems insufficient, using fallback")
            return get_english_fallback_response(user_message, "Product data temporarily unavailable")
        
        # 최신 데이터 사용
        prompt = f"""
[Product Info - Last Updated: {last_update_time.strftime('%Y-%m-%d %H:%M:%S')}]
{current_sheet_text[:5000]}

[Company Info - Last Updated: {last_update_time.strftime('%Y-%m-%d %H:%M:%S')}]  
{current_doc_text[:5000]}

[User Language Detected: {user_language}]
[User]
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
            logger.warning("⚠️ Generated response seems too short, falling back.")
            return get_english_fallback_response(user_message, "Response generation issue")
        
        # 하이퍼링크 추가
        response_text = add_hyperlinks(response_text)
        
        return response_text

    except Exception as e:
        logger.error(f"❌ GPT response generation error: {e}")
        error_context = f"GPT API error: {str(e)[:100]}"
        return get_english_fallback_response(user_message, error_context)


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
    return render_template('chat.html')

# ✅ 헬스체크 (업데이트 정보 포함)
@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "openai": "connected" if client else "disconnected",
        "line_token": "configured" if LINE_TOKEN else "missing",
        "line_secret": "configured" if LINE_SECRET else "missing",
        "google_api": "configured" if GOOGLE_API_KEY else "missing",
        "google_credentials": "configured" if GOOGLE_CREDENTIALS_JSON else "missing",
        "google_sheet_id": "configured" if GOOGLE_SHEET_ID else "missing",
        "google_doc_id": "configured" if GOOGLE_DOC_ID else "missing",
        "last_data_update": last_update_time.isoformat(),
        "update_interval_minutes": UPDATE_INTERVAL_MINUTES,
        "sheet_data_length": len(current_sheet_text),
        "doc_data_length": len(current_doc_text),
        "scheduler_running": scheduler.running if scheduler else False
    })

# ✅ 수동 업데이트 트리거 엔드포인트
@app.route('/trigger-update')
def trigger_update():
    """수동으로 데이터 업데이트 트리거"""
    try:
        old_sheet_hash = sheet_hash
        old_doc_hash = doc_hash
        
        check_and_update_google_data()
        
        return jsonify({
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "sheet_updated": sheet_hash != old_sheet_hash,
            "doc_updated": doc_hash != old_doc_hash,
            "last_update": last_update_time.isoformat(),
            "new_sheet_hash": sheet_hash,
            "new_doc_hash": doc_hash
        })
    except Exception as e:
        logger.error(f"❌ Manual update trigger error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ✅ 디버그용 엔드포인트
@app.route('/debug-data')
def debug_data():
    """데이터 상태 디버깅"""
    try:
        fresh_sheet = fetch_google_sheet_data()
        fresh_doc = fetch_google_doc_data()
        
        return jsonify({
            "current_data": {
                "sheet_length": len(current_sheet_text),
                "sheet_hash": sheet_hash,
                "sheet_preview": current_sheet_text[:300] + "...",
            },
            "fresh_data": {
                "sheet_length": len(fresh_sheet) if fresh_sheet else 0,
                "sheet_hash": calculate_hash(fresh_sheet) if fresh_sheet else None,
                "sheet_preview": fresh_sheet[:300] + "..." if fresh_sheet else "No data",
            },
            "comparison": {
                "sheet_data_different": (calculate_hash(fresh_sheet) != sheet_hash) if fresh_sheet else "Cannot compare",
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ 웹 챗 라우트
@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.json.get('message', '').strip()
        if not user_message:
            return jsonify({"error": "Empty message."}), 400

        bot_response = get_gpt_response(user_message)
        save_chat(user_message, bot_response)
        
        return jsonify({
            "reply": bot_response,
            "is_html": True,
            "user_language": detect_user_language(user_message)
        })

    except Exception as e:
        logger.error(f"❌ Error in /chat: {e}")
        fallback_response = get_english_fallback_response(
            user_message if 'user_message' in locals() else "general inquiry", 
            f"Web chat system error: {str(e)[:100]}"
        )
        return jsonify({
            "reply": fallback_response,
            "is_html": True,
            "error": "fallback_mode"
        })

# ✅ LINE 챗봇 Webhook
@app.route('/line', methods=['POST'])
def line_webhook():
    """LINE Webhook 핸들러"""
    try:
        body = request.get_data(as_text=True)
        signature = request.headers.get('X-Line-Signature', '')
        
        logger.info(f"📨 LINE webhook received: {len(body)} bytes")
        
        if not verify_line_signature(body.encode('utf-8'), signature):
            logger.warning("⚠️ Invalid signature.")
            # 서명이 유효하지 않아도 개발 편의를 위해 일단 진행 (프로덕션에서는 400 반환 권장)
            # return "Invalid signature", 400
        
        webhook_data = json.loads(body)
        
        for event in webhook_data.get("events", []):
            if event.get("type") == "message" and event.get("message", {}).get("type") == "text":
                user_text = event["message"]["text"].strip()
                reply_token = event["replyToken"]
                user_id = event.get("source", {}).get("userId", "unknown")
                
                logger.info(f"👤 User {user_id}: {user_text}")
                
                welcome_keywords = ["สวัสดี", "หวัดดี", "hello", "hi", "สวัสดีค่ะ", "สวัสดีครับ", "ดีจ้า", "เริ่ม", "안녕하세요"]
                
                if user_text.lower() in [k.lower() for k in welcome_keywords]:
                    user_lang = detect_user_language(user_text)
                    if user_lang == 'thai':
                        response_text = "สวัสดีค่ะ! 💕 ยินดีต้อนรับสู่ SABOO THAILAND ค่ะ\n\nมีอะไรให้ดิฉันช่วยเหลือคะ? 😊"
                    elif user_lang == 'korean':
                        response_text = "안녕하세요! 💕 SABOO THAILAND에 오신 것을 환영합니다!\n\n무엇을 도와드릴까요? 😊"
                    else: # English
                        response_text = "Hello! 💕 Welcome to SABOO THAILAND!\n\nHow can I help you today? 😊"
                else:
                    response_text = get_gpt_response(user_text)
                
                # LINE은 HTML을 지원하지 않으므로 태그 제거
                clean_response = re.sub(r'<[^>]+>', '', response_text)
                
                if send_line_message(reply_token, clean_response):
                    save_chat(user_text, clean_response, user_id)
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ LINE Webhook fatal error: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return "Error", 500

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

# ✅ 앱 시작시 한 번만 초기화
app_initialized = False

@app.before_request
def initialize_once():
    """앱 시작시 한 번만 초기화 실행"""
    global app_initialized
    if not app_initialized:
        with threading.Lock():
            if not app_initialized:
                logger.info("🎯 Running one-time initialization...")
                initialize_google_data()
                setup_scheduler()
                app_initialized = True

# ✅ 실행 시작
if __name__ == '__main__':
    # 개발 환경에서는 before_request 후크가 아닌 직접 초기화가 더 안정적일 수 있음
    if not os.getenv('RAILWAY_ENVIRONMENT'):
        logger.info("🚀 Development mode - running direct initialization...")
        initialize_google_data()
        setup_scheduler()
        app_initialized = True
    
    port = int(os.environ.get("PORT", 5000))
    debug_mode = not os.getenv('RAILWAY_ENVIRONMENT')
    
    logger.info(f"🚀 Starting server on port {port} with debug_mode={debug_mode}")
    
    try:
        # use_reloader=False는 개발 환경에서 초기화가 두 번 실행되는 것을 방지합니다.
        app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=not debug_mode)
    finally:
        if scheduler and scheduler.running:
            scheduler.shutdown()
            logger.info("🛑 Scheduler shutdown completed")