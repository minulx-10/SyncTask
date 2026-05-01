from aiohttp import web
import os
import json
import re

# .env에서 비밀번호 로드 (없으면 기본값 설정)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin1234")

async def auth_middleware(app, handler):
    async def middleware(request):
        if request.path.startswith('/api') or request.path == '/':
            password = request.cookies.get('admin_pass')
            if password != ADMIN_PASSWORD and request.path != '/login' and request.path != '/do_login':
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
    data = await request.post()
    if data.get('password') == ADMIN_PASSWORD:
        resp = web.HTTPFound('/')
        resp.set_cookie('admin_pass', ADMIN_PASSWORD, max_age=86400)
        return resp
    return web.HTTPFound('/login?error=1')

async def admin_log_dashboard(request):
    html = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SyncTask Admin CCTV</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css">
        <style>
            :root { --bg: #0f1216; --card: rgba(255,255,255,0.05); --accent: #5865F2; --text: #fff; --text-m: #a0a0a0; }
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Pretendard', sans-serif; }
            body { background: var(--bg); color: var(--text); padding: 40px; }
            .container { max-width: 1000px; margin: 0 auto; }
            header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
            h1 { font-size: 1.5rem; color: var(--accent); }
            
            .controls { display: flex; gap: 15px; margin-bottom: 20px; }
            select { background: #1e1e1e; color: white; border: 1px solid #333; padding: 8px 15px; border-radius: 8px; }

            .log-item { 
                background: var(--card); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; padding: 15px 20px; margin-bottom: 10px;
                display: flex; justify-content: space-between; align-items: center; cursor: pointer; transition: 0.2s;
            }
            .log-item:hover { background: rgba(255,255,255,0.1); transform: translateX(5px); }
            .log-meta { font-size: 0.85rem; color: var(--text-m); }
            .log-content { font-weight: 500; }
            .guild-tag { background: rgba(88,101,242,0.2); color: #5865F2; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 10px; }

            /* Modal */
            .modal { display: none; position: fixed; z-index: 100; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); backdrop-filter: blur(5px); }
            .modal-content { background: #1e1e1e; margin: 15% auto; padding: 30px; border-radius: 20px; width: 500px; border: 1px solid #333; }
            .modal-header { color: var(--accent); margin-bottom: 15px; font-weight: bold; }
            .close { float: right; cursor: pointer; color: var(--text-m); }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🖥️ SyncTask Admin CCTV</h1>
                <div id="status">🟢 Online</div>
            </header>
            
            <div class="controls">
                <select id="guild-filter" onchange="renderLogs()">
                    <option value="all">모든 서버 보기</option>
                </select>
                <button onclick="fetchData()" style="background:none; border:1px solid #333; color:white; padding:5px 15px; border-radius:8px; cursor:pointer;">새로고침</button>
            </div>

            <div id="log-list"></div>
        </div>

        <div id="logModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="closeModal()">&times;</span>
                <div class="modal-header">📄 Log Detail</div>
                <div id="modal-body" style="line-height:1.6; word-break:break-all;"></div>
            </div>
        </div>

        <script>
            let allLogs = [];
            async function fetchData() {
                const res = await fetch('/api/logs_json');
                allLogs = await res.json();
                updateFilters();
                renderLogs();
            }

            function updateFilters() {
                const guilds = [...new Set(allLogs.map(l => l.guild_name))];
                const filter = document.getElementById('guild-filter');
                filter.innerHTML = '<option value="all">모든 서버 보기</option>';
                guilds.forEach(g => {
                    filter.innerHTML += `<option value="${g}">${g}</option>`;
                });
            }

            function renderLogs() {
                const filter = document.getElementById('guild-filter').value;
                const list = document.getElementById('log-list');
                list.innerHTML = '';
                
                allLogs.filter(l => filter === 'all' || l.guild_name === filter).forEach(l => {
                    const item = document.createElement('div');
                    item.className = 'log-item';
                    item.onclick = () => showDetail(l);
                    item.innerHTML = `
                        <div>
                            <span class="guild-tag">${l.guild_name}</span>
                            <span class="log-content">${l.user}: ${l.command}</span>
                        </div>
                        <div class="log-meta">${l.time}</div>
                    `;
                    list.appendChild(item);
                });
            }

            function showDetail(log) {
                document.getElementById('modal-body').innerHTML = `
                    <p><b>Time:</b> ${log.time}</p>
                    <p><b>Guild:</b> ${log.guild_name} (${log.guild_id})</p>
                    <p><b>User:</b> ${log.user}</p>
                    <p><b>Command:</b> <span style="color:#5865F2">/${log.command}</span></p>
                    <p><b>Details:</b> ${log.details || '없음'}</p>
                `;
                document.getElementById('logModal').style.display = "block";
            }

            function closeModal() { document.getElementById('logModal').style.display = "none"; }
            window.onclick = (e) => { if(e.target.className == 'modal') closeModal(); }

            fetchData();
            setInterval(fetchData, 5000);
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

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
            # [GID:ID] [TIME] [GUILD] [USER] COMMAND (DETAILS)
            match = re.match(r"\[GID:(.*?)\] \[(.*?)\] \[(.*?)\] 👤(.*?): \/(.*?)(?: \((.*)\))?$", line.strip())
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
                    "guild_name": match.group(3),
                    "guild_icon": guild_icons[gid],
                    "user": match.group(4),
                    "command": match.group(5),
                    "details": match.group(6) or ""
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
            :root { --bg: #0b0e11; --card: #15191d; --accent: #5865F2; --text: #ffffff; --text-m: #8e9297; --danger: #ed4245; }
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Pretendard', sans-serif; }
            body { background: var(--bg); color: var(--text); overflow-x: hidden; }
            
            .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; }
            header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; }
            .brand { display: flex; align-items: center; gap: 12px; }
            .brand h1 { font-size: 1.6rem; font-weight: 800; background: linear-gradient(45deg, #5865F2, #a370f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .status-dot { width: 10px; height: 10px; background: #3ba55c; border-radius: 50%; box-shadow: 0 0 10px #3ba55c; }

            /* Server Grid */
            .server-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 20px; }
            .server-card { 
                background: var(--card); border-radius: 20px; padding: 25px; text-align: center; cursor: pointer; 
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); border: 1px solid rgba(255,255,255,0.05);
            }
            .server-card:hover { transform: translateY(-8px); border-color: var(--accent); box-shadow: 0 10px 30px rgba(88, 101, 242, 0.2); }
            .server-icon { width: 80px; height: 80px; border-radius: 25%; object-fit: cover; margin-bottom: 15px; background: #2f3136; padding: 5px; }
            .server-name { font-weight: 700; font-size: 1rem; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            
            /* Log View */
            #log-view { display: none; animation: fadeIn 0.4s ease; }
            @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
            
            .view-header { display: flex; align-items: center; gap: 20px; margin-bottom: 30px; }
            .back-btn { background: var(--card); border: 1px solid #333; color: white; padding: 10px 20px; border-radius: 12px; cursor: pointer; font-weight: 600; transition: 0.2s; }
            .back-btn:hover { background: #25292e; border-color: var(--accent); }

            .search-bar { flex: 1; position: relative; }
            .search-bar input { 
                width: 100%; background: var(--card); border: 1px solid #333; padding: 12px 20px 12px 45px; 
                border-radius: 15px; color: white; font-size: 0.95rem; outline: none; transition: 0.2s;
            }
            .search-bar input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(88, 101, 242, 0.1); }
            .search-icon { position: absolute; left: 15px; top: 50%; transform: translateY(-50%); color: var(--text-m); pointer-events: none; }

            .log-list { display: flex; flex-direction: column; gap: 12px; }
            .log-item { 
                background: var(--card); padding: 18px 25px; border-radius: 15px; display: flex; justify-content: space-between; 
                align-items: center; border: 1px solid transparent; transition: 0.2s; cursor: pointer;
            }
            .log-item:hover { border-color: rgba(255,255,255,0.1); background: #1c2126; }
            .log-main { display: flex; flex-direction: column; gap: 4px; }
            .log-user { font-weight: 700; color: var(--accent); font-size: 0.95rem; }
            .log-cmd { font-weight: 500; font-size: 1.05rem; }
            .log-time { color: var(--text-m); font-size: 0.85rem; font-family: monospace; }

            /* Modal */
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); backdrop-filter: blur(8px); z-index: 1000; }
            .modal-content { 
                position: relative; background: #1e1e1e; width: 90%; max-width: 500px; margin: 100px auto; 
                padding: 40px; border-radius: 30px; border: 1px solid #333; box-shadow: 0 20px 50px rgba(0,0,0,0.5);
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
                <div style="font-size: 0.9rem; color: var(--text-m); font-weight: 600;">CCTV Monitoring System</div>
            </header>

            <!-- Main Server Grid View -->
            <div id="grid-view">
                <div class="server-grid" id="server-list">
                    <!-- Servers will be injected here -->
                </div>
            </div>

            <!-- Detail Log View -->
            <div id="log-view">
                <div class="view-header">
                    <button class="back-btn" onclick="showGrid()">← 서버 목록</button>
                    <div class="search-bar">
                        <span class="search-icon">🔍</span>
                        <input type="text" id="log-search" placeholder="사용자 이름 또는 명령어 검색..." oninput="renderLogs()">
                    </div>
                </div>
                <div class="log-list" id="log-container">
                    <!-- Logs will be injected here -->
                </div>
            </div>
        </div>

        <!-- Detail Modal -->
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

            function renderGrid() {
                const serverList = document.getElementById('server-list');
                const servers = {};
                
                allLogs.forEach(log => {
                    if (!servers[log.guild_id]) {
                        servers[log.guild_id] = {
                            id: log.guild_id,
                            name: log.guild_name,
                            icon: log.guild_icon
                        };
                    }
                });

                serverList.innerHTML = Object.values(servers).map(s => `
                    <div class="server-card" onclick="selectServer('${s.id}')">
                        <img src="${s.icon}" class="server-icon" onerror="this.src='https://cdn-icons-png.flaticon.com/512/2111/2111370.png'">
                        <div class="server-name">${s.name}</div>
                    </div>
                `).join('');
            }

            function selectServer(gid) {
                currentServer = gid;
                document.getElementById('grid-view').style.display = 'none';
                document.getElementById('log-view').style.display = 'block';
                document.getElementById('log-search').value = '';
                renderLogs();
            }

            function showGrid() {
                currentServer = null;
                document.getElementById('log-view').style.display = 'none';
                document.getElementById('grid-view').style.display = 'block';
                renderGrid();
            }

            function renderLogs() {
                const search = document.getElementById('log-search').value.toLowerCase();
                const container = document.getElementById('log-container');
                
                const filtered = allLogs.filter(l => {
                    const matchServer = l.guild_id === currentServer;
                    const matchSearch = l.user.toLowerCase().includes(search) || l.command.toLowerCase().includes(search) || l.details.toLowerCase().includes(search);
                    return matchServer && matchSearch;
                });

                container.innerHTML = filtered.map(l => `
                    <div class="log-item" onclick='showDetail(${JSON.stringify(l).replace(/'/g, "&apos;")})'>
                        <div class="log-main">
                            <span class="log-user">@${l.user}</span>
                            <span class="log-cmd">/${l.command}</span>
                        </div>
                        <div class="log-time">${l.time}</div>
                    </div>
                `).join('');
            }

            function showDetail(log) {
                const body = document.getElementById('modal-body');
                body.innerHTML = `
                    <p><b>⏰ Time:</b> ${log.time}</p>
                    <p><b>🛡️ Server:</b> ${log.guild_name} (${log.guild_id})</p>
                    <p><b>👤 User:</b> ${log.user}</p>
                    <p><b>⚡ Command:</b> /${log.command}</p>
                    <p><b>📝 Details:</b> ${log.details || 'None'}</p>
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
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    print("🌍 프리미엄 관리자 대시보드 기동 완료 (포트 10000)")

