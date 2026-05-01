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
        intents.members = True 
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
        print(f'🚀 SyncTask 봇 로그인 완료: {self.user.name}')
        tasks_cog = self.get_cog("TasksCog")
        if tasks_cog:
            await tasks_cog.update_dashboard()

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
