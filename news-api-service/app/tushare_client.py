# -*- coding: utf-8 -*-
"""Tushare 新闻抓取：按上次结束时间排重，默认 24 小时内"""
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import tushare as ts
from app.config import get_settings
from app import database

TUSHARE_TIMEOUT = 120

NEWS_SOURCES = [
    "sina", "wallstreetcn", "10jqka", "eastmoney",
    "yuncaijing", "fenghuang", "jinrongjie", "cls", "yicai",
]


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _start_end_default(hours: int) -> Tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(hours=hours)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def fetch_news_for_source(
    token: str,
    src: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    default_hours: int = 24,
    database_url: str = "",
) -> dict:
    """
    抓取单个来源的新闻并入库。
    若未传 start_date/end_date，则使用「上次抓取结束时间」为 start，当前时间为 end；
    若没有上次记录，则使用「当前时间 - default_hours」为 start。
    返回: {"src": str, "fetched": int, "inserted": int, "start_date": str, "end_date": str}
    """
    if not database_url:
        database_url = get_settings().database_url
    database.init_db(database_url)
    conn = database.get_connection(database_url)

    try:
        last_end = database.get_last_fetch_end(conn, src)
        if start_date and end_date:
            pass  # 使用调用方指定范围
        else:
            default_start, default_end = _start_end_default(default_hours)
            end_date = end_date or default_end
            # 排重：若有上次结束时间，则从上次结束时间之后开始抓
            if last_end:
                start_date = start_date or last_end
                # 若 last_end >= end_date，说明已抓过这段，不再重复抓
                if last_end >= end_date:
                    return {
                        "src": src,
                        "fetched": 0,
                        "inserted": 0,
                        "start_date": start_date,
                        "end_date": end_date,
                        "skip_reason": "last_fetch_end >= end_date, no new range",
                    }
            else:
                start_date = start_date or default_start

        pro = ts.pro_api(token, timeout=TUSHARE_TIMEOUT)
        df = pro.news(src=src, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            database.set_last_fetch_end(conn, src, end_date)
            return {
                "src": src,
                "fetched": 0,
                "inserted": 0,
                "start_date": start_date,
                "end_date": end_date,
            }

        rows = []
        for _, row in df.iterrows():
            dt = str(row.get("datetime", ""))
            title = str(row.get("title", "") or "")
            content = str(row.get("content", "") or "")
            channels = str(row.get("channels", "") or "")
            rows.append((src, dt, title, content, channels))
        inserted = database.insert_news_batch(conn, rows)
        database.set_last_fetch_end(conn, src, end_date)
        return {
            "src": src,
            "fetched": len(rows),
            "inserted": inserted,
            "start_date": start_date,
            "end_date": end_date,
        }
    finally:
        conn.close()


def fetch_news_all_sources(
    token: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    default_hours: int = 24,
    sources: Optional[List[str]] = None,
    database_url: str = "",
) -> List[dict]:
    """抓取多个来源（默认全部），每个来源按 last_fetch 排重。"""
    src_list = sources or NEWS_SOURCES
    results = []
    for src in src_list:
        r = fetch_news_for_source(
            token=token,
            src=src,
            start_date=start_date,
            end_date=end_date,
            default_hours=default_hours,
            database_url=database_url,
        )
        results.append(r)
    return results
