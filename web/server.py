from aiohttp import web
import aiohttp
import base64
import datetime
import json
import os
import re
import hmac
import hashlib
import html
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

import holidays

from core.announcements import (
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_IMAGE_BYTES,
    STATUS_LABELS,
    TARGET_TYPES,
    TEMPLATES,
    UPLOAD_DIR,
    AnnouncementValidationError,
    build_announcement_preview,
    cancel_announcement,
    create_announcement,
    fetch_announcement,
    format_dt,
    list_announcements,
    normalize_announcement_input,
    send_announcement_by_id,
    target_display,
)
from core.teacher_access import get_accessible_guild_ids, has_teacher_access
from core.neis_api import fetch_neis_timetable, fetch_neis_school_schedule
from utils.formatter import (
    parse_deadline, parse_exam_dates, get_cached_timetable, cache_timetable, kst,
)
from cogs.admin import SUPER_ADMINS

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
SESSION_COOKIE = "synctask_session"
OAUTH_STATE_COOKIE = "synctask_oauth_state"
SESSION_MAX_AGE = 60 * 60 * 24 * 7
DISCORD_API_BASE = "https://discord.com/api"

def _session_secret():
    base = (os.getenv("DISCORD_TOKEN") or "") + (ADMIN_PASSWORD or "")
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def _sign(value):
    return hmac.new(_session_secret().encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def make_legacy_admin_cookie():
    if not ADMIN_PASSWORD:
        return ""
    return hmac.new(_session_secret().encode("utf-8"), b"admin", hashlib.sha256).hexdigest()


def encode_session(payload):
    data = dict(payload)
    data["exp"] = int(time.time()) + SESSION_MAX_AGE
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{body}.{_sign(body)}"


def decode_session(cookie_value):
    if not cookie_value or "." not in cookie_value:
        return None
    body, signature = cookie_value.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(body)):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception:
        return None
    if int(data.get("exp", 0)) < int(time.time()):
        return None
    return data


def get_session(request):
    session = decode_session(request.cookies.get(SESSION_COOKIE, ""))
    if session:
        return session
    if ADMIN_PASSWORD and hmac.compare_digest(request.cookies.get('admin_session', ''), make_legacy_admin_cookie()):
        return {"type": "admin", "user_id": "0", "name": "관리자", "is_operator": True}
    return None

def is_authenticated(request):
    return get_session(request) is not None


def is_operator_session(session):
    if not session:
        return False
    if session.get("is_operator") or session.get("type") == "admin":
        return True
    user_id = str(session.get("user_id", ""))
    return user_id.isdigit() and int(user_id) in SUPER_ADMINS


def get_public_base_url(request=None):
    public_url = os.getenv("DASHBOARD_PUBLIC_URL")
    if public_url:
        return public_url.rstrip("/")
    if request:
        return str(request.url.origin()).rstrip("/")
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = os.getenv("DASHBOARD_PORT", "10000")
    return f"http://{host}:{port}"


def get_discord_client_id(request=None):
    client_id = os.getenv("DISCORD_CLIENT_ID")
    if client_id:
        return client_id
    bot = request.app.get("bot") if request else None
    if bot and bot.user:
        return str(bot.user.id)
    return ""


def get_discord_redirect_uri(request=None):
    configured = os.getenv("DISCORD_REDIRECT_URI")
    if configured:
        return configured
    return f"{get_public_base_url(request)}/auth/discord/callback"


def oauth_is_configured(request=None):
    return bool(get_discord_client_id(request) and os.getenv("DISCORD_CLIENT_SECRET"))


def build_discord_authorize_url(request):
    state = uuid.uuid4().hex
    params = {
        "client_id": get_discord_client_id(request),
        "redirect_uri": get_discord_redirect_uri(request),
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }
    return f"{DISCORD_API_BASE}/oauth2/authorize?{urlencode(params)}", state


def set_session_cookie(resp, payload):
    resp.set_cookie(
        SESSION_COOKIE,
        encode_session(payload),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=get_public_base_url().startswith("https://"),
    )
    resp.del_cookie("admin_session")
    return resp


async def get_allowed_guild_ids(request):
    session = get_session(request)
    if is_operator_session(session):
        return {guild.id for guild in request.app['bot'].guilds}
    user_id = str(session.get("user_id", "")) if session else ""
    if not user_id.isdigit():
        return set()
    return await get_accessible_guild_ids(request.app['db'], int(user_id))


