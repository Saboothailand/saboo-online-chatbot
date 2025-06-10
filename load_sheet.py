import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 인증 범위 설정
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

# 서비스 계정 키 파일
creds = ServiceAccountCredentials.from_json_keyfile_name('saboomap-528e7c1b24f5.json', scope)

# gspread 클라이언트 생성
client = gspread.authorize(creds)

# ✅ 문서 ID로 시트 열기
sheet = client.open_by_key("1PSuTYr_UnpEAwdFQz-Ky9pnJrMq0_CVvseJdAKXtDIM").sheet1

# 데이터 가져오기
data = sheet.get_all_records()

# 데이터 출력
for row in data:
    print(row)
