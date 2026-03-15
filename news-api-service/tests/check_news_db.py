import sqlite3
import os

db_path = "d:/lianghuatouzi/yuqing0309/news-api-service/newsdata.db"

if not os.path.exists(db_path):
    print(f"Database not found: {db_path}")
    print("\nSearching for .db files...")
    import glob
    db_files = glob.glob("d:/lianghuatouzi/yuqing0309/news-api-service/**/*.db", recursive=True)
    for f in db_files:
        print(f"  Found: {f}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM news")
    count = cursor.fetchone()[0]
    print(f"Total news count: {count}")
    
    cursor.execute("SELECT src, COUNT(*) FROM news GROUP BY src")
    sources = cursor.fetchall()
    print(f"\nSources breakdown:")
    for src, cnt in sources:
        print(f"  {src}: {cnt}")
    
    cursor.execute("SELECT datetime, title FROM news ORDER BY datetime DESC LIMIT 5")
    recent = cursor.fetchall()
    print(f"\nRecent 5 news:")
    for dt, title in recent:
        print(f"  {dt}: {title[:50]}...")
    
    conn.close()
