# -*- coding: utf-8 -*-

# ==============================================================================
# 1. 모듈 임포트 (Imports)
# ==============================================================================
import base64
import glob
import hashlib
import hmac
import json
import logging
import os
import re
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import OpenAI

# ==============================================================================
# 2. 기본 설정 (Initial Setup)
# ==============================================================================
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

if os.getenv('RAILWAY_ENVIRONMENT'):
    logger.info("✅ Railway 프로덕션 환경에서 실행 중입니다.")
else:
    logger.info("✅ 로컬 개발 환경에서 실행 중입니다.")

# ==============================================================================
# 3. Flask 앱 생성 (App Creation)
# ==============================================================================
app = Flask(__name__)

# ==============================================================================
# 4. 전역 변수 및 상수 정의 (Globals & Constants)
# ==============================================================================
CHAT_LOG_DIR = "save_chat"

# 전역 변수 초기화
product_data_cache: Dict[str, str] = {}
product_last_update: Optional[datetime] = None
language_data_cache: Dict[str, str] = {}
user_context_cache: Dict[str, List[Dict[str, Any]]] = {}
app_initialized = False

# OpenAI, LINE, Admin 설정
try:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY가 .env 파일에 없습니다.")
    client = OpenAI(api_key=openai_api_key)
    logger.info("✅ OpenAI 클라이언트가 성공적으로 초기화되었습니다.")
except Exception as e:
    logger.error(f"❌ OpenAI 클라이언트 초기화 실패: {e}")
    client = None

LINE_TOKEN = os.getenv("LINE_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_CHANNEL_SECRET") or os.getenv("LINE_SECRET")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

if not LINE_TOKEN:
    logger.error("❌ LINE_TOKEN 또는 LINE_CHANNEL_ACCESS_TOKEN을 찾을 수 없습니다!")
if not LINE_SECRET:
    logger.error("❌ LINE_SECRET 또는 LINE_CHANNEL_SECRET을 찾을 수 없습니다!")
if not ADMIN_API_KEY:
    logger.warning("⚠️ ADMIN_API_KEY가 설정되지 않았습니다. 관리자 엔드포인트가 보호되지 않습니다.")

# 제품 검색을 위한 키워드 매핑 (🔥 다국어 강화)
INTENT_KEYWORDS = {
    'product_names': [
        # 🔥 기본 제품 타입 (다국어)
        'bath bomb', 'bathbomb', '배스봄', '바스봄', '목욕폭탄', 'บาธบอม', 'บอม', 'ลูกบอลอาบน้ำ', 'バスボム', '泡澡球', '沐浴球', 'bomba de baño', 'badebombe', 'bombe de bain',
        'bubble', '버블', 'บับเบิล', 'ฟอง', 'バブル', '泡泡', 'burbuja', 'blase', 'bulle',
        'soap', '비누', '소프', 'สบู่', '石鹸', 'ソープ', '肥皂', 'jabón', 'seife', 'savon', 'мыло',
        'scrub', '스크럽', '각질제거', 'สครับ', 'スクラブ', '磨砂膏', 'exfoliante', 'peeling', 'gommage',
        'perfume', '향수', '퍼퓨', 'น้ำหอม', '香水', 'perfume', 'parfüm', 'духи',
        'spray', '스프레이', '분무기', 'สเปรย์', 'スプレー', '喷雾', 'aerosol',
        
        # 🔥 구체적인 제품명 (과일류)
        'mango', '망고', 'มะม่วง', 'マンゴー', '芒果', 'манго',
        'banana', '바나나', 'กล้วย', 'バナナ', '香蕉', 'plátano', 'banane', 'банан',
        'apple', '사과', 'แอปเปิ้ล', 'リンゴ', '苹果', 'manzana', 'apfel', 'pomme', 'яблоко',
        'orange', '오렌지', 'ส้ม', 'オレンジ', '橙子', 'naranja', 'orange', 'апельсин',
        'strawberry', '딸기', 'สตรอเบอรี่', 'イチゴ', '草莓', 'fresa', 'erdbeere', 'fraise', 'клубника',
        
        # 🔥 구체적인 제품명 (꽃류)
        'jasmine', '재스민', '자스민', 'ดอกมะลิ', 'มะลิ', 'ジャスミン', '茉莉花', '茉莉', 'jazmín', 'jasmin', 'жасмин',
        'lavender', '라벤더', 'ลาเวนเดอร์', 'ラベンダー', '薰衣草', 'lavanda', 'lavendel', 'lavande', 'лаванда',
        'rose', '장미', '로즈', 'กุหลาบ', 'ローズ', 'バラ', '玫瑰', 'rosa', 'роза',
        'orchid', '난초', 'กล้วยไม้', 'ラン', '兰花', 'orquídea', 'orchidee', 'орхидея',
        
        # 🔥 구체적인 제품명 (동물류)
        'elephant', '코끼리', 'ช้าง', 'ゾウ', '大象', 'elefante', 'elefant', 'éléphant', 'слон',
        'duck', '오리', 'เป็ด', 'アヒル', 'カモ', '鸭子', 'pato', 'ente', 'canard', 'утка',
        'bear', '곰', '베어', 'หมี', 'クマ', '熊', 'oso', 'bär', 'ours', 'медведь',
        'dinosaur', '공룡', '다이노소어', 'ไดโนเสาร์', '恐竜', '恐龙', 'dinosaurio', 'dinosaurier', 'dinosaure', 'динозавр',
        'cat', '고양이', 'แมว', 'ネコ', '猫', 'gato', 'katze', 'chat', 'кошка',
        'dog', '강아지', 'หมา', 'イヌ', '狗', 'perro', 'hund', 'chien', 'собака',
        
        # 🔥 구체적인 제품명 (허브/향료류)  
        'peppermint', '페퍼민트', '민트', '멘톨', 'เปปเปอร์มินต์', 'มินต์', 'เมนทอล', 'ペパーミント', 'ミント', '薄荷', 'menta', 'mentol', 'minze', 'pfefferminz', 'menthe', 'menthol',
        'vanilla', '바닐라', 'วานิลลา', 'バニラ', '香草', 'vainilla', 'vanille', 'ваниль',
        'coconut', '코코넛', 'มะพร้าว', 'ココナッツ', '椰子', 'coco', 'kokosnuss', 'noix de coco', 'кокос',
        'honey', '꿀', 'น้ำผึ้ง', 'ハチミツ', '蜂蜜', 'miel', 'honig', 'мёд',
        'milk', '우유', 'นม', 'ミルク', '牛奶', 'leche', 'milch', 'lait', 'молоко',
        
        # 기타
        'natural', '천연', 'ธรรมชาติ', '天然', 'natural', 'natürlich', 'naturel', 'натуральный',
        'handmade', '수제', 'ทำมือ', '手作り', '手工', 'hecho a mano', 'handgemacht', 'fait main', 'ручной работы',
        'gel', '젤', 'เจล', 'ジェル', '凝胶', 'gel', 'гель',
        'shampoo', '샴푸', 'แชมพู', 'シャンプー', '洗发水', 'champú', 'шампунь',
        'gift', 'set', '선물', '세트', 'ของขวัญ', 'เซ็ต', 'ギフト', 'セット', '礼物', '套装', 'regalo', 'conjunto', 'geschenk', 'set', 'cadeau', 'ensemble', 'подарок', 'набор',
        '100g', '150g', '185g', '500ml', '250ml', '25ml'
    ],
    'purchase_intent': [
        'price', 'prices', 'price list', 'cost', 'how much', 'pricing', 'rate', 'fee', 'buy', 'purchase',
        '가격', '비누 가격', '팬시비누 가격', '비누가격', '얼마', '값', '요금', '비용', '구매', '살래',
        'ราคา', 'สบู่ราคา', 'ราคาสบู่', 'เท่าไหร่', 'เท่าไร', 'ค่า', 'ค่าใช้จ่าย',
        '価格', '値段', 'いくら', '料金', 'コスト', 'プライス',
        '价格', '价钱', '多少钱', '费用', '成本', '定价',
        'precio', 'precios', 'costo', 'cuanto', 'tarifa',
        'preis', 'preise', 'kosten', 'wie viel', 'gebühr',
        'prix', 'coût', 'combien', 'tarif',
        'цена', 'цены', 'стоимость', 'сколько'
    ],
    'list_intent': [
        'list', 'show me', 'types', 'kinds', 'available', 'what do you have', 'what products',
        'looking for', 'search', 'find', 'sell',
        '목록', '리스트', '종류', '뭐있어', '뭐', '뭘', '무엇', '어떤', '있어', '있나', '품목',
        '보여줘', '알려줘', '찾', '파나', '팔아',
        'สินค้า', 'ผลิตภัณฑ์', 'มีอะไร', 'ขาย', 'หา', 'ค้นหา', 'อะไร', 'ชนิด', 'ประเภท', 'รายการ',
        '商品', '製品', '何', 'なに', '探', 'さが', 'ある', 'あります', 'リスト',
        '产品', '商品', '什么', '哪些', '种类', '类型', '有什么', '列表', '寻找', '搜索',
        'que', 'tipos', 'was', 'welche', 'arten', 'quoi', 'types', 'что', 'какие'
    ],
    'feature_intent': [
        '특징', '방법', '성분', '차이', '어떻게', '왜', '장점', '단점', '사용법', '효과',
        'feature', 'how to', 'ingredient', 'difference', 'what is', 'why', 'benefit', 'use',
        'คุณสมบัติ', 'วิธีใช้', 'ส่วนผสม', 'ความแตกต่าง', 'ทำไม', 'ประโยชน์',
        '특성', '설명', '어떤', '무엇인', '구성', '장단점'
    ]
}

