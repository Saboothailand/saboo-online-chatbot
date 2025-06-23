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
from typing import Dict, List, Optional, Tuple

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
    format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s'
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
product_data_cache = {}
product_last_update = None
language_data_cache = {}
user_context_cache = {}
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


# 제품 검색을 위한 키워드 매핑
PRODUCT_KEYWORDS = {
    # ... (이전과 동일한 키워드 내용) ...
    'bathbomb': ['bath bomb', 'bathbomb', '배스봄', '바스봄', 'บาธบอม', 'บอม', 'ลูกบอลอาบน้ำ'], 'bubble': ['bubble', '버블', 'บับเบิล', 'ฟอง'], 'fizzy': ['fizzy', '피지', 'ฟิซซี่', 'ฟิซ'],
    'soap': ['soap', '비누', 'สบู่'], 'fancy': ['fancy', '팬시', 'แฟนซี'], 'natural': ['natural', '천연', 'ธรรมชาติ'], 'handmade': ['handmade', '수제', 'ทำมือ'],
    'fruit': ['fruit', '과일', 'ผลไม้'], 'flower': ['flower', '꽃', 'ดอกไม้'], 'animal': ['animal', '동물', 'สัตว์'], 'dinosaur': ['dinosaur', '공룡', 'ไดโนเสาร์'], 'elephant': ['elephant', '코끼리', 'ช้าง'], 'duck': ['duck', '오리', 'เป็ด'], 'bear': ['bear', '곰', 'หมี'],
    'scrub': ['scrub', '스크럽', 'สครับ'], 'perfume': ['perfume', '향수', 'น้ำหอม'], 'spray': ['spray', '스프레이', 'สเปรย์'], 'gel': ['gel', '젤', 'เจล'], 'gift': ['gift', 'set', '선물', '세트', 'ของขวัญ', 'เซ็ต'],
    'price': ['price', 'prices', 'price list', 'cost', 'how much', 'pricing', 'rate', 'fee', '가격', '비누 가격', '팬시비누 가격', '비누가격', '얼마', '값', '요금', '비용', 'ราคา', 'สบู่ราคา', 'ราคาสบู่', 'เท่าไหร่', 'เท่าไร', 'ค่า', 'ค่าใช้จ่าย', '価格', '値段', 'いくら', '料金', 'コスト', 'プライス', '价格', '价钱', '多少钱', '费用', '成本', '定价', 'precio', 'precios', 'costo', 'cuanto', 'tarifa', 'preis', 'preise', 'kosten', 'wie viel', 'gebühr', 'prix', 'coût', 'combien', 'tarif', 'цена', 'цены', 'стоимость', 'сколько'],
    '100g': ['100g', '100 g', '100gram'], '150g': ['150g', '150 g', '150gram'], '185g': ['185g', '185 g', '185gram'], '500ml': ['500ml', '500 ml'], '250ml': ['250ml', '250 ml'], '25ml': ['25ml', '25 ml']
}

# 언어별 "더 자세한 정보" 안내 메시지 (개선: 영어 메시지 제거)
MORE_INFO_MESSAGES = {
    'thai': "💬 หากต้องการข้อมูลเพิ่มเติมหรือรายละเอียดมากขึ้น กรุณาพิมพ์ 'รายละเอียดเพิ่มเติม' หรือ 'ข้อมูลเพิ่มเติม' ค่ะ", 
    'korean': "💬 더 자세한 정보나 추가 설명이 필요하시면 '자세한 설명' 또는 '더 알려주세요'라고 말씀해 주세요", 
    'japanese': "💬 詳細情報や追加説明が必要でしたら「詳しく教えて」または「もっと詳しく」とお聞かせください", 
    'chinese': "💬 如需更详细信息或更多说明，请输入「详细说明」或「更多信息」", 
    'spanish': "💬 Para obtener información más detallada o explicación adicional, escriba 'más detalles' o 'cuéntame más'", 
    'german': "💬 Für detailliertere Informationen oder zusätzliche Erklärungen, tippen Sie 'mehr Details' oder 'erzählen Sie mir mehr'", 
    'french': "💬 Pour plus d'informations détaillées ou d'explications supplémentaires, tapez 'plus de détails' ou 'dites-moi plus'", 
    'vietnamese': "💬 Để biết thêm thông tin chi tiết hoặc giải thích bổ sung, vui lòng nhập 'chi tiết hơn' hoặc 'cho tôi biết thêm'", 
    'russian': "💬 Для получения более подробной информации или дополнительных объяснений, напишите 'подробнее' или 'расскажите больше'"
}

