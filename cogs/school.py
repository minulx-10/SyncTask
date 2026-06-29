import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import re
import holidays
from utils.logger import record_log
from utils.formatter import get_schedule_message, parse_exam_dates, normalize_deadline, parse_deadline, truncate_discord_text, kst
from utils.ui import (
    EXAM_COLOR, REMINDER_COLOR, SCHEDULE_COLOR, SUCCESS_COLOR, TASK_COLOR, MEAL_COLOR, FOOTER_TEXT, DIVIDER,
    E_EXAM, E_SCHEDULE, E_REMINDER, E_MEAL,
    embed, brand_footer, ok, warn,
)
from core.neis_api import fetch_neis_timetable, fetch_neis_meal, fetch_neis_school_schedule, fetch_neis_exam_dates
from cogs.admin import SUPER_ADMINS, is_manager_or_admin

def next_school_day(start_date: datetime.datetime) -> datetime.datetime:
    target_date = start_date + datetime.timedelta(days=1)
    kr_holidays = holidays.KR(years=[target_date.year, target_date.year + 1])
    while target_date.weekday() >= 5 or target_date.date() in kr_holidays:
        target_date += datetime.timedelta(days=1)
    return target_date

MEAL_LABELS = {"1": "아침", "2": "점심", "3": "저녁"}
MEAL_EMOJIS = {"1": "🥣", "2": "🍱", "3": "🍖"}
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

def meal_target_date(target: str) -> datetime.datetime:
    now = datetime.datetime.now(kst)
    if target == "내일":
        return now + datetime.timedelta(days=1)
    return now

def default_meal_selection(now: datetime.datetime | None = None) -> tuple[datetime.datetime, str]:
    target_date = now or datetime.datetime.now(kst)
    current = target_date.time()
    if current <= datetime.time(hour=8, minute=10):
        return target_date, "1"
    if current <= datetime.time(hour=13, minute=30):
        return target_date, "2"
    if current <= datetime.time(hour=19, minute=30):
        return target_date, "3"
    return target_date + datetime.timedelta(days=1), "1"

def format_calorie(raw: str | None) -> str | None:
    """NEIS CAL_INFO('845.0 Kcal')를 '845kcal' 형태로 정규화. 숫자가 없으면 None."""
    if not raw:
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", raw)
    if not m:
        return None
    value = float(m.group().replace(",", ""))
    number = int(value) if value == int(value) else round(value, 1)
    return f"{number}kcal"


def format_meal_value(meal: dict | None, limit: int = 1000) -> str:
    if not meal:
        return "등록된 급식 정보가 없습니다."

    dishes = meal.get("dishes") or []
    if dishes:
        text = "\n".join(f"• {dish}" for dish in dishes)
    else:
        text = "등록된 메뉴가 없습니다."

    calorie = format_calorie(meal.get("calorie"))
    if calorie:
        text += f"\n\n*{calorie}*"
    return truncate_discord_text(text, limit)