# 🔥 포괄적인 다국어 제품명 매핑 테이블
PRODUCT_NAME_MAPPING = {
    # 페퍼민트/민트 관련 (7개 언어)
    '페퍼민트': 'peppermint', '민트': 'peppermint', '멘톨': 'peppermint',  # 한국어
    'เปปเปอร์มินต์': 'peppermint', 'มินต์': 'peppermint', 'เมนทอล': 'peppermint',  # 태국어
    'ペパーミント': 'peppermint', 'ミント': 'peppermint',  # 일본어
    '薄荷': 'peppermint', '薄荷糖': 'peppermint',  # 중국어
    'menta': 'peppermint', 'mentol': 'peppermint',  # 스페인어
    'minze': 'peppermint', 'pfefferminz': 'peppermint',  # 독일어
    'menthe': 'peppermint', 'menthol': 'peppermint',  # 프랑스어
    
    # 망고 관련 (7개 언어)
    '망고': 'mango',  # 한국어
    'มะม่วง': 'mango',  # 태국어
    'マンゴー': 'mango',  # 일본어
    '芒果': 'mango',  # 중국어
    'манго': 'mango',  # 러시아어
    
    # 바나나 관련 (7개 언어)
    '바나나': 'banana',  # 한국어
    'กล้วย': 'banana',  # 태국어
    'バナナ': 'banana',  # 일본어
    '香蕉': 'banana',  # 중국어
    'plátano': 'banana',  # 스페인어
    'banane': 'banana',  # 독일어/프랑스어
    'банан': 'banana',  # 러시아어
    
    # 재스민 관련 (7개 언어)
    '재스민': 'jasmine', '자스민': 'jasmine',  # 한국어
    'ดอกมะลิ': 'jasmine', 'มะลิ': 'jasmine',  # 태국어
    'ジャスミン': 'jasmine',  # 일본어
    '茉莉花': 'jasmine', '茉莉': 'jasmine',  # 중국어
    'jazmín': 'jasmine',  # 스페인어
    'jasmin': 'jasmine',  # 독일어/프랑스어
    'жасмин': 'jasmine',  # 러시아어
    
    # 라벤더 관련 (7개 언어)
    '라벤더': 'lavender',  # 한국어
    'ลาเวนเดอร์': 'lavender',  # 태국어
    'ラベンダー': 'lavender',  # 일본어
    '薰衣草': 'lavender',  # 중국어
    'lavanda': 'lavender',  # 스페인어
    'lavendel': 'lavender',  # 독일어
    'lavande': 'lavender',  # 프랑스어
    'лаванда': 'lavender',  # 러시아어
    
    # 장미 관련 (7개 언어)
    '장미': 'rose', '로즈': 'rose',  # 한국어
    'กุหลาบ': 'rose',  # 태국어
    'ローズ': 'rose', 'バラ': 'rose',  # 일본어
    '玫瑰': 'rose',  # 중국어
    'rosa': 'rose',  # 스페인어
    'rose': 'rose',  # 독일어/프랑스어/영어
    'роза': 'rose',  # 러시아어
    
    # 코끼리 관련 (7개 언어)
    '코끼리': 'elephant',  # 한국어
    'ช้าง': 'elephant',  # 태국어
    'ゾウ': 'elephant',  # 일본어
    '大象': 'elephant',  # 중국어
    'elefante': 'elephant',  # 스페인어
    'elefant': 'elephant',  # 독일어
    'éléphant': 'elephant',  # 프랑스어
    'слон': 'elephant',  # 러시아어
    
    # 오리 관련 (7개 언어)
    '오리': 'duck',  # 한국어
    'เป็ด': 'duck',  # 태국어
    'アヒル': 'duck', 'カモ': 'duck',  # 일본어
    '鸭子': 'duck',  # 중국어
    'pato': 'duck',  # 스페인어
    'ente': 'duck',  # 독일어
    'canard': 'duck',  # 프랑스어
    'утка': 'duck',  # 러시아어
    
    # 곰 관련 (7개 언어)
    '곰': 'bear', '베어': 'bear',  # 한국어
    'หมี': 'bear',  # 태국어
    'クマ': 'bear',  # 일본어
    '熊': 'bear',  # 중국어
    'oso': 'bear',  # 스페인어
    'bär': 'bear',  # 독일어
    'ours': 'bear',  # 프랑스어
    'медведь': 'bear',  # 러시아어
    
    # 공룡 관련 (7개 언어)
    '공룡': 'dinosaur', '다이노소어': 'dinosaur',  # 한국어
    'ไดโนเสาร์': 'dinosaur',  # 태국어
    '恐竜': 'dinosaur',  # 일본어
    '恐龙': 'dinosaur',  # 중국어
    'dinosaurio': 'dinosaur',  # 스페인어
    'dinosaurier': 'dinosaur',  # 독일어
    'dinosaure': 'dinosaur',  # 프랑스어
    'динозавр': 'dinosaur',  # 러시아어
    
    # 비누 관련 (7개 언어)
    '비누': 'soap', '소프': 'soap',  # 한국어
    'สบู่': 'soap',  # 태국어
    '石鹸': 'soap', 'ソープ': 'soap',  # 일본어
    '肥皂': 'soap',  # 중국어
    'jabón': 'soap',  # 스페인어
    'seife': 'soap',  # 독일어
    'savon': 'soap',  # 프랑스어
    'мыло': 'soap',  # 러시아어
    
    # 배스봄 관련 (7개 언어)
    '배스봄': 'bathbomb', '바스봄': 'bathbomb', '목욕폭탄': 'bathbomb',  # 한국어
    'บาธบอม': 'bathbomb', 'บอมอาบน้ำ': 'bathbomb',  # 태국어
    'バスボム': 'bathbomb',  # 일본어
    '泡澡球': 'bathbomb', '沐浴球': 'bathbomb',  # 중국어
    'bomba de baño': 'bathbomb',  # 스페인어
    'badebombe': 'bathbomb',  # 독일어
    'bombe de bain': 'bathbomb',  # 프랑스어
    
    # 스크럽 관련 (7개 언어)
    '스크럽': 'scrub', '각질제거': 'scrub',  # 한국어
    'สครับ': 'scrub',  # 태국어
    'スクラブ': 'scrub',  # 일본어
    '磨砂膏': 'scrub',  # 중국어
    'exfoliante': 'scrub',  # 스페인어
    'peeling': 'scrub',  # 독일어
    'gommage': 'scrub',  # 프랑스어
    
    # 향수/스프레이 관련
    '향수': 'perfume', '퍼퓨': 'perfume',  # 한국어
    'น้ำหอม': 'perfume',  # 태국어
    '香水': 'perfume',  # 일본어/중국어
    'perfume': 'perfume',  # 스페인어/프랑스어
    'parfüm': 'perfume',  # 독일어
    'духи': 'perfume',  # 러시아어
    
    '스프레이': 'spray', '분무기': 'spray',  # 한국어
    'สเปรย์': 'spray',  # 태국어
    'スプレー': 'spray',  # 일본어
    '喷雾': 'spray',  # 중국어
    'aerosol': 'spray',  # 스페인어
    'spray': 'spray',  # 독일어/프랑스어/영어
}