# "더 자세한 정보" 요청 키워드 감지
MORE_INFO_KEYWORDS = {
    'thai': ['รายละเอียดเพิ่มเติม', 'ข้อมูลเพิ่มเติม', 'อธิบายเพิ่ม', 'บอกเพิ่ม', 'เพิ่มเติม', 'รายละเอียด'], 'korean': ['자세한 설명', '더 알려주세요', '상세한 설명', '자세히', '더 자세히', '추가 설명', '더 설명'], 'japanese': ['詳しく教えて', 'もっと詳しく', '詳細を教えて', '詳しい説明', '追加説明', '詳細'], 'chinese': ['详细说明', '更多信息', '详细信息', '更详细', '详细一点', '具体说明'], 'spanish': ['más detalles', 'cuéntame más', 'más información', 'explicación detallada', 'explica más'], 'german': ['mehr details', 'erzählen sie mir mehr', 'mehr informationen', 'detaillierte erklärung'], 'french': ['plus de détails', 'dites-moi plus', 'plus d\'informations', 'explication détaillée'], 'vietnamese': ['chi tiết hơn', 'cho tôi biết thêm', 'thông tin thêm', 'giải thích chi tiết'], 'russian': ['подробнее', 'расскажите больше', 'больше информации', 'подробное объяснение']
}

# 시스템 메시지 정의
SYSTEM_MESSAGE = """
You are a knowledgeable and friendly Thai staff member of SABOO THAILAND.
Always reply in the **same language** the customer uses. Be warm and helpful. Use light emojis 😊.
Key Info: Founded in 2008, first Thai fruit-shaped soap, store at Mixt Chatuchak, phone 02-159-9880, website www.saboothailand.com.
"""

ENGLISH_FALLBACK_MESSAGE = """
You are a helpful customer service representative for SABOO THAILAND.
Always respond in English when there are technical issues. Be friendly and professional.
Key Info: Founded in 2008, first Thai fruit-shaped soap, store at Mixt Chatuchak, Bangkok, phone 02-159-9880, website www.saboothailand.com.
"""

# ==============================================================================
# 5. 헬퍼 함수 정의 (Helper Functions)
# ==============================================================================

def process_response_length(text: str, language: str, max_length: int = 500) -> tuple:
    """응답 텍스트의 길이를 체크하고 필요시 축약 및 '더보기' 메시지 추가"""
    try:
        clean_text = re.sub(r'<[^>]+>', '', text)
        if len(clean_text) <= max_length:
            return text, False
        
        # 문장 단위로 자르기 시도 (간소화된 버전)
        truncated_text = clean_text[:max_length]
        last_space = truncated_text.rfind(' ')
        if last_space != -1:
            truncated_text = truncated_text[:last_space]

        truncated_text = truncated_text.strip()
        if not truncated_text.endswith('...'):
            truncated_text += "..."
        
        # 영어가 아닌 경우만 "더보기" 메시지 추가
        if language != 'english' and language in MORE_INFO_MESSAGES:
            more_info_msg = MORE_INFO_MESSAGES[language]
            final_text = f"{truncated_text}\n\n{more_info_msg}"
        else:
            final_text = truncated_text
        
        return final_text, True
    except Exception as e:
        logger.error(f"❌ 응답 길이 처리 중 오류: {e}")
        return text, False

