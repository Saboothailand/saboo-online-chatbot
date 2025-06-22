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
import glob
from typing import Dict, List, Tuple, Optional

# ✅ 제품 데이터 캐시 추가
product_data_cache = {}
product_last_update = None

# ✅ 제품 검색을 위한 키워드 매핑
PRODUCT_KEYWORDS = {
    # Bath Bombs
    'bathbomb': ['bath bomb', 'bathbomb', '배스봄', '바스봄', 'บาธบอม', 'บอม', 'ลูกบอลอาบน้ำ'],
    'bubble': ['bubble', '버블', 'บับเบิล', 'ฟอง'],
    'fizzy': ['fizzy', '피지', 'ฟิซซี่', 'ฟิซ'],
    
    # Soap Types
    'soap': ['soap', '비누', 'สบู่'],
    'fancy': ['fancy', '팬시', 'แฟนซี'],
    'natural': ['natural', '천연', 'ธรรมชาติ'],
    'handmade': ['handmade', '수제', 'ทำมือ'],
    
    # Shapes
    'fruit': ['fruit', '과일', 'ผลไม้'],
    'flower': ['flower', '꽃', 'ดอกไม้'],
    'animal': ['animal', '동물', 'สัตว์'],
    'dinosaur': ['dinosaur', '공룡', 'ไดโนเสาร์'],
    'elephant': ['elephant', '코끼리', 'ช้าง'],
    'duck': ['duck', '오리', 'เป็ด'],
    'bear': ['bear', '곰', 'หมี'],
    
    # Other Products
    'scrub': ['scrub', '스크럽', 'สครับ'],
    'perfume': ['perfume', '향수', 'น้ำหอม'],
    'spray': ['spray', '스프레이', 'สเปรย์'],
    'gel': ['gel', '젤', 'เจล'],
    'gift': ['gift', 'set', '선물', '세트', 'ของขวัญ', 'เซ็ต'],
    
    # Price keywords - 가격 관련 키워드도 제품 검색에 포함
    'price': ['price', 'prices', 'price list', 'cost', 'how much', 'pricing', 'rate', 'fee',
             '가격', '비누 가격', '팬시비누 가격', '비누가격', '얼마', '값', '요금', '비용',
             'ราคา', 'สบู่ราคา', 'ราคาสบู่', 'เท่าไหร่', 'เท่าไร', 'ค่า', 'ค่าใช้จ่าย',
             '価格', '値段', 'いくら', '料金', 'コスト', 'プライス',
             '价格', '价钱', '多少钱', '费用', '成本', '定价',
             'precio', 'precios', 'costo', 'cuanto', 'tarifa',
             'preis', 'preise', 'kosten', 'wie viel', 'gebühr',
             'prix', 'coût', 'combien', 'tarif',
             'цена', 'цены', 'стоимость', 'сколько'],
    
    # Sizes
    '100g': ['100g', '100 g', '100gram'],
    '150g': ['150g', '150 g', '150gram'],
    '185g': ['185g', '185 g', '185gram'],
    '500ml': ['500ml', '500 ml'],
    '250ml': ['250ml', '250 ml'],
    '25ml': ['25ml', '25 ml']
}

# ✅ 제품 파일 로더 함수들
def load_product_files():
    """price_list 폴더에서 모든 제품 파일을 로드하여 캐시에 저장"""
    global product_data_cache, product_last_update
    
    try:
        price_list_dir = "price_list"
        if not os.path.exists(price_list_dir):
            logger.warning(f"⚠️ {price_list_dir} 폴더를 찾을 수 없습니다.")
            return False
        
        product_data_cache.clear()
        
        # 모든 .txt 파일 찾기
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