# "더 자세한 정보" 요청 키워드 감지
MORE_INFO_KEYWORDS = {
    'thai': ['รายละเอียดเพิ่มเติม', 'ข้อมูลเพิ่มเติม', 'อธิบายเพิ่ม', 'บอกเพิ่ม', 'เพิ่มเติม', 'รายละเอียด'],
    'korean': ['자세한 설명', '더 알려주세요', '상세한 설명', '자세히', '더 자세히', '추가 설명', '더 설명'],
    'japanese': ['詳しく教えて', 'もっと詳しく', '詳細を教えて', '詳しい説明', '追加説明', '詳細'],
    'chinese': ['详细说明', '更多信息', '详细信息', '更详细', '详细一点', '具体说明'],
    'english': ['more details', 'tell me more', 'more information', 'detailed explanation', 'explain more', 'additional details'],
    'spanish': ['más detalles', 'cuéntame más', 'más información', 'explicación detallada', 'explica más'],
    'german': ['mehr details', 'erzählen sie mir mehr', 'mehr informationen', 'detaillierte erklärung'],
    'french': ['plus de détails', 'dites-moi plus', 'plus d\'informations', 'explication détaillée'],
    'vietnamese': ['chi tiết hơn', 'cho tôi biết thêm', 'thông tin thêm', 'giải thích chi tiết'],
    'russian': ['подробнее', 'расскажите больше', 'больше информации', 'подробное объяснение']
}

# 🔥 개선된 시스템 메시지 - 정확한 정보 우선
NATURAL_SYSTEM_MESSAGE = """You are a knowledgeable and friendly customer service representative for SABOO THAILAND, a natural soap and bath product company.

CRITICAL RULES:
1. For company-specific information (phone numbers, addresses, store locations, contact details), you MUST use ONLY the exact information provided in the user's prompt under "COMPANY INFORMATION"
2. Do NOT use any phone numbers, addresses, or contact information from your training data
3. For general questions about soaps, skincare, and bath products, you may use your knowledge to be helpful
4. Always reply in the same language as the customer
5. Be warm, helpful, and professional like a real Thai staff member
6. Use light emojis to be friendly but don't overuse them
7. When you don't know specific product details, give general helpful advice and suggest contacting the store

Remember: Company information accuracy is CRITICAL for customer trust! 😊"""

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

# ==============================================================================
# 5. 헬퍼 함수 정의 (Helper Functions)
# ==============================================================================

def process_response_length(text: str, language: str, max_length: int = 500) -> Tuple[str, bool]:
    """
    응답 텍스트 길이를 500자로 체크하고, 초과 시 '...'로 축약합니다.
    """
    try:
        clean_text = re.sub(r'<[^>]+>', '', text)
        if len(clean_text) <= max_length:
            return text, False
        
        # 텍스트가 너무 길면 자르기
        truncated_text = clean_text[:max_length]
        
        # 마지막 단어가 잘리지 않도록 공백에서 자르기
        last_space = truncated_text.rfind(' ')
        if last_space > 0:
            truncated_text = truncated_text[:last_space]

        # 항상 '...' 추가
        truncated_text = truncated_text.strip() + "..."
        
        return truncated_text, True
    except Exception as e:
        logger.error(f"❌ 응답 길이 처리 중 오류: {e}")
        return text, False

def is_more_info_request(user_message: str, detected_language: str) -> bool:
    """사용자가 더 자세한 정보를 요청하는지 확인"""
    try:
        user_message_lower = user_message.lower().strip()
        if detected_language in MORE_INFO_KEYWORDS:
            for keyword in MORE_INFO_KEYWORDS[detected_language]:
                if keyword.lower() in user_message_lower:
                    return True
        for lang_keywords in MORE_INFO_KEYWORDS.values():
            for keyword in lang_keywords:
                if keyword.lower() in user_message_lower:
                    return True
        return False
    except Exception as e:
        logger.error(f"❌ 더 자세한 정보 요청 감지 중 오류: {e}")
        return False

def save_user_context(user_id: str, message: str, response: str, language: str):
    """사용자별 최근 대화 컨텍스트 저장"""
    try:
        if user_id not in user_context_cache:
            user_context_cache[user_id] = []
        
        clean_response = re.sub(r'<[^>]+>', '', response)

        user_context_cache[user_id].append({
            'timestamp': datetime.now(),
            'user_message': message,
            'bot_response': clean_response,
            'language': language
        })
        
        if len(user_context_cache[user_id]) > 3:
            user_context_cache[user_id] = user_context_cache[user_id][-3:]
    except Exception as e:
        logger.error(f"❌ 사용자 컨텍스트 저장 중 오류: {e}")

