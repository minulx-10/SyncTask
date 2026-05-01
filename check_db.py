import sqlite3

def check():
    conn = sqlite3.connect('school_tasks.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"Tables: {tables}")
    for table in tables:
        t_name = table[0]
        cursor.execute(f"PRAGMA table_info({t_name})")
        print(f"Schema for {t_name}: {cursor.fetchall()}")
        cursor.execute(f"SELECT count(*) FROM {t_name}")
        print(f"Count for {t_name}: {cursor.fetchone()[0]}")
    conn.close()

if __name__ == "__main__":
    check()
