import datetime

import discord

# ──────────────────────────────────────────────
# Design System: "Quiet Signal" v2
# 생생하되 정돈된, 정보가 한눈에 들어오는 디자인.
# 모든 임베드는 동일한 색 언어 · 이모지 언어 · 브랜드 푸터를 공유한다.
# ──────────────────────────────────────────────

# ── Color Palette ────────────────────────────
# Tailwind 500 계열을 기반으로 한 선명하고 조화로운 톤.
# 각 기능이 고유한 '감정 색'을 갖되, 전체가 한 세트로 보이도록 채도를 맞췄다.
BRAND_COLOR     = 0x6366F1   # 인디고 — 기본/브랜드 (배경에 묻히지 않는 메인 색)
SUCCESS_COLOR   = 0x22C55E   # 비비드 그린 — 성공/완료
WARNING_COLOR   = 0xF59E0B   # 앰버 — 주의/경고
ERROR_COLOR     = 0xEF4444   # 레드 — 오류/거절
MUTED_COLOR     = 0x94A3B8   # 슬레이트 그레이 — 보조 정보
SETUP_COLOR     = 0x6366F1   # 인디고 — 설정/가이드
SCHEDULE_COLOR  = 0x38BDF8   # 스카이 블루 — 시간표/학사
TASK_COLOR      = 0xFB923C   # 오렌지 — 숙제/수행평가
EXAM_COLOR      = 0xA855F7   # 퍼플 — 시험
REMINDER_COLOR  = 0x2DD4BF   # 틸 — 알림/요약
HISTORY_COLOR   = 0x64748B   # 슬레이트 — 이력/로그
DASHBOARD_COLOR = 0x06B6D4   # 시안 — 대시보드
BOOT_COLOR      = 0x22C55E   # 비비드 그린 — 가동 보고
MEAL_COLOR      = 0xD99A3A   # 카라멜 골드 — 급식 (따뜻하고 식욕 도는 톤)

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
E_MEAL      = "🍽️"

# ── Layout Constants ──────────────────────────
FOOTER_TEXT = "SyncTask · GSM 알리미"
DIVIDER = "─" * 26

# ── Brand Assets (런타임 주입) ─────────────────
# 봇 아바타 URL을 on_ready에서 set_brand_assets()로 넣으면,
# 모든 임베드 푸터/작성자 줄에 동일한 브랜드 아이콘이 붙어 일관성이 살아난다.
_BRAND_ICON: str | None = None
_BRAND_NAME: str = "SyncTask"


def set_brand_assets(name: str | None = None, icon_url: str | None = None) -> None:
    """봇 기동 시 브랜드 이름/아이콘을 등록한다. (utils.ui.set_brand_assets)"""
    global _BRAND_ICON, _BRAND_NAME
    if name:
        _BRAND_NAME = name
    if icon_url:
        _BRAND_ICON = icon_url


def brand_footer(item: discord.Embed, text: str = FOOTER_TEXT) -> discord.Embed:
    """임베드에 브랜드 아이콘이 포함된 푸터를 일관되게 적용한다."""
    item.set_footer(text=text, icon_url=_BRAND_ICON)
    return item


def brand_author(item: discord.Embed, name: str) -> discord.Embed:
    """임베드 상단 작성자 줄에 브랜드 아이콘과 카테고리 라벨을 붙인다."""
    item.set_author(name=name, icon_url=_BRAND_ICON)
    return item


# ── Embed Builders ────────────────────────────

def embed(
    title: str | None = None,
    description: str | None = None,
    color: int = BRAND_COLOR,
    *,
    author: str | None = None,
    thumbnail: str | None = None,
) -> discord.Embed:
    """기본 임베드. 모든 응답의 기반이 되는 빌더.

    author: 타이틀 위에 표시할 카테고리 라벨(브랜드 아이콘 동반).
    thumbnail: 우측 상단 썸네일 URL. 지정하지 않으면 채우지 않는다.
    """
    item = discord.Embed(title=title, description=description, color=color)
    if author:
        item.set_author(name=author, icon_url=_BRAND_ICON)
    if thumbnail:
        item.set_thumbnail(url=thumbnail)
    brand_footer(item)
    return item


def dated_embed(
    title: str | None = None,
    description: str | None = None,
    color: int = BRAND_COLOR,
    *,
    author: str | None = None,
    thumbnail: str | None = None,
) -> discord.Embed:
    """타임스탬프가 포함된 임베드. 시간표/일정 등 날짜가 중요한 응답에 사용."""
    item = embed(title, description, color, author=author, thumbnail=thumbnail)
    item.timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    return item


# ── Text Feedback ──────────────────────────────

def ok(message: str) -> str:
    return f"{E_OK} {message}"


def warn(message: str) -> str:
    return f"{E_WARN} {message}"


def deny(message: str) -> str:
    return f"{E_DENY} {message}"