def get_user_context(user_id: str) -> str:
    """사용자의 최근 대화 컨텍스트 가져오기"""
    try:
        if user_id not in user_context_cache:
            return ""
        context_parts = []
        for ctx in user_context_cache[user_id][-2:]:
            context_parts.append(f"Previous Q: {ctx['user_message']}")
            context_parts.append(f"Previous A: {ctx['bot_response'][:200]}...")
        return "\n".join(context_parts) if context_parts else ""
    except Exception as e:
        logger.error(f"❌ 사용자 컨텍스트 가져오기 중 오류: {e}")
        return ""

def load_product_files():
    """price_list 폴더에서 모든 제품 파일을 로드하여 캐시에 저장"""
    global product_data_cache, product_last_update
    try:
        price_list_dir = "price_list"
        if not os.path.exists(price_list_dir):
            logger.warning(f"⚠️ {price_list_dir} 폴더를 찾을 수 없습니다.")
            return False
        
        product_data_cache.clear()
        
        txt_files = glob.glob(os.path.join(price_list_dir, "*.txt"))
        logger.info(f"📂 {len(txt_files)}개의 제품 파일을 발견했습니다.")
        
        for file_path in txt_files:
            try:
                filename = os.path.basename(file_path)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        product_data_cache[filename] = content
                        logger.debug(f"✅ {filename} 로드 완료 ({len(content)} 문자)")
            except Exception as e:
                logger.error(f"❌ {file_path} 로드 실패: {e}")
        
        product_last_update = datetime.now()
        logger.info(f"✅ 총 {len(product_data_cache)}개의 제품 파일이 캐시에 로드되었습니다.")
        return True
    except Exception as e:
        logger.error(f"❌ 제품 파일 로드 중 오류: {e}")
        return False

def search_products_by_keywords(user_query: str) -> List[Dict[str, Any]]:
    """사용자 쿼리에서 키워드를 추출하여 관련 제품 찾기 (🔥 다국어 매핑 강화)"""
    try:
        user_query_lower = user_query.lower()
        found_products = []
        
        # 의도 분석
        is_price_query = any(keyword in user_query_lower for keyword in INTENT_KEYWORDS['purchase_intent'])
        is_list_query = any(keyword in user_query_lower for keyword in INTENT_KEYWORDS['list_intent'])
        
        if not is_price_query and not is_list_query:
            is_list_query = True
        
        logger.info(f"🎯 쿼리 의도 분석: 가격={is_price_query}, 목록={is_list_query}")
        
        # 🔥 다국어 제품명을 영어로 변환
        translated_query = user_query_lower
        for local_name, english_name in PRODUCT_NAME_MAPPING.items():
            if local_name.lower() in user_query_lower:
                translated_query = translated_query.replace(local_name.lower(), english_name)
                logger.info(f"🌐 제품명 변환: '{local_name}' → '{english_name}'")
        
        query_words = set(re.findall(r'\b\w+\b', translated_query))
        original_words = set(re.findall(r'\b\w+\b', user_query_lower))
        all_search_words = query_words.union(original_words)  # 원본과 번역본 모두 검색
        
        logger.info(f"🔍 검색 키워드: {all_search_words}")

        for filename, content in product_data_cache.items():
            relevance_score = 0
            matched_keywords = []
            filename_lower = filename.lower()

            # 의도에 맞지 않는 파일 타입은 건너뛰기
            if is_price_query and not filename.endswith('_price.txt'):
                continue
            elif is_list_query and not filename.endswith('_list.txt'):
                continue

            # 🔥 개선된 점수 계산 로직
            for keyword in all_search_words:
                if keyword in filename_lower:
                    # 구체적인 제품명이 파일명에 있으면 매우 높은 점수
                    if keyword in ['peppermint', 'mango', 'banana', 'jasmine', 'lavender', 'elephant', 'duck', 'bear', 'dinosaur']:
                        relevance_score += 15  # 구체적 제품명은 높은 점수
                        matched_keywords.append(keyword)
                        logger.info(f"🎯 구체적 제품명 매칭: '{keyword}' in '{filename}'")
                    elif keyword in INTENT_KEYWORDS['product_names']:
                        if keyword not in ['soap', '비누', 'fancy', '팬시']:  # 일반적인 단어가 아닌 경우
                            relevance_score += 10
                        else:
                            relevance_score += 3
                        matched_keywords.append(keyword)
                    else:
                        relevance_score += 1
                
                # 🔥 파일 내용에서도 검색 (추가 보완)
                if keyword in content.lower():
                    relevance_score += 2
                    logger.info(f"📄 파일 내용에서 매칭: '{keyword}' in '{filename}' content")

            if relevance_score > 0:
                found_products.append({
                    'filename': filename,
                    'content': content,
                    'relevance_score': relevance_score,
                    'matched_keywords': list(set(matched_keywords)),
                    'file_type': 'price' if filename.endswith('_price.txt') else 'list'
                })
        
        found_products.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        if found_products:
            logger.info(f"🏆 최고 점수 파일: {found_products[0]['filename']} (점수: {found_products[0]['relevance_score']})")
        else:
            logger.warning(f"❌ '{user_query}'에 대한 제품을 찾지 못했습니다. 사용 가능한 파일: {list(product_data_cache.keys())}")
        
        file_type = 'price' if is_price_query else 'list'
        logger.info(f"🔍 '{user_query}'에 대해 {len(found_products)}개의 {file_type} 파일을 찾았습니다.")
        return found_products[:5]  # 상위 5개만 반환
    except Exception as e:
        logger.error(f"❌ 제품 검색 중 오류: {e}")
        return []

def get_product_info(user_query: str, language: str = 'english', detailed: bool = False) -> str:
    """사용자 쿼리에 맞는 제품 정보를 순수 텍스트로 생성"""
    try:
        found_products = search_products_by_keywords(user_query)
        if not found_products:
            return get_no_products_message(language)
        
        # 가장 관련성 높은 제품 1개의 정보만 반환하여 혼동을 줄임
        top_product = found_products[0]
        
        response_parts = []
        file_type = top_product.get('file_type', 'list')
        
        headers = {
            'price': {
                'thai': "💰 ราคาสินค้าที่ท่านค้นหา:",
                'korean': "💰 찾으시는 제품의 가격 정보입니다:",
                'japanese': "💰 お探しの商品の価格情報:",
                'chinese': "💰 您查找的产品价格信息:",
                'english': "💰 Here is the price information for the product you're looking for:"
            },
            'list': {
                'thai': "🛍️ รายการสินค้าที่ท่านค้นหา:",
                'korean': "🛍️ 찾으시는 제품 목록입니다:",
                'japanese': "🛍️ お探しの商品一覧:",
                'chinese': "🛍️ 您查找的产品列表:",
                'english': "🛍️ Here is the product list you're looking for:"
            }
        }
        response_parts.append(headers[file_type].get(language, headers[file_type]['english']))
        
        filename = top_product['filename']
        content = top_product['content']
        
        if filename.endswith('_list.txt'):
            product_name = extract_product_name(filename.replace('_list.txt', ''))
        elif filename.endswith('_price.txt'):
            product_name = extract_product_name(filename.replace('_price.txt', ''))
        else:
            product_name = extract_product_name(filename)
        
        response_parts.append(f"\n**{product_name}**")
        response_parts.append(f"{content}\n")
        
        contact_info = {
            'thai': "\n📞 สำหรับข้อมูลเพิ่มเติม โทร: 02-159-9880, 085-595-9565",
            'korean': "\n📞 자세한 정보: 02-159-9880, 085-595-9565",
            'japanese': "\n📞 詳細情報: 02-159-9880, 085-595-9565",
            'chinese': "\n📞 更多信息: 02-159-9880, 085-595-9565",
            'english': "\n📞 For more info: 02-159-9880, 085-595-9565"
        }
        response_parts.append(contact_info.get(language, contact_info['english']))
        
        return "\n".join(response_parts)
    except Exception as e:
        logger.error(f"❌ 제품 정보 생성 중 오류: {e}")
        return get_error_message(language)

