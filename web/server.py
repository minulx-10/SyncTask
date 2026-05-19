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
    page = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SyncTask · Login</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                background: #0c0d10;
                color: #e4e6ea;
                font-family: 'Inter', -apple-system, sans-serif;
                display: flex; justify-content: center; align-items: center;
                min-height: 100vh;
            }
            .login-card {
                width: 380px;
                background: #16181d;
                border: 1px solid #2a2d35;
                border-radius: 16px;
                padding: 48px 36px;
                text-align: center;
            }
            .logo { font-size: 2rem; margin-bottom: 8px; }
            .title { font-size: 1.1rem; font-weight: 700; color: #fff; margin-bottom: 4px; }
            .subtitle { font-size: 0.8rem; color: #6b7280; margin-bottom: 32px; }
            input {
                width: 100%; padding: 14px 16px;
                background: #0c0d10; border: 1px solid #2a2d35;
                border-radius: 10px; color: #fff;
                font-size: 0.9rem; outline: none;
                transition: border-color 0.2s;
            }
            input:focus { border-color: #5865F2; }
            input::placeholder { color: #4b5563; }
            button {
                width: 100%; padding: 14px;
                background: #5865F2; color: #fff;
                border: none; border-radius: 10px;
                font-size: 0.9rem; font-weight: 600;
                cursor: pointer; margin-top: 16px;
                transition: background 0.2s, transform 0.1s;
            }
            button:hover { background: #4752c4; }
            button:active { transform: scale(0.98); }
            .error { color: #ed4245; font-size: 0.8rem; margin-top: 12px; }
        </style>
    </head>
    <body>
        <div class="login-card">
            <div class="logo">🔒</div>
            <div class="title">SyncTask Admin</div>
            <div class="subtitle">관리자 인증이 필요합니다</div>
            <form action="/do_login" method="post">
                <input type="password" name="password" placeholder="비밀번호 입력" required autofocus>
                <button type="submit">로그인</button>
            </form>
        </div>
    </body>
    </html>
    """
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
    page = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SyncTask · Dashboard</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg: #0c0d10; --surface: #16181d; --border: #2a2d35;
                --accent: #5865F2; --accent-h: #4752c4;
                --text: #e4e6ea; --text-s: #9ca3af; --text-d: #6b7280;
                --green: #57F287; --red: #ed4245; --amber: #f59e0b;
            }
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { background: var(--bg); color: var(--text); font-family: 'Inter', -apple-system, sans-serif; min-height: 100vh; }

            /* ── Layout ── */
            .app { max-width: 960px; margin: 0 auto; padding: 32px 24px 60px; }

            /* ── Header ── */
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 32px; }
            .brand { display: flex; align-items: center; gap: 10px; }
            .brand-dot { width: 8px; height: 8px; background: var(--green); border-radius: 50%; box-shadow: 0 0 8px var(--green); }
            .brand-name { font-size: 1.15rem; font-weight: 700; letter-spacing: -0.02em; }
            .header-badge { font-size: 0.75rem; color: var(--text-d); font-weight: 600; background: var(--surface); border: 1px solid var(--border); padding: 6px 14px; border-radius: 20px; }

            /* ── Server Grid ── */
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }
            .srv {
                background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
                padding: 20px; cursor: pointer;
                transition: border-color 0.2s, background 0.2s, transform 0.15s;
                display: flex; align-items: center; gap: 14px;
            }
            .srv:hover { border-color: var(--accent); background: #1a1d24; transform: translateY(-2px); }
            .srv-icon {
                width: 44px; height: 44px; border-radius: 12px; object-fit: cover;
                background: var(--border); flex-shrink: 0;
            }
            .srv-icon-placeholder {
                width: 44px; height: 44px; border-radius: 12px;
                background: linear-gradient(135deg, var(--accent), #7c3aed);
                display: flex; align-items: center; justify-content: center;
                font-size: 1.1rem; font-weight: 700; color: #fff; flex-shrink: 0;
            }
            .srv-name { font-weight: 600; font-size: 0.9rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .srv-count { font-size: 0.75rem; color: var(--text-d); margin-top: 2px; }

            /* ── Log View ── */
            #log-view { display: none; animation: slideUp 0.3s ease; }
            @keyframes slideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

            .log-header { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
            .back {
                background: var(--surface); border: 1px solid var(--border); color: var(--text);
                padding: 8px 16px; border-radius: 8px; cursor: pointer;
                font-size: 0.85rem; font-weight: 600; transition: 0.2s;
            }
            .back:hover { border-color: var(--accent); }
            .log-server-name { font-size: 1rem; font-weight: 700; }

            .filters { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
            .filters input {
                flex: 1; min-width: 140px; padding: 10px 14px;
                background: var(--surface); border: 1px solid var(--border);
                border-radius: 8px; color: var(--text); font-size: 0.85rem; outline: none;
                transition: border-color 0.2s;
            }
            .filters input:focus { border-color: var(--accent); }
            .filters input::placeholder { color: var(--text-d); }

            /* ── Log Items ── */
            .logs { display: flex; flex-direction: column; gap: 6px; }
            .log {
                background: var(--surface); border: 1px solid transparent; border-radius: 10px;
                padding: 14px 18px; display: flex; align-items: center; gap: 14px;
                cursor: pointer; transition: 0.15s;
            }
            .log:hover { border-color: var(--border); background: #1a1d24; }
            .log-time { font-size: 0.75rem; color: var(--text-d); font-family: 'SF Mono', 'Fira Code', monospace; min-width: 85px; flex-shrink: 0; }
            .log-user { font-weight: 600; color: var(--accent); min-width: 80px; font-size: 0.85rem; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .log-cmd {
                font-size: 0.8rem; font-weight: 600; color: #fff;
                background: rgba(88, 101, 242, 0.15); padding: 3px 10px; border-radius: 6px;
                flex-shrink: 0;
            }
            .log-detail { font-size: 0.8rem; color: var(--text-s); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
            .log-empty { text-align: center; color: var(--text-d); padding: 60px 0; font-size: 0.9rem; }

            /* ── Modal ── */
            .modal-bg { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(6px); z-index: 100; }
            .modal {
                position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
                background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
                padding: 32px; width: 90%; max-width: 440px;
            }
            .modal-title { font-size: 1rem; font-weight: 700; color: var(--accent); margin-bottom: 20px; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
            .modal-row { display: flex; margin-bottom: 12px; font-size: 0.9rem; line-height: 1.5; }
            .modal-label { color: var(--text-d); width: 80px; flex-shrink: 0; font-weight: 600; }
            .modal-value { color: var(--text); word-break: break-all; }
            .modal-close {
                position: absolute; top: 16px; right: 20px; cursor: pointer;
                font-size: 1.3rem; color: var(--text-d); transition: 0.2s;
            }
            .modal-close:hover { color: var(--text); }

            /* ── Responsive ── */
            @media (max-width: 600px) {
                .app { padding: 20px 16px; }
                .grid { grid-template-columns: 1fr; }
                .log { flex-wrap: wrap; gap: 8px; }
                .log-detail { flex-basis: 100%; }
                .filters { flex-direction: column; }
                .filters input { min-width: unset; }
            }
        </style>
    </head>
    <body>
        <div class="app">
            <div class="header">
                <div class="brand">
                    <div class="brand-dot"></div>
                    <div class="brand-name">SyncTask</div>
                </div>
                <div class="header-badge">운영 로그</div>
            </div>

            <div id="grid-view">
                <div class="grid" id="server-list"></div>
            </div>

            <div id="log-view">
                <div class="log-header">
                    <button class="back" onclick="showGrid()">← 목록</button>
                    <div class="log-server-name" id="log-title"></div>
                </div>
                <div class="filters">
                    <input type="text" id="f-user" placeholder="👤 유저 검색" oninput="renderLogs()">
                    <input type="text" id="f-cmd" placeholder="/ 명령어 검색" oninput="renderLogs()">
                    <input type="text" id="f-detail" placeholder="📋 내용 검색" oninput="renderLogs()">
                </div>
                <div class="logs" id="log-list"></div>
            </div>
        </div>

        <div class="modal-bg" id="modal-bg" onclick="if(event.target===this)closeModal()">
            <div class="modal">
                <span class="modal-close" onclick="closeModal()">&times;</span>
                <div class="modal-title">로그 상세</div>
                <div id="modal-body"></div>
            </div>
        </div>

        <script>
            let allLogs = [], currentServer = null, filteredCache = [];

            async function fetchData() {
                try {
                    const r = await fetch('/api/logs_json');
                    allLogs = await r.json();
                    if (!currentServer) renderGrid(); else renderLogs();
                } catch(e) { console.error(e); }
            }

            const esc = v => String(v??'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

            function renderGrid() {
                const el = document.getElementById('server-list');
                const srvs = {};
                allLogs.forEach(l => {
                    if (!srvs[l.guild_id]) srvs[l.guild_id] = { id: l.guild_id, name: l.guild_name, icon: l.guild_icon, count: 0 };
                    srvs[l.guild_id].count++;
                });
                if (!Object.keys(srvs).length) { el.innerHTML = '<div class="log-empty">아직 기록된 로그가 없습니다.</div>'; return; }
                el.innerHTML = Object.values(srvs).map(s => {
                    const iconEl = s.icon
                        ? `<img class="srv-icon" src="${esc(s.icon)}" onerror="this.outerHTML='<div class=srv-icon-placeholder>'+ '${esc(s.name)[0]}' +'</div>'">`
                        : `<div class="srv-icon-placeholder">${esc(s.name)[0] || '?'}</div>`;
                    return `<div class="srv" onclick="selectServer('${esc(s.id)}','${esc(s.name)}')">${iconEl}<div><div class="srv-name">${esc(s.name)}</div><div class="srv-count">${s.count}개의 로그</div></div></div>`;
                }).join('');
            }

            function selectServer(id, name) {
                currentServer = id;
                document.getElementById('grid-view').style.display = 'none';
                document.getElementById('log-view').style.display = 'block';
                document.getElementById('log-title').textContent = name;
                document.querySelectorAll('.filters input').forEach(i => i.value = '');
                renderLogs();
            }

            function showGrid() {
                currentServer = null;
                document.getElementById('log-view').style.display = 'none';
                document.getElementById('grid-view').style.display = 'block';
                renderGrid();
            }

            function renderLogs() {
                const uF = document.getElementById('f-user').value.toLowerCase();
                const cF = document.getElementById('f-cmd').value.toLowerCase();
                const dF = document.getElementById('f-detail').value.toLowerCase();
                const el = document.getElementById('log-list');

                filteredCache = allLogs.filter(l =>
                    l.guild_id === currentServer &&
                    l.user.toLowerCase().includes(uF) &&
                    l.command.toLowerCase().includes(cF) &&
                    l.details.toLowerCase().includes(dF)
                );

                if (!filteredCache.length) { el.innerHTML = '<div class="log-empty">조건에 맞는 로그가 없습니다.</div>'; return; }

                el.innerHTML = filteredCache.map((l, i) => {
                    const t = l.time.split(' ');
                    const timeStr = t.length > 1 ? `${t[0].substring(5).replace('-', '/')} ${t[1].substring(0, 5)}` : t[0];
                    return `<div class="log" onclick="showDetail(${i})"><span class="log-time">${esc(timeStr)}</span><span class="log-user">${esc(l.user)}</span><span class="log-cmd">/${esc(l.command)}</span><span class="log-detail">${esc(l.details)}</span></div>`;
                }).join('');
            }

            function showDetail(i) {
                const l = filteredCache[i]; if (!l) return;
                document.getElementById('modal-body').innerHTML = [
                    ['시간', l.time], ['서버', `${l.guild_name}`], ['유저', l.user],
                    ['명령어', `/${l.command}`], ['상세', l.details || '—']
                ].map(([k,v]) => `<div class="modal-row"><div class="modal-label">${k}</div><div class="modal-value">${esc(v)}</div></div>`).join('');
                document.getElementById('modal-bg').style.display = 'block';
            }

            function closeModal() { document.getElementById('modal-bg').style.display = 'none'; }
            document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
            fetchData();
            setInterval(fetchData, 5000);
        </script>
    </body>
    </html>
    """
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
