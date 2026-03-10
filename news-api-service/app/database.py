# -*- coding: utf-8 -*-
"""数据库：newsdata 库、新闻表、抓取记录表（用于排重）"""
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import sqlite3

# 从 database_url 解析 SQLite 路径，如 sqlite:///./newsdata.db -> ./newsdata.db
def _sqlite_path_from_url(url: str) -> str:
    m = re.match(r"sqlite:///(.+)", url.strip())
    if m:
        return m.group(1).lstrip("/")
    return "newsdata.db"


def get_db_path(database_url: str) -> str:
    path = _sqlite_path_from_url(database_url)
    if path.startswith("./"):
        # 相对路径：相对于项目根目录（news-api-service）
        base = Path(__file__).resolve().parent.parent
        path = str(base / path[2:])
    return path


def init_db(database_url: str) -> None:
    """创建数据库文件及表结构"""
    path = get_db_path(database_url)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            src TEXT NOT NULL,
            datetime TEXT NOT NULL,
            title TEXT,
            content TEXT,
            channels TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(src, datetime)
        );
        CREATE INDEX IF NOT EXISTS idx_news_src ON news(src);
        CREATE INDEX IF NOT EXISTS idx_news_datetime ON news(datetime);

        CREATE TABLE IF NOT EXISTS fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            src TEXT NOT NULL UNIQUE,
            last_end_datetime TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        """)
        conn.commit()
    finally:
        conn.close()


def get_connection(database_url: str):
    return sqlite3.connect(get_db_path(database_url))


def get_last_fetch_end(conn: sqlite3.Connection, src: str) -> Optional[str]:
    """获取某来源上次抓取的结束时间，用于排重"""
    cur = conn.execute(
        "SELECT last_end_datetime FROM fetch_log WHERE src = ?", (src,)
    )
    row = cur.fetchone()
    return row[0] if row else None


def set_last_fetch_end(conn: sqlite3.Connection, src: str, end_datetime: str) -> None:
    """更新某来源的上次抓取结束时间"""
    conn.execute(
        """INSERT INTO fetch_log (src, last_end_datetime, updated_at)
           VALUES (?, ?, datetime('now', 'localtime'))
           ON CONFLICT(src) DO UPDATE SET
             last_end_datetime = excluded.last_end_datetime,
             updated_at = datetime('now', 'localtime')""",
        (src, end_datetime),
    )
    conn.commit()


def insert_news_batch(
    conn: sqlite3.Connection,
    rows: List[tuple],
) -> int:
    """批量插入新闻，忽略重复 (src, datetime)。返回实际插入条数"""
    inserted = 0
    for r in rows:
        try:
            cur = conn.execute(
                """INSERT OR IGNORE INTO news (src, datetime, title, content, channels)
                   VALUES (?, ?, ?, ?, ?)""",
                r,
            )
            if cur.rowcount > 0:
                inserted += 1
        except Exception:
            pass
    conn.commit()
    return inserted


def list_news(
    conn: sqlite3.Connection,
    src: Optional[str] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> List[dict]:
    """查询新闻列表"""
    sql = "SELECT id, src, datetime, title, content, channels, created_at FROM news WHERE 1=1"
    params: list = []
    if src:
        sql += " AND src = ?"
        params.append(src)
    if start_datetime:
        sql += " AND datetime >= ?"
        params.append(start_datetime)
    if end_datetime:
        sql += " AND datetime <= ?"
        params.append(end_datetime)
    sql += " ORDER BY datetime DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