def extract_product_name(filename: str) -> str:
    """파일명에서 읽기 쉬운 제품명 추출"""
    try:
        name = filename.replace('.txt', '').replace('_', ' ')
        return ' '.join(word.capitalize() for word in name.split())
    except:
        return filename

def get_no_products_message(language: str) -> str:
    """제품을 찾지 못했을 때의 메시지"""
    messages = {
        'thai': "❌ ขออภัยค่ะ ไม่พบผลิตภัณฑ์ที่ตรงกับคำค้นหาของคุณ\n\n🔍 ลองค้นหาด้วยคำอื่น เช่น: สบู่มะม่วง, บาธบอม, สครับ\n📞 หรือติดต่อเราโดยตรง: 02-159-9880",
        'korean': "❌ 죄송합니다. 검색어와 일치하는 제품을 찾을 수 없습니다.\n\n🔍 다른 키워드로 시도해보세요: 망고 비누, 배스봄, 스크럽\n📞 또는 직접 문의: 02-159-9880",
        'japanese': "❌ 申し訳ございません。検索条件に一致する商品が見つかりませんでした。\n\n🔍 他のキーワードでお試しください: マンゴー石鹸、バスボム、スクラブ\n📞 またはお電話で: 02-159-9880",
        'chinese': "❌ 抱歉，没有找到符合搜索条件的产品。\n\n🔍 请尝试其他关键词: 芒果香皂、沐浴球、磨砂膏\n📞 或直接联系: 02-159-9880",
        'english': "❌ Sorry, no products found matching your search.\n\n🔍 Try other keywords like: mango soap, bath bomb, scrub\n📞 Or contact us directly: 02-159-9880"
    }
    return messages.get(language, messages['english'])

def get_error_message(language: str) -> str:
    """오류 발생 시 메시지"""
    messages = {
        'thai': "❌ เกิดข้อผิดพลาดในการค้นหาสินค้า โปรดติดต่อเราโดยตรง: 02-159-9880",
        'korean': "❌ 제품 검색 중 오류가 발생했습니다. 직접 문의해주세요: 02-159-9880",
        'japanese': "❌ 商品検索中にエラーが発生しました。直接お問い合わせください: 02-159-9880",
        'chinese': "❌ 产品搜索时出现错误，请直接联系我们: 02-159-9880",
        'english': "❌ Error occurred while searching products. Please contact us directly: 02-159-9880"
    }
    return messages.get(language, messages['english'])

def is_product_search_query(user_message: str) -> bool:
    """사용자 메시지가 제품 검색 쿼리인지 판단 (개선됨)"""
    try:
        msg_lower = user_message.lower()
        
        # 제품명이 포함되어 있는지 확인
        has_product = any(keyword in msg_lower for keyword in INTENT_KEYWORDS['product_names'])
        if not has_product:
            return False
        
        # 검색 의도가 있는지 확인
        has_search_intent = any(keyword in msg_lower for keyword in 
                               INTENT_KEYWORDS['purchase_intent'] + INTENT_KEYWORDS['list_intent'])
        
        # 특징/설명 질문인지 확인
        is_feature_q = any(keyword in msg_lower for keyword in INTENT_KEYWORDS['feature_intent'])
        
        if is_feature_q:
            logger.info("🎯 의도 분석: 설명 질문 (Q&A 처리)")
            return False
        
        # '가격' 등 검색 의도가 있거나, '망고 비누'처럼 제품명만 짧게 말한 경우
        if has_search_intent or len(msg_lower.split()) <= 3:
            logger.info("🎯 의도 분석: 제품 검색")
            return True
            
        return False
    except Exception as e:
        logger.error(f"❌ 제품 검색 쿼리 판단 중 오류: {e}")
        return False

def format_text_for_messenger(text: str) -> str:
    """웹/메신저용: \n → <br> 로 변환하고 마크다운을 HTML로 변환"""
    try:
        # Markdown Bold/Italic to HTML
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
        # Newlines to <br>
        return text.replace("\n", "<br>")
    except Exception as e:
        logger.error(f"❌ 메신저용 포맷 변환 오류: {e}")
        return text

def format_text_for_line(text: str) -> str:
    """LINE 용: 마크다운 제거, \n → \n\n 로 변환"""
    try:
        # Markdown 제거
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        text = re.sub(r'\*(.*?)\*', r'\1', text)
        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', text)
        # Newlines to double newlines
        return text.replace("\n", "\n\n")
    except Exception as e:
        logger.error(f"❌ LINE용 포맷 변환 오류: {e}")
        return text

