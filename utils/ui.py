import datetime

import discord

# ──────────────────────────────────────────────
# Design System: "Quiet Signal"
# 화려하되 시끄럽지 않고, 정보가 한눈에 들어오는 디자인
# ──────────────────────────────────────────────

# ── Color Palette ────────────────────────────
# 채도를 약간 낮춘 모던한 톤. 각 기능이 고유한 '감정 색'을 갖는다.
BRAND_COLOR     = 0x2B2D31   # 디스코드 다크 기본 — 무채색 기반
SUCCESS_COLOR   = 0x57F287   # 민트 그린 — 성공/완료
WARNING_COLOR   = 0xFEE75C   # 소프트 옐로 — 주의/경고
ERROR_COLOR     = 0xED4245   # 레드 — 오류/거절
MUTED_COLOR     = 0x99AAB5   # 쿨 그레이 — 보조 정보
SETUP_COLOR     = 0x5865F2   # 블루퍼플 — 설정/가이드
SCHEDULE_COLOR  = 0x3498DB   # 스카이 블루 — 시간표/학사
TASK_COLOR      = 0xE67E22   # 앰버 — 숙제/수행평가
EXAM_COLOR      = 0xAD6BEA   # 라벤더 — 시험
REMINDER_COLOR  = 0x2EECD6   # 틸 민트 — 알림/요약
HISTORY_COLOR   = 0x7C8DB0   # 슬레이트 — 이력/로그
DASHBOARD_COLOR = 0xF47FFF   # 소프트 핑크 — 대시보드
BOOT_COLOR      = 0x57F287   # 민트 그린 — 가동 보고

# ── Emoji Prefix ──────────────────────────────
# 일관된 이모지 언어. 모든 임베드 타이틀에 통일적으로 사용.
E_TODAY     = "📋"
E_SCHEDULE  = "🏫"
E_TASK      = "📌"
E_EXAM      = "📝"
E_REMINDER  = "🔔"
E_SETTING   = "⚙️"
E_HELP      = "📖"
E_HISTORY   = "📜"
E_DASHBOARD = "📊"
E_BOOT      = "🟢"
E_WARN      = "⚠️"
E_OK        = "✅"
E_DENY      = "🚫"
E_CLOCK     = "🕐"
E_STAR      = "✨"

# ── Layout Constants ──────────────────────────
FOOTER_TEXT = "SyncTask · GSM 알리미"
DIVIDER = "─" * 26


# ── Embed Builders ────────────────────────────

def embed(title: str, description: str | None = None, color: int = BRAND_COLOR) -> discord.Embed:
    """기본 임베드. 모든 응답의 기반이 되는 빌더."""
    item = discord.Embed(title=title, description=description, color=color)
    item.set_footer(text=FOOTER_TEXT)
    return item


def dated_embed(title: str, description: str | None = None, color: int = BRAND_COLOR) -> discord.Embed:
    """타임스탬프가 포함된 임베드. 시간표/일정 등 날짜가 중요한 응답에 사용."""
    item = embed(title, description, color)
    item.timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    return item


# ── Text Feedback ──────────────────────────────

def ok(message: str) -> str:
    return f"{E_OK} {message}"


def warn(message: str) -> str:
    return f"{E_WARN} {message}"


def deny(message: str) -> str:
    return f"{E_DENY} {message}"
