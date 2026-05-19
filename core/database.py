import aiosqlite
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(BASE_DIR, 'school_tasks.db')
print(f"📁 Database Path: {db_path}")

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
    await db.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            guild_id INTEGER,
            user_id INTEGER,
            reminder_enabled INTEGER DEFAULT 0,
            reminder_scope TEXT DEFAULT '전체',
            PRIMARY KEY (guild_id, user_id)
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS change_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            created_at TEXT
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS timetable_cache (
            guild_id INTEGER,
            date_str TEXT,
            grade TEXT,
            class_nm TEXT,
            payload TEXT,
            updated_at TEXT,
            PRIMARY KEY (guild_id, date_str, grade, class_nm)
        )
    ''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target_label TEXT,
            template_key TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            date_text TEXT,
            location TEXT,
            deadline TEXT,
            materials TEXT,
            note TEXT,
            image_filename TEXT,
            scheduled_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'scheduled',
            message_id TEXT,
            sent_at TEXT,
            last_error TEXT,
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_announcements_due ON announcements (status, scheduled_at)')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_announcements_guild ON announcements (guild_id, id)')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS teacher_access (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            display_name TEXT NOT NULL,
            granted_by INTEGER,
            granted_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )
    ''')
    await db.execute('CREATE INDEX IF NOT EXISTS idx_teacher_access_user ON teacher_access (user_id)')
    await db.commit()
    return db
