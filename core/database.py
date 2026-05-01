import aiosqlite
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(BASE_DIR, 'school_tasks.db')

async def init_db():
    db = await aiosqlite.connect(db_path)
    await db.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            task_type TEXT, deadline TEXT, content TEXT, channel_id INTEGER
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS config (
            guild_id INTEGER, key TEXT, value TEXT,
            PRIMARY KEY (guild_id, key)
        )
    ''')
    await db.commit()
    return db