def search_products_by_keywords(user_query: str) -> List[Dict]:
    """사용자 쿼리에서 키워드를 추출하여 관련 제품 찾기 (쿼리 의도에 따라 list/price 필터링)"""
    try:
        user_query_lower = user_query.lower()
        found_products = []
        
        # 1. 사용자 쿼리 의도 분석
        price_intent_keywords = [
            # 한국어
            '가격', '얼마', '값', '요금', '비용', '돈', '원', '바트',
            # 영어  
            'price', 'cost', 'how much', 'pricing', 'rate', 'fee', 'baht', 'dollar',
            # 태국어
            'ราคา', 'เท่าไหร่', 'เท่าไร', 'ค่า', 'ค่าใช้จ่าย', 'บาท',
            # 일본어
            '価格', '値段', 'いくら', '料金', 'コスト', '円',
            # 중국어
            '价格', '价钱', '多少钱', '费用', '成本', '元',
            # 기타 언어
            'precio', 'precios', 'costo', 'cuanto', 'preis', 'kosten', 'prix', 'цена'
        ]
        
        list_intent_keywords = [
            # 한국어
            '어떤', '뭐', '뭘', '무엇', '종류', '있어', '있나', '품목', '목록', '리스트',
            # 영어
            'what', 'which', 'types', 'kinds', 'available', 'have', 'list', 'products', 'items',
            # 태국어  
            'อะไร', 'มีอะไร', 'ชนิด', 'ประเภท', 'รายการ', 'สินค้า',
            # 일본어
            '何', 'なに', '種類', 'タイプ', 'ある', 'あります', 'リスト',
            # 중국어
            '什么', '哪些', '种类', '类型', '有什么', '列表',
            # 기타 언어
            'que', 'tipos', 'was', 'welche', 'arten', 'quoi', 'types', 'что', 'какие'
        ]
        
        # 의도 판별
        is_price_query = any(keyword in user_query_lower for keyword in price_intent_keywords)
        is_list_query = any(keyword in user_query_lower for keyword in list_intent_keywords)
        
        # 기본값: 가격과 목록 키워드가 모두 없으면 목록으로 간주
        if not is_price_query and not is_list_query:
            is_list_query = True
        
        logger.info(f"🎯 쿼리 의도 분석: 가격={is_price_query}, 목록={is_list_query}")
        
        # 2. 각 제품 파일명과 사용자 쿼리 매칭
        for filename, content in product_data_cache.items():
            relevance_score = 0
            matched_keywords = []
            
            # 파일 타입 필터링
            if is_price_query and not filename.endswith('_price.txt'):
                continue  # 가격 쿼리인데 price 파일이 아니면 건너뛰기
            elif is_list_query and not filename.endswith('_list.txt'):
                continue  # 목록 쿼리인데 list 파일이 아니면 건너뛰기
            
            filename_lower = filename.lower()
            
            # 키워드 매칭 (가격/목록 키워드 제외하고 제품 관련 키워드만)
            for category, keywords in PRODUCT_KEYWORDS.items():
                if category == 'price':  # 가격 키워드는 매칭에서 제외
                    continue
                    
                for keyword in keywords:
                    if keyword.lower() in user_query_lower:
                        if category in filename_lower or any(k in filename_lower for k in keywords):
                            relevance_score += 2
                            matched_keywords.append(keyword)
                    
                    if keyword.lower() in filename_lower and keyword.lower() in user_query_lower:
                        relevance_score += 3
            
            # 직접적인 단어 매칭 (가격/목록 키워드 제외)
            query_words = [word for word in user_query_lower.split() 
                          if word not in price_intent_keywords + list_intent_keywords]
            
            for word in query_words:
                if len(word) > 2 and word in filename_lower:
                    relevance_score += 1
                    matched_keywords.append(word)
            
            if relevance_score > 0:
                found_products.append({
                    'filename': filename,
                    'content': content,
                    'relevance_score': relevance_score,
                    'matched_keywords': matched_keywords,
                    'file_type': 'price' if filename.endswith('_price.txt') else 'list'
                })
        
        # 관련도 순으로 정렬
        found_products.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        file_type = 'price' if is_price_query else 'list'
        logger.info(f"🔍 '{user_query}'에 대해 {len(found_products)}개의 {file_type} 파일을 찾았습니다.")
        return found_products[:10]  # 상위 10개만 반환
        
    except Exception as e:
        logger.error(f"❌ 제품 검색 중 오류: {e}")
        return []

