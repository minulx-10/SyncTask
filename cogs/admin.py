import discord
from discord.ext import commands
from discord import app_commands
from utils.logger import record_log
from utils.ui import (
    DASHBOARD_COLOR, SETUP_COLOR, MUTED_COLOR, BRAND_COLOR, DIVIDER,
    E_SETTING, E_HELP, E_STAR, E_DASHBOARD, E_OK, E_TASK,
    embed, ok,
)

SUPER_ADMINS = [771274777443696650]

def is_manager_or_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id in SUPER_ADMINS:
            return True
        if hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.manage_messages:
            return True
        return False
    return app_commands.check(predicate)

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="학급설정", description="시간표 조회를 위해 우리 반의 학년과 반을 설정합니다.")
    @is_manager_or_admin()
    async def class_setup(self, interaction: discord.Interaction, grade: int, class_nm: int):
        await record_log(interaction, "학급설정", f"{grade}학년 {class_nm}반")
        await self.bot.db.execute("REPLACE INTO config (guild_id, key, value) VALUES (?, 'grade', ?)", (interaction.guild_id, str(grade)))
        await self.bot.db.execute("REPLACE INTO config (guild_id, key, value) VALUES (?, 'class_nm', ?)", (interaction.guild_id, str(class_nm)))
        await self.bot.db.commit()
        await interaction.response.send_message(ok(f"시간표 기준을 **{grade}학년 {class_nm}반**으로 설정했습니다."), ephemeral=True)

    @app_commands.command(name="시작", description="처음 사용하는 서버를 위한 빠른 설정 안내를 보여줍니다.")
    async def start_guide(self, interaction: discord.Interaction):
        await record_log(interaction, "시작")
        guide = embed(
            title=f"{E_STAR}  SyncTask 빠른 시작",
            description="아래 순서대로 설정하면 바로 사용할 수 있어요.",
            color=SETUP_COLOR,
        )
        guide.add_field(
            name="Step 1 · 학급 등록",
            value=f"```/학급설정 grade:학년 class_nm:반```\n시간표 조회의 기준이 됩니다.",
            inline=False,
        )
        guide.add_field(
            name="Step 2 · 대시보드 설치",
            value=f"```/공지설정```\n공지 채널에서 실행하면 실시간 일정판이 생성됩니다.",
            inline=False,
        )
        guide.add_field(
            name="Step 3 · 일정 등록",
            value="`/추가` · `/시험일정설정` · `/시험범위추가`\n숙제, 수행평가, 시험 범위를 등록합니다.",
            inline=False,
        )
        guide.add_field(
            name="Step 4 · 개인 알림 (선택)",
            value="`/알림설정`으로 DM 알림을 받을 수 있습니다.",
            inline=False,
        )
        await interaction.response.send_message(embed=guide, ephemeral=True)

    @app_commands.command(name="도움말", description="SyncTask 주요 명령어와 사용 흐름을 확인합니다.")
    async def help_command(self, interaction: discord.Interaction):
        await record_log(interaction, "도움말")
        help_embed = embed(f"{E_HELP}  SyncTask 도움말", color=SETUP_COLOR)
        help_embed.add_field(
            name="📋 조회",
            value="`/오늘` `/내일` `/시간표` `/학사일정`\n`/전체일정` `/숙제` `/수행평가` `/시험범위` `/주간요약`",
            inline=False,
        )
        help_embed.add_field(
            name="📌 관리",
            value="`/추가` `/수정` `/삭제`\n`/시험일정설정` `/시험일정동기화` `/시험범위추가` `/변경이력`",
            inline=False,
        )
        help_embed.add_field(
            name="⚙️ 설정",
            value="`/시작` `/설정상태` `/학급설정`\n`/공지설정` `/로그채널설정` `/소개카드`",
            inline=False,
        )
        help_embed.add_field(
            name="🔔 개인",
            value="`/알림설정`으로 DM 알림을 관리합니다.",
            inline=False,
        )
        await interaction.response.send_message(embed=help_embed, ephemeral=True)

    @app_commands.command(name="설정상태", description="이 서버의 SyncTask 설정 상태를 확인합니다.")
    async def setup_status(self, interaction: discord.Interaction):
        await record_log(interaction, "설정상태")
        keys = ["grade", "class_nm", "dashboard_channel", "dashboard_message", "admin_log_channel"]
        values = {}
        for key in keys:
            async with self.bot.db.execute("SELECT value FROM config WHERE guild_id=? AND key=?", (interaction.guild_id, key)) as cursor:
                row = await cursor.fetchone()
                values[key] = row[0] if row else None

        status_embed = embed(f"{E_SETTING}  설정 상태", color=MUTED_COLOR)

        # 각 항목에 체크 표시
        class_ok = values["grade"] and values["class_nm"]
        dash_ok = values["dashboard_channel"] and values["dashboard_message"]
        log_ok = values["admin_log_channel"]

        class_value = f"✅ {values['grade']}학년 {values['class_nm']}반" if class_ok else "❌ 미설정"
        dashboard_value = "✅ 설정됨" if dash_ok else "❌ 미설정"
        log_value = f"✅ <#{values['admin_log_channel']}>" if log_ok else "➖ 미설정 (선택)"

        status_embed.add_field(name="학급", value=class_value, inline=True)
        status_embed.add_field(name="대시보드", value=dashboard_value, inline=True)
        status_embed.add_field(name="로그 채널", value=log_value, inline=True)

        if not class_ok or not dash_ok:
            status_embed.set_footer(text="💡 /시작 에서 설정 순서를 확인할 수 있습니다.")
        await interaction.response.send_message(embed=status_embed, ephemeral=True)

    @app_commands.command(name="소개카드", description="채널에 SyncTask 소개 메시지를 게시합니다.")
    @is_manager_or_admin()
    async def intro_card(self, interaction: discord.Interaction):
        await record_log(interaction, "소개카드")
        intro = embed(
            title=f"{E_STAR}  SyncTask — 학급 알리미",
            description="시간표 · 과제 · 수행평가 · 시험 범위를\n**한 곳에서** 확인하세요.",
            color=BRAND_COLOR,
        )
        intro.add_field(name="📋 일정 조회", value="`/오늘`  `/내일`  `/전체일정`  `/주간요약`", inline=False)
        intro.add_field(name="📌 일정 제안", value="`/추가` 명령어로 누구나 일정을 제안할 수 있어요.", inline=False)
        intro.add_field(name="🔔 개인 알림", value="`/알림설정`으로 DM 알림을 켜보세요.", inline=False)
        await interaction.response.send_message(ok("소개 카드를 게시했습니다."), ephemeral=True)
        await interaction.channel.send(embed=intro)

    @app_commands.command(name="공지설정", description="이 채널에 실시간 대시보드를 생성합니다.")
    @is_manager_or_admin()
    async def dashboard_setup(self, interaction: discord.Interaction):
        from cogs.tasks import DashboardView
        await record_log(interaction, "공지설정")
        await interaction.response.send_message(ok("대시보드를 설치했습니다."), ephemeral=True)
        msg = await interaction.channel.send(
            embed=embed(f"{E_DASHBOARD}  학급 일정 대시보드", "불러오는 중...", color=DASHBOARD_COLOR),
            view=DashboardView(self.bot),
        )
        await self.bot.db.execute("REPLACE INTO config (guild_id, key, value) VALUES (?, 'dashboard_channel', ?)", (interaction.guild_id, str(msg.channel.id)))
        await self.bot.db.execute("REPLACE INTO config (guild_id, key, value) VALUES (?, 'dashboard_message', ?)", (interaction.guild_id, str(msg.id)))
        await self.bot.db.commit()
        
        tasks_cog = self.bot.get_cog("TasksCog")
        if tasks_cog:
            await tasks_cog.update_dashboard(interaction.guild_id)

    @app_commands.command(name="로그채널설정", description="숙제 추가 요청(PR)을 받을 관리자 전 전용 채널을 설정합니다.")
    @is_manager_or_admin()
    async def log_channel_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await record_log(interaction, "로그채널설정", f"채널: {channel.name}")
        await self.bot.db.execute("REPLACE INTO config (guild_id, key, value) VALUES (?, 'admin_log_channel', ?)", (interaction.guild_id, str(channel.id)))
        await self.bot.db.commit()
        await interaction.response.send_message(ok(f"요청 채널을 {channel.mention}로 설정했습니다."), ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
