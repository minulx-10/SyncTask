from aiohttp import web
import os
import json

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
            :root {
                --bg-color: #0f1216;
                --card-bg: rgba(255, 255, 255, 0.05);
                --accent-color: #5865F2;
                --text-main: #ffffff;
                --text-muted: #a0a0a0;
                --success: #57F287;
            }
            * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Pretendard', sans-serif; }
            body { 
                background-color: var(--bg-color); 
                color: var(--text-main); 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                min-height: 100vh;
                background-image: radial-gradient(circle at 10% 20%, rgba(88, 101, 242, 0.1) 0%, transparent 40%);
            }
            .container { 
                width: 90%; 
                max-width: 900px; 
                background: var(--card-bg); 
                backdrop-filter: blur(15px); 
                -webkit-backdrop-filter: blur(15px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 24px; 
                padding: 40px; 
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            }
            header { 
                display: flex; 
                justify-content: space-between; 
                align-items: center; 
                margin-bottom: 30px; 
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                padding-bottom: 20px;
            }
            h1 { font-size: 1.5rem; font-weight: 700; color: var(--accent-color); letter-spacing: -0.5px; }
            .status-badge { 
                background: rgba(87, 242, 135, 0.1); 
                color: var(--success); 
                padding: 6px 12px; 
                border-radius: 100px; 
                font-size: 0.75rem; 
                font-weight: 600;
                display: flex; align-items: center; gap: 6px;
            }
            .status-dot { width: 8px; height: 8px; background: var(--success); border-radius: 50%; box-shadow: 0 0 10px var(--success); }
            
            #log-list { 
                list-style: none; 
                max-height: 500px; 
                overflow-y: auto; 
                padding-right: 10px;
            }
            #log-list::-webkit-scrollbar { width: 6px; }
            #log-list::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }
            
            li { 
                background: rgba(255, 255, 255, 0.02); 
                margin-bottom: 12px; 
                padding: 16px 20px; 
                border-radius: 12px; 
                border: 1px solid rgba(255, 255, 255, 0.03);
                font-size: 0.9rem; 
                line-height: 1.5;
                transition: transform 0.2s, background 0.2s;
                animation: fadeIn 0.4s ease-out;
            }
            li:hover { background: rgba(255, 255, 255, 0.05); transform: translateX(5px); }
            
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .footer { 
                text-align: center; 
                margin-top: 30px; 
                font-size: 0.8rem; 
                color: var(--text-muted);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>SyncTask Live Monitor</h1>
                <div class="status-badge"><div class="status-dot"></div> Live Monitoring</div>
            </header>
            <ul id="log-list">
                <li style='text-align:center;'>Initializing Connection... 🔄</li>
            </ul>
            <div class="footer">© 2024 SyncTask Service • Powered by Google Deepmind</div>
        </div>

        <script>
            function fetchLogs() {
                fetch('/api/logs?t=' + new Date().getTime())
                .then(response => response.text())
                .then(html => {
                    const list = document.getElementById('log-list');
                    if (list.innerHTML !== html) {
                        list.innerHTML = html;
                    }
                });
            }
            fetchLogs();
            setInterval(fetchLogs, 3000);
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def api_get_logs(request):
    try:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_path = os.path.join(BASE_DIR, "alimi_cmd_log.txt")
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        lines.reverse()
        recent_logs = lines[:50] 
        log_html = ""
        for line in recent_logs:
            if not line.strip(): continue
            log_html += f"<li>{line.strip()}</li>"
            
        if not log_html: log_html = "<li style='text-align:center;'>아직 기록된 명령어가 없습니다.</li>"
        return web.Response(text=log_html, content_type='text/html')
    except FileNotFoundError:
        return web.Response(text="<li style='text-align:center;'>로그 파일이 아직 없습니다.</li>", content_type='text/html')
    except Exception as e:
        return web.Response(text=f"<li>에러 발생: {e}</li>", content_type='text/html')

async def api_get_tasks(request):
    try:
        db = request.app['db']
        grade = request.query.get('grade')
        class_nm = request.query.get('class_nm')
        common_guilds = []
        if grade and class_nm:
            async with db.execute("SELECT guild_id FROM config WHERE key='grade' AND value=?", (str(grade),)) as cursor:
                grade_guilds = set([row[0] for row in await cursor.fetchall()])
            async with db.execute("SELECT guild_id FROM config WHERE key='class_nm' AND value=?", (str(class_nm),)) as cursor:
                class_guilds = set([row[0] for row in await cursor.fetchall()])
            common_guilds = list(grade_guilds.intersection(class_guilds))
        
        if common_guilds:
            placeholders = ','.join('?' for _ in common_guilds)
            async with db.execute(f'SELECT id, task_type, deadline, content FROM tasks WHERE guild_id IN ({placeholders})', common_guilds) as cursor:
                rows = await cursor.fetchall()
        else:
            return web.Response(text="[]", content_type='application/json')
            
        tasks_list = [{"id": r[0], "task_type": r[1], "deadline": r[2], "content": r[3]} for r in rows]
        return web.Response(text=json.dumps(tasks_list, ensure_ascii=False), content_type='application/json')
    except Exception as e:
        return web.Response(text=json.dumps({"error": str(e)}), status=500, content_type='application/json')

async def run_web_server(db):
    app = web.Application()
    app['db'] = db
    app.router.add_get('/', admin_log_dashboard)          
    app.router.add_get('/api/logs', api_get_logs)         
    app.router.add_get('/api/tasks', api_get_tasks)       
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000) 
    await site.start()
    print("🌍 관리자 CCTV 웹사이트 & API 서버 정상 작동 시작! (포트 10000)")
