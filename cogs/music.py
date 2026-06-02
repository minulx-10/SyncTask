import asyncio
import random
import re
from html import unescape
from urllib.parse import quote

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

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

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def song_key(title: str, artist: str) -> str:
    return f"{artist}::{title}"


def random_song(previous_key: str | None = None) -> tuple[str, str]:
    candidates = [song for song in SONG_POOL if song_key(song[0], song[1]) != previous_key]
    return random.choice(candidates or SONG_POOL)


def format_duration(milliseconds: int | None) -> str:
    if not milliseconds:
        return "-"
    seconds = milliseconds // 1000
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}:{seconds:02d}"


def clean_text(value: str | None) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def bigger_artwork_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.replace("100x100bb", "600x600bb").replace("100x100", "600x600")


def platform_label(platform_key: str | None) -> str:
    return PLATFORMS.get(platform_key or "", "Apple Music")


def search_query(title: str, artist: str) -> str:
    return f"{artist} {title}".strip()


async def fetch_text(session: aiohttp.ClientSession, url: str, **kwargs) -> str | None:
    for _ in range(2):
        try:
            async with session.get(url, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.text()
        except Exception:
            pass
        await asyncio.sleep(0.2)
    return None


async def fetch_json(session: aiohttp.ClientSession, url: str, **kwargs) -> dict | None:
    for _ in range(2):
        try:
            async with session.get(url, **kwargs) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        except Exception:
            pass
        await asyncio.sleep(0.2)
    return None


def first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.DOTALL)
    return clean_text(match.group(1)) if match else None


def split_title_artist(value: str, separator: str, fallback_title: str, fallback_artist: str) -> tuple[str, str]:
    if separator in value:
        title, artist = value.split(separator, 1)
        return clean_text(title), clean_text(artist)
    return fallback_title, fallback_artist


async def resolve_apple_track(session: aiohttp.ClientSession, title: str, artist: str) -> dict | None:
    data = await fetch_json(
        session,
        "https://itunes.apple.com/search",
        params={
            "term": search_query(title, artist),
            "country": "KR",
            "media": "music",
            "entity": "song",
            "limit": 5,
        },
    )
    results = (data or {}).get("results") or []
    if not results:
        return None

    title_lower = title.lower()
    artist_lower = artist.lower()
    track = results[0]
    for item in results:
        if title_lower in item.get("trackName", "").lower() and artist_lower in item.get("artistName", "").lower():
            track = item
            break

    return {
        "platform": "apple",
        "url": track.get("trackViewUrl"),
        "title": track.get("trackName") or title,
        "artist": track.get("artistName") or artist,
        "album": track.get("collectionName"),
        "genre": track.get("primaryGenreName"),
        "duration": format_duration(track.get("trackTimeMillis")),
        "artwork_url": bigger_artwork_url(track.get("artworkUrl100")),
    }


async def resolve_spotify_track(session: aiohttp.ClientSession, title: str, artist: str) -> dict | None:
    encoded_query = quote(search_query(title, artist))
    data = await fetch_text(session, f"https://r.jina.ai/http://r.jina.ai/http://https://open.spotify.com/search/{encoded_query}")
    if not data:
        return None

    url = first_match(r"\[.*?\]\((https://open\.spotify\.com/track/[A-Za-z0-9]+)\)", data)
    if not url:
        return None

    duration = first_match(rf"\({re.escape(url)}\)\s*\n\[.*?\]\(https://open\.spotify\.com/artist/[A-Za-z0-9]+\)\s*\n\n(\d+:\d+)", data)
    meta = await fetch_json(session, "https://open.spotify.com/oembed", params={"url": url}) or {}
    return {
        "platform": "spotify",
        "url": url,
        "title": meta.get("title") or title,
        "artist": artist,
        "album": None,
        "genre": None,
        "duration": duration,
        "artwork_url": meta.get("thumbnail_url"),
    }


async def resolve_melon_track(session: aiohttp.ClientSession, title: str, artist: str) -> dict | None:
    data = await fetch_text(
        session,
        "https://www.melon.com/search/song/index.htm",
        params={"q": search_query(title, artist), "section": "", "searchGnbYn": "Y", "kkoSpl": "N", "kkoDpType": ""},
    )
    song_id = first_match(r'data-song-no="(\d+)"', data or "")
    if not song_id:
        return None

    url = f"https://www.melon.com/song/detail.htm?songId={song_id}"
    detail = await fetch_text(session, url) or ""
    og_title = first_match(r'<meta property="og:title" content="([^"]+)"', detail)
    artwork_url = first_match(r'<meta property="og:image" content="([^"]+)"', detail)
    resolved_title, resolved_artist = split_title_artist(og_title or "", " - ", title, artist)
    album = first_match(r'<dt>앨범</dt>\s*<dd>.*?<a[^>]*>(.*?)</a>', detail)

    return {
        "platform": "melon",
        "url": url,
        "title": resolved_title,
        "artist": resolved_artist,
        "album": album,
        "genre": "Melon",
        "duration": None,
        "artwork_url": artwork_url,
    }


async def resolve_bugs_track(session: aiohttp.ClientSession, title: str, artist: str) -> dict | None:
    data = await fetch_text(
        session,
        "https://music.bugs.co.kr/search/track",
        params={"q": search_query(title, artist)},
    )
    url = first_match(r'href="(https://music\.bugs\.co\.kr/track/\d+[^"]*)"', data or "")
    if not url:
        return None
    url = url.split("?")[0]

    detail = await fetch_text(session, url) or ""
    og_title = first_match(r'<meta property="og:title" content="([^"]+)"', detail)
    artwork_url = first_match(r'<meta property="og:image" content="([^"]+)"', detail)
    resolved_title, resolved_artist = split_title_artist(og_title or "", " / ", title, artist)
    album = first_match(r'<th scope="row">앨범</th>\s*<td>.*?<a[^>]*>(.*?)</a>', detail)

    return {
        "platform": "bugs",
        "url": url,
        "title": resolved_title,
        "artist": resolved_artist,
        "album": album,
        "genre": "Bugs",
        "duration": None,
        "artwork_url": artwork_url,
    }


