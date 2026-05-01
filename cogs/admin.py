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
        url = "http://localhost:10000"
        try:
            # 타임아웃을 설정하여 IP 조회가 무한정 길어지는 것을 방지
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.ipify.org', timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
                    if resp.status == 200:
                        public_ip = (await resp.text()).strip()
                        url = f"http://{public_ip}:10000"
        except Exception:
            pass

        embed = discord.Embed(
            title="✨ SyncTask Admin Dashboard",
            description="서버에서 실행 중인 대시보드 접속 정보입니다. 아래 버튼을 클릭하여 바로 이동할 수 있습니다.",
            color=0x2b2d31 # 디스코드 다크모드 배경색과 어울리는 세련된 색상
        )
        
        # 디자인 개선을 위해 이모지와 깔끔한 포맷 적용
        embed.add_field(name="🌍 **접속 주소 (URL)**", value=f"```http\n{url}\n```", inline=False)
        embed.add_field(name="🔑 **비밀번호 (Password)**", value=f"||**{os.getenv('ADMIN_PASSWORD', 'admin1234')}**||", inline=False)
        
        embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else None)
        embed.set_footer(text="이 메시지는 슈퍼 관리자에게만 표시되는 보안 메시지입니다.", icon_url="https://cdn-icons-png.flaticon.com/512/2097/2097276.png")

        # 바로가기 버튼 추가
        view = discord.ui.View()
        if public_ip != "확인 불가":
            view.add_item(discord.ui.Button(label="대시보드 바로가기", url=url, style=discord.ButtonStyle.link, emoji="🔗"))

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
