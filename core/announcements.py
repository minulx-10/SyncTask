import datetime
import os
from pathlib import Path
from typing import Any

import discord

from utils.ui import brand_footer


kst = datetime.timezone(datetime.timedelta(hours=9))

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "web" / "uploads" / "announcements"
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

ANNOUNCEMENT_COLUMNS = [
    "id",
    "guild_id",
    "channel_id",
    "target_type",
    "target_label",
    "template_key",
    "title",
    "body",
    "date_text",
    "location",
    "deadline",
    "materials",
    "note",
    "image_filename",
    "scheduled_at",
    "status",
    "message_id",
    "sent_at",
    "last_error",
    "created_by",
    "created_at",
    "updated_at",
]

TARGET_TYPES = ["전체", "1학년", "2학년", "3학년", "반별", "동아리", "기타"]

TEMPLATES: dict[str, dict[str, Any]] = {
    "general": {
        "label": "일반 공지",
        "emoji": "📣",
        "color": 0x6366F1,
        "default_title": "공지 안내",
        "body_label": "공지 내용",
    },
    "performance": {
        "label": "수행평가",
        "emoji": "📌",
        "color": 0xFB923C,
        "default_title": "수행평가 안내",
        "body_label": "수행평가 내용",
    },
    "exam": {
        "label": "시험",
        "emoji": "📝",
        "color": 0xA855F7,
        "default_title": "시험 안내",
        "body_label": "시험 범위/안내",
    },
    "materials": {
        "label": "준비물",
        "emoji": "🎒",
        "color": 0x2DD4BF,
        "default_title": "준비물 안내",
        "body_label": "준비물 안내",
    },
    "schedule": {
        "label": "일정 안내",
        "emoji": "🏫",
        "color": 0x38BDF8,
        "default_title": "일정 안내",
        "body_label": "일정 내용",
    },
}

STATUS_LABELS = {
    "scheduled": "예약됨",
    "sending": "발송 중",
    "sent": "발송 완료",
    "failed": "발송 실패",
    "cancelled": "취소됨",
}


class AnnouncementValidationError(ValueError):
    pass


def now_kst() -> datetime.datetime:
    return datetime.datetime.now(kst)


def format_dt(value: datetime.datetime | None = None) -> str:
    value = value or now_kst()
    return value.astimezone(kst).strftime("%Y-%m-%d %H:%M:%S")


def row_to_announcement(row) -> dict[str, Any]:
    if row is None:
        return {}
    return {key: row[index] for index, key in enumerate(ANNOUNCEMENT_COLUMNS)}


def clean_text(value: Any, max_len: int, required: bool = False, field_name: str = "값") -> str:
    text = str(value or "").strip()
    if required and not text:
        raise AnnouncementValidationError(f"{field_name}을(를) 입력해주세요.")
    if len(text) > max_len:
        raise AnnouncementValidationError(f"{field_name}은(는) {max_len}자 이내로 입력해주세요.")
    return text


def parse_scheduled_at(value: str | None, *, require_future: bool) -> str:
    text = (value or "").strip()
    if not text:
        if require_future:
            raise AnnouncementValidationError("예약 시간을 입력해주세요.")
        return format_dt()

    candidates = [text]
    if "T" in text:
        candidates.append(text.replace("T", " "))

    parsed = None
    for candidate in candidates:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.datetime.strptime(candidate, fmt)
                break
            except ValueError:
                continue
        if parsed:
            break

    if not parsed:
        raise AnnouncementValidationError("예약 시간 형식이 올바르지 않습니다.")

    parsed = parsed.replace(tzinfo=kst)
    if require_future and parsed < now_kst() - datetime.timedelta(seconds=30):
        raise AnnouncementValidationError("예약 시간은 현재 이후로 설정해주세요.")
    return format_dt(parsed)


def target_display(data: dict[str, Any]) -> str:
    target_type = data.get("target_type") or "전체"
    target_label = data.get("target_label") or ""
    if target_type == "전체":
        return "전체"
    return f"{target_type} · {target_label}" if target_label else target_type