def build_meal_embed(target_date: datetime.datetime, meal_data: dict, meal_code: str) -> discord.Embed:
    weekday = WEEKDAYS[target_date.weekday()]
    date_label = f"{target_date.month}월 {target_date.day}일 ({weekday})"

    if not meal_data:
        item = embed(
            title=f"{E_MEAL}  {date_label} 급식",
            description="아직 등록된 급식 정보가 없어요.",
            color=MEAL_COLOR,
            author="오늘의 급식",
        )
    elif meal_code == "전체":
        item = embed(
            title=f"{E_MEAL}  {date_label} 급식",
            color=MEAL_COLOR,
            author="오늘의 급식",
        )
        for code in ("1", "2", "3"):
            item.add_field(
                name=f"{MEAL_EMOJIS[code]}　{MEAL_LABELS[code]}",
                value=format_meal_value(meal_data.get(code)),
                inline=False,
            )
    else:
        label = MEAL_LABELS[meal_code]
        emoji = MEAL_EMOJIS[meal_code]
        item = embed(
            title=f"{emoji}  {date_label} · {label}",
            description=format_meal_value(meal_data.get(meal_code), 3900),
            color=MEAL_COLOR,
            author="오늘의 급식",
        )

    brand_footer(item, f"{target_date.strftime('%Y.%m.%d')} ({weekday}) · {FOOTER_TEXT}")
    return item

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

    @app_commands.command(name="급식", description="급식을 보여줍니다. 옵션 없이 실행하면 현재 시간 기준 다음 급식을 보여줍니다.")
    @app_commands.describe(target="볼 날짜. '전체'는 오늘 아침/점심/저녁을 한 번에 표시. 선택하지 않으면 오늘", meal="전체 또는 아침/점심/저녁 선택")
    @app_commands.choices(
        target=[
            app_commands.Choice(name="오늘", value="오늘"),
            app_commands.Choice(name="내일", value="내일"),
            app_commands.Choice(name="전체", value="전체"),
        ],
        meal=[
            app_commands.Choice(name="전체", value="전체"),
            app_commands.Choice(name="아침", value="1"),
            app_commands.Choice(name="점심", value="2"),
            app_commands.Choice(name="저녁", value="3"),
        ],
    )
    async def meal(self, interaction: discord.Interaction, target: app_commands.Choice[str] = None, meal: app_commands.Choice[str] = None):
        target_value = target.value if target else "오늘"
        # '전체' 타겟은 날짜가 아니라 '오늘 모든 끼니'를 의미 → 오늘 날짜로 매핑하고 아래 전체 분기를 타게 함
        if target_value == "전체":
            target_value = "오늘"
        if meal:
            meal_value = meal.value
            meal_name = meal.name
        elif target:
            meal_value = "전체"
            meal_name = "전체"
        else:
            target_date, meal_value = default_meal_selection()
            target_value = "내일" if target_date.date() > datetime.datetime.now(kst).date() else "오늘"
            meal_name = f"자동-{MEAL_LABELS[meal_value]}"
        await record_log(interaction, "급식", f"날짜:[{target_value}] 식사:[{meal_name}]")
        await interaction.response.defer()

        if meal or target:
            target_date = meal_target_date(target_value)
        meal_data = await fetch_neis_meal(target_date.strftime("%Y%m%d"))

        if meal_data is None:
            return await interaction.followup.send(warn("NEIS API 오류로 급식을 불러오지 못했습니다."))

        meal_embed = build_meal_embed(target_date, meal_data, meal_value)
        await interaction.followup.send(embed=meal_embed)

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
        await interaction.response.send_message(ok(f"**{exam_type.name}** 기간을 `{formatted_date}`로 설정했습니다."), ephemeral=True)

    @app_commands.command(name="시험일정동기화", description="NEIS 학사일정에서 중간/기말고사 날짜를 자동으로 가져와 설정합니다.")
    @is_manager_or_admin()
    async def sync_exam_dates(self, interaction: discord.Interaction):
        await record_log(interaction, "시험일정동기화")
        await interaction.response.defer(ephemeral=True)

        now = datetime.datetime.now(kst)
        exam_data = await fetch_neis_exam_dates(now.year)

        if not exam_data:
            return await interaction.followup.send(
                warn("이번 학기 학사일정에서 시험 일정을 찾지 못했습니다.\n"
                     "아직 NEIS에 등록되지 않았을 수 있어요."),
                ephemeral=True,
            )

        semester = exam_data.pop("semester", "")
        result_lines = []
        name_map = {"midterm_date": "1차 지필평가 (중간)", "final_date": "2차 지필평가 (기말)"}

        for key, date_str in exam_data.items():
            if key not in name_map:
                continue
            await self.bot.db.execute(
                "REPLACE INTO config (guild_id, key, value) VALUES (?, ?, ?)",
                (interaction.guild_id, key, date_str),
            )
            result_lines.append(f"{E_EXAM} **{name_map[key]}** · `{date_str}`")

        await self.bot.db.commit()

        sync_embed = embed(
            title=f"{E_EXAM}  {semester} 시험 일정 동기화 완료",
            description=f"NEIS 학사일정에서 **{semester}** 시험 일정을\n자동으로 감지하여 설정했습니다.",
            color=SUCCESS_COLOR,
        )
        sync_embed.add_field(
            name="📅 감지된 일정",
            value="\n".join(result_lines),
            inline=False,
        )
        brand_footer(sync_embed, "💡 /시험일정설정 으로 수동 수정도 가능합니다.")
        await interaction.followup.send(embed=sync_embed, ephemeral=True)

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
            await interaction.response.send_message(ok(f"**{exam_type.name}** {subject} 시험 범위를 등록했습니다."), ephemeral=True)
        else:
            request_embed = embed(f"{E_EXAM}  시험 범위 등록 요청", color=EXAM_COLOR)
            request_embed.add_field(name="시험", value=exam_type.name, inline=True)
            request_embed.add_field(name="과목", value=subject, inline=True)
            request_embed.add_field(name="범위", value=scope, inline=False)
            request_embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            brand_footer(request_embed, "승인 후 시험 범위에 반영됩니다.")

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
        
        scope_embed = embed(f"{E_EXAM}  시험 범위", color=EXAM_COLOR)
        
        for e_key, e_name in [("midterm_date", "중간고사"), ("final_date", "기말고사")]:
            field_value = ""
            async with self.bot.db.execute("SELECT value FROM config WHERE key=? AND guild_id=?", (e_key, interaction.guild_id)) as cursor:
                row = await cursor.fetchone()
                if row:
                    try:
                        start_dt, end_dt = parse_exam_dates(row[0], now)
                        days_to_start = (start_dt.replace(hour=0, minute=0, second=0, microsecond=0) - today_date).days
                        days_to_end = (end_dt.replace(hour=0, minute=0, second=0, microsecond=0) - today_date).days
                        
                        if days_to_start > 0:
                            field_value += f"📅 {row[0]} · `D-{days_to_start}`\n"
                        elif days_to_end >= 0:
                            field_value += f"🔥 진행 중 · {abs(days_to_start) + 1}일차\n"
                        else:
                            field_value += f"✅ {row[0]} · 종료\n"
                    except Exception:
                        field_value += f"📅 {row[0]}\n"
                else:
                    field_value += "일정 미등록\n"
            
            async with self.bot.db.execute("SELECT id, content FROM tasks WHERE task_type='시험범위' AND deadline=? AND guild_id=?", (e_name, interaction.guild_id)) as cursor:
                tasks = await cursor.fetchall()
                if tasks:
                    for t_id, content in tasks:
                        field_value += f"　└ `#{t_id}` {content}\n"
                else:
                    field_value += "　└ 등록된 시험 범위 없음\n"
            
            scope_embed.add_field(name=f"📝 {e_name}", value=field_value.strip(), inline=False)
            
        await interaction.response.send_message(embed=scope_embed)

    @app_commands.command(name="학사일정", description="이번 달 또는 특정 달의 학사일정을 확인합니다.")
    @app_commands.describe(month="확인할 월 (1~12, 입력하지 않으면 이번 달)")
    async def school_schedule(self, interaction: discord.Interaction, month: int = None):
        await record_log(interaction, "학사일정", f"{month}월" if month else "이번달")
        
        # API 호출 시간이 걸릴 수 있으므로 미리 응답 대기 상태로 전환
        await interaction.response.defer()

        now = datetime.datetime.now(kst)
        target_year = now.year
        target_month = month if month else now.month

        if target_month < 1 or target_month > 12:
            return await interaction.followup.send(warn("월은 1에서 12 사이의 숫자로 입력해주세요."))

        # 요청할 월의 1일부터 31일까지로 설정 (존재하지 않는 31일도 API가 알아서 월별로 잘라서 반환함)
        start_date = f"{target_year}{target_month:02d}01"
        end_date = f"{target_year}{target_month:02d}31"

        schedule_data = await fetch_neis_school_schedule(start_date, end_date)

        if schedule_data is None:
            return await interaction.followup.send(warn("NEIS API 오류로 일정을 불러오지 못했습니다."))
        
        if not schedule_data:
            empty_embed = embed(
                f"{E_SCHEDULE}  {target_year}년 {target_month}월 학사일정",
                "등록된 학교 행사가 없습니다.",
                color=SCHEDULE_COLOR,
            )
            return await interaction.followup.send(embed=empty_embed)

        desc = ""
        for s_date, e_date, event in schedule_data:
            s_fmt = f"{int(s_date[4:6])}/{int(s_date[6:8])}"
            if e_date:
                e_fmt = f"{int(e_date[4:6])}/{int(e_date[6:8])}"
                desc += f"📅 **{s_fmt}~{e_fmt}** · {event}\n"
            else:
                desc += f"📅 **{s_fmt}** · {event}\n"

        schedule_embed = embed(
            title=f"{E_SCHEDULE}  {target_year}년 {target_month}월 학사일정", 
            description=desc.strip(), 
            color=SCHEDULE_COLOR,
        )
        await interaction.followup.send(embed=schedule_embed)

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
            INSERT INTO user_settings (guild_id, user_id, reminder_enabled, reminder_scope)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET
                reminder_enabled=excluded.reminder_enabled,
                reminder_scope=excluded.reminder_scope
            """,
            (interaction.guild_id, interaction.user.id, 1 if enabled else 0, selected_scope),
        )
        await self.bot.db.commit()
        status = "켜졌습니다 🔔" if enabled else "꺼졌습니다 🔕"
        await interaction.response.send_message(ok(f"개인 알림이 {status}\n범위: `{selected_scope}`"), ephemeral=True)

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
            title=f"{E_REMINDER}  이번 주 학급 일정 요약",
            description=f"{today_date.strftime('%m/%d')} ~ {week_end.strftime('%m/%d')} 기준",
            color=REMINDER_COLOR,
        )
        if upcoming:
            text = ""
            for days, t_id, task_type, deadline, content in upcoming:
                if days == 0:
                    d_txt = "🔴 오늘"
                elif days <= 2:
                    d_txt = f"🟡 D-{days}"
                else:
                    d_txt = f"🟢 D-{days}"
                text += f"`#{t_id}` [{task_type}] {content}\n　　{deadline} · {d_txt}\n"
            summary_embed.add_field(name="📌 이번 주 마감", value=truncate_discord_text(text, 1000), inline=False)
        else:
            summary_embed.add_field(name="📌 이번 주 마감", value="이번 주 안에 마감되는 일정이 없습니다. 🎉", inline=False)

        if tbd:
            text = "\n".join([f"`#{t_id}` [{task_type}] {content}" for t_id, task_type, _, content in tbd[:8]])
            summary_embed.add_field(name="📋 마감 미정", value=text, inline=False)
        await interaction.response.send_message(embed=summary_embed)

    @tasks.loop(time=[datetime.time(hour=6, minute=30, tzinfo=kst), datetime.time(hour=19, minute=30, tzinfo=kst)])
    async def send_reminder(self):
        now = datetime.datetime.now(kst)
        is_evening = now.hour >= 18
        if is_evening and now.weekday() in [4, 5]: return
        if not is_evening and now.weekday() in [5, 6]: return
        
        target_date = next_school_day(now) if is_evening else now
        if is_evening:
            prefix = f"**🌙 내일 일정 미리보기**"
        else: 
            prefix = f"**☀️ 오늘 일정 알림**"

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