def get_product_info(user_query: str, language: str = 'english') -> str:
    """사용자 쿼리에 맞는 제품 정보 생성 (의도에 따라 list 또는 price만 표시)"""
    try:
        # 제품 검색
        found_products = search_products_by_keywords(user_query)
        
        if not found_products:
            return get_no_products_message(language)
        
        # 결과 포맷팅
        response_parts = []
        
        # 파일 타입 확인 (첫 번째 결과로 판단)
        file_type = found_products[0].get('file_type', 'list')
        
        # 언어별 헤더
        if file_type == 'price':
            if language == 'thai':
                response_parts.append("💰 ราคาสินค้า:")
            elif language == 'korean':
                response_parts.append("💰 제품 가격:")
            elif language == 'japanese':
                response_parts.append("💰 商品価格:")
            elif language == 'chinese':
                response_parts.append("💰 产品价格:")
            else:
                response_parts.append("💰 Product Prices:")
        else:  # list
            if language == 'thai':
                response_parts.append("🛍️ รายการสินค้า:")
            elif language == 'korean':
                response_parts.append("🛍️ 제품 목록:")
            elif language == 'japanese':
                response_parts.append("🛍️ 商品一覧:")
            elif language == 'chinese':
                response_parts.append("🛍️ 产品列表:")
            else:
                response_parts.append("🛍️ Product List:")
        
        # 제품 정보 추가
        for i, product in enumerate(found_products[:5], 1):  # 상위 5개만 표시
            filename = product['filename']
            content = product['content']
            
            # 파일명에서 제품명 추출 (깔끔하게)
            if filename.endswith('_list.txt'):
                product_name = extract_product_name(filename.replace('_list.txt', ''))
            elif filename.endswith('_price.txt'):
                product_name = extract_product_name(filename.replace('_price.txt', ''))
            else:
                product_name = extract_product_name(filename)
            
            response_parts.append(f"\n**{i}. {product_name}**")
            
            # 내용 표시 (너무 길면 축약)
            if len(content) > 400:
                content = content[:400] + "..."
            
            response_parts.append(f"{content}\n")
        
        # 추가 정보 안내
        if language == 'thai':
            response_parts.append("\n📞 สำหรับข้อมูลเพิ่มเติม โทร: 02-159-9880, 085-595-9565")
        elif language == 'korean':
            response_parts.append("\n📞 자세한 정보: 02-159-9880, 085-595-9565")
        elif language == 'japanese':
            response_parts.append("\n📞 詳細情報: 02-159-9880, 085-595-9565")
        elif language == 'chinese':
            response_parts.append("\n📞 更多信息: 02-159-9880, 085-595-9565")
        else:
            response_parts.append("\n📞 For more info: 02-159-9880, 085-595-9565")
        
        return "\n".join(response_parts)
        
    except Exception as e:
        logger.error(f"❌ 제품 정보 생성 중 오류: {e}")
        return get_error_message(language)

def extract_product_name(filename: str) -> str:
    """파일명에서 읽기 쉬운 제품명 추출"""
    try:
        # 확장자 제거
        name = filename.replace('.txt', '')
        
        # 언더스코어를 공백으로 변경
        name = name.replace('_', ' ')
        
        # 각 단어의 첫 글자 대문자화
        name = ' '.join(word.capitalize() for word in name.split())
        
        return name
    except:
        return filename