def normalize_announcement_input(
    raw: dict[str, Any],
    *,
    image_filename: str | None = None,
    require_body: bool = True,
    immediate: bool = False,
) -> dict[str, Any]:
    template_key = clean_text(raw.get("template_key"), 40, required=True, field_name="공지 양식")
    if template_key not in TEMPLATES:
        raise AnnouncementValidationError("지원하지 않는 공지 양식입니다.")

    target_type = clean_text(raw.get("target_type") or "전체", 20, field_name="대상")
    if target_type not in TARGET_TYPES:
        raise AnnouncementValidationError("지원하지 않는 대상 구분입니다.")

    guild_id = clean_text(raw.get("guild_id"), 32, field_name="서버")
    channel_id = clean_text(raw.get("channel_id"), 32, field_name="채널")
    if guild_id and not guild_id.isdigit():
        raise AnnouncementValidationError("서버 값이 올바르지 않습니다.")
    if channel_id and not channel_id.isdigit():
        raise AnnouncementValidationError("채널 값이 올바르지 않습니다.")

    template = TEMPLATES[template_key]
    title = clean_text(raw.get("title") or template["default_title"], 120, required=True, field_name="제목")
    body = clean_text(raw.get("body"), 1800, required=require_body, field_name="내용")

    scheduled_at = format_dt() if immediate else parse_scheduled_at(raw.get("scheduled_at"), require_future=True)

    return {
        "guild_id": int(guild_id) if guild_id else None,
        "channel_id": int(channel_id) if channel_id else None,
        "target_type": target_type,
        "target_label": clean_text(raw.get("target_label"), 80, field_name="대상 설명"),
        "template_key": template_key,
        "title": title,
        "body": body,
        "date_text": clean_text(raw.get("date_text"), 120, field_name="일시"),
        "location": clean_text(raw.get("location"), 120, field_name="장소"),
        "deadline": clean_text(raw.get("deadline"), 120, field_name="마감/제출"),
        "materials": clean_text(raw.get("materials"), 700, field_name="준비물"),
        "note": clean_text(raw.get("note"), 700, field_name="비고"),
        "image_filename": image_filename or clean_text(raw.get("image_filename"), 200, field_name="이미지"),
        "scheduled_at": scheduled_at,
    }


def build_announcement_preview(data: dict[str, Any]) -> dict[str, Any]:
    template = TEMPLATES[data["template_key"]]
    display = target_display(data)
    fields = [{"name": "대상", "value": display}]

    optional_fields = [
        ("일시", data.get("date_text")),
        ("장소", data.get("location")),
        ("마감/제출", data.get("deadline")),
        ("준비물", data.get("materials")),
        ("비고", data.get("note")),
    ]
    for name, value in optional_fields:
        if value:
            fields.append({"name": name, "value": value})

    description = data.get("body") or "내용을 입력해주세요."
    return {
        "title": f"{template['emoji']}  {data['title']}",
        "description": description,
        "fields": fields,
        "color": f"#{template['color']:06x}",
        "footer": "SyncTask · 교사용 공지",
        "template_label": template["label"],
        "status_label": STATUS_LABELS.get(data.get("status", "scheduled"), "예약됨"),
    }


def build_discord_embed(data: dict[str, Any]) -> discord.Embed:
    preview = build_announcement_preview(data)
    color = int(preview["color"].replace("#", ""), 16)
    item = discord.Embed(title=preview["title"], description=preview["description"], color=color)
    for field in preview["fields"]:
        item.add_field(name=field["name"], value=field["value"], inline=False)
    brand_footer(item, preview["footer"])
    return item


def get_upload_path(image_filename: str | None) -> Path | None:
    if not image_filename:
        return None
    safe_name = os.path.basename(image_filename)
    return UPLOAD_DIR / safe_name


async def create_announcement(db, data: dict[str, Any], *, created_by: str = "web") -> int:
    now = format_dt()
    cursor = await db.execute(
        """
        INSERT INTO announcements (
            guild_id, channel_id, target_type, target_label, template_key,
            title, body, date_text, location, deadline, materials, note,
            image_filename, scheduled_at, status, created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?)
        """,
        (
            data["guild_id"],
            data["channel_id"],
            data["target_type"],
            data["target_label"],
            data["template_key"],
            data["title"],
            data["body"],
            data["date_text"],
            data["location"],
            data["deadline"],
            data["materials"],
            data["note"],
            data["image_filename"],
            data["scheduled_at"],
            created_by,
            now,
            now,
        ),
    )
    await db.commit()
    return cursor.lastrowid


