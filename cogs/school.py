import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import holidays
from utils.logger import record_log
from utils.formatter import get_schedule_message, parse_exam_dates, normalize_deadline, parse_deadline, truncate_discord_text, kst
from utils.ui import EXAM_COLOR, REMINDER_COLOR, embed, ok, warn
from core.neis_api import fetch_neis_timetable
from cogs.admin import SUPER_ADMINS, is_manager_or_admin

def next_school_day(start_date: datetime.datetime) -> datetime.datetime:
    target_date = start_date + datetime.timedelta(days=1)
    kr_holidays = holidays.KR(years=[target_date.year, target_date.year + 1])
    while target_date.weekday() >= 5 or target_date.date() in kr_holidays:
        target_date += datetime.timedelta(days=1)
    return target_date

class SchoolCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.send_reminder.start()

    def cog_unload(self):
        self.send_reminder.cancel()

    @app_commands.command(name="오늘", description="오늘의 시간표와 마감 일정을 보여줍니다.")
    async def today(self, interaction: discord.Interaction):
        await record_log(interaction, "오늘")
        embed = await get_schedule_message(datetime.datetime.now(kst), interaction.guild_id, self.bot.db, fetch_neis_timetable)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="내일", description="내일(다음 등교일)의 시간표와 일정을 보여줍니다.")
    async def tomorrow(self, interaction: discord.Interaction):
        await record_log(interaction, "내일")
        now = datetime.datetime.now(kst)
        target_date = next_school_day(now)
        
        embed = await get_schedule_message(target_date, interaction.guild_id, self.bot.db, fetch_neis_timetable)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="시간표", description="선택한 날짜의 시간표를 보여줍니다.")
    @app_commands.choices(target=[app_commands.Choice(name="오늘", value="오늘"), app_commands.Choice(name="내일", value="내일")])
    async def timetable(self, interaction: discord.Interaction, target: app_commands.Choice[str] = None):
        val = target.value if target else "오늘"
        await record_log(interaction, "시간표", f"대상:[{val}]")
        now = datetime.datetime.now(kst)
        target_date = now if val == "오늘" else next_school_day(now)
        if val == "내일":
            target_date = next_school_day(now)
            
        embed = await get_schedule_message(target_date, interaction.guild_id, self.bot.db, fetch_neis_timetable)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="시험일정설정", description="중간/기말고사의 시작일과 종료일을 설정합니다.")
    @is_manager_or_admin()
    @app_commands.choices(exam_type=[
        app_commands.Choice(name="중간고사", value="midterm_date"),
        app_commands.Choice(name="기말고사", value="final_date")
    ])
    async def set_exam_date(self, interaction: discord.Interaction, exam_type: app_commands.Choice[str], start_date: str, end_date: str):
        await record_log(interaction, "시험일정설정", f"{exam_type.name} 기간: {start_date}~{end_date}")
        try:
            start_date = normalize_deadline(start_date)
            end_date = normalize_deadline(end_date)
            formatted_date = f"{start_date}~{end_date}"
        except ValueError:
            return await interaction.response.send_message(warn("날짜는 `MM/DD` 형식으로 입력해주세요."), ephemeral=True)
        
        await self.bot.db.execute("REPLACE INTO config (guild_id, key, value) VALUES (?, ?, ?)", (interaction.guild_id, exam_type.value, formatted_date))
        await self.bot.db.commit()
        await interaction.response.send_message(ok(f"{exam_type.name} 기간을 {formatted_date}로 설정했습니다."), ephemeral=True)

    @app_commands.command(name="시험범위추가", description="과목별 시험 범위를 등록합니다. (일반 유저는 승인 후 등록)")
    @app_commands.choices(exam_type=[
        app_commands.Choice(name="중간고사", value="중간고사"),
        app_commands.Choice(name="기말고사", value="기말고사")
    ])
    async def add_exam_scope(self, interaction: discord.Interaction, exam_type: app_commands.Choice[str], subject: str, scope: str):
        from cogs.tasks import TaskReviewView
        await record_log(interaction, "시험범위추가_시도", f"{exam_type.name} [{subject}] {scope}")
        content = f"[{subject}] {scope}"
        
        is_admin = interaction.user.id in SUPER_ADMINS or (hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.manage_messages)

        if is_admin:
            await self.bot.db.execute('INSERT INTO tasks (guild_id, task_type, deadline, content, channel_id) VALUES (?, ?, ?, ?, ?)', 
                           (interaction.guild_id, "시험범위", exam_type.value, content, interaction.channel_id))
            await self.bot.db.execute(
                """
                INSERT INTO change_logs (guild_id, user_id, action, details, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    interaction.guild_id,
                    interaction.user.id,
                    "시험범위추가",
                    f"{exam_type.name} {content}",
                    datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            await self.bot.db.commit()
            tasks_cog = self.bot.get_cog("TasksCog")
            if tasks_cog:
                await tasks_cog.update_dashboard(interaction.guild_id)
            await interaction.response.send_message(ok(f"{exam_type.name} {subject} 시험 범위를 등록했습니다."), ephemeral=True)
        else:
            request_embed = embed("시험 범위 등록 요청", color=EXAM_COLOR)
            request_embed.add_field(name="시험", value=exam_type.name, inline=True)
            request_embed.add_field(name="과목", value=subject, inline=True)
            request_embed.add_field(name="범위", value=scope, inline=False)
            request_embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            request_embed.set_footer(text="승인 후 시험 범위에 반영됩니다.")

            target_channel = interaction.channel
            async with self.bot.db.execute("SELECT value FROM config WHERE key='admin_log_channel' AND guild_id=?", (interaction.guild_id,)) as cursor:
                log_row = await cursor.fetchone()
            
            if log_row:
                ch = self.bot.get_channel(int(log_row[0]))
                if ch: target_channel = ch
            else:
                async with self.bot.db.execute("SELECT value FROM config WHERE key='dashboard_channel' AND guild_id=?", (interaction.guild_id,)) as cursor:
                    dash_row = await cursor.fetchone()
                if dash_row:
                    ch = self.bot.get_channel(int(dash_row[0]))
                    if ch: target_channel = ch
            
            await target_channel.send(embed=request_embed, view=TaskReviewView(self.bot, "시험범위", exam_type.value, content, interaction.user.id))
            await interaction.response.send_message(ok("시험 범위 요청을 보냈습니다."), ephemeral=True)

    @app_commands.command(name="시험범위", description="등록된 시험 범위와 디데이(D-Day)를 확인합니다.")
    async def exam_scope(self, interaction: discord.Interaction):
        await record_log(interaction, "시험범위_조회")
        now = datetime.datetime.now(kst)
        today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        msg = "**시험 범위**\n\n"
        for e_key, e_name in [("midterm_date", "중간고사"), ("final_date", "기말고사")]:
            async with self.bot.db.execute("SELECT value FROM config WHERE key=? AND guild_id=?", (e_key, interaction.guild_id)) as cursor:
                row = await cursor.fetchone()
                if row:
                    try:
                        start_dt, end_dt = parse_exam_dates(row[0], now)
                        days_to_start = (start_dt.replace(hour=0, minute=0, second=0, microsecond=0) - today_date).days
                        days_to_end = (end_dt.replace(hour=0, minute=0, second=0, microsecond=0) - today_date).days
                        
                        if days_to_start > 0: msg += f"**{e_name}** · {row[0]} · D-{days_to_start}\n"
                        elif days_to_end >= 0: msg += f"**{e_name}** · 진행 중 · {abs(days_to_start) + 1}일차\n"
                        else: msg += f"**{e_name}** · {row[0]} · 종료\n"
                    except Exception: msg += f"**{e_name}** · {row[0]}\n"
                else: msg += f"**{e_name}** · 일정 미등록\n"
            
            async with self.bot.db.execute("SELECT id, content FROM tasks WHERE task_type='시험범위' AND deadline=? AND guild_id=?", (e_name, interaction.guild_id)) as cursor:
                tasks = await cursor.fetchall()
                if tasks:
                    for t_id, content in tasks: msg += f"- `ID:{t_id}` {content}\n"
                else: msg += "- 등록된 시험 범위가 없습니다.\n"
            msg += "\n"
            
        await interaction.response.send_message(msg.strip())

    @app_commands.command(name="알림설정", description="개인 DM 알림 구독 여부와 범위를 설정합니다.")
    @app_commands.choices(scope=[
        app_commands.Choice(name="전체", value="전체"),
        app_commands.Choice(name="숙제", value="숙제"),
        app_commands.Choice(name="수행평가", value="수행평가"),
        app_commands.Choice(name="시험", value="시험"),
    ])
    async def reminder_setting(self, interaction: discord.Interaction, enabled: bool, scope: app_commands.Choice[str] = None):
        await record_log(interaction, "알림설정", f"enabled={enabled}, scope={scope.value if scope else '전체'}")
        selected_scope = scope.value if scope else "전체"
        await self.bot.db.execute(
            """
            REPLACE INTO user_settings (guild_id, user_id, reminder_enabled, reminder_scope)
            VALUES (?, ?, ?, ?)
            """,
            (interaction.guild_id, interaction.user.id, 1 if enabled else 0, selected_scope),
        )
        await self.bot.db.commit()
        status = "켜졌습니다" if enabled else "꺼졌습니다"
        await interaction.response.send_message(ok(f"개인 알림이 {status}. 범위: `{selected_scope}`"), ephemeral=True)

    @app_commands.command(name="주간요약", description="이번 주 남은 숙제, 수행평가, 시험 범위를 요약합니다.")
    async def weekly_summary(self, interaction: discord.Interaction):
        await record_log(interaction, "주간요약")
        now = datetime.datetime.now(kst)
        today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = today_date + datetime.timedelta(days=6 - today_date.weekday())

        async with self.bot.db.execute(
            "SELECT id, task_type, deadline, content FROM tasks WHERE guild_id=?",
            (interaction.guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        upcoming = []
        tbd = []
        for t_id, task_type, deadline, content in rows:
            if deadline == "미정":
                tbd.append((t_id, task_type, deadline, content))
                continue
            try:
                target = parse_deadline(deadline, now)
            except ValueError:
                continue
            if today_date <= target <= week_end:
                upcoming.append(((target - today_date).days, t_id, task_type, deadline, content))

        upcoming.sort(key=lambda item: (item[0], item[2]))
        summary_embed = embed(
            title="이번 주 학급 일정 요약",
            description=f"{today_date.strftime('%m/%d')}~{week_end.strftime('%m/%d')} 기준",
            color=REMINDER_COLOR,
        )
        if upcoming:
            text = ""
            for days, t_id, task_type, deadline, content in upcoming:
                d_txt = "오늘" if days == 0 else f"D-{days}"
                text += f"`ID:{t_id}` [{task_type}] {content} · {deadline} · {d_txt}\n"
            summary_embed.add_field(name="이번 주 마감", value=truncate_discord_text(text, 1000), inline=False)
        else:
            summary_embed.add_field(name="이번 주 마감", value="이번 주 안에 마감되는 일정이 없습니다.", inline=False)

        if tbd:
            text = "\n".join([f"`ID:{t_id}` [{task_type}] {content}" for t_id, task_type, _, content in tbd[:8]])
            summary_embed.add_field(name="마감 미정", value=text, inline=False)
        await interaction.response.send_message(embed=summary_embed)

    @tasks.loop(time=[datetime.time(hour=6, minute=30, tzinfo=kst), datetime.time(hour=19, minute=30, tzinfo=kst)])
    async def send_reminder(self):
        now = datetime.datetime.now(kst)
        is_evening = now.hour >= 18
        if is_evening and now.weekday() in [4, 5]: return
        if not is_evening and now.weekday() in [5, 6]: return
        
        target_date = next_school_day(now) if is_evening else now
        if is_evening:
            prefix = "**내일 일정 미리보기**"
        else: 
            prefix = "**오늘 일정 알림**"

        async with self.bot.db.execute("SELECT guild_id, value FROM config WHERE key='dashboard_channel'") as cursor:
            rows = await cursor.fetchall()
            
        for g_id, ch_id in rows:
            schedule_embed = await get_schedule_message(target_date, g_id, self.bot.db, fetch_neis_timetable)
            channel = self.bot.get_channel(int(ch_id))
            if channel: 
                await channel.send(content=prefix, embed=schedule_embed)

            async with self.bot.db.execute(
                """
                SELECT user_id, reminder_scope
                FROM user_settings
                WHERE guild_id=? AND reminder_enabled=1
                """,
                (g_id,),
            ) as cursor:
                users = await cursor.fetchall()

            for user_id, scope in users:
                try:
                    user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
                    if not user:
                        continue
                    await user.send(content=f"{prefix}\n범위: {scope}", embed=schedule_embed)
                except discord.HTTPException:
                    pass

async def setup(bot):
    await bot.add_cog(SchoolCog(bot))