def is_more_info_request(user_message: str, detected_language: str) -> bool:
    """사용자가 더 자세한 정보를 요청하는지 확인"""
    try:
        user_message_lower = user_message.lower().strip()
        if detected_language in MORE_INFO_KEYWORDS:
            for keyword in MORE_INFO_KEYWORDS[detected_language]:
                if keyword.lower() in user_message_lower: return True
        for lang_keywords in MORE_INFO_KEYWORDS.values():
            for keyword in lang_keywords:
                if keyword.lower() in user_message_lower: return True
        return False
    except Exception as e:
        logger.error(f"❌ '더보기' 요청 감지 중 오류: {e}")
        return False

def save_user_context(user_id: str, message: str, response: str, language: str):
    """사용자별 최근 대화 컨텍스트 저장"""
    try:
        if user_id not in user_context_cache:
            user_context_cache[user_id] = []
        user_context_cache[user_id].append({'timestamp': datetime.now(), 'user_message': message, 'bot_response': response, 'language': language})
        if len(user_context_cache[user_id]) > 3:
            user_context_cache[user_id] = user_context_cache[user_id][-3:]
    except Exception as e:
        logger.error(f"❌ 사용자 컨텍스트 저장 중 오류: {e}")

def get_user_context(user_id: str) -> str:
    """사용자의 최근 대화 컨텍스트 가져오기"""
    try:
        if user_id not in user_context_cache: return ""
        context_parts = []
        for ctx in user_context_cache[user_id][-2:]:
            context_parts.append(f"Previous Q: {ctx['user_message']}")
            context_parts.append(f"Previous A (summary): {ctx['bot_response'][:200]}...")
        return "\n".join(context_parts)
    except Exception as e:
        logger.error(f"❌ 사용자 컨텍스트 가져오기 중 오류: {e}")
        return ""

def load_product_files():
    """제품 파일을 로드하여 캐시에 저장"""
    global product_data_cache, product_last_update
    try:
        price_list_dir = "price_list"
        if not os.path.exists(price_list_dir):
            logger.warning(f"⚠️ {price_list_dir} 폴더를 찾을 수 없습니다.")
            return False
        product_data_cache.clear()
        txt_files = glob.glob(os.path.join(price_list_dir, "*.txt"))
        for file_path in txt_files:
            try:
                filename = os.path.basename(file_path)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content: product_data_cache[filename] = content
            except Exception as e:
                logger.error(f"❌ {file_path} 로드 실패: {e}")
        product_last_update = datetime.now()
        logger.info(f"✅ 총 {len(product_data_cache)}개 제품 파일 로드 완료.")
        return True
    except Exception as e:
        logger.error(f"❌ 제품 파일 로드 중 오류: {e}")
        return False

def search_products_by_keywords(user_query: str) -> List[Dict]:
    """사용자 쿼리에서 키워드를 추출하여 관련 제품 '파일' 찾기"""
    try:
        user_query_lower = user_query.lower()
        found_products = []
        price_intent_keywords = PRODUCT_KEYWORDS['price']
        list_intent_keywords = ['어떤', '뭐', '종류', '목록', '리스트', 'what', 'which', 'types', 'list', 'items', 'อะไร', 'ชนิด', 'รายการ', '何', 'なに', '種類', '什么', '哪些']
        is_price_query = any(keyword in user_query_lower for keyword in price_intent_keywords)
        is_list_query = any(keyword in user_query_lower for keyword in list_intent_keywords)
        if not is_price_query and not is_list_query: is_list_query = True
        
        for filename, content in product_data_cache.items():
            relevance_score = 0
            if is_price_query and not filename.endswith('_price.txt'): continue
            elif is_list_query and not filename.endswith('_list.txt'): continue
            filename_lower = filename.lower()
            for category, keywords in PRODUCT_KEYWORDS.items():
                if category == 'price': continue
                for keyword in keywords:
                    if keyword.lower() in user_query_lower and (category in filename_lower or any(k in filename_lower for k in keywords)):
                        relevance_score += 2
            if relevance_score > 0:
                found_products.append({'filename': filename, 'content': content})
        
        found_products.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return found_products[:5]
    except Exception as e:
        logger.error(f"❌ 제품 파일 검색 중 오류: {e}")
        return []

