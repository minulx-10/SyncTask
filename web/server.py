from aiohttp import web
import os
import re
import hmac
import hashlib
import html

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
        if request.path.startswith('/api') or request.path == '/':
            if not is_authenticated(request) and request.path != '/login' and request.path != '/do_login':
                if request.path.startswith('/api'):
                    return web.json_response({"error": "Unauthorized"}, status=401)
                return web.HTTPFound('/login')
        return await handler(request)
    return middleware

async def login_page(request):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, "templates", "login.html")
    with open(template_path, "r", encoding="utf-8") as f:
        page = f.read()
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
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, "templates", "dashboard.html")
    with open(template_path, "r", encoding="utf-8") as f:
        page = f.read()
    return web.Response(text=page, content_type='text/html')

async def run_web_server(bot):
    app = web.Application(middlewares=[auth_middleware])
    app['bot'] = bot
    app['db'] = bot.db
    app.router.add_get('/', admin_log_dashboard)
    app.router.add_get('/login', login_page)
    app.router.add_post('/do_login', do_login)
    app.router.add_get('/api/logs_json', api_get_logs_json)
    
    runner = web.AppRunner(app)
    await runner.setup()
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", "10000"))
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"관리자 대시보드 기동 완료 ({host}:{port})")
