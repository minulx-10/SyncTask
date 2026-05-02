import datetime
import discord
import json

kst = datetime.timezone(datetime.timedelta(hours=9))

def normalize_deadline(deadline_str: str) -> str:
    if deadline_str == "미정":
        return deadline_str
    try:
        m, d = map(int, deadline_str.split('/'))
        datetime.date(2000, m, d)
    except (TypeError, ValueError):
        raise ValueError("날짜는 MM/DD 형식으로 입력해주세요.")
    return f"{m:02d}/{d:02d}"

def parse_deadline(deadline_str: str, now: datetime.datetime) -> datetime.datetime:
    normalized = normalize_deadline(deadline_str)
    if normalized == "미정":
        raise ValueError("미정은 날짜로 변환할 수 없습니다.")
    m, d = map(int, normalized.split('/'))
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

def truncate_discord_text(text: str, limit: int = 3900) -> str:
    if len(text) <= limit:
        return text
    return text[:limit - 40].rstrip() + "\n...표시할 항목이 더 있습니다."

async def cache_timetable(db, guild_id: int, date_str: str, grade: str, class_nm: str, timetable: list):
    payload = json.dumps(timetable, ensure_ascii=False)
    await db.execute(
        """
        REPLACE INTO timetable_cache
        (guild_id, date_str, grade, class_nm, payload, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (guild_id, date_str, str(grade), str(class_nm), payload, datetime.datetime.now(kst).isoformat()),
    )
    await db.commit()

async def get_cached_timetable(db, guild_id: int, date_str: str, grade: str, class_nm: str):
    async with db.execute(
        """
        SELECT payload, updated_at FROM timetable_cache
        WHERE guild_id=? AND date_str=? AND grade=? AND class_nm=?
        """,
        (guild_id, date_str, str(grade), str(class_nm)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row:
        return None, None
    try:
        return json.loads(row[0]), row[1]
    except json.JSONDecodeError:
        return None, None

async def get_schedule_message(target_date: datetime.datetime, guild_id: int, db, fetch_neis_timetable) -> discord.Embed:
    weekday_num = target_date.weekday()
    weekday_str = ['월', '화', '수', '목', '금', '토', '일'][weekday_num]
    
    # 임베드 컬러: 평일(Blurple), 주말(Green)
    color = 0x5865F2 if weekday_num < 5 else 0x57F287
    embed = discord.Embed(
        title=f"📅 {target_date.month}월 {target_date.day}일 {weekday_str}요일 일정",
        description=f"**{target_date.strftime('%Y-%m-%d')}** 학급 운영 정보입니다.",
        color=color,
        timestamp=datetime.datetime.now(kst)
    )
    
    now = datetime.datetime.now(kst)
    today_date = now.replace(hour=0, minute=0, second=0, microsecond=0) 
    
    # 📢 주요 학사 일정 (D-Day)
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
                        exam_info += f"🔔 **{e_name}**까지 `D-{days_to_start}`\n"
                    elif days_to_end >= 0:
                        day_num = abs(days_to_start) + 1
                        exam_info += f"🔥 **{e_name} 진행 중!** ({day_num}일차)\n"
                except Exception: pass
    
    if exam_info:
        embed.add_field(name="📢 주요 학사 일정", value=f"```\n{exam_info.strip()}\n```", inline=False)
        
    # 📖 시간표 섹션
    async with db.execute("SELECT value FROM config WHERE key='grade' AND guild_id=?", (guild_id,)) as cursor:
        g_row = await cursor.fetchone()
    async with db.execute("SELECT value FROM config WHERE key='class_nm' AND guild_id=?", (guild_id,)) as cursor:
        c_row = await cursor.fetchone()

    timetable_text = ""
    if weekday_num >= 5: 
        timetable_text = "✨ 오늘은 즐거운 휴일입니다! 푹 쉬세요."
    elif g_row and c_row:
        date_str = target_date.strftime("%Y%m%d")
        timetable = await fetch_neis_timetable(date_str, g_row[0], c_row[0])
        if timetable:
            await cache_timetable(db, guild_id, date_str, g_row[0], c_row[0], timetable)
            timetable_text = "\n".join([f"**{perio}교시** │ {subject}" for perio, subject in timetable])
        elif timetable is None:
            cached, updated_at = await get_cached_timetable(db, guild_id, date_str, g_row[0], c_row[0])
            if cached:
                timetable_text = "\n".join([f"**{perio}교시** │ {subject}" for perio, subject in cached])
                timetable_text += f"\n\n⚠️ NEIS 조회 실패로 마지막 저장본을 표시합니다.\n저장 시각: {updated_at[:16]}"
            else:
                timetable_text = "⚠️ NEIS 조회에 실패했습니다. API 키, 네트워크, NEIS 상태를 확인해주세요."
        else: 
            timetable_text = "❌ 나이스(NEIS)에 등록된 수업 데이터가 없습니다."
    else: 
        timetable_text = "⚠️ `/학급설정`을 통해 학년/반을 먼저 설정해주세요."
    
    embed.add_field(name="📖 오늘의 시간표", value=timetable_text, inline=False)
        
    # 📝 학급 일정 섹션 (숙제/수행)
    async with db.execute('SELECT task_type, content FROM tasks WHERE deadline = ? AND guild_id = ?', (target_date.strftime("%m/%d"), guild_id)) as cursor:
        target_tasks = await cursor.fetchall()
    
    task_text = ""
    if not target_tasks: 
        task_text = "✅ 오늘 마감인 일정이 없습니다. 깨끗하네요!"
    else:
        tasks_dict = {}
        for t_type, content in target_tasks: tasks_dict.setdefault(t_type, []).append(content)
        for t_type, contents in tasks_dict.items():
            emoji = "📙" if "숙제" in t_type else "📝" if "수행" in t_type else "📌"
            task_text += f"{emoji} **{t_type}**\n" + "\n".join([f"└ {c}" for c in contents]) + "\n\n"
            
    embed.add_field(name="📝 마감 임박 일정", value=truncate_discord_text(task_text.strip() if task_text else "내역 없음", 1000), inline=False)
    
    embed.set_footer(text="SyncTask Service • 광주소프트웨어마이스터고", icon_url="https://i.imgur.com/890v9Ic.png") # 예시 아이콘
    
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
        
    embed.description = truncate_discord_text(content_text.strip())
    embed.set_footer(text=f"총 {len(tasks_list)}개의 항목이 있습니다.")
    return embed