async def fetch_announcement(db, announcement_id: int) -> dict[str, Any] | None:
    async with db.execute(
        f"SELECT {', '.join(ANNOUNCEMENT_COLUMNS)} FROM announcements WHERE id=?",
        (announcement_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return row_to_announcement(row) if row else None


async def list_announcements(db, limit: int = 80) -> list[dict[str, Any]]:
    async with db.execute(
        f"""
        SELECT {', '.join(ANNOUNCEMENT_COLUMNS)}
        FROM announcements
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [row_to_announcement(row) for row in rows]


async def cancel_announcement(db, announcement_id: int) -> bool:
    now = format_dt()
    cursor = await db.execute(
        """
        UPDATE announcements
        SET status='cancelled', last_error=NULL, updated_at=?
        WHERE id=? AND status IN ('scheduled', 'failed')
        """,
        (now, announcement_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def claim_announcement(db, announcement_id: int, *, allow_failed: bool = False) -> dict[str, Any] | None:
    statuses = ("scheduled", "failed") if allow_failed else ("scheduled",)
    placeholders = ", ".join("?" for _ in statuses)
    now = format_dt()
    cursor = await db.execute(
        f"""
        UPDATE announcements
        SET status='sending', last_error=NULL, updated_at=?
        WHERE id=? AND status IN ({placeholders})
        """,
        (now, announcement_id, *statuses),
    )
    await db.commit()
    if cursor.rowcount <= 0:
        return None
    return await fetch_announcement(db, announcement_id)


async def claim_due_announcements(db, *, limit: int = 10) -> list[dict[str, Any]]:
    now = format_dt()
    async with db.execute(
        """
        SELECT id
        FROM announcements
        WHERE status='scheduled' AND scheduled_at <= ?
        ORDER BY scheduled_at ASC, id ASC
        LIMIT ?
        """,
        (now, limit),
    ) as cursor:
        rows = await cursor.fetchall()

    claimed = []
    for (announcement_id,) in rows:
        item = await claim_announcement(db, announcement_id)
        if item:
            claimed.append(item)
    return claimed


async def mark_sent(db, announcement_id: int, message_id: int | None) -> None:
    now = format_dt()
    await db.execute(
        """
        UPDATE announcements
        SET status='sent', message_id=?, sent_at=?, last_error=NULL, updated_at=?
        WHERE id=?
        """,
        (str(message_id) if message_id else None, now, now, announcement_id),
    )
    await db.commit()


async def mark_failed(db, announcement_id: int, error: str) -> None:
    now = format_dt()
    await db.execute(
        """
        UPDATE announcements
        SET status='failed', last_error=?, updated_at=?
        WHERE id=?
        """,
        (error[:700], now, announcement_id),
    )
    await db.commit()


async def send_claimed_announcement(bot, db, data: dict[str, Any]) -> None:
    announcement_id = int(data["id"])
    try:
        channel = bot.get_channel(int(data["channel_id"]))
        if channel is None:
            channel = await bot.fetch_channel(int(data["channel_id"]))
        if channel is None or not hasattr(channel, "send"):
            raise RuntimeError("발송할 채널을 찾을 수 없습니다.")

        item = build_discord_embed(data)
        file = None
        image_path = get_upload_path(data.get("image_filename"))
        if image_path and image_path.exists():
            attachment_name = f"announcement-{announcement_id}{image_path.suffix.lower()}"
            file = discord.File(str(image_path), filename=attachment_name)
            item.set_image(url=f"attachment://{attachment_name}")

        content = f"**공지 · {target_display(data)}**"
        message = await channel.send(
            content=content,
            embed=item,
            file=file,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await mark_sent(db, announcement_id, message.id)
    except Exception as exc:
        await mark_failed(db, announcement_id, str(exc))
        raise


async def send_announcement_by_id(bot, db, announcement_id: int, *, allow_failed: bool = False) -> bool:
    data = await claim_announcement(db, announcement_id, allow_failed=allow_failed)
    if not data:
        return False
    await send_claimed_announcement(bot, db, data)
    return True
