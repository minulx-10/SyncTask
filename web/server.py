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
    html = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>SyncTask - Login</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
        <style>
            body { background: #0f1216; color: white; font-family: 'Pretendard'; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .login-box { background: rgba(255,255,255,0.05); padding: 40px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.1); backdrop-filter: blur(10px); width: 350px; text-align: center; }
            h2 { color: #5865F2; margin-bottom: 20px; }
            input { width: 100%; padding: 12px; margin: 10px 0; border-radius: 8px; border: 1px solid #333; background: #1e1e1e; color: white; }
            button { width: 100%; padding: 12px; border-radius: 8px; border: none; background: #5865F2; color: white; font-weight: bold; cursor: pointer; margin-top: 10px; }
            button:hover { background: #4752c4; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>🔐 Admin Login</h2>
            <form action="/do_login" method="post">
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

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
                        guild_icons[gid] = "https://cdn-icons-png.flaticon.com/512/1077/1077063.png"
                    else:
                        guild = bot.get_guild(int(gid))
                        guild_icons[gid] = str(guild.icon.url) if guild and guild.icon else "https://cdn-icons-png.flaticon.com/512/2111/2111370.png"

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
    html = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SyncTask Admin Dashboard</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
        <style>
            :root { --bg: #0f1115; --card: #181b20; --line: #2a2e35; --accent: #5865F2; --text: #f5f6f8; --text-m: #9aa0a6; }
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Pretendard', sans-serif; }
            body { background: var(--bg); color: var(--text); overflow-x: hidden; }
            
            .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; }
            header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; }
            .brand { display: flex; align-items: center; gap: 12px; }
            .brand h1 { font-size: 1.35rem; font-weight: 700; color: var(--text); }
            .status-dot { width: 9px; height: 9px; background: #3ba55c; border-radius: 50%; }

            /* Server Grid */
            .server-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 25px; }
            .server-card { 
                background: var(--card); border-radius: 8px; overflow: hidden; cursor: pointer; 
                transition: border-color 0.2s ease, background 0.2s ease; border: 1px solid var(--line);
                display: flex; flex-direction: column;
            }
            .server-card:hover { border-color: var(--accent); background: #1d2128; }
            .server-icon { width: 100%; aspect-ratio: 1/1; object-fit: cover; background: #2f3136; }
            .server-info { padding: 12px; text-align: center; background: rgba(0,0,0,0.2); }
            .server-name { font-weight: 600; font-size: 0.85rem; color: var(--text-m); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            
            /* Log View */
            #log-view { display: none; animation: fadeIn 0.4s ease; }
            @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
            
            .view-header { margin-bottom: 30px; }
            .top-actions { display: flex; align-items: center; gap: 15px; margin-bottom: 20px; }
            .back-btn { background: var(--card); border: 1px solid var(--line); color: white; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-weight: 600; display: flex; align-items: center; gap: 8px; }
            .back-btn:hover { background: #25292e; border-color: var(--accent); }

            .filter-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
            .filter-item { position: relative; }
            .filter-item input { 
                width: 100%; background: var(--card); border: 1px solid #333; padding: 12px 15px 12px 40px; 
                border-radius: 8px; color: white; font-size: 0.9rem; outline: none; transition: 0.2s;
            }
            .filter-item input:focus { border-color: var(--accent); }
            .filter-icon { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); font-size: 0.9rem; color: var(--text-m); }

            .log-list { display: flex; flex-direction: column; gap: 10px; }
            .log-item { 
                background: var(--card); padding: 15px 20px; border-radius: 8px; display: flex; justify-content: space-between; 
                align-items: center; border: 1px solid transparent; transition: 0.2s; cursor: pointer;
            }
            .log-item:hover { border-color: rgba(255,255,255,0.1); background: #1c2126; }
            .log-main { display: flex; align-items: center; gap: 15px; }
            .log-user { font-weight: 700; color: var(--accent); min-width: 100px; }
            .log-cmd { font-weight: 600; color: #fff; background: rgba(255,255,255,0.05); padding: 4px 10px; border-radius: 6px; }
            .log-details { color: var(--text-m); font-size: 0.9rem; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .log-time { color: var(--text-m); font-size: 0.8rem; font-family: monospace; }

            /* Modal */
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); backdrop-filter: blur(8px); z-index: 1000; }
            .modal-content { 
                position: relative; background: #1e1e1e; width: 90%; max-width: 500px; margin: 100px auto; 
                padding: 40px; border-radius: 8px; border: 1px solid #333; box-shadow: 0 20px 50px rgba(0,0,0,0.5);
            }
            .modal-close { position: absolute; right: 25px; top: 25px; cursor: pointer; font-size: 1.5rem; color: var(--text-m); }
            .modal-header { font-size: 1.4rem; font-weight: 800; margin-bottom: 25px; color: var(--accent); border-bottom: 1px solid #333; padding-bottom: 15px; }
            .modal-body p { margin-bottom: 15px; font-size: 1rem; line-height: 1.6; color: #ddd; }
            .modal-body b { color: #fff; display: inline-block; width: 100px; }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div class="brand">
                    <div class="status-dot"></div>
                    <h1>SyncTask Dashboard</h1>
                </div>
                <div style="font-size: 0.9rem; color: var(--text-m); font-weight: 600;">운영 로그</div>
            </header>

            <div id="grid-view">
                <div class="server-grid" id="server-list"></div>
            </div>

            <div id="log-view">
                <div class="view-header">
                    <div class="top-actions">
                        <button class="back-btn" onclick="showGrid()"><span>←</span> 서버 목록</button>
                    </div>
                    <div class="filter-grid">
                        <div class="filter-item">
                            <span class="filter-icon">U</span>
                            <input type="text" id="filter-user" placeholder="유저명 검색..." oninput="renderLogs()">
                        </div>
                        <div class="filter-item">
                            <span class="filter-icon">/</span>
                            <input type="text" id="filter-cmd" placeholder="명령어 검색..." oninput="renderLogs()">
                        </div>
                        <div class="filter-item">
                            <span class="filter-icon">T</span>
                            <input type="text" id="filter-content" placeholder="내용 검색..." oninput="renderLogs()">
                        </div>
                    </div>
                </div>
                <div class="log-list" id="log-container"></div>
            </div>
        </div>

        <div id="logModal" class="modal" onclick="if(event.target == this) closeModal()">
            <div class="modal-content">
                <span class="modal-close" onclick="closeModal()">&times;</span>
                <div class="modal-header">Log Details</div>
                <div id="modal-body" class="modal-body"></div>
            </div>
        </div>

        <script>
            let allLogs = [];
            let currentServer = null;

            async function fetchData() {
                try {
                    const res = await fetch('/api/logs_json');
                    allLogs = await res.json();
                    if (!currentServer) renderGrid();
                    else renderLogs();
                } catch (e) { console.error("Data fetch failed", e); }
            }
            function escapeHTML(value) {
                return String(value ?? '').replace(/[&<>"']/g, ch => ({
                    '&': '&amp;',
                    '<': '&lt;',
                    '>': '&gt;',
                    '"': '&quot;',
                    "'": '&#39;'
                }[ch]));
            }

            function renderGrid() {
                const serverList = document.getElementById('server-list');
                const servers = {};
                allLogs.forEach(log => {
                    if (!servers[log.guild_id]) {
                        servers[log.guild_id] = { id: log.guild_id, name: log.guild_name, icon: log.guild_icon };
                    }
                });
                serverList.innerHTML = Object.values(servers).map(s => `
                    <div class="server-card" onclick="selectServer('${escapeHTML(s.id)}')">
                        <img src="${escapeHTML(s.icon)}" class="server-icon" onerror="this.src='https://cdn-icons-png.flaticon.com/512/2111/2111370.png'">
                        <div class="server-info"><div class="server-name">${escapeHTML(s.name)}</div></div>
                    </div>
                `).join('');
            }

            function selectServer(gid) {
                currentServer = gid;
                document.getElementById('grid-view').style.display = 'none';
                document.getElementById('log-view').style.display = 'block';
                document.querySelectorAll('.filter-item input').forEach(i => i.value = '');
                renderLogs();
            }

            function showGrid() {
                currentServer = null;
                document.getElementById('log-view').style.display = 'none';
                document.getElementById('grid-view').style.display = 'block';
                renderGrid();
            }

            function renderLogs() {
                const uF = document.getElementById('filter-user').value.toLowerCase();
                const cF = document.getElementById('filter-cmd').value.toLowerCase();
                const tF = document.getElementById('filter-content').value.toLowerCase();
                const container = document.getElementById('log-container');
                
                const filtered = allLogs.filter(l => {
                    return l.guild_id === currentServer && 
                           l.user.toLowerCase().includes(uF) && 
                           l.command.toLowerCase().includes(cF) && 
                           l.details.toLowerCase().includes(tF);
                });

                container.innerHTML = filtered.map((l, index) => `
                    <div class="log-item" onclick='showDetailByIndex(${index})'>
                        <div class="log-main">
                            <span class="log-user">${escapeHTML(l.user)}</span>
                            <span class="log-cmd">/${escapeHTML(l.command)}</span>
                            <span class="log-details">${escapeHTML(l.details)}</span>
                        </div>
                        <div class="log-time">${escapeHTML(l.time.split(' ')[1])}</div>
                    </div>
                `).join('');
                window.filteredLogs = filtered;
            }

            function showDetailByIndex(index) {
                showDetail(window.filteredLogs[index]);
            }
            function showDetail(log) {
                document.getElementById('modal-body').innerHTML = `
                    <p><b>Time:</b> ${escapeHTML(log.time)}</p>
                    <p><b>Server:</b> ${escapeHTML(log.guild_name)} (${escapeHTML(log.guild_id)})</p>
                    <p><b>User:</b> ${escapeHTML(log.user)}</p>
                    <p><b>Command:</b> /${escapeHTML(log.command)}</p>
                    <p><b>Details:</b> ${escapeHTML(log.details || 'None')}</p>
                `;
                document.getElementById('logModal').style.display = "block";
            }
            function closeModal() { document.getElementById('logModal').style.display = "none"; }
            fetchData();
            setInterval(fetchData, 5000);
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

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
    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("DASHBOARD_PORT", "10000"))
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"관리자 대시보드 기동 완료 ({host}:{port})")
