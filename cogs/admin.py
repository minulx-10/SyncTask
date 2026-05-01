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

    @app_commands.command(name="대시보드정보", description="[슈퍼 관리자 전용] 웹 대시보드 접속 정보를 확인합니다.")
    async def dashboard_info(self, interaction: discord.Interaction):
        if interaction.user.id != 771274777443696650:
            return await interaction.response.send_message("🚫 이 명령어는 슈퍼 관리자만 사용할 수 있습니다.", ephemeral=True)
            
        await record_log(interaction, "대시보드정보")
        await interaction.response.defer(ephemeral=True) # IP 조회 시간이 걸릴 수 있으므로 지연 응답
        
        import aiohttp
        import os
        public_ip = "확인 불가"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.ipify.org') as resp:
                    public_ip = await resp.text()
        except: pass

        embed = discord.Embed(
            title="🖥️ SyncTask Admin Dashboard Info",
            description="서버에서 실행 중인 대시보드 접속 정보입니다.",
            color=0x5865F2
        )
        embed.add_field(name="🌐 Dashboard URL", value=f"http://{public_ip}:10000", inline=False)
        embed.add_field(name="🔑 Password", value=f"||{os.getenv('ADMIN_PASSWORD', 'admin1234')}||", inline=False)
        embed.set_footer(text="이 정보는 유저님(슈퍼 관리자)에게만 보이는 비밀 메시지입니다.")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
