from googleapiclient.discovery import build
from google.oauth2 import service_account

# 인증 설정
SERVICE_ACCOUNT_FILE = 'saboomap-528e7c1b24f5.json'  # 실제 JSON 키 파일 이름
SCOPES = ['https://www.googleapis.com/auth/documents.readonly']

# 문서 ID (구글 문서 링크에서 복사)
DOCUMENT_ID = '1v9WbbjDHlI5dT8nwvmEKxiFjFZ8IAAYM_k2LM57kHKY'

# 인증 객체 생성
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)

# 구글 Docs API 클라이언트 생성
service = build('docs', 'v1', credentials=creds)

# 문서 가져오기
doc = service.documents().get(documentId=DOCUMENT_ID).execute()

# 본문 텍스트 추출
text = ""
for content in doc.get('body').get('content', []):
    if 'paragraph' in content:
        for element in content['paragraph']['elements']:
            if 'textRun' in element:
                text += element['textRun']['content']

# 결과 출력
print("문서 내용:\n")
print(text)
