import os
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from google.oauth2 import service_account

# ✅ .env 파일에서 환경변수 불러오기
load_dotenv()

# ✅ 환경변수 확인용 출력
print("✅ GOOGLE_APPLICATION_CREDENTIALS:", os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))


def load_sheet():
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]

    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not key_path or not os.path.exists(key_path):
        raise FileNotFoundError("❌ Google 서비스 계정 키 파일 경로가 잘못되었거나 존재하지 않습니다.")

    creds = ServiceAccountCredentials.from_json_keyfile_name(key_path, scope)
    client = gspread.authorize(creds)

    try:
        sheet = client.open_by_key("1PSuTYr_UnpEAwdFQz-Ky9pnJrMq0_CVvseJdAKXtDIM").sheet1
        raw_values = sheet.get_all_values()
    except Exception as e:
        print(f"❌ Google Sheet 불러오기 실패: {e}")
        return "⚠️ 구글 시트를 불러올 수 없습니다."

    transposed = list(zip(*raw_values))
    header = transposed[0]
    rows = transposed[1:]

    result = []
    for col in rows:
        entry = [f"{key.strip()}: {value.strip()}" for key, value in zip(header, col)]
        result.append(" | ".join(entry))

    return "\n".join(result)


def load_doc():
    scopes = ['https://www.googleapis.com/auth/documents.readonly']
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not key_path or not os.path.exists(key_path):
        raise FileNotFoundError("❌ Google 서비스 계정 키 파일 경로가 잘못되었거나 존재하지 않습니다.")

    try:
        creds = service_account.Credentials.from_service_account_file(
            key_path, scopes=scopes)
        service = build('docs', 'v1', credentials=creds)

        document_id = '1v9WbbjDHlI5dT8nwvmEKxiFjFZ8IAAYM_k2LM57kHKY'
        doc = service.documents().get(documentId=document_id).execute()

        text = ""
        for content in doc.get('body').get('content', []):
            if 'paragraph' in content:
                for element in content['paragraph']['elements']:
                    if 'textRun' in element:
                        text += element['textRun']['content']
        return text

    except Exception as e:
        print(f"❌ Google Docs 불러오기 실패: {e}")
        return "⚠️ 구글 문서를 불러올 수 없습니다."
