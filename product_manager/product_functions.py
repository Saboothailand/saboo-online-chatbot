from product_manager.db_config import get_connection

# ✅ 제품 추가
def add_new_product(name, size, category, language, retail_price, price_1_100, price_101_500, price_501_1000, price_1001_5000, barcode, fda_no):
    # 빈 값 처리
    if not barcode:
        barcode = ''
    if not fda_no:
        fda_no = ''

    db = get_connection()
    cursor = db.cursor()

    sql = """
    INSERT INTO products (name, size, category, language, retail_price, price_1_100, price_101_500, price_501_1000, price_1001_5000, barcode, fda_no)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    val = (name, size, category, language, retail_price, price_1_100, price_101_500, price_501_1000, price_1001_5000, barcode, fda_no)
    cursor.execute(sql, val)
    db.commit()
    db.close()
    print(f"새 제품 '{name}'이 추가되었습니다!")

# ✅ 제품 전체 목록 조회
def get_all_products():
    db = get_connection()
    cursor = db.cursor()

    sql = "SELECT * FROM products ORDER BY id DESC"
    cursor.execute(sql)
    result = cursor.fetchall()
    db.close()

    return result