def get_no_products_message(language: str) -> str:
    """제품을 찾지 못했을 때의 메시지"""
    messages = {
        'thai': "❌ ขออภัยค่ะ ไม่พบผลิตภัณฑ์ที่ตรงกับคำค้นหาของคุณ\n\n🔍 ลองค้นหาด้วยคำอื่น เช่น: สบู่, บาธบอม, สครับ, น้ำหอม\n📞 หรือติดต่อเราโดยตรง: 02-159-9880",
        'korean': "❌ 죄송합니다. 검색어와 일치하는 제품을 찾을 수 없습니다.\n\n🔍 다른 키워드로 시도해보세요: 비누, 배스봄, 스크럽, 향수\n📞 또는 직접 문의: 02-159-9880",
        'japanese': "❌ 申し訳ございません。検索条件に一致する商品が見つかりませんでした。\n\n🔍 他のキーワードでお試しください: 石鹸、バスボム、スクラブ、香水\n📞 またはお電話で: 02-159-9880",
        'chinese': "❌ 抱歉，没有找到符合搜索条件的产品。\n\n🔍 请尝试其他关键词: 香皂、沐浴球、磨砂膏、香水\n📞 或直接联系: 02-159-9880",
        'english': "❌ Sorry, no products found matching your search.\n\n🔍 Try other keywords like: soap, bath bomb, scrub, perfume\n📞 Or contact us directly: 02-159-9880"
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
    """사용자 메시지가 제품 검색 쿼리인지 판단 (가격 키워드도 포함)"""
    try:
        user_message_lower = user_message.lower()
        
        # 제품 카테고리 키워드 확인 (가격 키워드 포함)
        for category_keywords in PRODUCT_KEYWORDS.values():
            for keyword in category_keywords:
                if keyword.lower() in user_message_lower:
                    return True
        
        # 추가 검색 지시어 확인
        search_indicators = [
            # 영어
            'product', 'products', 'item', 'items', 'what do you have', 'what products',
            'show me', 'looking for', 'search', 'find', 'available', 'sell',
            # 한국어
            '제품', '상품', '뭐', '뭘', '무엇', '어떤', '찾', '있나', '파나', '팔아',
            # 태국어
            'สินค้า', 'ผลิตภัณฑ์', 'มีอะไร', 'ขาย', 'หา', 'ค้นหา',
            # 일본어
            '商品', '製品', '何', 'なに', '探', 'さが',
            # 중국어
            '产品', '商品', '什么', '寻找', '搜索'
        ]
        
        for indicator in search_indicators:
            if indicator in user_message_lower:
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"❌ 제품 검색 쿼리 판단 중 오류: {e}")
        return False

# ✅ 기존 함수들을 유지하면서 제품 검색 기능 통합

# ❌ get_price_list 함수 제거 (더 이상 사용하지 않음)
# def get_price_list(language='en'):
#     """이 함수는 더 이상 사용하지 않습니다. get_product_info()를 사용하세요."""
#     pass

# 메신저 / 웹용 줄바꿈 처리 함수 (기존 유지)
def format_text_for_messenger(text):
    """웹/메신저용: \n → <br> 로 변환"""
    try:
        text = text.replace("\n", "<br>")
        return text
    except Exception as e:
        logger.error(f"❌ 메신저용 줄바꿈 변환 오류: {e}")
        return text

# LINE 용 줄바꿈 처리 함수 (기존 유지)
def format_text_for_line(text):
    """LINE 용: \n → \n\n 로 변환"""
    try:
        text = text.replace("\n", "\n\n")
        return text
    except Exception as e:
        logger.error(f"❌ LINE용 줄바꿈 변환 오류: {e}")
        return text

# .env 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# 환경 확인 로그
if os.getenv('RAILWAY_ENVIRONMENT'):
    logger.info("✅ Railway 프로덕션 환경에서 실행 중입니다.")
else:
    logger.info("✅ 로컬 개발 환경에서 실행 중입니다.")

# Flask 앱 초기화
app = Flask(__name__)

# 채팅 로그를 저장할 폴더 이름 정의
CHAT_LOG_DIR = "save_chat"

# OpenAI 클라이언트 설정
try:
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY가 .env 파일에 없습니다.")
    client = OpenAI(api_key=openai_api_key)
    logger.info("✅ OpenAI 클라이언트가 성공적으로 초기화되었습니다.")
except Exception as e:
    logger.error(f"❌ OpenAI 클라이언트 초기화 실패: {e}")
    client = None

