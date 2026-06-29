import asyncio
import random
import re
import time
from html import unescape
from urllib.parse import quote

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

from utils.logger import record_log
from utils.ui import FOOTER_TEXT, SUCCESS_COLOR, brand_footer

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

GENRE_CHOICES = [
    app_commands.Choice(name="가요 (K-Pop)", value="kpop"),
    app_commands.Choice(name="팝 (Pop)", value="pop"),
    app_commands.Choice(name="댄스 (Dance)", value="dance"),
    app_commands.Choice(name="R&B/소울 (R&B/Soul)", value="rnb"),
    app_commands.Choice(name="힙합/랩 (Hip-Hop/Rap)", value="hiphop"),
    app_commands.Choice(name="록/얼터너티브 (Rock/Alt)", value="rock"),
    app_commands.Choice(name="OST (Soundtrack)", value="ost"),
    app_commands.Choice(name="인디/어쿠스틱 (Indie)", value="indie"),
]

GENRE_COLORS = {
    "kpop": 0xFF1493,      # Deep Pink
    "pop": 0x1E90FF,       # Sky Blue
    "dance": 0xFF4500,     # Orange Red
    "rnb": 0x800080,       # Purple
    "hiphop": 0xDAA520,    # Goldenrod
    "rock": 0xED2939,      # Imperial Red
    "ost": 0x4B0082,       # Indigo
    "indie": 0x3EB489,     # Mint
}

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}
CHART_CACHE_TTL = 900
CHART_CACHE: dict[str, tuple[float, list[dict]]] = {}


def song_key(title: str, artist: str) -> str:
    return f"{artist}::{title}"


def pick_random_candidate(candidates: list[dict], previous_key: str | None = None) -> dict | None:
    available = [
        item for item in candidates
        if item.get("title") and item.get("artist") and song_key(item["title"], item["artist"]) != previous_key
    ]
    if not available:
        available = [item for item in candidates if item.get("title") and item.get("artist")]
    return random.choice(available) if available else None


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


def genre_label(genre_value: str | None) -> str:
    for choice in GENRE_CHOICES:
        if choice.value == genre_value:
            return choice.name.split(" (")[0]
    return "전체"


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


async def fetch_apple_chart(session: aiohttp.ClientSession) -> list[dict]:
    data = await fetch_json(session, "https://rss.applemarketingtools.com/api/v2/kr/music/most-played/100/songs.json")
    results = ((data or {}).get("feed") or {}).get("results") or []
    songs = []
    for item in results:
        title = clean_text(item.get("name"))
        artist = clean_text(item.get("artistName"))
        if not title or not artist:
            continue
        genres = item.get("genres") or []
        genre = clean_text((genres[0] or {}).get("name")) if genres else "Apple Music"
        songs.append({
            "platform": "apple",
            "title": title,
            "artist": artist,
            "album": clean_text(item.get("collectionName")),
            "genre": genre,
            "url": item.get("url"),
            "artwork_url": bigger_artwork_url(item.get("artworkUrl100")),
        })
    return songs


async def fetch_chart_candidates() -> list[dict]:
    key = "apple"
    cached = CHART_CACHE.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < CHART_CACHE_TTL:
        return cached[1]

    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(headers=HTTP_HEADERS, timeout=timeout) as session:
        songs = await fetch_apple_chart(session)

    if songs:
        CHART_CACHE[key] = (now, songs)
    return songs


def filter_by_genre(songs: list[dict], genre_value: str | None) -> list[dict]:
    if not genre_value:
        return songs
    
    mapping = {
        "kpop": ["k-pop", "가요"],
        "pop": ["팝", "pop"],
        "dance": ["댄스", "dance"],
        "rnb": ["r&b", "소울", "soul"],
        "hiphop": ["힙합", "랩", "hip-hop", "rap"],
        "rock": ["록", "rock", "얼터너티브", "alternative"],
        "ost": ["ost", "soundtrack"],
        "indie": ["인디", "indie", "싱어송라이터", "singer-songwriter"],
    }
    
    targets = mapping.get(genre_value, [])
    filtered = []
    for s in songs:
        song_genre = (s.get("genre") or "").lower()
        if any(t in song_genre for t in targets):
            filtered.append(s)
    return filtered


