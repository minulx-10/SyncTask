import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View
import datetime
from utils.logger import record_log
from utils.formatter import parse_deadline, normalize_deadline, truncate_discord_text, kst, get_task_list_embed
from utils.ui import DASHBOARD_COLOR, HISTORY_COLOR, SUCCESS_COLOR, ERROR_COLOR, MUTED_COLOR, TASK_COLOR, embed, ok, warn, deny
from cogs.admin import SUPER_ADMINS

class TaskReviewView(View):
    def __init__(self, bot, task_type, deadline, content, requester_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.task_type = task_type
        self.deadline = deadline
        self.content = content
        self.requester_id = requester_id

    @discord.ui.button(label="승인", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (interaction.user.id in SUPER_ADMINS or (hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.manage_messages)):
            return await interaction.response.send_message(deny("승인할 수 없습니다."), ephemeral=True)

        await self.bot.db.execute('INSERT INTO tasks (guild_id, task_type, deadline, content, channel_id) VALUES (?, ?, ?, ?, ?)', 
                       (interaction.guild_id, self.task_type, self.deadline, self.content, interaction.channel_id))
        await self.bot.db.execute(
            """
            INSERT INTO change_logs (guild_id, user_id, action, details, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                interaction.guild_id,
                interaction.user.id,
                "승인등록",
                f"[{self.task_type}] {self.content} / {self.deadline}",
                datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        await self.bot.db.commit()
        
        tasks_cog = self.bot.get_cog("TasksCog")
        if tasks_cog:
            await tasks_cog.update_dashboard(interaction.guild_id)
        
        embed = interaction.message.embeds[0]
        embed.title = "일정 요청 승인"
        embed.color = SUCCESS_COLOR
        embed.set_footer(text=f"승인자: {interaction.user.name}")
        await interaction.response.edit_message(embed=embed, view=None)
        
        try:
            requester = await self.bot.fetch_user(self.requester_id)
            if requester: await requester.send(ok(f"`{self.content}` 일정이 등록되었습니다."))
        except Exception:
            pass

    @discord.ui.button(label="거절", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not (interaction.user.id in SUPER_ADMINS or (hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.manage_messages)):
            return await interaction.response.send_message(deny("거절할 수 없습니다."), ephemeral=True)

        embed = interaction.message.embeds[0]
        embed.title = "일정 요청 거절"
        embed.color = ERROR_COLOR
        embed.set_footer(text=f"거절자: {interaction.user.name}")
        await interaction.response.edit_message(embed=embed, view=None)

class DashboardView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    @discord.ui.button(label="새로고침", style=discord.ButtonStyle.secondary, custom_id="refresh_dashboard")
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await record_log(interaction, "대시보드_새로고침")
        await interaction.response.defer(ephemeral=True)
        tasks_cog = self.bot.get_cog("TasksCog")
        if tasks_cog:
            await tasks_cog.update_dashboard(interaction.guild_id)
        await interaction.followup.send(ok("대시보드를 최신 상태로 반영했습니다."), ephemeral=True)

class TasksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_update_loop.start()

    def cog_unload(self):
        self.auto_update_loop.cancel()

    async def record_change(self, interaction: discord.Interaction, action: str, details: str):
        await self.bot.db.execute(
            """
            INSERT INTO change_logs (guild_id, user_id, action, details, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                interaction.guild_id,
                interaction.user.id,
                action,
                details,
                datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        await self.bot.db.commit()

    async def update_dashboard(self, target_guild_id=None):
        now = datetime.datetime.now(kst)
        today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if target_guild_id: guilds = [(target_guild_id,)]
        else:
            async with self.bot.db.execute("SELECT DISTINCT guild_id FROM config WHERE key='dashboard_channel'") as cursor:
                guilds = await cursor.fetchall()

        for (g_id,) in guilds:
            async with self.bot.db.execute('SELECT id, task_type, deadline, content FROM tasks WHERE guild_id = ?', (g_id,)) as cursor:
                tasks_list = await cursor.fetchall()
            dated_tasks, tbd_tasks, embed_desc = [], [], ""
            
            for row in tasks_list:
                if row[2] == "미정": tbd_tasks.append(row)
                else:
                    try:
                        target_date = parse_deadline(row[2], now)
                        days_left = (target_date - today_date).days
                        if days_left >= 0: dated_tasks.append((days_left, row))
                    except ValueError: pass
                    
            dated_tasks.sort(key=lambda x: x[0])
            
            for days, (t_id, t_type, d_str, content) in dated_tasks:
                d_txt = "오늘" if days == 0 else f"D-{days}"
                embed_desc += f"`ID:{t_id}` [{t_type}] {content} · {d_str} · {d_txt}\n"
            for t_id, t_type, d_str, content in tbd_tasks:
                embed_desc += f"`ID:{t_id}` [{t_type}] {content} · 마감 미정\n"
                
            if not embed_desc: embed_desc = "등록된 일정이 없습니다."
            embed_desc = truncate_discord_text(embed_desc)

            async with self.bot.db.execute("SELECT value FROM config WHERE key='dashboard_channel' AND guild_id=?", (g_id,)) as cursor:
                ch_row = await cursor.fetchone()
            async with self.bot.db.execute("SELECT value FROM config WHERE key='dashboard_message' AND guild_id=?", (g_id,)) as cursor:
                msg_row = await cursor.fetchone()

            if ch_row and msg_row:
                channel = self.bot.get_channel(int(ch_row[0]))
                if channel:
                    try:
                        msg = await channel.fetch_message(int(msg_row[0]))
                        embed = discord.Embed(title="학급 일정 대시보드", description=embed_desc, color=DASHBOARD_COLOR)
                        embed.set_footer(text=f"마지막 새로고침: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                        await msg.edit(embed=embed, view=DashboardView(self.bot))
                    except discord.NotFound: pass

        await self.bot.change_presence(activity=discord.Game("학급 일정 관리 중!"))

    @app_commands.command(name="추가", description="새로운 숙제나 일정을 추가합니다. (일반 유저는 승인 후 등록)")
    @app_commands.choices(task_type=[
        app_commands.Choice(name="숙제", value="숙제"),
        app_commands.Choice(name="수행평가", value="수행평가"),
        app_commands.Choice(name="기타일정", value="기타일정")
    ])
    async def add_task(self, interaction: discord.Interaction, task_type: app_commands.Choice[str], deadline: str, content: str):
        await record_log(interaction, "추가_시도", f"종류:[{task_type.value}], 마감:[{deadline}], 내용:[{content}]")
        
        try:
            deadline = normalize_deadline(deadline)
        except ValueError:
            return await interaction.response.send_message(warn("마감일은 `MM/DD` 또는 `미정`으로 입력해주세요."), ephemeral=True)

        is_admin = interaction.user.id in SUPER_ADMINS or (hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.manage_messages)

        if is_admin:
            await self.bot.db.execute('INSERT INTO tasks (guild_id, task_type, deadline, content, channel_id) VALUES (?, ?, ?, ?, ?)', 
                           (interaction.guild_id, task_type.value, deadline, content, interaction.channel_id))
            await self.bot.db.commit()
            await self.record_change(interaction, "추가", f"[{task_type.value}] {content} / {deadline}")
            await self.update_dashboard(interaction.guild_id)
            await interaction.response.send_message(ok(f"`{content}` 일정을 등록했습니다."), ephemeral=True)
        else:
            request_embed = embed("일정 등록 요청", color=TASK_COLOR)
            request_embed.add_field(name="종류", value=task_type.value, inline=True)
            request_embed.add_field(name="마감", value=deadline, inline=True)
            request_embed.add_field(name="내용", value=content, inline=False)
            request_embed.add_field(name="요청자", value=interaction.user.mention, inline=False)
            request_embed.set_footer(text="승인 후 대시보드에 반영됩니다.")

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
            
            await target_channel.send(embed=request_embed, view=TaskReviewView(self.bot, task_type.value, deadline, content, interaction.user.id))
            await interaction.response.send_message(ok("일정 요청을 보냈습니다."), ephemeral=True)

    @app_commands.command(name="삭제", description="등록된 일정을 삭제합니다.")
    async def delete_task(self, interaction: discord.Interaction, ids_str: str):
        if not (interaction.user.id in SUPER_ADMINS or (hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.manage_messages)):
            return await interaction.response.send_message(deny("일정을 삭제할 수 없습니다."), ephemeral=True)

        await record_log(interaction, "삭제", f"대상 ID:[{ids_str}]")
        id_list = [int(i.strip()) for i in ids_str.split(',') if i.strip().isdigit()]
        if not id_list: return await interaction.response.send_message(warn("삭제할 ID를 숫자로 입력해주세요."), ephemeral=True)
        
        placeholders = ', '.join('?' for _ in id_list)
        await self.bot.db.execute(f'DELETE FROM tasks WHERE id IN ({placeholders}) AND guild_id = ?', id_list + [interaction.guild_id])
        await self.bot.db.commit()
        await self.record_change(interaction, "삭제", f"ID: {', '.join(map(str, id_list))}")
        await interaction.response.send_message(ok(f"ID {', '.join(map(str, id_list))} 일정을 삭제했습니다."), ephemeral=True)
        await self.update_dashboard(interaction.guild_id)

    @app_commands.command(name="수정", description="등록된 일정의 정보를 수정합니다.")
    @app_commands.choices(task_type=[
        app_commands.Choice(name="숙제", value="숙제"),
        app_commands.Choice(name="수행평가", value="수행평가"),
        app_commands.Choice(name="기타일정", value="기타일정")
    ])
    async def edit_task(self, interaction: discord.Interaction, task_id: int, task_type: app_commands.Choice[str] = None, deadline: str = None, content: str = None):
        if not (interaction.user.id in SUPER_ADMINS or (hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.manage_messages)):
            return await interaction.response.send_message(deny("일정을 수정할 수 없습니다."), ephemeral=True)

        await record_log(interaction, "수정", f"ID:{task_id}")
        
        async with self.bot.db.execute("SELECT task_type, deadline, content FROM tasks WHERE id = ? AND guild_id = ?", (task_id, interaction.guild_id)) as cursor:
            row = await cursor.fetchone()
        
        if not row: return await interaction.response.send_message(warn("해당 ID의 일정을 찾을 수 없습니다."), ephemeral=True)
        
        new_type = task_type.value if task_type else row[0]
        new_deadline = deadline if deadline else row[1]
        new_content = content if content else row[2]
        
        if deadline:
            try:
                new_deadline = normalize_deadline(deadline)
            except ValueError:
                return await interaction.response.send_message(warn("마감일은 `MM/DD` 또는 `미정`으로 입력해주세요."), ephemeral=True)

        await self.bot.db.execute("UPDATE tasks SET task_type=?, deadline=?, content=? WHERE id=? AND guild_id=?", 
                       (new_type, new_deadline, new_content, task_id, interaction.guild_id))
        await self.bot.db.commit()
        await self.record_change(interaction, "수정", f"ID:{task_id} -> [{new_type}] {new_content} / {new_deadline}")
        await self.update_dashboard(interaction.guild_id)
        await interaction.response.send_message(ok(f"`ID:{task_id}` 일정을 수정했습니다."), ephemeral=True)

    @app_commands.command(name="전체일정", description="모든 일정을 한 번에 보여줍니다.")
    async def all_tasks(self, interaction: discord.Interaction):
        await record_log(interaction, "전체일정")
        async with self.bot.db.execute('SELECT id, task_type, deadline, content FROM tasks WHERE guild_id = ?', (interaction.guild_id,)) as cursor:
            tasks_list = await cursor.fetchall()
        if not tasks_list: return await interaction.response.send_message("등록된 일정이 없습니다.")
        msg = "**전체 일정**\n"
        for r in tasks_list: msg += f"`ID:{r[0]}` [{r[1]}] {r[3]} · {r[2]}\n"
        await interaction.response.send_message(truncate_discord_text(msg))

    @app_commands.command(name="숙제", description="앞으로 남은 숙제 목록을 D-Day 순으로 보여줍니다.")
    async def homework_list(self, interaction: discord.Interaction):
        await record_log(interaction, "숙제")
        embed = await get_task_list_embed("숙제", interaction.guild_id, self.bot.db)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="수행평가", description="앞으로 남은 수행평가 목록을 D-Day 순으로 보여줍니다.")
    async def performance_list(self, interaction: discord.Interaction):
        await record_log(interaction, "수행평가")
        embed = await get_task_list_embed("수행평가", interaction.guild_id, self.bot.db)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="변경이력", description="최근 일정 추가/수정/삭제 기록을 확인합니다.")
    async def change_history(self, interaction: discord.Interaction):
        await record_log(interaction, "변경이력")
        async with self.bot.db.execute(
            """
            SELECT user_id, action, details, created_at
            FROM change_logs
            WHERE guild_id=?
            ORDER BY id DESC
            LIMIT 10
            """,
            (interaction.guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return await interaction.response.send_message("아직 기록된 변경 이력이 없습니다.", ephemeral=True)

        history_embed = embed("최근 변경 이력", color=HISTORY_COLOR)
        for user_id, action, details, created_at in rows:
            history_embed.add_field(
                name=f"{created_at} / {action}",
                value=f"<@{user_id}> - {details}",
                inline=False,
            )
        await interaction.response.send_message(embed=history_embed)


    @tasks.loop(minutes=5)
    async def auto_update_loop(self):
        if self.bot.db:
            now = datetime.datetime.now(kst)
            today_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            async with self.bot.db.execute('SELECT id, guild_id, deadline FROM tasks WHERE deadline != "미정" AND task_type != "시험범위"') as cursor:
                rows = await cursor.fetchall()
                
            ids_to_delete = []
            for t_id, g_id, d_str in rows:
                try:
                    target_date = parse_deadline(d_str, now)
                    if (target_date - today_date).days <= -2: 
                        ids_to_delete.append((t_id, g_id))
                except ValueError: pass
                
            for t_id, g_id in ids_to_delete:
                await self.bot.db.execute('DELETE FROM tasks WHERE id=? AND guild_id=?', (t_id, g_id)) 
            if ids_to_delete:
                await self.bot.db.commit()
            await self.update_dashboard()

async def setup(bot):
    await bot.add_cog(TasksCog(bot))
