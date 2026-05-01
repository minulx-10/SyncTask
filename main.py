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
        # 봇이 완전히 준비될 때까지 잠시 대기
        await asyncio.sleep(2)
        
        # 대시보드 초기 업데이트
        tasks_cog = self.get_cog("TasksCog")
        if tasks_cog:
            await tasks_cog.update_dashboard()
        
        # DB 데이터 개수 확인 로그
        async with self.db.execute("SELECT count(*) FROM tasks") as cursor:
            count = (await cursor.fetchone())[0]
            
        print(f"🚀 {self.user.name} 가동 완료 (서버: {len(self.guilds)}개 / 총 일정: {count}개)")

        # 슈퍼 관리자에게 DM 전송
        super_admin_id = 771274777443696650
        try:
            user = self.get_user(super_admin_id) or await self.fetch_user(super_admin_id)
            if user:
                embed = discord.Embed(
                    title="🌐 SyncTask 시스템 재가동 완료",
                    description="SSH 기반 고속 터널링 기술을 통해 대시보드가 활성화되었습니다.",
                    color=0x5865F2,
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="👉 대시보드 주소", value="`http://서버IP:10000`", inline=False)
                embed.add_field(name="🔑 접속 비밀번호", value=f"||{os.getenv('ADMIN_PASSWORD', 'admin1234')}||", inline=False)
                embed.add_field(name="📊 데이터 상태", value=f"총 {count}개의 일정이 로드되었습니다.", inline=True)
                embed.set_footer(text="이 정보는 유출되지 않도록 주의해 주세요.")
                await user.send(embed=embed)
                print(f"📬 슈퍼 관리자({user.name})에게 접속 정보를 전송했습니다.")
        except Exception as e:
            print(f"❌ DM 전송 실패: {e}")

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
