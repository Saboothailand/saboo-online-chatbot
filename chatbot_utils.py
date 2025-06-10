import os
import json
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ✅ .env 파일에서 환경변수 불러오기
load_dotenv()

def load_sheet():
    try:
        # Railway에서 JSON 키를 환경변수로 직접 가져오기
        service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not service_account_json:
            raise ValueError("❌ GOOGLE_SERVICE_ACCOUNT_JSON 환경변수가 설정되지 않았습니다.")

        # JSON 문자열을 파이썬 딕셔너리로 변환
        service_account_info = json.loads(service_account_json)
        
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]

        # 최신 google-auth 라이브러리 사용
        creds = Credentials.from_service_account_info(service_account_info, scopes=scope)
        client = gspread.authorize(creds)

        # Google Sheets 접근
        sheet = client.open_by_key("1PSuTYr_UnpEAwdFQz-Ky9pnJrMq0_CVvseJdAKXtDIM").sheet1
        raw_values = sheet.get_all_values()
        
        if not raw_values:
            return "⚠️ 구글 시트가 비어있습니다."

        # 데이터 처리
        transposed = list(zip(*raw_values))
        header = transposed[0]
        rows = transposed[1:]

        result = []
        for col in rows:
            entry = [f"{key.strip()}: {value.strip()}" for key, value in zip(header, col) if value.strip()]
            if entry:  # 빈 항목 제외
                result.append(" | ".join(entry))

        return "\n".join(result) if result else "⚠️ 유효한 데이터가 없습니다."

    except json.JSONDecodeError:
        print("❌ Google Service Account JSON 형식이 잘못되었습니다.")
        return "⚠️ Google 인증 설정 오류입니다."
    except Exception as e:
        print(f"❌ Google Sheet 불러오기 실패: {e}")
        return "⚠️ 구글 시트를 불러올 수 없습니다."


def load_doc():
    try:
        # Railway에서 JSON 키를 환경변수로 직접 가져오기
        service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not service_account_json:
            raise ValueError("❌ GOOGLE_SERVICE_ACCOUNT_JSON 환경변수가 설정되지 않았습니다.")

        # JSON 문자열을 파이썬 딕셔너리로 변환
        service_account_info = json.loads(service_account_json)
        
        scopes = ['https://www.googleapis.com/auth/documents.readonly']
        
        # 최신 google-auth 라이브러리 사용
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        service = build('docs', 'v1', credentials=creds)

        document_id = '1v9WbbjDHlI5dT8nwvmEKxiFjFZ8IAAYM_k2LM57kHKY'
        doc = service.documents().get(documentId=document_id).execute()

        text = ""
        for content in doc.get('body', {}).get('content', []):
            if 'paragraph' in content:
                for element in content.get('paragraph', {}).get('elements', []):
                    if 'textRun' in element:
                        text += element['textRun'].get('content', '')
        
        return text.strip() if text.strip() else "⚠️ 구글 문서가 비어있습니다."

    except json.JSONDecodeError:
        print("❌ Google Service Account JSON 형식이 잘못되었습니다.")
        return "⚠️ Google 인증 설정 오류입니다."
    except Exception as e:
        print(f"❌ Google Docs 불러오기 실패: {e}")
        return "⚠️ 구글 문서를 불러올 수 없습니다."