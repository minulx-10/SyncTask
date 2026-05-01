import discord
import datetime
import os
import asyncio

async def record_log(interaction: discord.Interaction, command_name, details="", kst=None):
    if kst is None:
        kst = datetime.timezone(datetime.timedelta(hours=9))
        
    now = datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
    guild_id = interaction.guild_id if interaction.guild_id else "DM"
    guild_name = interaction.guild.name if interaction.guild else "개인메시지"
    user_name = interaction.user.name
    
    # [GID:ID] [TIME] [GUILD] [USER] COMMAND [DETAILS]
    log_msg = f"[GID:{guild_id}] [{now}] [{guild_name}] 👤{user_name}: /{command_name}" + (f" ({details})\n" if details else "\n")
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_path = os.path.join(BASE_DIR, "alimi_cmd_log.txt")
    
    def write_log():
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_msg)
            
    await asyncio.to_thread(write_log)
    print(log_msg.strip())
