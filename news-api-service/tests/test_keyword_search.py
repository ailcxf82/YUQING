import sqlite3

db_path = "d:/lianghuatouzi/yuqing0309/news-api-service/newsdata.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

keywords = ["A股", "跳水", "股市", "下跌", "大盘"]

for kw in keywords:
    like = f"%{kw}%"
    sql = """
        SELECT COUNT(*) FROM news
        WHERE title LIKE ? OR content LIKE ?
    """
    cursor.execute(sql, (like, like))
    count = cursor.fetchone()[0]
    print(f"Keyword '{kw}': {count} matches")

print("\n--- Searching for 'A股 跳水' ---")
sql = """
    SELECT datetime, title FROM news
    WHERE (title LIKE '%A股%' OR content LIKE '%A股%')
    AND (title LIKE '%跳水%' OR content LIKE '%跳水%')
    ORDER BY datetime DESC
    LIMIT 10
"""
cursor.execute(sql)
results = cursor.fetchall()
for dt, title in results:
    print(f"  {dt}: {title[:60]}...")

conn.close()
