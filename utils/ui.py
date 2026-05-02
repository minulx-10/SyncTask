import datetime

import discord

BRAND_COLOR = 0x2B2D31
SUCCESS_COLOR = 0x3BA55C
WARNING_COLOR = 0xF0B232
ERROR_COLOR = 0xED4245
MUTED_COLOR = 0x5865F2
SETUP_COLOR = 0x5865F2
SCHEDULE_COLOR = 0x3498DB
TASK_COLOR = 0xF1C40F
EXAM_COLOR = 0x9B59B6
REMINDER_COLOR = 0x1ABC9C
HISTORY_COLOR = 0x95A5A6
DASHBOARD_COLOR = 0xE67E22

FOOTER_TEXT = "SyncTask"


def embed(title: str, description: str | None = None, color: int = BRAND_COLOR) -> discord.Embed:
    item = discord.Embed(title=title, description=description, color=color)
    item.set_footer(text=FOOTER_TEXT)
    return item


def dated_embed(title: str, description: str | None = None, color: int = BRAND_COLOR) -> discord.Embed:
    item = embed(title, description, color)
    item.timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    return item


def ok(message: str) -> str:
    return f"완료: {message}"


def warn(message: str) -> str:
    return f"확인 필요: {message}"


def deny(message: str) -> str:
    return f"권한 없음: {message}"
