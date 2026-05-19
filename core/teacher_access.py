from core.announcements import format_dt


TEACHER_ACCESS_COLUMNS = [
    "guild_id",
    "user_id",
    "display_name",
    "granted_by",
    "granted_at",
]


def row_to_teacher_access(row):
    if row is None:
        return {}
    return {key: row[index] for index, key in enumerate(TEACHER_ACCESS_COLUMNS)}


async def grant_teacher_access(db, guild_id: int, user_id: int, display_name: str, granted_by: int) -> None:
    await db.execute(
        """
        REPLACE INTO teacher_access (guild_id, user_id, display_name, granted_by, granted_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (guild_id, user_id, display_name, granted_by, format_dt()),
    )
    await db.commit()


async def revoke_teacher_access(db, guild_id: int, user_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM teacher_access WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def list_teacher_access(db, guild_id: int) -> list[dict]:
    async with db.execute(
        f"""
        SELECT {', '.join(TEACHER_ACCESS_COLUMNS)}
        FROM teacher_access
        WHERE guild_id=?
        ORDER BY display_name COLLATE NOCASE
        """,
        (guild_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return [row_to_teacher_access(row) for row in rows]


async def get_accessible_guild_ids(db, user_id: int) -> set[int]:
    async with db.execute(
        "SELECT guild_id FROM teacher_access WHERE user_id=?",
        (user_id,),
    ) as cursor:
        rows = await cursor.fetchall()
    return {int(row[0]) for row in rows}


async def has_teacher_access(db, guild_id: int, user_id: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM teacher_access WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
    return row is not None