async def resolve_youtube_track(session: aiohttp.ClientSession, title: str, artist: str) -> dict | None:
    data = await fetch_text(
        session,
        "https://www.youtube.com/results",
        params={"search_query": f"{search_query(title, artist)} official audio"},
    )
    video_ids = []
    for video_id in re.findall(r'"videoId":"([\w-]{11})"', data or ""):
        if video_id not in video_ids:
            video_ids.append(video_id)
    if not video_ids:
        return None

    video_id = video_ids[0]
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    music_url = f"https://music.youtube.com/watch?v={video_id}"
    meta = await fetch_json(session, "https://www.youtube.com/oembed", params={"url": watch_url, "format": "json"}) or {}

    return {
        "platform": "youtube",
        "url": music_url,
        "title": meta.get("title") or title,
        "artist": meta.get("author_name") or artist,
        "album": None,
        "genre": "YouTube Music",
        "duration": None,
        "artwork_url": meta.get("thumbnail_url"),
    }


async def resolve_platform_track(
    session: aiohttp.ClientSession,
    platform: str,
    title: str,
    artist: str,
) -> dict | None:
    resolvers = {
        "apple": resolve_apple_track,
        "spotify": resolve_spotify_track,
        "melon": resolve_melon_track,
        "bugs": resolve_bugs_track,
        "youtube": resolve_youtube_track,
    }
    resolver = resolvers.get(platform)
    result = await resolver(session, title, artist) if resolver else None
    if result and result.get("url"):
        return result
    return None


async def resolve_music_links(title: str, artist: str, preferred_platform: str) -> tuple[dict, dict[str, dict]]:
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(headers=HTTP_HEADERS, timeout=timeout) as session:
        preferred = await resolve_platform_track(session, preferred_platform, title, artist)
        tasks = {
            key: resolve_platform_track(session, key, title, artist)
            for key in PLATFORMS
            if key != preferred_platform
        }
        resolved = await asyncio.gather(*tasks.values(), return_exceptions=True)

    if not preferred:
        preferred = {
            "platform": preferred_platform,
            "url": None,
            "title": title,
            "artist": artist,
            "album": None,
            "genre": f"{platform_label(preferred_platform)} 직접 링크 없음",
            "duration": None,
            "artwork_url": None,
        }

    results = {preferred_platform: preferred} if preferred.get("url") else {}
    for key, result in zip(tasks.keys(), resolved):
        if isinstance(result, dict) and result.get("url"):
            results[key] = result
    return preferred, results


def build_onochu_embed(seed_title: str, seed_artist: str, preferred: dict, platform: str) -> discord.Embed:
    title = preferred.get("title") or seed_title
    artist = preferred.get("artist") or seed_artist
    album = preferred.get("album") or "앨범 정보 없음"
    genre = preferred.get("genre") or platform_label(platform)
    duration = preferred.get("duration") or "-"

    item = discord.Embed(
        title=title,
        url=preferred.get("url"),
        description=(
            f"**{artist}**\n"
            f"앨범: {album}\n\n"
            f"⏱ {duration} | {genre}\n"
            f"기본 플랫폼: **{platform_label(platform)}**"
        ),
        color=SUCCESS_COLOR,
    )
    artwork_url = preferred.get("artwork_url")
    if artwork_url:
        item.set_thumbnail(url=artwork_url)
    item.set_footer(text=f"랜덤 노래 추천 · {FOOTER_TEXT}")
    return item


class MusicLinkView(View):
    def __init__(self, links: dict[str, dict], preferred_platform: str):
        super().__init__(timeout=180)
        ordered_keys = [preferred_platform] + [key for key in PLATFORMS if key != preferred_platform]
        for key in ordered_keys:
            item = links.get(key)
            if item and item.get("url"):
                self.add_item(Button(label=platform_label(key), style=discord.ButtonStyle.link, url=item["url"]))


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

    async def get_last_song_key(self, guild_id: int, user_id: int) -> str | None:
        async with self.bot.db.execute(
            "SELECT music_last_song FROM user_settings WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else None

    async def set_last_song_key(self, guild_id: int, user_id: int, last_song: str):
        await self.bot.db.execute(
            """
            INSERT INTO user_settings (guild_id, user_id, music_last_song)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET music_last_song=excluded.music_last_song
            """,
            (guild_id, user_id, last_song),
        )
        await self.bot.db.commit()

    async def send_onochu(self, interaction: discord.Interaction, platform: str):
        guild_id = interaction.guild_id or 0
        previous_key = await self.get_last_song_key(guild_id, interaction.user.id)
        seed_title, seed_artist = random_song(previous_key)
        await self.set_last_song_key(guild_id, interaction.user.id, song_key(seed_title, seed_artist))

        preferred, links = await resolve_music_links(seed_title, seed_artist, platform)

        await interaction.followup.send(
            embed=build_onochu_embed(seed_title, seed_artist, preferred, platform),
            view=MusicLinkView(links, platform),
        )

    @app_commands.command(name="오노추", description="랜덤으로 노래를 추천합니다. 저장된 음악 플랫폼을 우선 표시합니다.")
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
