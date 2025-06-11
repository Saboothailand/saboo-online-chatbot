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
คุณเป็นผู้เชี่ยวชาญด้านผลิตภัณฑ์ของ SABOO THAILAND และเป็นพนักงานหญิงไทยที่มีความรู้เกี่ยวกับผลิตภัณฑ์เป็นอย่างดี
คุณต้องตอบเป็นภาษาไทยเสมอ ไม่ว่าลูกค้าจะถามเป็นภาษาอะไร
ใช้คำสุภาพและเป็นกันเอง เหมือนพนักงานหญิงไทยที่อยากช่วยลูกค้า
ใช้คำว่า "ค่ะ" "คะ" ในการตอบ และใช้ภาษาไทยที่อ่อนโยนและเป็นมิตร
ตอบคำถามจากข้อมูลผลิตภัณฑ์ที่ให้มา และให้คำแนะนำที่เป็นประโยชน์
ใช้อีโมจิเล็กน้อยเพื่อให้ดูเป็นมิตร แต่อย่าใช้มากเกินไป

ข้อมูลสำคัญที่ต้องจำ:
- SABOO THAILAND ก่อตั้งปี 2008 เป็นผู้นำด้านสบู่ธรรมชาติ
- บริษัทแรกที่ทำสบู่รูปผลไม้ในไทย
- ส่งออกไปกว่า 20 ประเทศ
- ร้าน: มิกซ์ จตุจักร ชั้น 2
- โทร: 02-159-9880, 085-595-9565
- เว็บไซต์: www.saboothailand.com
- Shopee: shopee.co.th/thailandsoap

เมื่อลูกค้าถามเกี่ยวกับ:
- ที่อยู่ → บอกร้านมิกซ์ จตุจักร และโรงงานปทุมธานี
- การสั่งซื้อ → แนะนำ Shopee, Lazada, เว็บไซต์
- ผลิตภัณฑ์ → อธิบายสบู่รูปผลไม้, บาธบอมบ์, สครับ
- ติดต่อ → ให้เบอร์โทรและอีเมล
"""

# ✅ LINE Flex Message 템플릿 생성 함수
def create_flex_message(bot_response, user_message=""):
    """LINE Flex Message 포맷으로 응답 생성"""
    
    # 응답 길이에 따라 다른 템플릿 사용
    if len(bot_response) > 800:
        return create_long_response_flex(bot_response)
    else:
        return create_standard_response_flex(bot_response)

def create_standard_response_flex(bot_response):
    """표준 응답용 Flex Message"""
    return {
        "type": "flex",
        "altText": "SABOO THAILAND ตอบคำถาม",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🧴 SABOO THAILAND",
                                "weight": "bold",
                                "size": "lg",
                                "color": "#2E7D32",
                                "flex": 1
                            },
                            {
                                "type": "text",
                                "text": "💕",
                                "size": "lg",
                                "align": "end"
                            }
                        ]
                    }
                ],
                "backgroundColor": "#FFE4E6",
                "paddingAll": "15px",
                "spacing": "md"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": bot_response,
                        "wrap": True,
                        "size": "md",
                        "color": "#333333",
                        "lineSpacing": "sm"
                    }
                ],
                "paddingAll": "20px",
                "spacing": "md"
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "button",
                                "style": "link",
                                "height": "sm",
                                "action": {
                                    "type": "postback",
                                    "label": "สอบถามผลิตภัณฑ์",
                                    "data": "action=product_inquiry"
                                },
                                "color": "#E91E63"
                            },
                            {
                                "type": "button",
                                "style": "link",
                                "height": "sm",
                                "action": {
                                    "type": "uri",
                                    "label": "เว็บไซต์",
                                    "uri": "https://www.saboothailand.com"
                                },
                                "color": "#2E7D32"
                            }
                        ],
                        "spacing": "sm",
                        "margin": "md"
                    }
                ],
                "paddingAll": "15px"
            }
        }
    }

def create_long_response_flex(bot_response):
    """긴 응답용 Carousel Flex Message"""
    # 응답을 적절한 길이로 분할
    chunks = split_response(bot_response, 600)
    
    bubbles = []
    for i, chunk in enumerate(chunks):
        bubble = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"🧴 SABOO THAILAND ({i+1}/{len(chunks)})",
                        "weight": "bold",
                        "size": "lg",
                        "color": "#2E7D32"
                    }
                ],
                "backgroundColor": "#FFE4E6",
                "paddingAll": "15px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": chunk,
                        "wrap": True,
                        "size": "md",
                        "color": "#333333",
                        "lineSpacing": "sm"
                    }
                ],
                "paddingAll": "20px"
            }
        }
        
        # 마지막 bubble에만 footer 추가
        if i == len(chunks) - 1:
            bubble["footer"] = {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {
                                "type": "button",
                                "style": "link",
                                "height": "sm",
                                "action": {
                                    "type": "postback",
                                    "label": "สอบถามเพิ่มเติม",
                                    "data": "action=more_inquiry"
                                },
                                "color": "#E91E63"
                            },
                            {
                                "type": "button",
                                "style": "link",
                                "height": "sm",
                                "action": {
                                    "type": "uri",
                                    "label": "แคตตาล็อก",
                                    "uri": "https://books.saboothailand.com/books/bxte/#p=1"
                                },
                                "color": "#2E7D32"
                            }
                        ],
                        "spacing": "sm",
                        "margin": "md"
                    }
                ],
                "paddingAll": "15px"
            }
        
        bubbles.append(bubble)
    
    return {
        "type": "flex",
        "altText": "SABOO THAILAND คำตอบแบบละเอียด",
        "contents": {
            "type": "carousel",
            "contents": bubbles
        }
    }

def create_quick_reply_buttons():
    """자주 묻는 질문 빠른 답변 버튼"""
    return [
        {
            "type": "action",
            "action": {
                "type": "message",
                "label": "ผลิตภัณฑ์มีอะไรบ้าง",
                "text": "มีผลิตภัณฑ์อะไรบ้างคะ"
            }
        },
        {
            "type": "action", 
            "action": {
                "type": "message",
                "label": "ร้านอยู่ที่ไหน",
                "text": "ร้าน SABOO อยู่ที่ไหนคะ"
            }
        },
        {
            "type": "action",
            "action": {
                "type": "message", 
                "label": "วิธีสั่งซื้อ",
                "text": "สั่งซื้อสินค้าได้อย่างไรคะ"
            }
        },
        {
            "type": "action",
            "action": {
                "type": "uri",
                "label": "Shopee",
                "uri": "https://shopee.co.th/thailandsoap"
            }
        }
    ]

def split_response(text, max_length):
    """응답을 적절한 길이로 분할"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    sentences = text.split('. ')
    for sentence in sentences:
        if len(current_chunk + sentence + '. ') <= max_length:
            current_chunk += sentence + '. '
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence + '. '
            else:
                # 단일 문장이 너무 긴 경우
                chunks.append(sentence[:max_length] + '...')
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

