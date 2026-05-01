import sqlite3
import os

def migrate():
    if not os.path.exists('school_tasks.db'):
        print("❌ school_tasks.db not found.")
        return

    old_conn = sqlite3.connect('school_tasks.db')
    new_conn = sqlite3.connect('alimi_v2.db')
    old_conn.row_factory = sqlite3.Row
    
    # Create tables if not exist
    new_conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, task_type TEXT, deadline TEXT, content TEXT, channel_id INTEGER)')
    new_conn.execute('CREATE TABLE IF NOT EXISTS config (guild_id INTEGER, key TEXT, value TEXT, PRIMARY KEY (guild_id, key))')
    
    # Migrate tasks
    try:
        old_tasks = old_conn.execute('SELECT * FROM tasks').fetchall()
        for row in old_tasks:
            new_conn.execute('INSERT INTO tasks (guild_id, task_type, deadline, content, channel_id) VALUES (?, ?, ?, ?, ?)', 
                           (row['guild_id'], row['task_type'], row['deadline'], row['content'], row['channel_id']))
        print(f"✅ Migrated {len(old_tasks)} tasks.")
    except Exception as e:
        print(f"⚠️ Task migration skipped or failed: {e}")

    # Migrate config
    try:
        old_config = old_conn.execute('SELECT * FROM config').fetchall()
        for row in old_config:
            new_conn.execute('REPLACE INTO config (guild_id, key, value) VALUES (?, ?, ?)', 
                           (row['guild_id'], row['key'], row['value']))
        print(f"✅ Migrated {len(old_config)} configs.")
    except Exception as e:
        print(f"⚠️ Config migration skipped or failed: {e}")

    new_conn.commit()
    old_conn.close()
    new_conn.close()
    print("✨ Migration Process Finished.")

if __name__ == "__main__":
    migrate()
