import os
from dotenv import load_dotenv
from openai import OpenAI

# ✅ 환경변수 로드
load_dotenv()

# ✅ Google Sheets 불러오는 함수
def load_sheet():
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials

    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    # 환경변수에서 JSON 파일 경로 가져오기
    json_keyfile = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'saboo-online-7212295d629d.json')
    creds = ServiceAccountCredentials.from_json_keyfile_name(json_keyfile, scope)
    client = gspread.authorize(creds)

    sheet = client.open_by_key("1PSuTYr_UnpEAwdFQz-Ky9pnJrMq0_CVvseJdAKXtDIM").sheet1
    data = sheet.get_all_records()

    # ✅ 헤더 확인용 (한 줄만 출력)
    print("데이터 확인용 예시 한 줄:")
    print(data[0])

    # ✅ 컬럼 이름 수정 ('Expriy Date'는 시트에 맞춘 오타 포함)
    sheet_text = "\n".join([f"{row['No.']} - {row['Expiry Date']}" for row in data])
    return sheet_text

# ✅ Google Docs 불러오는 함수
def load_doc():
    from googleapiclient.discovery import build
    from google.oauth2 import service_account

    # 환경변수에서 JSON 파일 경로 가져오기
    SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'saboomap-528e7c1b24f5.json')
    SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
    DOCUMENT_ID = '1v9WbbjDHlI5dT8nwvmEKxiFjFZ8IAAYM_k2LM57kHKY'

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('docs', 'v1', credentials=creds)
    doc = service.documents().get(documentId=DOCUMENT_ID).execute()

    text = ""
    for content in doc.get('body').get('content', []):
        if 'paragraph' in content:
            for element in content['paragraph']['elements']:
                if 'textRun' in element:
                    text += element['textRun']['content']
    return text

# ✅ GPT API 클라이언트 설정 (환경변수에서 API 키 가져오기)
openai_api_key = os.getenv('OPENAI_API_KEY')
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다. .env 파일을 확인해주세요.")

client = OpenAI(api_key=openai_api_key)

# ✅ 데이터 불러오기
sheet_text = load_sheet()
doc_text = load_doc()
context_text = sheet_text + "\n\n" + doc_text

# ✅ 손님 질문
question = "임산부도 쓸 수 있는 비누 있어요?"

# ✅ GPT 호출 (최신 방식)
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "당신은 화장품 상담사이며 고객에게 가장 적절한 제품을 추천해야 합니다."},
        {"role": "user", "content": f"회사 문서 정보:\n{context_text}\n\n고객 질문: {question}"}
    ]
)

# ✅ 응답 출력
print("\n💬 GPT 응답:")
print(response.choices[0].message.content)