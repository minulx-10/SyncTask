from aiohttp import web
import os
import re
import hmac
import hashlib
import html
import uuid
from pathlib import Path

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

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

def _session_secret():
    base = (os.getenv("DISCORD_TOKEN") or "") + (ADMIN_PASSWORD or "")
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def make_session_cookie():
    if not ADMIN_PASSWORD:
        return ""
    return hmac.new(_session_secret().encode("utf-8"), b"admin", hashlib.sha256).hexdigest()

def is_authenticated(request):
    if not ADMIN_PASSWORD:
        return False
    return hmac.compare_digest(request.cookies.get('admin_session', ''), make_session_cookie())

async def auth_middleware(app, handler):
    async def middleware(request):
        public_paths = {'/login', '/do_login'}
        if request.path not in public_paths and not is_authenticated(request):
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


async def record_web_change(db, guild_id, action, details):
    await db.execute(
        """
        INSERT INTO change_logs (guild_id, user_id, action, details, created_at)
        VALUES (?, 0, ?, ?, ?)
        """,
        (guild_id, action, details, format_dt()),
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
    return web.Response(text=page, content_type='text/html')

async def do_login(request):
    if not ADMIN_PASSWORD:
        return web.HTTPFound('/login?error=not_configured')
    data = await request.post()
    if data.get('password') == ADMIN_PASSWORD:
        resp = web.HTTPFound('/')
        resp.set_cookie('admin_session', make_session_cookie(), max_age=86400, httponly=True, samesite='Strict')
        return resp
    return web.HTTPFound('/login?error=1')

async def api_get_logs_json(request):
    try:
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

async def admin_log_dashboard(request):
    page = read_template("dashboard.html")
    return web.Response(text=page, content_type='text/html')


async def announcements_page(request):
    page = read_template("announcements.html")
    return web.Response(text=page, content_type='text/html')


async def api_announcement_context(request):
    bot = request.app['bot']
    guilds = []
    for guild in bot.guilds:
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
        "guilds": guilds,
        "templates": templates,
        "target_types": TARGET_TYPES,
        "now": format_dt(),
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
        items = [item for item in items if str(item["guild_id"]) == guild_id]
    return web.json_response({
        "ok": True,
        "announcements": [serialize_announcement(bot, item) for item in items],
    })


async def api_create_announcement(request):
    bot = request.app['bot']
    db = request.app['db']
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

        guild = bot.get_guild(int(normalized["guild_id"]))
        channel = bot.get_channel(int(normalized["channel_id"]))
        channel_guild_id = getattr(getattr(channel, "guild", None), "id", None)
        if not guild or not channel or channel_guild_id != guild.id:
            raise AnnouncementValidationError("선택한 서버와 채널을 확인해주세요.")

        image_field = form.get("image")
        if image_field and getattr(image_field, "filename", ""):
            image_filename = await save_uploaded_image(image_field)
            normalized["image_filename"] = image_filename

        announcement_id = await create_announcement(db, normalized, created_by="teacher_web")
        await record_web_change(
            db,
            normalized["guild_id"],
            "공지등록",
            f"#{announcement_id} {normalized['title']} / {normalized['scheduled_at']}",
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
    announcement_id = int(request.match_info["announcement_id"])
    item = await fetch_announcement(db, announcement_id)
    if not item:
        return json_error("공지를 찾을 수 없습니다.", status=404)
    ok = await cancel_announcement(db, announcement_id)
    if ok:
        await record_web_change(db, item["guild_id"], "공지취소", f"#{announcement_id} {item['title']}")
    updated = await fetch_announcement(db, announcement_id)
    return web.json_response({"ok": ok, "announcement": serialize_announcement(request.app['bot'], updated)})


async def api_send_announcement_now(request):
    bot = request.app['bot']
    db = request.app['db']
    announcement_id = int(request.match_info["announcement_id"])
    item = await fetch_announcement(db, announcement_id)
    if not item:
        return json_error("공지를 찾을 수 없습니다.", status=404)
    try:
        sent = await send_announcement_by_id(bot, db, announcement_id, allow_failed=True)
        if sent:
            await record_web_change(db, item["guild_id"], "공지즉시발송", f"#{announcement_id} {item['title']}")
        updated = await fetch_announcement(db, announcement_id)
        return web.json_response({"ok": sent, "announcement": serialize_announcement(bot, updated)})
    except Exception as exc:
        updated = await fetch_announcement(db, announcement_id)
        return web.json_response({
            "ok": False,
            "error": str(exc),
            "announcement": serialize_announcement(bot, updated),
        }, status=202)

async def run_web_server(bot):
    app = web.Application(middlewares=[auth_middleware])
    app['bot'] = bot
    app['db'] = bot.db
    app.router.add_get('/', admin_log_dashboard)
    app.router.add_get('/announcements', announcements_page)
    app.router.add_get('/login', login_page)
    app.router.add_post('/do_login', do_login)
    app.router.add_get('/api/logs_json', api_get_logs_json)
    app.router.add_get('/api/announcement_context', api_announcement_context)
    app.router.add_get('/api/announcements', api_list_announcements)
    app.router.add_post('/api/announcements/preview', api_preview_announcement)
    app.router.add_post('/api/announcements', api_create_announcement)
    app.router.add_post('/api/announcements/{announcement_id:\\d+}/cancel', api_cancel_announcement)
    app.router.add_post('/api/announcements/{announcement_id:\\d+}/send_now', api_send_announcement_now)
    
    runner = web.AppRunner(app)
    await runner.setup()
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", "10000"))
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"관리자 대시보드 기동 완료 ({host}:{port})")
