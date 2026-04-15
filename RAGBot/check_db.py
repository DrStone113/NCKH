import sqlite3
from config import SQLITE_PATH

conn = sqlite3.connect(SQLITE_PATH)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])
for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({t[0]})").fetchall()]
    print(f"  {t[0]}: {count:,} rows | cols: {cols[:8]}")
    if count > 0:
        row = conn.execute(f"SELECT * FROM {t[0]} LIMIT 1").fetchone()
        print(f"    sample: {str(row)[:120]}")
conn.close()
