import datetime
import hashlib
from urllib.parse import quote

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

from utils.formatter import kst
from utils.logger import record_log
from utils.ui import FOOTER_TEXT, SUCCESS_COLOR

SONG_POOL = [
    ("Ditto", "NewJeans"),
    ("Hype Boy", "NewJeans"),
    ("Supernova", "aespa"),
    ("I AM", "IVE"),
    ("Dynamite", "BTS"),
    ("Pink Venom", "BLACKPINK"),
    ("EASY", "LE SSERAFIM"),
    ("MAESTRO", "SEVENTEEN"),
    ("Love wins all", "IU"),
    ("Love Lee", "AKMU"),
    ("Welcome to the Show", "DAY6"),
    ("INVU", "TAEYEON"),
    ("Mantra", "JENNIE"),
    ("APT", "ROSE"),
    ("Viva La Vida", "Coldplay"),
    ("Bohemian Rhapsody", "Queen"),
    ("NIGHT DANCER", "imase"),
    ("Lemon", "Kenshi Yonezu"),
    ("Idol", "YOASOBI"),
    ("STAY", "The Kid LAROI Justin Bieber"),
]

PLATFORMS = {
    "apple": "Apple Music",
    "spotify": "Spotify",
    "melon": "Melon",
    "bugs": "Bugs",
    "youtube": "YouTube Music",
}

PLATFORM_CHOICES = [
    app_commands.Choice(name="Apple Music", value="apple"),
    app_commands.Choice(name="Spotify", value="spotify"),
    app_commands.Choice(name="Melon", value="melon"),
    app_commands.Choice(name="Bugs", value="bugs"),
    app_commands.Choice(name="YouTube Music", value="youtube"),
]


def daily_song_seed(guild_id: int | None, target_date: datetime.date) -> tuple[str, str]:
    key = f"{guild_id or 'dm'}:{target_date.isoformat()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(SONG_POOL)
    return SONG_POOL[index]


def format_duration(milliseconds: int | None) -> str:
    if not milliseconds:
        return "-"
    seconds = milliseconds // 1000
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}:{seconds:02d}"


def bigger_artwork_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.replace("100x100bb", "600x600bb").replace("100x100", "600x600")


def platform_links(title: str, artist: str, apple_url: str | None = None) -> dict[str, str]:
    query = f"{artist} {title}".strip()
    encoded = quote(query)
    return {
        "Apple Music": apple_url or f"https://music.apple.com/search?term={encoded}",
        "Spotify": f"https://open.spotify.com/search/{encoded}",
        "Melon": f"https://www.melon.com/search/total/index.htm?q={encoded}",
        "Bugs": f"https://music.bugs.co.kr/search/integrated?q={encoded}",
        "YouTube Music": f"https://music.youtube.com/search?q={encoded}",
    }


def platform_label(platform_key: str | None) -> str:
    return PLATFORMS.get(platform_key or "", "Apple Music")


async def fetch_itunes_track(title: str, artist: str) -> dict | None:
    params = {
        "term": f"{artist} {title}",
        "country": "KR",
        "media": "music",
        "entity": "song",
        "limit": 5,
    }
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://itunes.apple.com/search", params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except Exception:
        return None

    results = data.get("results") or []
    if not results:
        return None

    title_lower = title.lower()
    artist_lower = artist.lower()
    for item in results:
        if title_lower in item.get("trackName", "").lower() and artist_lower in item.get("artistName", "").lower():
            return item
    return results[0]


def build_onochu_embed(seed_title: str, seed_artist: str, track: dict | None, platform: str, links: dict[str, str]) -> discord.Embed:
    title = (track or {}).get("trackName") or seed_title
    artist = (track or {}).get("artistName") or seed_artist
    album = (track or {}).get("collectionName") or "앨범 정보 없음"
    genre = (track or {}).get("primaryGenreName") or "genre unknown"
    duration = format_duration((track or {}).get("trackTimeMillis"))
    preferred_label = platform_label(platform)

    item = discord.Embed(
        title=title,
        url=links.get(preferred_label),
        description=(
            f"**{artist}**\n"
            f"앨범: {album}\n\n"
            f"⏱ {duration} | {genre}\n"
            f"기본 플랫폼: **{platform_label(platform)}**"
        ),
        color=SUCCESS_COLOR,
    )
    artwork_url = bigger_artwork_url((track or {}).get("artworkUrl100"))
    if artwork_url:
        item.set_thumbnail(url=artwork_url)
    item.set_footer(text=f"오늘의 노래 추천 · {FOOTER_TEXT}")
    return item


class MusicLinkView(View):
    def __init__(self, links: dict[str, str], preferred_platform: str):
        super().__init__(timeout=180)
        preferred_label = platform_label(preferred_platform)
        ordered_labels = [preferred_label] + [label for label in links if label != preferred_label]
        for label in ordered_labels:
            self.add_item(Button(label=label, style=discord.ButtonStyle.link, url=links[label]))


class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_music_platform(self, guild_id: int, user_id: int) -> str:
        async with self.bot.db.execute(
            "SELECT music_platform FROM user_settings WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row and row[0] in PLATFORMS else "apple"

    async def set_music_platform(self, guild_id: int, user_id: int, platform: str):
        await self.bot.db.execute(
            """
            INSERT INTO user_settings (guild_id, user_id, music_platform)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET music_platform=excluded.music_platform
            """,
            (guild_id, user_id, platform),
        )
        await self.bot.db.commit()

    async def send_onochu(self, interaction: discord.Interaction, platform: str):
        target_date = datetime.datetime.now(kst).date()
        seed_title, seed_artist = daily_song_seed(interaction.guild_id, target_date)
        track = await fetch_itunes_track(seed_title, seed_artist)

        title = (track or {}).get("trackName") or seed_title
        artist = (track or {}).get("artistName") or seed_artist
        links = platform_links(title, artist, (track or {}).get("trackViewUrl"))

        await interaction.followup.send(
            embed=build_onochu_embed(seed_title, seed_artist, track, platform, links),
            view=MusicLinkView(links, platform),
        )

    @app_commands.command(name="오노추", description="오늘의 노래를 추천합니다. 저장된 음악 플랫폼을 우선 표시합니다.")
    @app_commands.describe(platform="사용할 음악 플랫폼. 선택하면 다음부터 기본값으로 저장됩니다.")
    @app_commands.choices(platform=PLATFORM_CHOICES)
    async def onochu(self, interaction: discord.Interaction, platform: app_commands.Choice[str] = None):
        await record_log(interaction, "오노추", f"플랫폼:[{platform.name}]" if platform else "저장값")
        await interaction.response.defer()

        guild_id = interaction.guild_id or 0
        if platform:
            selected_platform = platform.value
            await self.set_music_platform(guild_id, interaction.user.id, selected_platform)
        else:
            selected_platform = await self.get_music_platform(guild_id, interaction.user.id)

        await self.send_onochu(interaction, selected_platform)

    @app_commands.command(name="오노추설정", description="오노추에서 우선 표시할 음악 플랫폼을 저장합니다.")
    @app_commands.describe(platform="기본 음악 플랫폼")
    @app_commands.choices(platform=PLATFORM_CHOICES)
    async def onochu_setting(self, interaction: discord.Interaction, platform: app_commands.Choice[str]):
        await record_log(interaction, "오노추설정", f"플랫폼:[{platform.name}]")
        await self.set_music_platform(interaction.guild_id or 0, interaction.user.id, platform.value)
        await interaction.response.send_message(
            f"✅ 오노추 기본 플랫폼을 **{platform.name}**으로 저장했습니다.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
