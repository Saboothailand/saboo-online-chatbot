# utils_product.py

import pymysql
from dotenv import load_dotenv
import os

# .env 에 DATABASE_URL 저장
load_dotenv()

# DB 연결 정보
DB_HOST = os.getenv('MYSQL_HOST')
DB_PORT = int(os.getenv('MYSQL_PORT'))
DB_USER = os.getenv('MYSQL_USER')
DB_PASSWORD = os.getenv('MYSQL_PASSWORD')
DB_NAME = os.getenv('MYSQL_DATABASE')

# DB 연결 함수
def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# 새로운 제품 등록
def add_new_product(name, size, category, language, retail, price_1_100, price_101_500, price_501_1000, price_1001_5000):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO product_info
                (product_name, product_size, category, language, retail_price, price_1_100, price_101_500, price_501_1000, price_1001_5000)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (name, size, category, language, retail, price_1_100, price_101_500, price_501_1000, price_1001_5000))
            connection.commit()
            print(f"✅ 새 제품 '{name}' 이 등록되었습니다!")
    finally:
        connection.close()

# 키워드 검색
def search_products_by_keyword(keyword):
    connection = get_connection()
    keyword = f"%{keyword.upper()}%"
    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT * FROM product_info
                WHERE UPPER(product_name) LIKE %s
            """
            cursor.execute(sql, (keyword,))
            results = cursor.fetchall()

            if results:
                print(f"✅ '{keyword}' 검색 결과 ({len(results)}개):")
                for product in results:
                    print(f"- {product['product_name']} ({product['category']})")
                    print(f"  소매가: {product['retail_price']} Baht")
            else:
                print(f"❌ '{keyword}' 키워드로 검색된 제품이 없습니다.")
    finally:
        connection.close()

# 카테고리별 조회
def get_products_by_category(category):
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT * FROM product_info
                WHERE category = %s
            """
            cursor.execute(sql, (category,))
            results = cursor.fetchall()

            print(f"✅ 카테고리 '{category}' 조회 결과 ({len(results)}개):")
            for product in results:
                print(f"- {product['product_name']} ({product['product_size']})")
                print(f"  소매가: {product['retail_price']} Baht")
    finally:
        connection.close()
