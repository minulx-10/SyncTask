import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import datetime
import aiohttp
from dotenv import load_dotenv
from core.database import init_db
from utils.ui import BRAND_COLOR

load_dotenv()
kst = datetime.timezone(datetime.timedelta(hours=9))

async def get_dashboard_url():
    public_url = os.getenv("DASHBOARD_PUBLIC_URL")
    if public_url:
        return public_url

    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = os.getenv("DASHBOARD_PORT", "10000")
    if host in ("0.0.0.0", "::"):
        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://api.ipify.org") as resp:
                    if resp.status == 200:
                        public_ip = (await resp.text()).strip()
                        return f"http://{public_ip}:{port}"
        except Exception:
            pass
    return f"http://localhost:{port}"

class SyncTaskBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = False # 기본 인텐트만 사용 (필요시 Portal에서 활성화 후 True 변경)
        super().__init__(command_prefix='!', intents=intents)
        self.db = None
        self.remove_command('help')

    async def setup_hook(self):
        # 1. DB 초기화
        self.db = await init_db()
        
        # 2. Cogs 로드
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        for filename in os.listdir(os.path.join(BASE_DIR, 'cogs')):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"Loaded Cog: {filename}")
                except Exception as e:
                    print(f"Failed to load Cog {filename}: {e}")

        # 3. Persistent Views 등록
        from cogs.tasks import DashboardView
        self.add_view(DashboardView(self))

        if os.getenv("SYNC_COMMANDS_ON_BOOT", "1") == "1":
            print("Syncing slash commands...")
            await self.tree.sync()
            print("Slash commands synced.")

    async def on_ready(self):
        # 봇이 완전히 준비될 때까지 잠시 대기
        await asyncio.sleep(5)
        
        if os.getenv("GUILD_SYNC_ON_READY", "1") == "1":
            print("서버별 즉시 동기화 진행 중...")
            for guild in self.guilds:
                try:
                    self.tree.copy_global_to(guild=guild)
                    await self.tree.sync(guild=guild)
                    print(f"즉시 동기화 완료: {guild.name}")
                except Exception as e:
                    print(f"{guild.name} 동기화 실패: {e}")

        tasks_cog = self.get_cog("TasksCog")
        if tasks_cog:
            await tasks_cog.update_dashboard()
        
        try:
            async with self.db.execute("SELECT count(*) FROM tasks") as cursor:
                count = (await cursor.fetchone())[0]
            db_status = f"정상 연결 · 일정 {count}개"
        except Exception as e:
            db_status = f"조회 실패 · {e}"
            count = 0
            
        print(f"\n{'='*60}\n{self.user.name} 가동 완료 | {db_status}\n{'='*60}")

        # 슈퍼 관리자 DM 알림
        super_admin_id = 771274777443696650
        user = self.get_user(super_admin_id) or await self.fetch_user(super_admin_id)
        if user:
            try:
                admin_password = os.getenv("ADMIN_PASSWORD")
                dashboard_url = await get_dashboard_url()
                embed = discord.Embed(
                    title="SyncTask 가동 보고",
                    description="시스템이 정상적으로 시작되었습니다.",
                    color=BRAND_COLOR,
                )
                embed.add_field(name="DB 상태", value=db_status, inline=False)
                embed.add_field(name="대시보드", value=dashboard_url, inline=False)
                embed.add_field(name="비밀번호", value=f"||{admin_password or '미설정 - 웹 로그인이 잠깁니다'}||", inline=False)
                embed.set_footer(text=datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S KST"))
                await user.send(embed=embed)
            except Exception:
                pass

bot = SyncTaskBot()

async def main():
    from web.server import run_web_server
    async def start_web():
        while bot.db is None: await asyncio.sleep(0.5)
        await run_web_server(bot)

    async with bot:
        bot.loop.create_task(start_web())
        token = os.getenv('DISCORD_TOKEN')
        if not token:
            raise RuntimeError("DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
