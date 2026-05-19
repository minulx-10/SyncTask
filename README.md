<div align="center">

# 🔄 SyncTask (GSM 알리미)

광주소프트웨어마이스터고등학교(GSM) 학생들을 위한 **학급 일정 관리 및 알림 디스코드 봇**입니다.  
NEIS 학사일정 자동 연동부터 수행평가, 숙제, 시험 범위 관리까지 한곳에서 관리하세요.

</div>

## 🚀 주요 기능

- **NEIS API 연동 (학사일정/시간표)**:
  - 매일 자정 자동으로 나이스(NEIS) 시간표를 조회합니다.
  - `/시험일정동기화` 명령어로 현재 학기의 지필평가(중간/기말) 기간을 자동으로 감지해 설정합니다.
- **스마트 대시보드 (Discord)**:
  - `/공지설정`을 통해 채널에 상시 업데이트되는 통합 일정 대시보드(Embed)를 고정합니다.
  - 오늘/내일 시간표, 수행평가, 숙제, 시험 범위, D-Day가 한눈에 보입니다.
- **관리자 웹 대시보드 (Web UI)**:
  - `aiohttp` 기반으로 구동되는 관리자 전용 웹 모니터링 페이지를 제공합니다.
  - 실시간으로 봇 명령어 사용 로그(누가, 어떤 서버에서, 무슨 명령어를 썼는지)를 모니터링할 수 있습니다.
- **교사용 공지 작성/예약 (Web UI)**:
  - `/announcements`에서 선생님이 공지 양식, 대상, 채널, 예약 시간을 선택해 공지를 등록할 수 있습니다.
  - 일반 공지, 수행평가, 시험, 준비물, 일정 안내 템플릿을 제공하고 이미지 첨부를 지원합니다.
  - 예약된 공지는 봇이 자동 발송하며, 실패/취소/발송 완료 상태를 웹에서 확인할 수 있습니다.
- **자동 브리핑 알림**:
  - 매일 아침(7:30)에 오늘 일정, 저녁(19:30)에 내일 일정을 요약해서 알려줍니다.

---

## 🛠 설치 및 실행 방법

### 1. 환경 변수 설정
최상위 경로에 `.env` 파일을 생성하고 아래 항목을 입력합니다.

```env
DISCORD_TOKEN=your_discord_bot_token
NEIS_API_KEY=your_neis_api_key
ADMIN_PASSWORD=strong_admin_password
DASHBOARD_PUBLIC_URL=https://your-dashboard.example.com
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=10000
GUILD_SYNC_ON_READY=1
```

> **Note**: `ADMIN_PASSWORD`를 설정하지 않으면 웹 대시보드 로그인이 비활성화됩니다.

### 2. 의존성 설치
Python 3.10 이상을 권장합니다.
```bash
pip install -r requirements.txt
```

### 3. 실행
```bash
python main.py
```

---

## 📂 프로젝트 아키텍처

이 프로젝트는 모듈화된 **Cog 아키텍처**와 뷰/로직이 분리된 구조를 따릅니다.

```text
SyncTask/
├── main.py                # 봇 엔트리포인트 및 초기 설정
├── core/
│   ├── announcements.py   # 교사용 공지 템플릿/예약 발송 공통 로직
│   └── neis_api.py        # NEIS OpenAPI 통신 (시간표/학사일정/시험 감지)
├── cogs/                  # 기능별 디스코드 Cog 모듈
│   ├── announcements.py   # 예약 공지 자동 발송 루프
│   ├── admin.py           # 일정 추가/수정/삭제 및 관리 명령어
│   ├── school.py          # 시간표/시험범위 조회 및 동기화 명령어
│   └── tasks.py           # 아침/저녁 브리핑 및 자동 새로고침 루프
├── web/                   # 웹 대시보드 모듈
│   ├── server.py          # aiohttp 기반 웹 서버 
│   ├── templates/         # HTML 템플릿 (login.html, dashboard.html, announcements.html)
│   └── uploads/           # 공지 이미지 업로드 저장소 (자동 생성)
├── utils/
│   └── ui.py              # "Quiet Signal" 디자인 시스템 (Embed/Button 통합)
├── requirements.txt       # 의존성 패키지
└── school_tasks.db        # SQLite 데이터베이스 (자동 생성됨)
```

---

## 🎨 디자인 철학: *Quiet Signal*
- **시각적 일관성**: 디스코드 내 Embed는 불필요한 시각적 노이즈를 줄이고 일관된 컬러 팔레트를 유지합니다.
- **명확한 피드백**: 성공(`✅`), 경고(`⚠️`), 실패(`❌`) 등 이모지를 활용하여 유저에게 직관적으로 상태를 전달합니다.
- **웹 대시보드 통일성**: 모바일과 데스크톱을 모두 지원하는 반응형 UI(Inter 폰트 적용)로 디스코드와 유사한 다크 테마 감성을 이어갑니다.

---

## 📡 CI/CD 배포
이 프로젝트는 **GitHub Actions**를 통해 서버에 자동 배포됩니다.
`main` 브랜치에 코드가 푸시되면 원격 인스턴스에서 자동으로 `git pull` 후 `systemctl restart`가 트리거됩니다.