async def random_chart_song(genre_value: str | None = None, previous_key: str | None = None) -> tuple[dict | None, bool]:
    candidates = await fetch_chart_candidates()
    if not candidates:
        return None, False
        
    filtered = filter_by_genre(candidates, genre_value)
    is_filtered = True
    if not filtered:
        filtered = candidates
        is_filtered = False
        
    item = pick_random_candidate(filtered, previous_key)
    return item, is_filtered


async def resolve_apple_track(session: aiohttp.ClientSession, title: str, artist: str) -> str:
    query = f"{artist} {title}"
    fallback_url = f"https://music.apple.com/kr/search?term={quote(query)}"
    try:
        data = await fetch_json(
            session,
            "https://itunes.apple.com/search",
            params={
                "term": query,
                "country": "KR",
                "media": "music",
                "entity": "song",
                "limit": 3,
            },
        )
        results = (data or {}).get("results") or []
        if results:
            title_lower = title.lower()
            artist_lower = artist.lower()
            track = results[0]
            for item in results:
                if title_lower in item.get("trackName", "").lower() and artist_lower in item.get("artistName", "").lower():
                    track = item
                    break
            url = track.get("trackViewUrl")
            if url:
                return url
    except Exception:
        pass
    return fallback_url


async def resolve_melon_track(session: aiohttp.ClientSession, title: str, artist: str) -> str:
    query = f"{artist} {title}"
    fallback_url = f"https://www.melon.com/search/total/index.htm?q={quote(query)}"
    try:
        data = await fetch_text(
            session,
            "https://www.melon.com/search/song/index.htm",
            params={"q": query, "section": "", "searchGnbYn": "Y", "kkoSpl": "N", "kkoDpType": ""}
        )
        song_id = first_match(r'data-song-no="(\d+)"', data or "")
        if song_id:
            return f"https://www.melon.com/song/detail.htm?songId={song_id}"
    except Exception:
        pass
    return fallback_url


async def resolve_bugs_track(session: aiohttp.ClientSession, title: str, artist: str) -> str:
    query = f"{artist} {title}"
    fallback_url = f"https://music.bugs.co.kr/search/integrated?q={quote(query)}"
    try:
        data = await fetch_text(
            session,
            "https://music.bugs.co.kr/search/track",
            params={"q": query},
        )
        track_id = first_match(r'trackId="(\d+)"', data or "")
        if track_id:
            return f"https://music.bugs.co.kr/track/{track_id}"
    except Exception:
        pass
    return fallback_url



async def resolve_youtube_track(session: aiohttp.ClientSession, title: str, artist: str) -> str:
    query = f"{artist} {title}"
    fallback_url = f"https://music.youtube.com/search?q={quote(query)}"
    try:
        data = await fetch_text(
            session,
            "https://www.youtube.com/results",
            params={"search_query": f"{query} official audio"},
        )
        video_ids = []
        for video_id in re.findall(r'"videoId":"([\w-]{11})"', data or ""):
            if video_id not in video_ids:
                video_ids.append(video_id)
        if video_ids:
            return f"https://music.youtube.com/watch?v={video_ids[0]}"
    except Exception:
        pass
    return fallback_url


async def resolve_spotify_track(session: aiohttp.ClientSession, title: str, artist: str) -> str:
    query = f"{artist} {title}"
    fallback_url = f"https://open.spotify.com/search/{quote(query)}"
    try:
        data = await fetch_text(session, f"https://r.jina.ai/https://open.spotify.com/search/{quote(query)}")
        if data:
            url = first_match(r"\[.*?\]\((https://open\.spotify\.com/track/[A-Za-z0-9]+)\)", data)
            if url:
                return url
    except Exception:
        pass
    return fallback_url


