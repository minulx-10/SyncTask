import datetime
import discord

kst = datetime.timezone(datetime.timedelta(hours=9))

def parse_deadline(deadline_str: str, now: datetime.datetime) -> datetime.datetime:
    m, d = map(int, deadline_str.split('/'))
    target_year = now.year
    if now.month >= 11 and m <= 2:
        target_year += 1
    return datetime.datetime(target_year, m, d, tzinfo=kst)

def parse_exam_dates(date_range_str: str, now: datetime.datetime):
    if '~' in date_range_str:
        start_str, end_str = date_range_str.split('~')
    else:
        start_str = end_str = date_range_str
        
    start_dt = parse_deadline(start_str.strip(), now)
    end_dt = parse_deadline(end_str.strip(), now)
    return start_dt, end_dt

async def get_schedule_message(target_date: datetime.datetime, guild_id: int, db, fetch_neis_timetable) -> discord.Embed:
    weekday_num = target_date.weekday()
    weekday_str = ['월', '화', '수', '목', '금', '토', '일'][weekday_num]
    
    # 임베드 기본 설정
    color = 0x5865F2 if weekday_num < 5 else 0x57F287  # 평일은 파랑, 주말은 초록
    embed = discord.Embed(
        title=f"📅 {target_date.month}월 {target_date.day}일 {weekday_str}요일 일정",
        color=color,
        timestamp=datetime.datetime.now(kst)
    )
    
    now = datetime.datetime.now(kst)
    today_date = now.replace(hour=0, minute=0, second=0, microsecond=0) 
    
    # 🚨 시험 일정 (D-Day)
    exam_info = ""
    for e_key, e_name in [("midterm_date", "중간고사"), ("final_date", "기말고사")]:
        async with db.execute("SELECT value FROM config WHERE key=? AND guild_id=?", (e_key, guild_id)) as cursor:
            row = await cursor.fetchone()
            if row:
                try:
                    start_dt, end_dt = parse_exam_dates(row[0], now)
                    days_to_start = (start_dt.replace(hour=0, minute=0, second=0, microsecond=0) - today_date).days
                    days_to_end = (end_dt.replace(hour=0, minute=0, second=0, microsecond=0) - today_date).days
                    
                    if days_to_start > 0:
                        exam_info += f"🔔 **{e_name}**까지 `D-{days_to_start}` (기간: {row[0]})\n"
                    elif days_to_end >= 0:
                        day_num = abs(days_to_start) + 1
                        exam_info += f"🔥 **{e_name} 진행 중!** ({day_num}일차 / 기간: {row[0]})\n"
                except Exception: pass
    
    if exam_info:
        embed.add_field(name="📢 주요 학사 일정", value=exam_info.strip(), inline=False)
        
    # 📚 시간표
    timetable_text = ""
    async with db.execute("SELECT value FROM config WHERE key='grade' AND guild_id=?", (guild_id,)) as cursor:
        g_row = await cursor.fetchone()
    async with db.execute("SELECT value FROM config WHERE key='class_nm' AND guild_id=?", (guild_id,)) as cursor:
        c_row = await cursor.fetchone()

    if weekday_num >= 5: 
        timetable_text = "✨ 오늘은 즐거운 휴일입니다! 푹 쉬세요."
    elif g_row and c_row:
        date_str = target_date.strftime("%Y%m%d")
        timetable = await fetch_neis_timetable(date_str, g_row[0], c_row[0])
        if timetable:
            timetable_text = "".join([f"`{perio}교시` {subject}\n" for perio, subject in timetable])
        else: 
            timetable_text = "❌ 나이스(NEIS) 데이터가 없습니다."
    else: 
        timetable_text = "⚠️ `/학급설정`을 먼저 진행해주세요."
    
    embed.add_field(name="📖 시간표", value=timetable_text.strip(), inline=True)
        
    # 📝 학급 일정 (숙제/수행)
    async with db.execute('SELECT task_type, content FROM tasks WHERE deadline = ? AND guild_id = ?', (target_date.strftime("%m/%d"), guild_id)) as cursor:
        target_tasks = await cursor.fetchall()
    
    task_text = ""
    if not target_tasks: 
        task_text = "✅ 마감인 일정이 없습니다."
    else:
        tasks_dict = {}
        for t_type, content in target_tasks: tasks_dict.setdefault(t_type, []).append(content)
        for t_type, contents in tasks_dict.items():
            emoji = "✏️" if "숙제" in t_type else "🧪" if "수행" in t_type else "📌"
            task_text += f"**{emoji} {t_type}**\n" + "".join([f"└ {c}\n" for c in contents])
            
    embed.add_field(name="📝 학급 일정", value=task_text.strip(), inline=True)
    embed.set_footer(text="SyncTask Service • 광주소프트웨어마이스터고")
    
    return embed

async def get_task_list_embed(task_type_name: str, guild_id: int, db) -> discord.Embed:
    now = datetime.datetime.now(kst)
    today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    async with db.execute('SELECT id, deadline, content FROM tasks WHERE task_type = ? AND guild_id = ?', (task_type_name, guild_id)) as cursor:
        tasks_list = await cursor.fetchall()
    
    color = 0xF1C40F if "숙제" in task_type_name else 0x3498DB
    embed = discord.Embed(title=f"📌 남은 {task_type_name} 목록", color=color)
    
    if not tasks_list:
        embed.description = f"✅ 현재 등록된 **{task_type_name}** 일정이 없습니다!"
        return embed

    dated_tasks, tbd_tasks = [], []
    for r in tasks_list:
        if r[1] == "미정": tbd_tasks.append(r)
        else:
            try:
                target = parse_deadline(r[1], now)
                dated_tasks.append(((target - today_date).days, r))
            except ValueError: pass
            
    dated_tasks.sort(key=lambda x: x[0])
    
    content_text = ""
    for days, r in dated_tasks:
        d_txt = "🔴 당일!" if days == 0 else (f"⚪ D+{-days} (종료)" if days < 0 else f"🟡 D-{days}")
        content_text += f"`ID:{r[0]}` **{r[2]}**\n└ 마감: {r[1]} ({d_txt})\n"
    
    for r in tbd_tasks:
        content_text += f"`ID:{r[0]}` **{r[2]}**\n└ 마감: 미정 (⚪)\n"
        
    embed.description = content_text.strip()
    embed.set_footer(text=f"총 {len(tasks_list)}개의 항목이 있습니다.")
    return embed
