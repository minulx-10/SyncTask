# SyncTask (GSM 알리미)

GSM(광주소프트웨어마이스터고등학교) 학생들을 위한 학급 일정 및 시간표 관리 디스코드 봇입니다.

## 🚀 주요 기능
- **실시간 대시보드**: `/공지설정`을 통해 채널에 고정된 일정 대시보드를 생성합니다.
- **시간표 자동 조회**: 나이스(NEIS) API를 연동하여 오늘의 시간표를 자동으로 보여줍니다.
- **일정 관리**: 숙제, 수행평가, 기타 일정을 등록하고 D-Day를 확인합니다.
- **시험 관리**: 중간/기말고사 기간 설정 및 과목별 시험 범위를 관리합니다.
- **자동 알림**: 매일 아침(7:30)과 저녁(19:30)에 당일 및 다음 날 일정을 브리핑합니다.
- **관리자 CCTV**: 웹 인터페이스를 통해 봇의 명령어 로그를 실시간으로 모니터링합니다.
- **개인 알림/주간 요약**: `/알림설정`, `/주간요약`으로 개인별 확인 흐름을 지원합니다.

## 🛠 설치 및 실행 방법

### 1. 환경 변수 설정
`.env` 파일을 생성하고 아래 항목을 입력합니다.
```env
DISCORD_TOKEN=your_discord_bot_token
NEIS_API_KEY=your_neis_api_key
ADMIN_PASSWORD=strong_admin_password
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=10000
```

`ADMIN_PASSWORD`가 없으면 관리자 웹 대시보드 로그인이 잠깁니다.
외부 접속이 필요할 때만 `DASHBOARD_HOST=0.0.0.0`으로 변경하세요.

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. 실행
```bash
python main.py
```

## 📂 프로젝트 구조
- `main.py`: 봇의 메인 로직 및 웹 서버
- `school_tasks.db`: 데이터베이스 (SQLite)
- `requirements.txt`: 필요한 라이브러리 목록
- `.env`: 환경 변수 설정 (보안 주의)

## 📡 CI/CD
GitHub Actions를 통해 서버에 자동 배포되도록 설정되어 있습니다.
`main` 브랜치에 푸시하면 서버에서 자동으로 최신 코드를 반영하고 재시작합니다.
