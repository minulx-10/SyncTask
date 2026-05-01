import discord
import datetime
import os
import asyncio

async def record_log(interaction: discord.Interaction, command_name, details="", kst=None):
    if kst is None:
        kst = datetime.timezone(datetime.timedelta(hours=9))
        
    now = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
    guild_name = interaction.guild.name if interaction.guild else "DM(개인메시지)"
    user_name = interaction.user.name
    log_msg = f"[{now}] [서버: {guild_name}] 👤{user_name} 님이 [/{command_name}] 사용" + (f" ➡️ 세부내용: {details}\n" if details else "\n")
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_path = os.path.join(BASE_DIR, "alimi_cmd_log.txt")
    
    def write_log():
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_msg)
            
    await asyncio.to_thread(write_log)
    print(log_msg.strip())
