import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from dotenv import load_dotenv
from core.database import init_db
from web.server import run_web_server

load_dotenv()

class SyncTaskBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix='!', intents=intents)
        self.db = None
        self.remove_command('help')

    async def setup_hook(self):
        # 1. DB 초기화
        self.db = await init_db()
        
        # 2. Cog 로드
        initial_extensions = [
            'cogs.admin',
            'cogs.tasks',
            'cogs.school'
        ]
        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                print(f"✅ Cog 로드 완료: {extension}")
            except Exception as e:
                print(f"❌ Cog 로드 실패: {extension} ({e})")
        
        # 3. 슬래시 명령어 동기화
        await self.tree.sync()
        
        # 4. 지속형 뷰(Buttons) 등록
        from cogs.tasks import DashboardView
        self.add_view(DashboardView(self))

    async def on_ready(self):
        # 봇이 완전히 준비될 때까지 넉넉히 대기 (5초)
        await asyncio.sleep(5)
        
        # 대시보드 및 내부 상태 업데이트
        tasks_cog = self.get_cog("TasksCog")
        if tasks_cog:
            await tasks_cog.update_dashboard()
        
        # DB 상태 정밀 점검
        try:
            async with self.db.execute("SELECT count(*) FROM tasks") as cursor:
                count = (await cursor.fetchone())[0]
            db_status = f"✅ DB 연결 성공 (총 일정: {count}개)"
        except Exception as e:
            db_status = f"❌ DB 조회 에러: {e}"
            count = 0
            
        print(f"\n{'='*60}")
        print(f"🚀 {self.user.name} 가동 완료 | {db_status}")
        print(f"{'='*60}")
        print("🌐 SyncTask Admin Dashboard is LIVE!")
        print(f"🔗 URL: http://서버IP:10000")
        print("🔑 Password: [PROTECTED] (Check your .env file)")
        print(f"{'='*60}\n")

        # 슈퍼 관리자(유저님) 찾기 및 DM 전송 시도
        super_admin_id = 771274777443696650
        user = self.get_user(super_admin_id)
        
        if not user:
            for guild in self.guilds:
                member = guild.get_member(super_admin_id)
                if member: user = member; break
        
        if not user:
            try: user = await self.fetch_user(super_admin_id)
            except: pass

        if user:
            try:
                embed = discord.Embed(
                    title="🌐 SyncTask 서버 가동 보고",
                    description=f"배포 서버에서 시스템이 성공적으로 재시작되었습니다.\n\n**📊 현재 DB 상태:** {db_status}",
                    color=0x5865F2,
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="👉 대시보드 주소", value="`http://서버IP:10000`", inline=False)
                embed.add_field(name="🔑 접속 비밀번호", value=f"||{os.getenv('ADMIN_PASSWORD', 'admin1234')}||", inline=False)
                embed.set_footer(text="이 메시지가 보인다면 대시보드에 접속해 보세요.")
                await user.send(embed=embed)
                print(f"📬 슈퍼 관리자({user.name})에게 DM을 보냈습니다.")
            except:
                print("⚠️ DM 발송에 실패했습니다. 터미널의 주소를 확인해 주세요.")

@app_commands.command(name="sync", description="전역 명령어를 동기화합니다.")
async def sync(interaction: discord.Interaction):
    if interaction.user.id == 771274777443696650:
        await interaction.client.tree.sync()
        await interaction.response.send_message("✅ 명령어 동기화 완료!", ephemeral=True)
    else:
        await interaction.response.send_message("🚫 권한이 없습니다.", ephemeral=True)

async def main():
    bot = SyncTaskBot()
    
    # 에러 핸들러 추가
    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("🚫 권한이 없습니다! 반장/부반장 또는 봇 관리자만 사용 가능합니다.", ephemeral=True)
        else:
            print(f"AppCommand error: {error}")

    async def start_web():
        while bot.db is None:
            await asyncio.sleep(0.5)
        await run_web_server(bot.db)

    async with bot:
        bot.loop.create_task(start_web())
        await bot.start(os.getenv('DISCORD_TOKEN'))

if __name__ == "__main__":
    asyncio.run(main())