def build_onochu_embed(song: dict, url: str, platform: str, genre_value: str | None = None, is_filtered: bool = True) -> discord.Embed:
    title = song["title"]
    artist = song["artist"]
    album = song.get("album") or "앨범 정보 없음"
    genre = song.get("genre") or "기타"

    embed_color = GENRE_COLORS.get(genre_value or "", SUCCESS_COLOR)

    desc = f"**{artist}**\n\n💿 **앨범**: {album}\n🏷️ **장르**: {genre}\n\n"
    if genre_value:
        if is_filtered:
            desc += f"✨ 선택하신 **{genre_label(genre_value)}** 장르의 인기 추천곡입니다!"
        else:
            desc += f"⚠️ 차트에 **{genre_label(genre_value)}** 장르의 곡이 없어 전체 인기곡 중 추천합니다."
    else:
        desc += "🎵 오늘의 인기 추천곡입니다!"

    embed = discord.Embed(
        title=title,
        url=url,
        description=desc,
        color=embed_color,
    )
    artwork_url = song.get("artwork_url")
    if artwork_url:
        embed.set_thumbnail(url=artwork_url)
    brand_footer(embed, f"랜덤 노래 추천 · {FOOTER_TEXT}")
    return embed


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

    async def send_onochu(self, interaction: discord.Interaction, platform: str, genre_value: str | None = None):
        guild_id = interaction.guild_id or 0
        previous_key = await self.get_last_song_key(guild_id, interaction.user.id)
        source_song, is_filtered = await random_chart_song(genre_value, previous_key)
        if not source_song:
            await interaction.followup.send("⚠️ 랜덤 곡 후보를 가져오지 못했습니다. 잠시 후 다시 시도해주세요.")
            return

        seed_title = source_song["title"]
        seed_artist = source_song["artist"]
        await self.set_last_song_key(guild_id, interaction.user.id, song_key(seed_title, seed_artist))

        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(headers=HTTP_HEADERS, timeout=timeout) as session:
            if platform == "melon":
                track_url = await resolve_melon_track(session, seed_title, seed_artist)
            elif platform == "bugs":
                track_url = await resolve_bugs_track(session, seed_title, seed_artist)
            elif platform == "spotify":
                track_url = await resolve_spotify_track(session, seed_title, seed_artist)
            elif platform == "youtube":
                track_url = await resolve_youtube_track(session, seed_title, seed_artist)
            else:
                track_url = source_song.get("url") or await resolve_apple_track(session, seed_title, seed_artist)

        embed = build_onochu_embed(source_song, track_url, platform, genre_value, is_filtered)
        
        view = View(timeout=180)
        view.add_item(Button(
            label=f"{platform_label(platform)} 바로가기",
            style=discord.ButtonStyle.link,
            url=track_url
        ))

        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="오노추", description="랜덤으로 노래를 추천합니다. 저장된 음악 플랫폼의 링크를 표시합니다.")
    @app_commands.describe(
        genre="추천받을 노래의 장르",
        platform="사용할 음악 플랫폼. 선택하면 다음부터 기본값으로 저장됩니다."
    )
    @app_commands.choices(genre=GENRE_CHOICES, platform=PLATFORM_CHOICES)
    async def onochu(
        self,
        interaction: discord.Interaction,
        genre: app_commands.Choice[str] = None,
        platform: app_commands.Choice[str] = None
    ):
        genre_val = genre.value if genre else None
        genre_name = genre.name if genre else "전체"
        platform_name = platform.name if platform else "기록값"
        await record_log(interaction, "오노추", f"장르:[{genre_name}] 플랫폼:[{platform_name}]")
        
        await interaction.response.defer()

        guild_id = interaction.guild_id or 0
        if platform:
            selected_platform = platform.value
            await self.set_music_platform(guild_id, interaction.user.id, selected_platform)
        else:
            selected_platform = await self.get_music_platform(guild_id, interaction.user.id)

        await self.send_onochu(interaction, selected_platform, genre_val)

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
