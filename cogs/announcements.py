from discord.ext import commands, tasks

from core.announcements import claim_due_announcements, send_claimed_announcement


class AnnouncementsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.dispatch_announcements.start()

    def cog_unload(self):
        self.dispatch_announcements.cancel()

    @tasks.loop(seconds=30)
    async def dispatch_announcements(self):
        if not self.bot.db:
            return

        due_items = await claim_due_announcements(self.bot.db)
        for item in due_items:
            try:
                await send_claimed_announcement(self.bot, self.bot.db, item)
            except Exception as exc:
                print(f"공지 발송 실패 #{item.get('id')}: {exc}")

    @dispatch_announcements.before_loop
    async def before_dispatch_announcements(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(AnnouncementsCog(bot))
