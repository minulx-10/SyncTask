import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import datetime
from dotenv import load_dotenv
from core.database import init_db
from core.neis_api import fetch_neis_timetable
from utils.logger import record_log
from utils.formatter import get_schedule_message

load_dotenv()
kst = datetime.timezone(datetime.timedelta(hours=9))

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
                    print(f"✅ Loaded Cog: {filename}")
                except Exception as e:
                    print(f"❌ Failed to load Cog {filename}: {e}")

        # 3. Persistent Views 등록
        from cogs.tasks import DashboardView
        self.add_view(DashboardView(self))

        # 4. 자동 동기화 (Slash Commands Auto-Sync)
        print("🔄 Syncing slash commands...")
        await self.tree.sync()
        print("✅ Slash commands synced!")

    async def on_ready(self):
        # 봇이 완전히 준비될 때까지 잠시 대기
        await asyncio.sleep(5)
        
        # [긴급] 서버별 즉시 동기화 (Instant Guild Sync)
        # 전역 명령어의 1시간 지연을 방지하기 위해 각 서버에 직접 등록합니다.
        print("⚡ 서버별 즉시 동기화 진행 중...")
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                print(f"✅ 즉시 동기화 완료: {guild.name}")
            except Exception as e:
                print(f"❌ {guild.name} 동기화 실패: {e}")

        tasks_cog = self.get_cog("TasksCog")
        if tasks_cog:
            await tasks_cog.update_dashboard()
        
        try:
            async with self.db.execute("SELECT count(*) FROM tasks") as cursor:
                count = (await cursor.fetchone())[0]
            db_status = f"✅ DB 연결 성공 (총 일정: {count}개)"
        except Exception as e:
            db_status = f"❌ DB 조회 에러: {e}"
            count = 0
            
        print(f"\n{'='*60}\n🚀 {self.user.name} 가동 완료 | {db_status}\n{'='*60}")

        # 슈퍼 관리자 DM 알림
        super_admin_id = 771274777443696650
        user = self.get_user(super_admin_id) or await self.fetch_user(super_admin_id)
        if user:
            try:
                embed = discord.Embed(
                    title="🌐 SyncTask 서버 가동 보고",
                    description=f"시스템이 재시작되었습니다.\n**📊 DB 상태:** {db_status}",
                    color=0x5865F2
                )
                embed.add_field(name="🔑 관리자 비밀번호", value=f"||{os.getenv('ADMIN_PASSWORD', 'admin1234')}||")
                await user.send(embed=embed)
            except: pass

bot = SyncTaskBot()

async def main():
    from web.server import run_web_server
    async def start_web():
        while bot.db is None: await asyncio.sleep(0.5)
        await run_web_server(bot.db)

    async with bot:
        bot.loop.create_task(start_web())
        await bot.start(os.getenv('DISCORD_TOKEN'))

if __name__ == "__main__":
    asyncio.run(main())