async def can_access_guild(request, guild_id):
    session = get_session(request)
    if is_operator_session(session):
        return True
    user_id = str(session.get("user_id", "")) if session else ""
    if not user_id.isdigit():
        return False
    return await has_teacher_access(request.app['db'], int(guild_id), int(user_id))

async def auth_middleware(app, handler):
    async def middleware(request):
        public_paths = {'/login', '/do_login', '/auth/discord', '/auth/discord/callback', '/logout', '/'}
        if request.path.startswith('/static/') or request.path.startswith('/api/public/'):
            return await handler(request)
        if request.path in public_paths:
            return await handler(request)
        if not is_authenticated(request):
            if request.path.startswith('/api'):
                return web.json_response({"error": "Unauthorized"}, status=401)
            return web.HTTPFound('/login')
        return await handler(request)
    return middleware


def read_template(name):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, "templates", name)
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def json_error(message, status=400):
    return web.json_response({"ok": False, "error": message}, status=status)


async def record_web_change(db, guild_id, action, details, session=None):
    user_id = 0
    if session and str(session.get("user_id", "")).isdigit():
        user_id = int(session["user_id"])
    await db.execute(
        """
        INSERT INTO change_logs (guild_id, user_id, action, details, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (guild_id, user_id, action, details, format_dt()),
    )
    await db.commit()


def get_channel_label(bot, channel_id):
    channel = bot.get_channel(int(channel_id)) if channel_id else None
    if not channel:
        return str(channel_id or "")
    return f"#{getattr(channel, 'name', channel_id)}"


def serialize_announcement(bot, item):
    guild = bot.get_guild(int(item["guild_id"])) if item.get("guild_id") else None
    preview = build_announcement_preview(item)
    result = dict(item)
    result["guild_name"] = guild.name if guild else str(item.get("guild_id") or "")
    result["channel_name"] = get_channel_label(bot, item.get("channel_id"))
    result["target_display"] = target_display(item)
    result["status_label"] = STATUS_LABELS.get(item.get("status"), item.get("status"))
    result["preview"] = preview
    result["can_cancel"] = item.get("status") in ("scheduled", "failed")
    result["can_send_now"] = item.get("status") in ("scheduled", "failed")
    return result


async def save_uploaded_image(file_field):
    filename = getattr(file_field, "filename", "") or ""
    if not filename:
        return None

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
        raise AnnouncementValidationError(f"이미지는 {allowed} 형식만 업로드할 수 있습니다.")

    file_field.file.seek(0)
    content = file_field.file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise AnnouncementValidationError("이미지 용량은 5MB 이하만 업로드할 수 있습니다.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / stored_name).write_bytes(content)
    return stored_name

async def login_page(request):
    page = read_template("login.html")
    oauth_url = "/auth/discord" if oauth_is_configured(request) else ""
    oauth_status = "Discord 로그인을 사용할 수 있습니다." if oauth_url else "Discord OAuth 환경 변수가 아직 설정되지 않았습니다."
    page = (
        page.replace("{{OAUTH_URL}}", html.escape(oauth_url))
        .replace("{{OAUTH_STATUS}}", html.escape(oauth_status))
        .replace("{{PASSWORD_ENABLED}}", "1" if ADMIN_PASSWORD else "0")
        .replace("{{PUBLIC_URL}}", html.escape(f"{get_public_base_url(request)}/announcements"))
    )
    return web.Response(text=page, content_type='text/html')

async def do_login(request):
    if not ADMIN_PASSWORD:
        return web.HTTPFound('/login?error=not_configured')
    data = await request.post()
    if data.get('password') == ADMIN_PASSWORD:
        resp = web.HTTPFound('/announcements')
        return set_session_cookie(resp, {
            "type": "admin",
            "user_id": "0",
            "name": "관리자",
            "is_operator": True,
        })
    return web.HTTPFound('/login?error=1')


async def discord_login(request):
    if not oauth_is_configured(request):
        return web.HTTPFound('/login?error=oauth_not_configured')
    authorize_url, state = build_discord_authorize_url(request)
    resp = web.HTTPFound(authorize_url)
    resp.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True, samesite="Lax")
    return resp


async def discord_callback(request):
    if not oauth_is_configured(request):
        return web.HTTPFound('/login?error=oauth_not_configured')

    code = request.query.get("code")
    state = request.query.get("state")
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not state or not expected_state or not hmac.compare_digest(state, expected_state):
        return web.HTTPFound('/login?error=oauth_state')

    token_payload = {
        "client_id": get_discord_client_id(request),
        "client_secret": os.getenv("DISCORD_CLIENT_SECRET"),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": get_discord_redirect_uri(request),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{DISCORD_API_BASE}/oauth2/token", data=token_payload) as resp:
                if resp.status != 200:
                    return web.HTTPFound('/login?error=oauth_token')
                token_data = await resp.json()
            headers = {"Authorization": f"Bearer {token_data['access_token']}"}
            async with session.get(f"{DISCORD_API_BASE}/users/@me", headers=headers) as resp:
                if resp.status != 200:
                    return web.HTTPFound('/login?error=oauth_user')
                user_data = await resp.json()
    except Exception:
        return web.HTTPFound('/login?error=oauth_network')

    user_id = str(user_data["id"])
    name = user_data.get("global_name") or user_data.get("username") or user_id
    is_operator = user_id.isdigit() and int(user_id) in SUPER_ADMINS
    resp = web.HTTPFound('/announcements')
    resp.del_cookie(OAUTH_STATE_COOKIE)
    return set_session_cookie(resp, {
        "type": "discord",
        "user_id": user_id,
        "name": name,
        "username": user_data.get("username") or name,
        "avatar": user_data.get("avatar") or "",
        "is_operator": is_operator,
    })


async def logout(request):
    resp = web.HTTPFound('/login')
    resp.del_cookie(SESSION_COOKIE)
    resp.del_cookie("admin_session")
    resp.del_cookie(OAUTH_STATE_COOKIE)
    return resp

async def api_get_logs_json(request):
    try:
        if not is_operator_session(get_session(request)):
            return web.json_response({"error": "Forbidden"}, status=403)
        bot = request.app['bot']
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_path = os.path.join(BASE_DIR, "alimi_cmd_log.txt")
        if not os.path.exists(log_path): return web.json_response([])
        
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        parsed = []
        guild_icons = {}

        for line in reversed(lines):
            match = re.match(r"\[GID:(.*?)\] \[(.*?)\] \[(.*?)\] (?:👤)?(.*?): \/(.*?)(?: \((.*)\))?$", line.strip())
            if match:
                gid = match.group(1)
                if gid not in guild_icons:
                    if gid == "DM":
                        guild_icons[gid] = ""
                    else:
                        guild = bot.get_guild(int(gid))
                        guild_icons[gid] = str(guild.icon.url) if guild and guild.icon else ""

                parsed.append({
                    "guild_id": gid,
                    "time": match.group(2),
                    "guild_name": html.escape(match.group(3)),
                    "guild_icon": guild_icons[gid],
                    "user": html.escape(match.group(4)),
                    "command": html.escape(match.group(5)),
                    "details": html.escape(match.group(6) or "")
                })
        return web.json_response(parsed[:200])
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def home_page(request):
    page = read_template("home.html")
    return web.Response(text=page, content_type='text/html')


async def admin_log_dashboard(request):
    if not is_operator_session(get_session(request)):
        return web.HTTPFound('/')
    page = read_template("dashboard.html")
    return web.Response(text=page, content_type='text/html')


async def announcements_page(request):
    page = read_template("announcements.html")
    return web.Response(text=page, content_type='text/html')


async def api_me(request):
    session = get_session(request) or {}
    allowed_guild_ids = await get_allowed_guild_ids(request)
    return web.json_response({
        "ok": True,
        "user": {
            "id": str(session.get("user_id", "")),
            "name": session.get("name", "사용자"),
            "type": session.get("type", "discord"),
            "is_operator": is_operator_session(session),
        },
        "announcement_url": f"{get_public_base_url(request)}/announcements",
        "allowed_guild_count": len(allowed_guild_ids),
    })


async def api_announcement_context(request):
    bot = request.app['bot']
    session = get_session(request) or {}
    allowed_guild_ids = await get_allowed_guild_ids(request)
    guilds = []
    for guild in bot.guilds:
        if guild.id not in allowed_guild_ids:
            continue
        channels = []
        for channel in guild.text_channels:
            can_send = True
            if guild.me:
                perms = channel.permissions_for(guild.me)
                can_send = perms.view_channel and perms.send_messages
            if can_send:
                channels.append({"id": str(channel.id), "name": f"#{channel.name}"})
        guilds.append({
            "id": str(guild.id),
            "name": guild.name,
            "icon": str(guild.icon.url) if guild.icon else "",
            "channels": channels,
        })

    templates = [
        {
            "key": key,
            "label": value["label"],
            "body_label": value["body_label"],
            "color": f"#{value['color']:06x}",
        }
        for key, value in TEMPLATES.items()
    ]
    return web.json_response({
        "ok": True,
        "user": {
            "id": str(session.get("user_id", "")),
            "name": session.get("name", "사용자"),
            "type": session.get("type", "discord"),
            "is_operator": is_operator_session(session),
        },
        "guilds": guilds,
        "templates": templates,
        "target_types": TARGET_TYPES,
        "now": format_dt(),
        "has_access": bool(guilds),
        "announcement_url": f"{get_public_base_url(request)}/announcements",
    })


async def api_preview_announcement(request):
    try:
        data = await request.json()
        normalized = normalize_announcement_input(data, require_body=False, immediate=True)
        return web.json_response({"ok": True, "preview": build_announcement_preview(normalized)})
    except AnnouncementValidationError as exc:
        return json_error(str(exc))
    except Exception as exc:
        return json_error(str(exc), status=500)


async def api_list_announcements(request):
    bot = request.app['bot']
    db = request.app['db']
    items = await list_announcements(db)
    guild_id = request.query.get("guild_id")
    if guild_id:
        if not await can_access_guild(request, guild_id):
            return json_error("이 서버의 공지에 접근할 권한이 없습니다.", status=403)
        items = [item for item in items if str(item["guild_id"]) == guild_id]
    else:
        allowed_guild_ids = await get_allowed_guild_ids(request)
        items = [item for item in items if int(item["guild_id"]) in allowed_guild_ids]
    return web.json_response({
        "ok": True,
        "announcements": [serialize_announcement(bot, item) for item in items],
    })


async def api_create_announcement(request):
    bot = request.app['bot']
    db = request.app['db']
    session = get_session(request)
    image_filename = None
    try:
        form = await request.post()
        action = str(form.get("action") or "schedule")
        immediate = action == "immediate"
        raw = {
            "guild_id": form.get("guild_id"),
            "channel_id": form.get("channel_id"),
            "target_type": form.get("target_type"),
            "target_label": form.get("target_label"),
            "template_key": form.get("template_key"),
            "title": form.get("title"),
            "body": form.get("body"),
            "date_text": form.get("date_text"),
            "location": form.get("location"),
            "deadline": form.get("deadline"),
            "materials": form.get("materials"),
            "note": form.get("note"),
            "scheduled_at": form.get("scheduled_at"),
        }
        normalized = normalize_announcement_input(raw, require_body=True, immediate=immediate)
        if not normalized["guild_id"] or not normalized["channel_id"]:
            raise AnnouncementValidationError("서버와 발송 채널을 선택해주세요.")
        if not await can_access_guild(request, normalized["guild_id"]):
            return json_error("이 서버에 공지를 등록할 권한이 없습니다.", status=403)

        guild = bot.get_guild(int(normalized["guild_id"]))
        channel = bot.get_channel(int(normalized["channel_id"]))
        channel_guild_id = getattr(getattr(channel, "guild", None), "id", None)
        if not guild or not channel or channel_guild_id != guild.id:
            raise AnnouncementValidationError("선택한 서버와 채널을 확인해주세요.")

        image_field = form.get("image")
        if image_field and getattr(image_field, "filename", ""):
            image_filename = await save_uploaded_image(image_field)
            normalized["image_filename"] = image_filename

        created_by = f"{session.get('name', 'web')} ({session.get('user_id', '0')})" if session else "teacher_web"
        announcement_id = await create_announcement(db, normalized, created_by=created_by)
        await record_web_change(
            db,
            normalized["guild_id"],
            "공지등록",
            f"#{announcement_id} {normalized['title']} / {normalized['scheduled_at']}",
            session,
        )

        send_error = None
        if immediate:
            try:
                await send_announcement_by_id(bot, db, announcement_id)
            except Exception as exc:
                send_error = str(exc)

        item = await fetch_announcement(db, announcement_id)
        return web.json_response({
            "ok": send_error is None,
            "announcement": serialize_announcement(bot, item),
            "send_error": send_error,
        }, status=201 if send_error is None else 202)
    except AnnouncementValidationError as exc:
        if image_filename:
            try:
                (UPLOAD_DIR / image_filename).unlink(missing_ok=True)
            except Exception:
                pass
        return json_error(str(exc))
    except Exception as exc:
        return json_error(str(exc), status=500)


async def api_cancel_announcement(request):
    db = request.app['db']
    session = get_session(request)
    announcement_id = int(request.match_info["announcement_id"])
    item = await fetch_announcement(db, announcement_id)
    if not item:
        return json_error("공지를 찾을 수 없습니다.", status=404)
    if not await can_access_guild(request, item["guild_id"]):
        return json_error("이 공지를 취소할 권한이 없습니다.", status=403)
    ok = await cancel_announcement(db, announcement_id)
    if ok:
        await record_web_change(db, item["guild_id"], "공지취소", f"#{announcement_id} {item['title']}", session)
    updated = await fetch_announcement(db, announcement_id)
    return web.json_response({"ok": ok, "announcement": serialize_announcement(request.app['bot'], updated)})


async def api_send_announcement_now(request):
    bot = request.app['bot']
    db = request.app['db']
    session = get_session(request)
    announcement_id = int(request.match_info["announcement_id"])
    item = await fetch_announcement(db, announcement_id)
    if not item:
        return json_error("공지를 찾을 수 없습니다.", status=404)
    if not await can_access_guild(request, item["guild_id"]):
        return json_error("이 공지를 발송할 권한이 없습니다.", status=403)
    try:
        sent = await send_announcement_by_id(bot, db, announcement_id, allow_failed=True)
        if sent:
            await record_web_change(db, item["guild_id"], "공지즉시발송", f"#{announcement_id} {item['title']}", session)
        updated = await fetch_announcement(db, announcement_id)
        return web.json_response({"ok": sent, "announcement": serialize_announcement(bot, updated)})
    except Exception as exc:
        updated = await fetch_announcement(db, announcement_id)
        return web.json_response({
            "ok": False,
            "error": str(exc),
            "announcement": serialize_announcement(bot, updated),
        }, status=202)

# ═══════════════════════════════════════════════
# Public API — no authentication required
# ═══════════════════════════════════════════════

def _next_school_day(start_date):
    target_date = start_date + datetime.timedelta(days=1)
    kr_holidays = holidays.KR(years=[target_date.year, target_date.year + 1])
    while target_date.weekday() >= 5 or target_date.date() in kr_holidays:
        target_date += datetime.timedelta(days=1)
    return target_date


async def _resolve_guild_id(request):
    guild_id = request.query.get("guild_id")
    bot = request.app["bot"]
    if guild_id:
        return int(guild_id)
    if bot.guilds:
        return bot.guilds[0].id
    return None


async def _get_grade_class(db, guild_id):
    async with db.execute("SELECT value FROM config WHERE key='grade' AND guild_id=?", (guild_id,)) as c:
        g_row = await c.fetchone()
    async with db.execute("SELECT value FROM config WHERE key='class_nm' AND guild_id=?", (guild_id,)) as c:
        c_row = await c.fetchone()
    if g_row and c_row:
        return g_row[0], c_row[0]
    return None, None


async def api_public_guilds(request):
    bot = request.app["bot"]
    guilds = []
    for guild in bot.guilds:
        guilds.append({
            "id": str(guild.id),
            "name": guild.name,
            "icon": str(guild.icon.url) if guild.icon else "",
            "member_count": guild.member_count,
        })
    return web.json_response({"ok": True, "guilds": guilds})


async def api_public_schedule(request):
    bot = request.app["bot"]
    db = request.app["db"]
    guild_id = await _resolve_guild_id(request)
    if not guild_id:
        return web.json_response({"ok": False, "error": "서버를 찾을 수 없습니다."})

    is_tomorrow = request.match_info.get("when") == "tomorrow"
    now = datetime.datetime.now(kst)

    if is_tomorrow:
        target_date = _next_school_day(now)
    else:
        target_date = now

    weekday_num = target_date.weekday()
    weekday_str = ['월', '화', '수', '목', '금', '토', '일'][weekday_num]
    date_label = f"{target_date.month}월 {target_date.day}일 ({weekday_str})"

    if weekday_num >= 5:
        return web.json_response({
            "ok": True, "is_weekend": True, "date_label": date_label,
            "timetable": [], "message": "쉬는 날!",
        })

    grade, class_nm = await _get_grade_class(db, guild_id)
    if not grade:
        return web.json_response({
            "ok": True, "is_weekend": False, "date_label": date_label,
            "timetable": [], "message": "학급 설정이 필요합니다. (디스코드: /학급설정)",
        })

    date_str = target_date.strftime("%Y%m%d")
    timetable = await fetch_neis_timetable(date_str, grade, class_nm)
    cached = False
    cached_at = None

    if timetable:
        await cache_timetable(db, guild_id, date_str, grade, class_nm, timetable)
    elif timetable is None:
        cached_data, updated_at = await get_cached_timetable(db, guild_id, date_str, grade, class_nm)
        if cached_data:
            timetable = cached_data
            cached = True
            cached_at = (updated_at or "")[:16]
        else:
            return web.json_response({
                "ok": True, "is_weekend": False, "date_label": date_label,
                "timetable": [], "message": "NEIS 조회에 실패했습니다.",
            })
    else:
        timetable = []

    return web.json_response({
        "ok": True, "is_weekend": False, "date_label": date_label,
        "timetable": timetable, "cached": cached, "cached_at": cached_at,
    })


async def api_public_tasks(request):
    db = request.app["db"]
    guild_id = await _resolve_guild_id(request)
    if not guild_id:
        return web.json_response({"ok": False, "error": "서버를 찾을 수 없습니다."})

    now = datetime.datetime.now(kst)
    today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with db.execute(
        "SELECT id, task_type, deadline, content FROM tasks WHERE guild_id=?",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    tasks = []
    for t_id, task_type, deadline, content in rows:
        if task_type == "시험범위":
            continue
        days_left = None
        if deadline != "미정":
            try:
                target = parse_deadline(deadline, now)
                days_left = (target - today_date).days
            except ValueError:
                pass
        tasks.append({
            "id": t_id, "task_type": task_type, "deadline": deadline,
            "content": content, "days_left": days_left,
        })

    # Sort: dated first (by days_left asc), then undated
    dated = sorted([t for t in tasks if t["days_left"] is not None], key=lambda t: t["days_left"])
    undated = [t for t in tasks if t["days_left"] is None]
    tasks = dated + undated

    return web.json_response({"ok": True, "tasks": tasks, "total": len(tasks)})


async def api_public_exam(request):
    db = request.app["db"]
    guild_id = await _resolve_guild_id(request)
    if not guild_id:
        return web.json_response({"ok": False, "error": "서버를 찾을 수 없습니다."})

    now = datetime.datetime.now(kst)
    today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    exams = []

    for e_key, e_name in [("midterm_date", "중간고사"), ("final_date", "기말고사")]:
        async with db.execute(
            "SELECT value FROM config WHERE key=? AND guild_id=?", (e_key, guild_id)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            continue

        date_range = row[0]
        status = "unknown"
        days_to_start = None
        day_number = None

        try:
            start_dt, end_dt = parse_exam_dates(date_range, now)
            days_to_start = (start_dt.replace(hour=0, minute=0, second=0, microsecond=0) - today_date).days
            days_to_end = (end_dt.replace(hour=0, minute=0, second=0, microsecond=0) - today_date).days
            if days_to_start > 0:
                status = "upcoming"
            elif days_to_end >= 0:
                status = "ongoing"
                day_number = abs(days_to_start) + 1
            else:
                status = "done"
        except Exception:
            pass

        # Fetch exam scopes
        scopes = []
        async with db.execute(
            "SELECT id, content FROM tasks WHERE task_type='시험범위' AND deadline=? AND guild_id=?",
            (e_name, guild_id),
        ) as cursor:
            scope_rows = await cursor.fetchall()
        for _, content in scope_rows:
            # content format: [과목] 범위
            if content.startswith("[") and "]" in content:
                subject = content[1:content.index("]")]
                range_text = content[content.index("]")+1:].strip()
            else:
                subject = ""
                range_text = content
            scopes.append({"subject": subject, "range": range_text})

        exams.append({
            "name": e_name, "date_range": date_range, "status": status,
            "days_to_start": days_to_start, "day_number": day_number,
            "scopes": scopes,
        })

    return web.json_response({"ok": True, "exams": exams})


async def api_public_weekly(request):
    db = request.app["db"]
    guild_id = await _resolve_guild_id(request)
    if not guild_id:
        return web.json_response({"ok": False, "error": "서버를 찾을 수 없습니다."})

    now = datetime.datetime.now(kst)
    today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = today_date + datetime.timedelta(days=6 - today_date.weekday())

    async with db.execute(
        "SELECT id, task_type, deadline, content FROM tasks WHERE guild_id=?",
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    upcoming = []
    tbd = []
    for t_id, task_type, deadline, content in rows:
        if task_type == "시험범위":
            continue
        if deadline == "미정":
            tbd.append({"id": t_id, "task_type": task_type, "content": content})
            continue
        try:
            target = parse_deadline(deadline, now)
        except ValueError:
            continue
        if today_date <= target <= week_end:
            days = (target - today_date).days
            upcoming.append({
                "id": t_id, "task_type": task_type, "deadline": deadline,
                "content": content, "days": days,
            })

    upcoming.sort(key=lambda t: (t["days"], t["task_type"]))
    range_label = f"{today_date.strftime('%m/%d')} ~ {week_end.strftime('%m/%d')}"

    return web.json_response({
        "ok": True, "range": range_label,
        "upcoming": upcoming, "tbd": tbd[:8],
    })


async def api_public_school_events(request):
    now = datetime.datetime.now(kst)
    try:
        year = int(request.query.get("year", now.year))
        month = int(request.query.get("month", now.month))
    except ValueError:
        year, month = now.year, now.month

    if month < 1 or month > 12:
        return web.json_response({"ok": False, "error": "월은 1~12 사이여야 합니다."})

    start_date = f"{year}{month:02d}01"
    end_date = f"{year}{month:02d}31"
    schedule_data = await fetch_neis_school_schedule(start_date, end_date)

    if schedule_data is None:
        return web.json_response({"ok": False, "error": "NEIS API 오류"})

    events = []
    for s_date, e_date, event in (schedule_data or []):
        s_fmt = f"{int(s_date[4:6])}/{int(s_date[6:8])}"
        if e_date:
            e_fmt = f"{int(e_date[4:6])}/{int(e_date[6:8])}"
            date_str = f"{s_fmt} ~ {e_fmt}"
        else:
            date_str = s_fmt
        events.append({"date": date_str, "name": event})

    return web.json_response({"ok": True, "events": events})


async def run_web_server(bot):
    app = web.Application(middlewares=[auth_middleware])
    app['bot'] = bot
    app['db'] = bot.db

    # ── Public pages ──
    app.router.add_get('/', home_page)
    app.router.add_get('/login', login_page)
    app.router.add_post('/do_login', do_login)
    app.router.add_get('/auth/discord', discord_login)
    app.router.add_get('/auth/discord/callback', discord_callback)
    app.router.add_get('/logout', logout)

    # ── Authenticated pages ──
    app.router.add_get('/admin/logs', admin_log_dashboard)
    app.router.add_get('/announcements', announcements_page)

    # ── Authenticated APIs ──
    app.router.add_get('/api/me', api_me)
    app.router.add_get('/api/logs_json', api_get_logs_json)
    app.router.add_get('/api/announcement_context', api_announcement_context)
    app.router.add_get('/api/announcements', api_list_announcements)
    app.router.add_post('/api/announcements/preview', api_preview_announcement)
    app.router.add_post('/api/announcements', api_create_announcement)
    app.router.add_post('/api/announcements/{announcement_id:\\d+}/cancel', api_cancel_announcement)
    app.router.add_post('/api/announcements/{announcement_id:\\d+}/send_now', api_send_announcement_now)

    # ── Public APIs (no auth) ──
    app.router.add_get('/api/public/guilds', api_public_guilds)
    app.router.add_get('/api/public/schedule/{when}', api_public_schedule)
    app.router.add_get('/api/public/tasks', api_public_tasks)
    app.router.add_get('/api/public/exam', api_public_exam)
    app.router.add_get('/api/public/weekly', api_public_weekly)
    app.router.add_get('/api/public/school_events', api_public_school_events)

    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    if os.path.isdir(static_dir):
        app.router.add_static('/static/', static_dir)

    runner = web.AppRunner(app)
    await runner.setup()
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", "10000"))
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"웹 대시보드 기동 완료 ({host}:{port})")