def get_product_info(user_query: str, language: str = 'english') -> str:
    """사용자 쿼리에 맞는 제품 정보를 '정확하고 읽기 쉽게' 생성합니다."""
    try:
        # 1. 관련 제품 '파일'들을 먼저 검색
        found_files = search_products_by_keywords(user_query)
        if not found_files:
            return get_no_products_message(language)

        # 2. 사용자 쿼리에서 검색할 핵심 단어 추출 (더 정확한 키워드 추출)
        # 제외할 단어들을 더 포괄적으로 설정
        exclude_words = {"가격", "얼마", "종류", "알려줘", "price", "cost", "how", "much", "what", "tell", "me", "show", "ราคา", "เท่าไหร่", "อะไร"}
        query_keywords = [word for word in user_query.lower().split() if len(word) > 1 and word not in exclude_words]

        # 3. 찾은 정보들을 담을 리스트
        response_items = []
        
        # 4. 찾은 각 '파일'의 '내용'을 한 줄씩 확인
        for file_data in found_files:
            content_lines = file_data['content'].splitlines()

            for line in content_lines:
                line_lower = line.lower()
                
                # 더 정확한 매칭을 위한 개선된 로직
                # 핵심 키워드 중 적어도 하나가 해당 줄에 포함되어야 하고,
                # 사용자가 특정 제품을 언급했다면 그 제품명이 반드시 포함되어야 함
                keyword_matches = 0
                specific_product_found = False
                
                # 특정 제품명이 있는지 확인 (mango, strawberry, etc.)
                specific_products = ["mango", "strawberry", "banana", "orange", "apple", "grape", "peach", "pineapple", 
                                   "elephant", "duck", "bear", "dinosaur", "rose", "jasmine", "lavender"]
                user_specific_products = [prod for prod in specific_products if prod in user_query.lower()]
                
                if user_specific_products:
                    # 특정 제품이 언급된 경우, 해당 제품명이 줄에 포함되어야 함
                    specific_product_found = any(prod in line_lower for prod in user_specific_products)
                    if not specific_product_found:
                        continue
                
                # 일반 키워드 매칭
                for keyword in query_keywords:
                    if keyword in line_lower:
                        keyword_matches += 1
                
                # 매칭 조건: 특정 제품이 있으면 반드시 포함되어야 하고, 키워드도 매칭되어야 함
                if user_specific_products:
                    # 특정 제품 + 키워드 매칭
                    if specific_product_found and keyword_matches > 0:
                        # 5. 가독성을 위해 '|'를 기준으로 줄바꿈 처리
                        items = [item.strip() for item in line.split(' | ')]
                        formatted_line = items[0]
                        if len(items) > 1:
                            formatted_line += "\n- " + "\n- ".join(items[1:])
                        response_items.append(formatted_line)
                else:
                    # 일반적인 키워드 매칭 (키워드 중 절반 이상 매칭)
                    if keyword_matches >= max(1, len(query_keywords) // 2):
                        items = [item.strip() for item in line.split(' | ')]
                        formatted_line = items[0]
                        if len(items) > 1:
                            formatted_line += "\n- " + "\n- ".join(items[1:])
                        response_items.append(formatted_line)
        
        # 6. 만약 특정 제품 정보를 찾았다면, 깔끔하게 조합해서 반환
        if response_items:
            # 헤더 추가
            header = "💰 제품 가격:" if any(p in user_query for p in ["가격", "얼마", "price", "cost"]) else "🛍️ 제품 목록:"
            # 중복 제거 후 최종 결과 생성
            final_response_text = header + "\n\n" + "\n\n".join(list(dict.fromkeys(response_items)))
            return final_response_text

        # 7. 특정 항목을 찾지 못했다면, 가장 관련도 높은 파일의 내용을 일부 보여주는 폴백 로직
        logger.warning(f"⚠️ '{user_query}'에 대한 특정 항목을 찾지 못해, 최상위 검색 파일 내용으로 대체합니다.")
        first_product = found_files[0]
        product_name = extract_product_name(first_product['filename'])
        content_preview = first_product['content'][:400] + "..." if len(first_product['content']) > 400 else first_product['content']
        return f"**연관된 제품 카테고리: {product_name}**\n{content_preview}"

    except Exception as e:
        logger.error(f"❌ 제품 정보 생성 중 치명적 오류: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return get_error_message(language)


def extract_product_name(filename: str) -> str:
    """파일명에서 읽기 쉬운 제품명 추출"""
    try:
        name = filename.replace('.txt', '').replace('_price', '').replace('_list', '').replace('_', ' ')
        return ' '.join(word.capitalize() for word in name.split())
    except:
        return filename

def get_no_products_message(language: str) -> str:
    messages = {'thai': "❌ ขออภัยค่ะ ไม่พบผลิตภัณฑ์ที่ตรงกับคำค้นหาของคุณ\n\n🔍 ลองค้นหาด้วยคำอื่น เช่น: สบู่, บาธบอม, สครับ, น้ำหอม\n📞 หรือติดต่อเราโดยตรง: 02-159-9880", 'korean': "❌ 죄송합니다. 검색어와 일치하는 제품을 찾을 수 없습니다.\n\n🔍 다른 키워드로 시도해보세요: 비누, 배스봄, 스크럽, 향수\n📞 또는 직접 문의: 02-159-9880", 'japanese': "❌ 申し訳ございません。検索条件に一致する商品が見つかりませんでした。\n\n🔍 他のキーワードでお試しください: 石鹸、バスボム、スクラブ、香水\n📞 またはお電話で: 02-159-9880", 'chinese': "❌ 抱歉，没有找到符合搜索条件的产品。\n\n🔍 请尝试其他关键词: 香皂、沐浴球、磨砂膏、香水\n📞 或直接联系: 02-159-9880", 'english': "❌ Sorry, no products found matching your search.\n\n🔍 Try other keywords like: soap, bath bomb, scrub, perfume\n📞 Or contact us directly: 02-159-9880"}
    return messages.get(language, messages['english'])

def get_error_message(language: str) -> str:
    messages = {'thai': "❌ เกิดข้อผิดพลาดในการค้นหาสินค้า โปรดติดต่อเราโดยตรง: 02-159-9880", 'korean': "❌ 제품 검색 중 오류가 발생했습니다. 직접 문의해주세요: 02-159-9880", 'japanese': "❌ 商品検索中にエラーが発生しました。直接お問い合わせください: 02-159-9880", 'chinese': "❌ 产品搜索时出现错误，请直接联系我们: 02-159-9880", 'english': "❌ Error occurred while searching products. Please contact us directly: 02-159-9880"}
    return messages.get(language, messages['english'])

def is_product_search_query(user_message: str) -> bool:
    try:
        user_message_lower = user_message.lower()
        for category_keywords in PRODUCT_KEYWORDS.values():
            for keyword in category_keywords:
                if keyword.lower() in user_message_lower: return True
        search_indicators = ['product', 'item', 'show me', 'looking for', 'search', 'find', 'sell', '제품', '상품', '뭐', '찾', '파나', '팔아', 'สินค้า', 'ผลิตภัณฑ์', 'มีอะไร', 'ขาย', 'หา', 'ค้นหา', '商品', '製品', '何', '探', 'さが', '产品', '什么', '寻找', '搜索']
        for indicator in search_indicators:
            if indicator in user_message_lower: return True
        return False
    except Exception as e:
        logger.error(f"❌ 제품 검색 쿼리 판단 중 오류: {e}")
        return False

def format_text_for_messenger(text: str) -> str:
    return text.replace("\n", "<br>")

def format_text_for_line(text: str) -> str:
    return text.replace("\n", "\n\n")

def fetch_company_info(user_language: str) -> str:
    global language_data_cache
    if user_language in language_data_cache: return language_data_cache[user_language]
    lang_map = {'thai': 'th', 'english': 'en', 'korean': 'kr', 'japanese': 'ja', 'german': 'de', 'spanish': 'es', 'arabic': 'ar', 'chinese': 'zh_cn', 'taiwanese': 'zh_tw', 'vietnamese': 'vi', 'myanmar': 'my', 'khmer': 'km', 'russian': 'ru', 'french': 'fr'}
    lang_code = lang_map.get(user_language, 'en')
    filepath = os.path.join("company_info", f"company_info_{lang_code}.txt")
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if len(content) > 20:
                    language_data_cache[user_language] = content
                    return content
    except Exception as e: logger.error(f"❌ {filepath} 파일 로드 중 오류 발생: {e}")
    logger.warning(f"⚠️ {filepath} 파일 없음. 영어로 대체.")
    try:
        fallback_filepath = os.path.join("company_info", "company_info_en.txt")
        if os.path.exists(fallback_filepath):
            with open(fallback_filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if len(content) > 20:
                    language_data_cache[user_language] = content
                    return content
    except Exception as e: logger.error(f"❌ {fallback_filepath} 파일 로드 중 오류 발생: {e}")
    default_info = "Welcome to SABOO THAILAND! We are Thailand's first natural fruit-shaped soap manufacturer since 2008. Contact: 02-159-9880."
    language_data_cache[user_language] = default_info
    return default_info


def initialize_data():
    """앱 시작 시 데이터 로드"""
    logger.info("🚀 앱 초기화 시작...")
    load_product_files()
    common_languages = ['english', 'korean', 'thai', 'japanese', 'chinese']
    for lang in common_languages:
        fetch_company_info(lang)
    logger.info("✅ 데이터 초기화 완료.")

def detect_user_language(message: str) -> str:
    try:
        if re.search(r'[\u0e00-\u0e7f]+', message): return 'thai'
        elif re.search(r'[\uac00-\ud7af]+', message): return 'korean'
        elif re.search(r'[\u3040-\u309f\u30a0-\u30ff]+', message): return 'japanese'
        elif re.search(r'[\u4e00-\u9fff]+', message): return 'japanese' if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', message) else 'chinese'
        return 'english'
    except: return 'english'


def get_english_fallback_response(user_message, error_context=""):
    logger.warning(f"⚠️ 폴백 응답 활성화: {error_context}")
    return "I apologize, we're experiencing technical difficulties. Please contact us directly at 02-159-9880. Thank you! 😊"

def add_hyperlinks(text: str) -> str:
    """하이퍼링크 추가 - 개선된 버전"""
    try:
        # 전화번호 링크 추가
        text = re.sub(r'\b(0\d{1,2}-\d{3,4}-\d{4})\b', r'<a href="tel:\1" style="color: #ff69b4; text-decoration: underline;">\1</a>', text)
        
        # 웹사이트 링크 처리 (개선된 정규식)
        # 완전한 URL (http/https 포함)
        text = re.sub(
            r'\b(https?://[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*(?:/[^\s<]*)?)\b',
            r'<a href="\1" target="_blank" style="color: #ff69b4; text-decoration: underline;">\1</a>',
            text
        )
        
        # www로 시작하는 URL
        text = re.sub(
            r'\b(www\.[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*(?:/[^\s<]*)?)\b',
            r'<a href="https://\1" target="_blank" style="color: #ff69b4; text-decoration: underline;">\1</a>',
            text
        )
        
        # 도메인만 있는 경우 (예: shopee.co.th/thailandsoap)
        text = re.sub(
            r'\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,6}(?:/[^\s<]*)?)\b',
            r'<a href="https://\1" target="_blank" style="color: #ff69b4; text-decoration: underline;">\1</a>',
            text
        )
        
        return text
    except Exception as e:
        logger.error(f"❌ 하이퍼링크 추가 중 오류: {e}")
        return text

def get_gpt_response(user_message, user_id="anonymous"):
    """GPT 모델을 사용하여 최종 답변 생성"""
    user_language = detect_user_language(user_message)
    logger.info(f"🌐 사용자 언어: {user_language}")

    try:
        if not client: return get_english_fallback_response(user_message, "OpenAI service unavailable")

        # "더 자세한 정보" 요청 처리
        if is_more_info_request(user_message, user_language):
            logger.info("📋 '더보기' 요청 감지됨.")
            user_context = get_user_context(user_id)
            if user_context:
                prompt = f"[Previous Conversation]\n{user_context}\n\n[Current Request]\nThe user wants more details about the previous answer: '{user_message}'\n\nPlease provide a detailed explanation in {user_language}."
                completion = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": SYSTEM_MESSAGE}, {"role": "user", "content": prompt}], max_tokens=1000)
                detailed_response = completion.choices[0].message.content.strip()
                save_user_context(user_id, user_message, detailed_response, user_language)
                return detailed_response
            else:
                return "이전 대화 내용이 없어 더 자세한 정보를 드릴 수 없습니다. 궁금한 점을 다시 질문해주세요."

        # 제품 검색 쿼리 처리 (새로운 get_product_info 사용)
        if is_product_search_query(user_message):
            logger.info("🔍 제품 검색 쿼리 감지됨.")
            product_info = get_product_info(user_message, user_language)
            # 제품 정보에 연락처 추가
            contact_info = "\n\n📞 자세한 정보: 02-159-9880, 085-595-9565"
            full_response = product_info + contact_info
            
            # 컨텍스트 저장 및 길이 처리
            save_user_context(user_id, user_message, full_response, user_language)
            processed_response, _ = process_response_length(full_response, user_language)
            return processed_response

        # 일반 질문 처리
        company_info = fetch_company_info(user_language)
        user_context = get_user_context(user_id)
        context_section = f"\n\n[Previous Conversation]\n{user_context}" if user_context else ""
        prompt = f"[Company Info ({user_language})]\n{company_info}{context_section}\n\n[User's Question]\n{user_message}"
        
        completion = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": SYSTEM_MESSAGE}, {"role": "user", "content": prompt}], max_tokens=800)
        response_text = completion.choices[0].message.content.strip()

        if not response_text: return get_english_fallback_response(user_message, "Empty GPT response")
        
        save_user_context(user_id, user_message, response_text, user_language)
        processed_response, _ = process_response_length(response_text, user_language)
        return processed_response

    except Exception as e:
        logger.error(f"❌ GPT 응답 생성 중 오류: {e}")
        return get_english_fallback_response(user_message, f"GPT API error: {str(e)[:100]}")

def save_chat(user_msg, bot_msg, user_id="anonymous"):
    now = datetime.now()
    datestamp = now.strftime("%Y_%m_%d")
    try:
        os.makedirs(CHAT_LOG_DIR, exist_ok=True)
        filename = f"save_chat_{datestamp}.txt"
        full_path = os.path.join(CHAT_LOG_DIR, filename)
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] User({user_id}): {user_msg}\nBot: {bot_msg}\n---\n")
    except Exception as e:
        logger.error(f"❌ 로그 파일 저장 실패: {e}")

def verify_line_signature(body, signature):
    if not LINE_SECRET: return True
    try:
        hash_val = hmac.new(LINE_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
        return hmac.compare_digest(base64.b64encode(hash_val).decode('utf-8'), signature)
    except: return False

def send_line_message(reply_token, message):
    try:
        if not LINE_TOKEN: return False
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
        payload = {"replyToken": reply_token, "messages": [{"type": "text", "text": message}]}
        response = requests.post("https://api.line.me/v2/bot/message/reply", headers=headers, json=payload, timeout=10)
        return response.status_code == 200
    except: return False

def initialize_once():
    """앱 첫 요청 시 1회 실행"""
    global app_initialized
    if not app_initialized:
        with threading.Lock():
            if not app_initialized:
                logger.info("🎯 첫 요청 감지, 데이터 초기화 실행...")
                initialize_data()
                app_initialized = True

def check_admin_access():
    """관리자 API 키 확인"""
    if not ADMIN_API_KEY: return True
    return request.headers.get('X-Admin-API-Key') == ADMIN_API_KEY


# ==============================================================================
# 6. Flask 라우트 및 데코레이터 (Routes & Decorators)
# ==============================================================================
@app.before_request
def before_request():
    """모든 요청 전 처리"""
    admin_endpoints = ['/reload-products', '/reload-language-data', '/clear-language-cache']
    if request.path in admin_endpoints and not check_admin_access():
        return jsonify({"error": "Unauthorized"}), 403
    initialize_once()

@app.route('/')
def index():
    """웹 챗 UI 렌더링"""
    return render_template('chat.html')

@app.route('/health')
def health():
    """헬스 체크"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/reload-products')
def reload_products():
    """제품 데이터 다시 로드"""
    if load_product_files():
        return jsonify({"status": "success", "message": f"{len(product_data_cache)} product files reloaded."})
    return jsonify({"status": "error", "message": "Failed to reload product files."}), 500

@app.route('/chat', methods=['POST'])
def chat():
    """웹 챗 API 엔드포인트"""
    try:
        user_message = request.json.get('message', '').strip()
        user_id = request.json.get('user_id', 'web_user')
        if not user_message:
            return jsonify({"error": "Empty message."}), 400

        bot_response = get_gpt_response(user_message, user_id)
        
        # HTML 형식으로 최종 응답 가공
        formatted_response = format_text_for_messenger(bot_response)
        response_with_links = add_hyperlinks(formatted_response)
        
        save_chat(user_message, re.sub(r'<[^>]+>', '', response_with_links), user_id)
        
        return jsonify({"reply": response_with_links, "is_html": True})
    except Exception as e:
        logger.error(f"❌ /chat 엔드포인트 오류: {e}")
        return jsonify({"reply": "An error occurred.", "is_html": True}), 500

@app.route('/line', methods=['POST'])
def line_webhook():
    """LINE 웹훅 엔드포인트"""
    try:
        body = request.get_data(as_text=True)
        signature = request.headers.get('X-Line-Signature', '')
        
        if not verify_line_signature(body.encode('utf-8'), signature):
            logger.warning("⚠️ 잘못된 LINE 서명.")
            return "OK", 200

        for event in request.json.get("events", []):
            if event.get("type") == "message" and event["message"].get("type") == "text":
                user_text = event["message"]["text"].strip()
                reply_token = event["replyToken"]
                user_id = event["source"]["userId"]
                
                logger.info(f"👤 LINE 사용자({user_id[:8]}): {user_text}")
                
                bot_response = get_gpt_response(user_text, user_id)
                clean_response = re.sub(r'<[^>]+>', '', bot_response)
                formatted_response = format_text_for_line(clean_response)

                send_line_message(reply_token, formatted_response)
                save_chat(user_text, formatted_response, user_id)
                
        return "OK", 200
    except Exception as e:
        logger.error(f"❌ LINE 웹훅 처리 오류: {e}")
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
        logger.info("🚀 개발 모드로 직접 초기화 실행...")
        initialize_data()
        app_initialized = True
    
    port = int(os.environ.get("PORT", 5000))
    debug_mode = not os.getenv('RAILWAY_ENVIRONMENT')
    
    logger.info(f"🚀 Flask 서버를 포트 {port}에서 시작합니다. (디버그 모드: {debug_mode})")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=debug_mode, use_reloader=not debug_mode)
    except KeyboardInterrupt:
        logger.info("🛑 서버 종료.")
    except Exception as e:
        logger.error(f"❌ 서버 실행 중 오류 발생: {e}")
    finally:
        logger.info("🔚 서버가 정상적으로 종료되었습니다.") '