def fetch_company_info(user_language: str) -> str:
    """언어별 company_info.txt 파일을 읽어오고, 결과를 캐시에 저장합니다."""
    global language_data_cache
    
    # 캐시 키를 언어별로 구분
    cache_key = f"company_info_{user_language}"
    if cache_key in language_data_cache:
        logger.info(f"📋 캐시된 '{user_language}' 회사 정보를 사용합니다.")
        return language_data_cache[cache_key]

    lang_map = {
        'thai': 'th', 'english': 'en', 'korean': 'kr', 'japanese': 'ja', 
        'german': 'de', 'spanish': 'es', 'arabic': 'ar', 'chinese': 'zh_cn', 
        'taiwanese': 'zh_tw', 'vietnamese': 'vi', 'myanmar': 'my', 
        'khmer': 'km', 'russian': 'ru', 'french': 'fr'
    }
    lang_code = lang_map.get(user_language, 'en')
    filepath = os.path.join("company_info", f"company_info_{lang_code}.txt")

    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if len(content) > 20:
                    logger.info(f"✅ '{user_language}' 회사 정보를 {filepath} 파일에서 성공적으로 로드했습니다.")
                    language_data_cache[cache_key] = content
                    return content
    except Exception as e:
        logger.error(f"❌ {filepath} 파일 로드 중 오류 발생: {e}")

    logger.warning(f"⚠️ {filepath} 파일을 찾을 수 없거나 내용이 비어있습니다. 영어 버전을 시도합니다.")
    try:
        fallback_filepath = os.path.join("company_info", "company_info_en.txt")
        if os.path.exists(fallback_filepath):
            with open(fallback_filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if len(content) > 20:
                    logger.info(f"✅ 영어 버전({fallback_filepath})을 폴백으로 사용합니다.")
                    language_data_cache[cache_key] = content
                    return content
    except Exception as e:
        logger.error(f"❌ {fallback_filepath} 파일 로드 중 오류 발생: {e}")

    logger.warning("⚠️ 모든 파일 로드에 실패하여, 언어별 하드코딩된 기본 정보를 사용합니다.")
    
    # 🔥 언어별 기본 정보 제공
    default_info_by_lang = {
        'korean': """
SABOO THAILAND 회사 정보:

전화: 062-897-8962
공장: https://maps.app.goo.gl/7kXY4zmYWkxWYp5G9
Big C 라차담리: https://maps.app.goo.gl/RXGhSGbh2nYwkMb38
Mixt 짜뚜짝: https://maps.app.goo.gl/6jp92vRAmG4ftzvu7

2008년 설립, 태국 최초 과일 모양 천연 비누 제조회사
20개국 이상 수출, 웹사이트: www.saboothailand.com
""",
        'thai': """
ข้อมูล SABOO THAILAND:

โทรศัพท์: 062-897-8962
โรงงาน: https://maps.app.goo.gl/7kXY4zmYWkxWYp5G9
Big C ราชดำริ: https://maps.app.goo.gl/RXGhSGbh2nYwkMb38
Mixt จตุจักร: https://maps.app.goo.gl/6jp92vRAmG4ftzvu7

ก่อตั้งปี 2008 บริษัทแรกในไทยที่ผลิตสบู่ธรรมชาติรูปผลไม้
ส่งออกไปกว่า 20 ประเทศ เว็บไซต์: www.saboothailand.com
""",
        'english': """
SABOO THAILAND Company Information:

Phone: 062-897-8962
Factory: https://maps.app.goo.gl/7kXY4zmYWkxWYp5G9
Big C Ratchadamri: https://maps.app.goo.gl/RXGhSGbh2nYwkMb38
Mixt Chatuchak: https://maps.app.goo.gl/6jp92vRAmG4ftzvu7

Founded in 2008, Thailand's first natural fruit-shaped soap manufacturer
Exports to over 20 countries, Website: www.saboothailand.com
"""
    }
    
    default_info = default_info_by_lang.get(user_language, default_info_by_lang['english'])
    language_data_cache[cache_key] = default_info
    return default_info

def initialize_data():
    """앱 시작 시 필요한 언어별 데이터와 제품 데이터를 미리 로드합니다."""
    logger.info("🚀 앱 초기화를 시작합니다...")
    if load_product_files():
        logger.info(f"✅ 제품 데이터 로드 완료: {len(product_data_cache)}개 파일")
    else:
        logger.warning("⚠️ 제품 데이터 로드 실패")
    
    common_languages = ['english', 'korean', 'thai', 'japanese', 'chinese', 'spanish', 'german']
    for lang in common_languages:
        try:
            fetch_company_info(lang)
        except Exception as e:
            logger.warning(f"⚠️ {lang} 언어 정보 미리 로드 실패: {e}")
    logger.info(f"✅ 캐시된 언어: {list(language_data_cache.keys())}")

def detect_user_language(message: str) -> str:
    """사용자 메시지에서 언어를 감지합니다."""
    try:
        if re.search(r'[\u0e00-\u0e7f]+', message): return 'thai'
        elif re.search(r'[\uac00-\ud7af]+', message): return 'korean'
        elif re.search(r'[\u3040-\u309f\u30a0-\u30ff]+', message): return 'japanese'
        elif re.search(r'[\u4e00-\u9fff]+', message):
            return 'japanese' if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', message) else 'chinese'
        elif re.search(r'[\u0600-\u06ff]+', message): return 'arabic'
        elif re.search(r'[\u0401\u0451\u0410-\u044f]+', message): return 'russian'
        elif re.search(r'[àâäéèêëïîôùûüÿç]+', message.lower()): return 'french'
        elif re.search(r'[àáâãçéêíóôõú]+', message.lower()): return 'spanish'
        elif re.search(r'[äöüß]+', message.lower()): return 'german'
        elif re.search(r'[ăâđêôơưàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụ]+', message.lower()): return 'vietnamese'
        return 'english'
    except Exception as e:
        logger.error(f"❌ 언어 감지 중 오류 발생: {e}")
        return 'english'

def get_english_fallback_response(user_message, error_context=""):
    """문제 발생 시 영어로 된 기본 응답을 생성합니다."""
    logger.warning(f"⚠️ 폴백 응답을 활성화합니다. 원인: {error_context}")
    
    base_info = """I apologize, but we're experiencing technical difficulties at the moment. 

Here's some basic information about SABOO THAILAND:
- We're Thailand's first natural fruit-shaped soap manufacturer since 2008
- Store location: Mixt Chatuchak, 2nd Floor, Bangkok
- Phone: 02-159-9880, 085-595-9565
- Website: www.saboothailand.com
- Shopee: shopee.co.th/thailandsoap

Please try again later or contact us directly. Thank you for your understanding! 😊"""

    if not client:
        return base_info
    
    try:
        prompt = f"""
The user asked: "{user_message}"
There was a technical issue: {error_context}
Please provide a helpful response in English using basic company information."""
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": ENGLISH_FALLBACK_MESSAGE},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600, temperature=0.7, timeout=20
        )
        response_text = completion.choices[0].message.content.strip()
        
        if error_context:
            response_text += "\n\n(Note: We're currently experiencing some technical issues with our data system, but I'm happy to help with basic information about SABOO THAILAND.)"
        return response_text
    except Exception as e:
        logger.error(f"❌ 폴백 응답 생성 중에도 오류 발생: {e}")
        return base_info