# LINE 설정 확인
LINE_TOKEN = os.getenv("LINE_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_SECRET = os.getenv("LINE_CHANNEL_SECRET") or os.getenv("LINE_SECRET")

if not LINE_TOKEN:
    logger.error("❌ LINE_TOKEN 또는 LINE_CHANNEL_ACCESS_TOKEN을 찾을 수 없습니다!")
if not LINE_SECRET:
    logger.error("❌ LINE_SECRET 또는 LINE_CHANNEL_SECRET을 찾을 수 없습니다!")

# 전역 변수: 언어별 캐시만 사용
language_data_cache = {}
last_update_time = datetime.now()

# 언어별 회사 정보 로드 (기존 유지)
def fetch_company_info(user_language):
    """언어별 company_info.txt 파일을 읽어오고, 결과를 캐시에 저장합니다."""
    global language_data_cache
    
    if user_language in language_data_cache:
        logger.info(f"📋 캐시된 '{user_language}' 회사 정보를 사용합니다.")
        return language_data_cache[user_language]

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
    company_info_dir = "company_info"
    filepath = os.path.join(company_info_dir, filename)

    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if len(content) > 20:
                    logger.info(f"✅ '{user_language}' 회사 정보를 {filepath} 파일에서 성공적으로 로드했습니다.")
                    language_data_cache[user_language] = content
                    return content
    except Exception as e:
        logger.error(f"❌ {filepath} 파일 로드 중 오류 발생: {e}")

    # 영어 폴백 시도
    logger.warning(f"⚠️ {filepath} 파일을 찾을 수 없거나 내용이 비어있습니다. 영어 버전을 시도합니다.")
    try:
        fallback_filepath = os.path.join(company_info_dir, "company_info_en.txt")
        if os.path.exists(fallback_filepath):
             with open(fallback_filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if len(content) > 20:
                    logger.info(f"✅ 영어 버전({fallback_filepath})을 폴백으로 사용합니다.")
                    language_data_cache[user_language] = content
                    return content
    except Exception as e:
        logger.error(f"❌ {fallback_filepath} 파일 로드 중 오류 발생: {e}")

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

# ✅ 초기 데이터 로드 (제품 데이터 포함)
def initialize_data():
    """앱 시작 시 필요한 언어별 데이터와 제품 데이터를 미리 로드합니다."""
    logger.info("🚀 앱 초기화를 시작합니다...")
    
    # 제품 데이터 로드
    if load_product_files():
        logger.info(f"✅ 제품 데이터 로드 완료: {len(product_data_cache)}개 파일")
    else:
        logger.warning("⚠️ 제품 데이터 로드 실패")
    
    # 주요 언어 회사 정보 미리 캐싱
    common_languages = ['english', 'korean', 'thai', 'japanese', 'chinese', 'spanish', 'german']
    for lang in common_languages:
        try:
            fetch_company_info(lang)
        except Exception as e:
            logger.warning(f"⚠️ {lang} 언어 정보 미리 로드 실패: {e}")
    
    logger.info(f"✅ 캐시된 언어: {list(language_data_cache.keys())}")

# 시스템 메시지 정의 (기존 유지)
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

# 언어 감지 함수 (기존 유지)
def detect_user_language(message):
    """사용자 메시지에서 언어를 감지합니다."""
    try:
        if re.search(r'[\u0e00-\u0e7f]+', message):
            return 'thai'
        elif re.search(r'[\uac00-\ud7af]+', message):
            return 'korean'
        elif re.search(r'[\u3040-\u309f\u30a0-\u30ff]+', message):
            return 'japanese'
        elif re.search(r'[\u4e00-\u9fff]+', message):
            if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', message):
                return 'japanese'
            else:
                return 'chinese'
        elif re.search(r'[\u0600-\u06ff]+', message):
            return 'arabic'
        elif re.search(r'[\u0401\u0451\u0410-\u044f]+', message):
            return 'russian'
        elif re.search(r'[àâäéèêëïîôùûüÿç]+', message.lower()):
            return 'french'
        elif re.search(r'[àáâãçéêíóôõú]+', message.lower()):
            return 'spanish'
        elif re.search(r'[äöüß]+', message.lower()):
            return 'german'
        elif re.search(r'[ăâđêôơưàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụ]+', message.lower()):
            return 'vietnamese'
        
        return 'english'
    except Exception as e:
        logger.error(f"❌ 언어 감지 중 오류 발생: {e}")
        return 'english'

# 영어 폴백 응답 생성 (기존 유지)
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

# 하이퍼링크 추가 함수 (기존 유지)
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

# ✅ GPT 응답 생성 함수 (제품 검색 기능 통합)
def get_gpt_response(user_message):
    """언어별 파일 데이터와 제품 검색을 통합하여 OpenAI GPT 모델로 최종 답변을 생성합니다."""
    user_language = detect_user_language(user_message)
    logger.info(f"🌐 감지된 사용자 언어: {user_language}")
    
    try:
        if not client:
            logger.error("❌ OpenAI client가 없습니다.")
            return get_english_fallback_response(user_message, "OpenAI service unavailable")
        
        # 1. 제품 검색 쿼리인지 확인
        if is_product_search_query(user_message):
            logger.info("🔍 제품 검색 쿼리로 감지되었습니다.")
            product_info = get_product_info(user_message, user_language)
            
            # 제품 정보만으로도 충분한 경우 바로 반환
            if "관련 제품:" in product_info or "Related Products:" in product_info or "ผลิตภัณฑ์ที่เกี่ยวข้อง:" in product_info:
                return product_info
        
        # 2. 회사 정보 가져오기
        company_info = fetch_company_info(user_language)
        
        # 회사 정보 유효성 검사
        if not company_info or len(company_info.strip()) < 50:
            logger.warning("⚠️ 회사 정보가 불충분합니다. 폴백을 사용합니다.")
            return get_english_fallback_response(user_message, "Company data temporarily unavailable")
        
        # 3. 제품 데이터 포함 여부 결정
        product_context = ""
        if is_product_search_query(user_message):
            found_products = search_products_by_keywords(user_message)
            if found_products:
                product_context = f"\n\n[제품 검색 결과]\n"
                for i, product in enumerate(found_products[:3], 1):  # 상위 3개만 포함
                    product_name = extract_product_name(product['filename'])
                    content_preview = product['content'][:150] + "..." if len(product['content']) > 150 else product['content']
                    product_context += f"{i}. {product_name}: {content_preview}\n"
        
        # 4. GPT 프롬프트 생성
        prompt = f"""
[회사 정보 및 제품 정보 - 언어: {user_language}]
{company_info}
{product_context}

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

# 대화 로그 저장 함수 (기존 유지)
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
    
    detected_lang = detect_user_language(user_msg)
    
    try:
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] User ({user_id}) [{detected_lang}]: {user_msg}\n")
            f.write(f"[{timestamp}] Bot: {bot_msg}\n")
            f.write("-" * 50 + "\n")
        logger.info(f"💬 채팅 로그를 '{full_path}' 파일에 저장했습니다.")
    except Exception as e:
        logger.error(f"❌ 로그 파일 '{full_path}' 저장 실패: {e}")

# LINE 서명 검증 (기존 유지)
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

# LINE 메시지 전송 (기존 유지)
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
        "product_files_loaded": len(product_data_cache),
        "product_last_update": product_last_update.isoformat() if product_last_update else None,
        "data_source": "language_files_and_product_search",
        "google_services": "disabled",
        "linebreak_functions": "enabled"
    })

@app.route('/products')
def products_status():
    """제품 데이터 상태 확인"""
    try:
        return jsonify({
            "total_product_files": len(product_data_cache),
            "product_files": list(product_data_cache.keys()),
            "last_update": product_last_update.isoformat() if product_last_update else None,
            "price_list_folder_exists": os.path.exists("price_list"),
            "sample_keywords": dict(list(PRODUCT_KEYWORDS.items())[:5])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/search-products')
def search_products_endpoint():
    """제품 검색 테스트 엔드포인트"""
    try:
        query = request.args.get('q', '')
        if not query:
            return jsonify({"error": "검색어를 입력해주세요 (q 파라미터)"}), 400
        
        found_products = search_products_by_keywords(query)
        
        result = {
            "query": query,
            "found_count": len(found_products),
            "products": []
        }
        
        for product in found_products[:10]:
            result["products"].append({
                "filename": product['filename'],
                "product_name": extract_product_name(product['filename']),
                "relevance_score": product['relevance_score'],
                "matched_keywords": product['matched_keywords'],
                "content_preview": product['content'][:200] + "..." if len(product['content']) > 200 else product['content']
            })
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/reload-products')
def reload_products():
    """제품 데이터 다시 로드"""
    try:
        if load_product_files():
            return jsonify({
                "status": "success",
                "message": "제품 데이터가 성공적으로 다시 로드되었습니다.",
                "loaded_files": len(product_data_cache),
                "timestamp": datetime.now().isoformat()
            })
        else:
            return jsonify({
                "status": "error",
                "message": "제품 데이터 로드에 실패했습니다."
            }), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/language-status')
def language_status():
    """언어별 데이터 로딩 상태 확인"""
    try:
        status = {}
        
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
                filepath = os.path.join("company_info", filename)
                
                file_exists = os.path.exists(filepath)
                cached = lang in language_data_cache
                
                if file_exists:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content_length = len(f.read())
                else:
                    content_length = 0
                
                status[lang] = {
                    "file_exists": file_exists,
                    "filename": filename,
                    "filepath": filepath,
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
            "company_info_folder_exists": os.path.exists("company_info"),
            "price_list_folder_exists": os.path.exists("price_list"),
            "data_source": "language_files_and_product_search"
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
        global language_data_cache
        language_data_cache.clear()
        
        initialize_data()
        
        return jsonify({
            "status": "success",
            "message": "Language data reloaded successfully.",
            "cached_languages": list(language_data_cache.keys()),
            "product_files": len(product_data_cache),
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
        
        detected_language = detect_user_language(user_message)
        
        # ✅ 모든 제품/가격 관련 쿼리를 제품 검색으로 통합 처리
        if is_product_search_query(user_message):
            logger.info(f"🔍 제품/가격 검색 요청 감지 - 언어: {detected_language}")
            
            product_response = get_product_info(user_message, detected_language)
            formatted_response = format_text_for_messenger(product_response)
            clean_response_for_log = re.sub(r'<[^>]+>', '', formatted_response)
            save_chat(user_message, clean_response_for_log)
            response_with_links = add_hyperlinks(formatted_response)
            
            return jsonify({
                "reply": response_with_links,
                "is_html": True,
                "user_language": detected_language,
                "data_source": "product_search",
                "request_type": "product_or_price_inquiry"
            })
        
        # ✅ 기존 GPT 호출 (일반 질문)
        bot_response = get_gpt_response(user_message)
        formatted_response = format_text_for_messenger(bot_response)
        clean_response_for_log = re.sub(r'<[^>]+>', '', formatted_response)
        save_chat(user_message, clean_response_for_log)
        
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
            "language_file_used": os.path.join("company_info", language_file_used),
            "data_source": "language_files_and_gpt",
            "request_type": "general_inquiry"
        })
        
    except Exception as e:
        logger.error(f"❌ /chat 엔드포인트에서 오류 발생: {e}")
        fallback_response = get_english_fallback_response(
            user_message if 'user_message' in locals() else "general inquiry", 
            f"Web chat system error: {str(e)[:100]}"
        )
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
        
        webhook_data = json.loads(body)
        
        for event in webhook_data.get("events", []):
            if event.get("type") == "message" and event.get("message", {}).get("type") == "text":
                user_text = event["message"]["text"].strip()
                reply_token = event["replyToken"]
                user_id = event.get("source", {}).get("userId", "unknown")
                
                detected_language = detect_user_language(user_text)
                logger.info(f"👤 사용자 {user_id[:8]} ({detected_language}): {user_text}")
                
                # ✅ 모든 제품/가격 관련 쿼리를 제품 검색으로 통합 처리
                if is_product_search_query(user_text):
                    logger.info(f"🔍 LINE에서 제품/가격 검색 요청 감지 - 언어: {detected_language}")
                    product_info = get_product_info(user_text, detected_language)
                    formatted_product_text = format_text_for_line(product_info)
                    clean_product_response = re.sub(r'<[^>]+>', '', formatted_product_text)
                    
                    if send_line_message(reply_token, clean_product_response):
                        save_chat(user_text, clean_product_response, user_id)
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
        with threading.Lock():
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
    logger.info("📂 데이터 소스: company_info 폴더 + price_list 폴더 개별 파일 검색")
    logger.info("🔍 제품 검색: price_list 폴더에서 실시간 검색 지원 (통합 price_list.txt 제거)")
    logger.info("🌈 줄바꿈 처리 기능: 웹용 <br>, LINE용 \\n\\n 지원")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=not debug_mode)
    except KeyboardInterrupt:
        logger.info("🛑 서버 종료 요청을 받았습니다.")
    except Exception as e:
        logger.error(f"❌ 서버 실행 중 오류 발생: {e}")
    finally:
        logger.info("🔚 서버가 정상적으로 종료되었습니다.")