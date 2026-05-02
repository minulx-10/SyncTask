import discord
from discord.ext import commands
from discord import app_commands
from utils.logger import record_log

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
        await interaction.response.send_message(f"🏫 이 서버의 시간표가 **{grade}학년 {class_nm}반**으로 설정되었습니다!", ephemeral=True)

    @app_commands.command(name="시작", description="처음 사용하는 서버를 위한 빠른 설정 안내를 보여줍니다.")
    async def start_guide(self, interaction: discord.Interaction):
        await record_log(interaction, "시작")
        embed = discord.Embed(
            title="SyncTask 빠른 시작",
            description="아래 순서대로 설정하면 학급 일정 대시보드를 바로 사용할 수 있습니다.",
            color=0x57F287,
        )
        embed.add_field(name="1. 학급 설정", value="`/학급설정 grade class_nm`으로 시간표 학년과 반을 등록합니다.", inline=False)
        embed.add_field(name="2. 대시보드 설치", value="공지로 쓸 채널에서 `/공지설정`을 실행합니다.", inline=False)
        embed.add_field(name="3. 일정 등록", value="`/추가`, `/시험일정설정`, `/시험범위추가`로 학급 정보를 쌓습니다.", inline=False)
        embed.add_field(name="4. 개인 알림", value="원하는 학생은 `/알림설정`으로 DM 알림을 켤 수 있습니다.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="도움말", description="SyncTask 주요 명령어와 사용 흐름을 확인합니다.")
    async def help_command(self, interaction: discord.Interaction):
        await record_log(interaction, "도움말")
        embed = discord.Embed(title="SyncTask 도움말", color=0x5865F2)
        embed.add_field(name="조회", value="`/오늘`, `/내일`, `/시간표`, `/전체일정`, `/숙제`, `/수행평가`, `/시험범위`, `/주간요약`", inline=False)
        embed.add_field(name="등록/관리", value="`/추가`, `/수정`, `/삭제`, `/시험일정설정`, `/시험범위추가`, `/변경이력`", inline=False)
        embed.add_field(name="초기 설정", value="`/시작`, `/설정상태`, `/학급설정`, `/공지설정`, `/로그채널설정`, `/소개카드`", inline=False)
        embed.add_field(name="개인화", value="`/알림설정`으로 DM 알림을 켜거나 끌 수 있습니다.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="설정상태", description="이 서버의 SyncTask 설정 상태를 확인합니다.")
    async def setup_status(self, interaction: discord.Interaction):
        await record_log(interaction, "설정상태")
        keys = ["grade", "class_nm", "dashboard_channel", "dashboard_message", "admin_log_channel"]
        values = {}
        for key in keys:
            async with self.bot.db.execute("SELECT value FROM config WHERE guild_id=? AND key=?", (interaction.guild_id, key)) as cursor:
                row = await cursor.fetchone()
                values[key] = row[0] if row else None

        embed = discord.Embed(title="SyncTask 설정 상태", color=0xf5a442)
        class_value = f"{values['grade']}학년 {values['class_nm']}반" if values["grade"] and values["class_nm"] else "미설정"
        dashboard_value = "설정됨" if values["dashboard_channel"] and values["dashboard_message"] else "미설정"
        log_value = f"<#{values['admin_log_channel']}>" if values["admin_log_channel"] else "미설정"
        embed.add_field(name="학급", value=class_value, inline=False)
        embed.add_field(name="대시보드", value=dashboard_value, inline=False)
        embed.add_field(name="관리자 요청 채널", value=log_value, inline=False)
        if class_value == "미설정" or dashboard_value == "미설정":
            embed.set_footer(text="/시작을 실행하면 빠른 설정 순서를 볼 수 있습니다.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="소개카드", description="채널에 SyncTask 소개 메시지를 게시합니다.")
    @is_manager_or_admin()
    async def intro_card(self, interaction: discord.Interaction):
        await record_log(interaction, "소개카드")
        embed = discord.Embed(
            title="SyncTask 학급 알리미",
            description="시간표, 숙제, 수행평가, 시험 범위를 한 곳에서 확인하는 학급 일정 봇입니다.",
            color=0x5865F2,
        )
        embed.add_field(name="바로 쓰기", value="`/오늘`, `/내일`, `/전체일정`, `/주간요약`", inline=False)
        embed.add_field(name="일정 제안", value="`/추가`로 누구나 일정을 제안하고, 관리자가 승인할 수 있습니다.", inline=False)
        embed.add_field(name="개인 알림", value="`/알림설정`으로 DM 알림을 직접 켜고 끌 수 있습니다.", inline=False)
        await interaction.response.send_message("소개 카드를 게시했습니다.", ephemeral=True)
        await interaction.channel.send(embed=embed)

    @app_commands.command(name="공지설정", description="이 채널에 실시간 대시보드를 생성합니다.")
    @is_manager_or_admin()
    async def dashboard_setup(self, interaction: discord.Interaction):
        from cogs.tasks import DashboardView
        await record_log(interaction, "공지설정")
        await interaction.response.send_message("📊 대시보드 설치 완료!", ephemeral=True)
        msg = await interaction.channel.send(embed=discord.Embed(title="대시보드 로딩 중..."), view=DashboardView(self.bot))
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
        await interaction.response.send_message(f"📢 이제 숙제 추가 요청이 {channel.mention} 채널로 전송됩니다!", ephemeral=True)

    @app_commands.command(name="dashboard", description="[슈퍼 관리자 전용] 웹 대시보드 접속 정보를 확인합니다.")
    async def dashboard_info(self, interaction: discord.Interaction):
        if interaction.user.id not in SUPER_ADMINS:
            return await interaction.response.send_message("🚫 이 명령어는 슈퍼 관리자만 사용할 수 있습니다.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True) # IP 조회 시간이 걸릴 수 있으므로 지연 응답을 가장 먼저 수행
        await record_log(interaction, "dashboard")
        
        import aiohttp
        import os
        
        public_ip = "확인 불가"
        dashboard_port = os.getenv("DASHBOARD_PORT", "10000")
        dashboard_host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
        url = f"http://localhost:{dashboard_port}"
        try:
            # 타임아웃을 설정하여 IP 조회가 무한정 길어지는 것을 방지
            if dashboard_host in ("0.0.0.0", "::"):
                async with aiohttp.ClientSession() as session:
                    async with session.get('https://api.ipify.org', timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
                        if resp.status == 200:
                            public_ip = (await resp.text()).strip()
                            url = f"http://{public_ip}:{dashboard_port}"
        except Exception:
            pass

        embed = discord.Embed(
            title="✨ SyncTask Admin Dashboard",
            description="서버에서 실행 중인 대시보드 접속 정보입니다. 아래 버튼을 클릭하여 바로 이동할 수 있습니다.",
            color=0x2b2d31 # 디스코드 다크모드 배경색과 어울리는 세련된 색상
        )
        
        # 디자인 개선을 위해 이모지와 깔끔한 포맷 적용
        public_value = f"```http\n{url}\n```" if public_ip != "확인 불가" else "`DASHBOARD_HOST=0.0.0.0`일 때 표시됩니다."
        embed.add_field(name="🌍 **외부 접속 주소 (Public URL)**", value=public_value, inline=False)
        embed.add_field(name="🏠 **내부 접속 주소 (Local URL)**", value=f"```http\nhttp://localhost:{dashboard_port}\n```\n*(봇이 켜져있는 컴퓨터에서 접속할 때 사용)*", inline=False)
        password_status = "설정됨" if os.getenv("ADMIN_PASSWORD") else "미설정 - 웹 로그인이 잠깁니다"
        embed.add_field(name="🔑 **비밀번호 상태 (Password)**", value=password_status, inline=False)
        
        embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else None)
        embed.set_footer(text="이 메시지는 슈퍼 관리자에게만 표시되는 보안 메시지입니다.", icon_url="https://cdn-icons-png.flaticon.com/512/2097/2097276.png")

        # 바로가기 버튼 추가
        view = discord.ui.View()
        if public_ip != "확인 불가":
            view.add_item(discord.ui.Button(label="외부망 접속", url=url, style=discord.ButtonStyle.link, emoji="🌍"))
        view.add_item(discord.ui.Button(label="로컬 접속", url=f"http://localhost:{dashboard_port}", style=discord.ButtonStyle.link, emoji="🏠"))

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