def add_hyperlinks(text: str) -> str:
    """[웹 전용] 응답 텍스트에 포함된 전화번호와 URL을 클릭 가능한 HTML 링크로 변환합니다."""
    try:
        # 전화번호 링크 변환 (한국 스타일 포함)
        text = re.sub(r'\b(0\d{1,2}-\d{3,4}-\d{4})\b', r'<a href="tel:\1" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        text = re.sub(r'\b(0\d{9,10})\b', r'<a href="tel:\1" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        # URL 링크 변환 (http/https)
        text = re.sub(r'(https?://[^\s<>"\']+)', r'<a href="\1" target="_blank" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        # URL 링크 변환 (www. 시작) - http가 없는 경우
        text = re.sub(r'\b(www\.[a-zA-Z0-9-]+\.(com|co\.th|net|org|co\.kr)[^\s<>"\']*)', r'<a href="https://\1" target="_blank" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        return text
    except Exception as e:
        logger.error(f"❌ 하이퍼링크 변환 중 오류 발생: {e}")
        return text

# 🔥 핵심 개선: 자연스러운 GPT 응답 생성 함수
def get_gpt_response(user_message, user_id="anonymous"):
    """
    핵심 응답 생성 함수.
    언어 감지, 제품 검색, GPT 호출을 통해 순수 '텍스트' 응답을 생성합니다.
    """
    user_language = detect_user_language(user_message)
    logger.info(f"🌐 감지된 사용자 언어: {user_language}")

    try:
        if not client:
            logger.error("❌ OpenAI client가 없습니다.")
            return get_english_fallback_response(user_message, "OpenAI service unavailable")

        # 1. 제품 검색 쿼리인지 먼저 확인
        if is_product_search_query(user_message):
            logger.info("🔍 제품 검색 쿼리로 감지되었습니다.")
            product_info = get_product_info(user_message, user_language)
            # 제품 정보는 길이 제한 없이 그대로 반환
            save_user_context(user_id, user_message, product_info, user_language)
            return product_info

        # 2. '더 자세한 정보' 요청 처리
        if is_more_info_request(user_message, user_language):
            logger.info("📋 더 자세한 정보 요청으로 감지되었습니다.")
            user_context = get_user_context(user_id)
            if user_context:
                prompt = f"""[Previous Conversation Context]
{user_context}

[Current Request]
The user is asking for more details with the phrase: "{user_message}"

Based on the previous context, please provide a more detailed and specific explanation in the user's language ({user_language})."""
                
                completion = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": NATURAL_SYSTEM_MESSAGE},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1000, temperature=0.7, timeout=25
                )
                detailed_response = completion.choices[0].message.content.strip()
                save_user_context(user_id, user_message, detailed_response, user_language)
                return detailed_response

        # 🔥 3. 일반적인 대화 처리 - 언어별 정확한 정보 사용
        company_info = fetch_company_info(user_language)
        if not company_info or len(company_info.strip()) < 50:
            logger.warning("⚠️ 회사 정보가 불충분합니다. 폴백을 사용합니다.")
            return get_english_fallback_response(user_message, "Company data temporarily unavailable")
        
        user_context = get_user_context(user_id)
        context_section = f"\n\n[Previous Conversation Context]\n{user_context}" if user_context else ""
        
        # 🔥 개선된 프롬프트 - 언어별 정확한 정보 우선, 일반 지식 보완
        prompt = f"""You are a friendly and professional customer service agent for SABOO THAILAND.

[COMPANY INFORMATION FOR {user_language.upper()} - THIS IS YOUR PRIMARY SOURCE OF TRUTH]
{company_info}

CRITICAL RULES - READ CAREFULLY:
1. For company-specific questions (store locations, phone numbers, addresses, contact info), you MUST use ONLY the exact information provided in the COMPANY INFORMATION section above.
2. The company information above is specifically for {user_language} language users - use it exactly as written, including all phone numbers, addresses, and links.
3. NEVER use these numbers: 02-159-9880, 085-595-9565 - they are outdated and incorrect.
4. NEVER use any phone numbers, addresses, or contact information from your training data.
5. For general questions about soaps, skincare, and bath products, you may use your general knowledge to be helpful.
6. Always answer in {user_language} language.
7. Be warm and helpful like a real Thai staff member.
8. Use light emojis 😊 for a friendly touch.
9. If the COMPANY INFORMATION doesn't contain specific product details, give general advice and suggest contacting us using the phone number provided in the COMPANY INFORMATION above.

{context_section}

Customer question: {user_message}"""

        logger.info(f"🌐 '{user_language}' 언어용 회사 정보를 사용하여 GPT 프롬프트 생성 완료")
        
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": NATURAL_SYSTEM_MESSAGE},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800, 
            temperature=0.7,  # 더 자연스러운 응답을 위해 0.3 → 0.7로 증가
            timeout=25
        )
        response_text = completion.choices[0].message.content.strip()

        if not response_text or len(response_text.strip()) < 10:
            logger.warning("⚠️ 생성된 응답이 너무 짧습니다. 폴백을 사용합니다.")
            return get_english_fallback_response(user_message, "Response generation issue")

        processed_response, is_truncated = process_response_length(response_text, user_language)
        save_user_context(user_id, user_message, response_text, user_language)
        
        logger.info(f"✅ '{user_language}' 언어로 GPT 응답을 성공적으로 생성했습니다. (축약됨: {is_truncated})")
        return processed_response
    except Exception as e:
        logger.error(f"❌ GPT 응답 생성 중 오류 발생: {e}")
        return get_english_fallback_response(user_message, f"GPT API error: {str(e)[:100]}")

def save_chat(user_msg, bot_msg, user_id="anonymous"):
    """대화 내용을 날짜별 텍스트 파일로 저장합니다. (HTML 태그 없이)"""
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
    detected_lang = detect_user_language(user_msg)
    
    try:
        clean_bot_msg = re.sub(r'<[^>]+>', '', bot_msg)
        
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] User ({user_id}) [{detected_lang}]: {user_msg}\n")
            f.write(f"[{timestamp}] Bot: {clean_bot_msg}\n")
            f.write("-" * 50 + "\n")
        logger.info(f"💬 채팅 로그를 '{full_path}' 파일에 저장했습니다.")
    except Exception as e:
        logger.error(f"❌ 로그 파일 '{full_path}' 저장 실패: {e}")

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

def send_line_message(reply_token, message):
    """LINE API로 메시지 전송"""
    try:
        if not LINE_TOKEN:
            logger.error("❌ LINE_TOKEN이 없습니다.")
            return False
        
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": message}]}
        
        response = requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers, json=payload, timeout=10
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

def initialize_once():
    """첫 번째 요청이 들어왔을 때 딱 한 번만 앱 초기화를 실행합니다."""
    global app_initialized
    if not app_initialized:
        with threading.Lock():
            if not app_initialized:
                logger.info("🎯 첫 요청 감지, 앱 초기화를 진행합니다...")
                initialize_data()
                app_initialized = True

def check_admin_access():
    """관리자 엔드포인트 접근 권한 확인"""
    if not ADMIN_API_KEY:
        return True
    return request.headers.get('X-Admin-API-Key') == ADMIN_API_KEY

# ==============================================================================
# 6. Flask 라우트 및 데코레이터 (Routes & Decorators)
# ==============================================================================
@app.before_request
def before_request():
    """요청 전 처리 - 관리자 엔드포인트 보안 및 초기화"""
    admin_endpoints = ['/reload-products', '/reload-language-data', '/clear-language-cache']
    if request.path in admin_endpoints:
        if not check_admin_access():
            return jsonify({
                "error": "Unauthorized access to admin endpoint",
                "message": "X-Admin-API-Key header required"
            }), 403
    initialize_once()

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
        "admin_security": "enabled" if ADMIN_API_KEY else "disabled",
        "cached_languages": list(language_data_cache.keys()),
        "product_files_loaded": len(product_data_cache),
        "product_last_update": product_last_update.isoformat() if product_last_update else None,
        "user_context_cache_size": len(user_context_cache)
    })

@app.route('/products')
def products_status():
    """제품 데이터 상태 확인"""
    return jsonify({
        "total_product_files": len(product_data_cache),
        "product_files": list(product_data_cache.keys()),
        "last_update": product_last_update.isoformat() if product_last_update else None,
        "price_list_folder_exists": os.path.exists("price_list"),
        "sample_keywords": dict(list(INTENT_KEYWORDS.items())[:3]),
        "more_info_keywords_count": {lang: len(keywords) for lang, keywords in MORE_INFO_KEYWORDS.items()}
    })

