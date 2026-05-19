import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import datetime
import aiohttp
from dotenv import load_dotenv
from core.database import init_db
from utils.ui import BOOT_COLOR, E_BOOT, DIVIDER

load_dotenv()
kst = datetime.timezone(datetime.timedelta(hours=9))

async def get_dashboard_url():
    """대시보드 URL을 결정한다. 외부 접근 가능 여부도 함께 반환."""
    public_url = os.getenv("DASHBOARD_PUBLIC_URL")
    if public_url:
        return public_url, True  # 명시적으로 설정된 공개 URL → 접근 가능

    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = os.getenv("DASHBOARD_PORT", "10000")

    if host in ("0.0.0.0", "::"):
        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://api.ipify.org") as resp:
                    if resp.status == 200:
                        public_ip = (await resp.text()).strip()
                        url = f"http://{public_ip}:{port}"
                        # 실제 접근 가능한지 셀프 체크
                        try:
                            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as check:
                                if check.status in (200, 302, 401):
                                    return url, True
                        except Exception:
                            pass
                        return url, False  # IP는 알지만 접근 불가 (방화벽 등)
        except Exception:
            pass

    # localhost 전용 — 외부 접근 불가
    return f"http://{host}:{port}", False


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
                    print(f"  ✓ Loaded: {filename}")
                except Exception as e:
                    print(f"  ✗ Failed: {filename} — {e}")

        # 3. Persistent Views 등록
        from cogs.tasks import DashboardView
        self.add_view(DashboardView(self))

        if os.getenv("SYNC_COMMANDS_ON_BOOT", "1") == "1":
            print("⟳ Syncing slash commands...")
            await self.tree.sync()
            print("✓ Slash commands synced.")

    async def on_ready(self):
        # 봇이 완전히 준비될 때까지 잠시 대기
        await asyncio.sleep(5)
        
        if os.getenv("GUILD_SYNC_ON_READY", "1") == "1":
            print("⟳ 서버별 즉시 동기화 진행 중...")
            for guild in self.guilds:
                try:
                    self.tree.copy_global_to(guild=guild)
                    await self.tree.sync(guild=guild)
                    print(f"  ✓ {guild.name}")
                except Exception as e:
                    print(f"  ✗ {guild.name}: {e}")

        tasks_cog = self.get_cog("TasksCog")
        if tasks_cog:
            await tasks_cog.update_dashboard()
        
        try:
            async with self.db.execute("SELECT count(*) FROM tasks") as cursor:
                count = (await cursor.fetchone())[0]
            db_status = f"✅ 정상 · 일정 {count}개"
        except Exception as e:
            db_status = f"⚠️ 조회 실패 · {e}"
            count = 0
            
        now_str = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'━'*50}")
        print(f"  {self.user.name} 가동 완료")
        print(f"  DB: {db_status}")
        print(f"  Time: {now_str} KST")
        print(f"{'━'*50}")

        # ── 슈퍼 관리자 DM 가동 보고 ──
        super_admin_id = 771274777443696650
        user = self.get_user(super_admin_id) or await self.fetch_user(super_admin_id)
        if user:
            try:
                dashboard_url, is_accessible = await get_dashboard_url()
                
                boot_embed = discord.Embed(
                    title=f"{E_BOOT}  SyncTask 가동 완료",
                    color=BOOT_COLOR,
                )
                
                # 서버 정보
                guilds_text = "\n".join([f"　└ {g.name} ({g.member_count}명)" for g in self.guilds]) or "연결된 서버 없음"
                boot_embed.add_field(name="📡 연결된 서버", value=guilds_text, inline=False)
                boot_embed.add_field(name="💾 데이터베이스", value=db_status, inline=True)
                
                # 대시보드 — 접근 가능 여부에 따라 표시 분기
                if is_accessible:
                    admin_password = os.getenv("ADMIN_PASSWORD")
                    dash_value = f"[{dashboard_url}]({dashboard_url})"
                    if admin_password:
                        dash_value += f"\n비밀번호: ||{admin_password}||"
                    boot_embed.add_field(name="🌐 대시보드", value=dash_value, inline=False)
                else:
                    boot_embed.add_field(
                        name="🌐 대시보드",
                        value=(
                            f"로컬 주소: `{dashboard_url}`\n"
                            "⚠️ 외부에서 접근할 수 없습니다.\n"
                            "공개 URL이 필요하면 `.env`에\n"
                            "`DASHBOARD_PUBLIC_URL`을 설정하세요."
                        ),
                        inline=False,
                    )

                boot_embed.set_footer(text=f"{now_str} KST · {DIVIDER}")
                await user.send(embed=boot_embed)
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
