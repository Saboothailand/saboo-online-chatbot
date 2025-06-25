from product_manager.product_functions import add_new_product, get_all_products

# 테스트용 제품 추가
add_new_product(
    name='Lavender Soap',
    size='100g',
    category='Soap',
    language='EN',
    retail_price=10.0,
    price_1_100=9.5,
    price_101_500=9.0,
    price_501_1000=8.5,
    price_1001_5000=8.0,
    barcode='1234567890123',
    fda_no='FDA-2025-TH-001'
)

# 제품 목록 조회
products = get_all_products()
for product in products:
    print(product)