@app.route('/search-products')
def search_products_endpoint():
    """제품 검색 테스트 엔드포인트"""
    query = request.args.get('q', '')
    if not query:
        return jsonify({"error": "검색어를 입력해주세요 (q 파라미터)"}), 400
    found_products = search_products_by_keywords(query)
    result = {
        "query": query,
        "found_count": len(found_products),
        "products": []
    }
    for product in found_products:
        result["products"].append({
            "filename": product['filename'],
            "product_name": extract_product_name(product['filename']),
            "relevance_score": product['relevance_score'],
            "matched_keywords": product['matched_keywords'],
            "content_preview": product['content'][:200] + "..."
        })
    return jsonify(result)

@app.route('/reload-products')
def reload_products():
    """제품 데이터 다시 로드"""
    if load_product_files():
        return jsonify({
            "status": "success", 
            "message": "제품 데이터가 성공적으로 다시 로드되었습니다.", 
            "loaded_files": len(product_data_cache), 
            "timestamp": datetime.now().isoformat()
        })
    else:
        return jsonify({"status": "error", "message": "제품 데이터 로드에 실패했습니다."}), 500

@app.route('/clear-language-cache')
def clear_language_cache():
    """언어별 캐시 및 사용자 컨텍스트 초기화"""
    global language_data_cache, user_context_cache
    old_cache_size = len(language_data_cache)
    old_context_size = len(user_context_cache)
    language_data_cache.clear()
    user_context_cache.clear()
    return jsonify({
        "status": "success",
        "message": f"Caches cleared. Removed {old_cache_size} language entries and {old_context_size} user contexts.",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/reload-language-data')
def reload_language_data():
    """언어별 데이터 다시 로드 (초기화 함수 호출)"""
    global language_data_cache
    language_data_cache.clear()
    initialize_data()
    return jsonify({
        "status": "success",
        "message": "All data reloaded successfully.",
        "cached_languages": list(language_data_cache.keys()),
        "product_files": len(product_data_cache),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/chat', methods=['POST'])
def chat():
    """
    [웹 UI 전용] 메시지를 받아 처리하고 HTML 형식의 응답을 반환합니다.
    """
    try:
        user_message = request.json.get('message', '').strip()
        user_id = request.json.get('user_id', 'web_user')
        if not user_message:
            return jsonify({"error": "Empty message."}), 400

        bot_response = get_gpt_response(user_message, user_id)
        
        save_chat(user_message, bot_response, user_id)

        formatted_html = format_text_for_messenger(bot_response)
        response_with_links = add_hyperlinks(formatted_html)
        
        return jsonify({"reply": response_with_links, "is_html": True})

    except Exception as e:
        logger.error(f"❌ /chat 엔드포인트에서 오류 발생: {e}")
        fallback_text = get_english_fallback_response("general inquiry", f"Web chat system error: {str(e)[:100]}")
        
        formatted_fallback = format_text_for_messenger(fallback_text)
        final_fallback_html = add_hyperlinks(formatted_fallback)
        
        return jsonify({"reply": final_fallback_html, "is_html": True, "error": "fallback_mode"})

@app.route('/line', methods=['POST'])
def line_webhook():
    """
    [LINE 플랫폼 전용] 웹훅 이벤트를 처리합니다.
    """
    try:
        body = request.get_data(as_text=True)
        signature = request.headers.get('X-Line-Signature', '')
        
        if not verify_line_signature(body.encode('utf-8'), signature):
            logger.warning("⚠️ 잘못된 서명입니다.")
            return "OK", 200

        webhook_data = json.loads(body)
        for event in webhook_data.get("events", []):
            if event.get("type") == "message" and event.get("message", {}).get("type") == "text":
                user_text = event["message"]["text"].strip()
                reply_token = event["replyToken"]
                user_id = event.get("source", {}).get("userId", "unknown")
                
                detected_language = detect_user_language(user_text)
                logger.info(f"👤 LINE 사용자 {user_id[:8]} ({detected_language}): {user_text}")
                
                welcome_keywords = ["สวัสดี", "หวัดดี", "hello", "hi", "สวัสดีค่ะ", "สวัสดีครับ", "ดีจ้า", "เริ่ม", "안녕하세요", "안녕", "こんにちは", "你好", "नमस्ते"]
                
                if user_text.lower() in [k.lower() for k in welcome_keywords]:
                    responses = {
                        'thai': "สวัสดีค่ะ! 💕 ยินดีต้อนรับสู่ SABOO THAILAND ค่ะ\n\nมีอะไรให้ดิฉันช่วยเหลือคะ? 😊",
                        'korean': "안녕하세요! 💕 SABOO THAILAND에 오신 것을 환영합니다!\n\n무엇을 도와드릴까요? 😊",
                        'japanese': "こんにちは！💕 SABOO THAILANDへようこそ！\n\n何かお手伝いできることはありますか？😊",
                        'chinese': "您好！💕 欢迎来到 SABOO THAILAND！\n\n有什么可以帮您的吗？😊",
                        'english': "Hello! 💕 Welcome to SABOO THAILAND!\n\nHow can I help you today? 😊"
                    }
                    response_text = responses.get(detected_language, responses['english'])
                else:
                    response_text = get_gpt_response(user_text, user_id)

                formatted_for_line = format_text_for_line(response_text)

                if send_line_message(reply_token, formatted_for_line):
                    save_chat(user_text, formatted_for_line, user_id)
        return "OK", 200
    except Exception as e:
        logger.error(f"❌ LINE 웹훅 처리 중 심각한 오류 발생: {e}")
        import traceback
        logger.error(f"❌ 전체 트레이스백: {traceback.format_exc()}")
        return "Error", 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"❌ 내부 서버 오류: {error}")
    return jsonify({"error": "Server error"}), 500

# ==============================================================================
# 7. 앱 실행 (App Execution)
# ==============================================================================
if __name__ == '__main__':
    if not os.getenv('RAILWAY_ENVIRONMENT'):
        logger.info("🚀 개발 모드이므로 직접 초기화를 실행합니다...")
        initialize_data()
        app_initialized = True
    
    port = int(os.environ.get("PORT", 5000))
    debug_mode = not os.getenv('RAILWAY_ENVIRONMENT')
    
    logger.info(f"🚀 Flask 서버를 포트 {port}에서 시작합니다. (디버그 모드: {debug_mode})")
    logger.info("📂 데이터 소스: company_info 폴더 + price_list 폴더 개별 파일 검색")
    logger.info("📏 응답 길이 제어: 긴 답변 자동 축약 (500자)")
    logger.info("🧠 대화 컨텍스트: 사용자별 최근 대화 기억")
    logger.info("🎯 개선된 질문 의도 파악: 제품 검색 vs 일반 Q&A 정확히 구분")
    logger.info("✨ 새로운 기능: 자연스러운 GPT 응답 (제한 없는 일반 상식 활용)")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=not debug_mode)
    except KeyboardInterrupt:
        logger.info("🛑 서버 종료 요청을 받았습니다.")
    except Exception as e:
        logger.error(f"❌ 서버 실행 중 오류 발생: {e}")
    finally:
        logger.info("🔚 서버가 정상적으로 종료되었습니다.")