def create_welcome_message():
    """환영 메시지용 Flex Message"""
    return {
        "type": "flex",
        "altText": "ยินดีต้อนรับสู่ SABOO THAILAND ค่ะ!",
        "contents": {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": "https://via.placeholder.com/1040x585/E91E63/FFFFFF?text=SABOO+THAILAND+🧴",
                "size": "full",
                "aspectRatio": "20:13",
                "aspectMode": "cover"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🧴 SABOO THAILAND",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#2E7D32"
                    },
                    {
                        "type": "text",
                        "text": "สวัสดีค่ะ! 💕 ดิฉันยินดีให้คำแนะนำเกี่ยวกับผลิตภัณฑ์สบู่และผลิตภัณฑ์อาบน้ำธรรมชาติของเราค่ะ",
                        "size": "sm",
                        "color": "#666666",
                        "margin": "md",
                        "wrap": True
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "text",
                        "text": "🌟 บริการของเรา",
                        "weight": "bold",
                        "margin": "lg",
                        "color": "#2E7D32"
                    },
                    {
                        "type": "text",
                        "text": "• สอบถามข้อมูลผลิตภัณฑ์\n• คำแนะนำวิธีใช้\n• ส่วนประกอบและสรรพคุณ\n• ช่องทางการสั่งซื้อ\n• คำแนะนำดูแลผิว",
                        "size": "sm",
                        "margin": "md",
                        "wrap": True
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "text",
                                "text": "📍 ร้าน: มิกซ์ จตุจักร ชั้น 2",
                                "size": "xs",
                                "color": "#888888"
                            },
                            {
                                "type": "text", 
                                "text": "📞 โทร: 02-159-9880",
                                "size": "xs",
                                "color": "#888888"
                            },
                            {
                                "type": "text",
                                "text": "🛒 Shopee: shopee.co.th/thailandsoap",
                                "size": "xs", 
                                "color": "#888888"
                            }
                        ]
                    }
                ],
                "spacing": "sm",
                "paddingAll": "20px"
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "action": {
                            "type": "message",
                            "label": "สอบถามผลิตภัณฑ์",
                            "text": "อยากทราบเกี่ยวกับผลิตภัณฑ์ค่ะ"
                        },
                        "color": "#E91E63"
                    },
                    {
                        "type": "button",
                        "style": "link",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "เว็บไซต์ SABOO",
                            "uri": "https://www.saboothailand.com"
                        }
                    }
                ],
                "spacing": "sm",
                "paddingAll": "20px"
            }
        }
    }

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
            if event.get("type") == "message" and event["message"]["type"] == "text":
                user_text = event["message"]["text"].strip()
                reply_token = event["replyToken"]
                user_id = event["source"]["userId"]

                # 환영 메시지 처리
                if user_text.lower() in ["สวัสดี", "หวัดดี", "hello", "hi", "สวัสดีค่ะ", "สวัสดีครับ", "ดีจ้า", "เริ่ม"]:
                    flex_message = create_welcome_message()
                    payload = {
                        "replyToken": reply_token,
                        "messages": [flex_message]
                    }
                else:
                    # 일반 질문 처리 - OpenAI 클라이언트 확인
                    if not client:
                        simple_message = {
                            "type": "text",
                            "text": "ขออภัยค่ะ ระบบมีปัญหาชั่วคราว กรุณาลองใหม่อีกครั้งค่ะ 🙏"
                        }
                        payload = {
                            "replyToken": reply_token,
                            "messages": [simple_message]
                        }
                    else:
                        # GPT 응답 생성
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
                        flex_message = create_flex_message(bot_response, user_text)
                        
                        # Quick Reply 버튼 추가 (특정 키워드에 대해)
                        if any(keyword in user_text.lower() for keyword in ["ผลิตภัณฑ์", "สินค้า", "ขาย", "มีอะไร"]):
                            # 제품 관련 질문에는 Quick Reply 추가
                            payload = {
                                "replyToken": reply_token,
                                "messages": [flex_message],
                                "quickReply": {
                                    "items": create_quick_reply_buttons()
                                }
                            }
                        else:
                            payload = {
                                "replyToken": reply_token,
                                "messages": [flex_message]
                            }

                save_chat(user_text, "Flex message sent", user_id)

                # LINE API로 응답 전송
                line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or os.getenv("LINE_TOKEN", "")
                if not line_token:
                    logger.error("❌ LINE_CHANNEL_ACCESS_TOKEN not found!")
                    return "Error: Missing LINE token", 500
                    
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {line_token}"
                }

                response = requests.post(
                    "https://api.line.me/v2/bot/message/reply", 
                    headers=headers, 
                    json=payload,
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.error(f"❌ LINE API Error: {response.status_code} - {response.text}")
                else:
                    logger.info(f"✅ Message sent successfully to user {user_id}")
                
            elif event.get("type") == "postback":
                # Postback 이벤트 처리
                postback_data = event["postback"]["data"]
                reply_token = event["replyToken"]
                user_id = event["source"]["userId"]
                
                handle_postback(postback_data, reply_token, user_id)

        return "OK", 200
    except Exception as e:
        logger.error(f"❌ LINE Webhook Error: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return "Error", 500

def handle_postback(data, reply_token, user_id):
    """Postback 이벤트 처리"""
    try:
        line_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or os.getenv("LINE_TOKEN", "")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_token}"
        }
        
        if "action=product_inquiry" in data:
            message = {
                "type": "text",
                "text": "มีผลิตภัณฑ์อะไรที่อยากทราบเพิ่มเติมคะ? บอกดิฉันได้เลยค่ะ! 😊\n\nตัวอย่างเช่น:\n• วิธีใช้บาธบอมบ์\n• ผลิตภัณฑ์สำหรับผิวแพ้ง่าย\n• ส่วนประกอบของสบู่\n• ช่องทางการสั่งซื้อ\n• การดูแลผิวหน้า"
            }
        elif "action=more_inquiry" in data:
            message = {
                "type": "text", 
                "text": "หากมีคำถามเพิ่มเติม สามารถสอบถามได้ตลอดเวลาค่ะ! 💕\n\nติดต่อเรา:\n📧 saboothailand@gmail.com\n📞 02-159-9880\n🌐 www.saboothailand.com\n\nยินดีให้บริการค่ะ! 😊"
            }
        else:
            message = {
                "type": "text",
                "text": "ขออภัยค่ะ ดิฉันไม่เข้าใจคำขอนี้ค่ะ กรุณาลองใหม่อีกครั้งนะคะ 😊"
            }
        
        payload = {
            "replyToken": reply_token,
            "messages": [message]
        }
        
        requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        save_chat(f"Postback: {data}", f"Response sent", user_id)
        
    except Exception as e:
        logger.error(f"❌ Postback handling error: {e}")

# ✅ 대화 로그 저장 (user_id 포함)
def save_chat(user_msg, bot_msg, user_id="anonymous"):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[LINE CHAT] {timestamp} | User({user_id}): {user_msg}")
        logger.info(f"[LINE CHAT] {timestamp} | Bot: {bot_msg}")
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
    app.run(host='0.0.0.0', port=port, debug_debug_mode)