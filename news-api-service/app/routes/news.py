# -*- coding: utf-8 -*-
"""新闻抓取与查询 API"""
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from app.config import get_settings
from app import database
from app import tushare_client

router = APIRouter(prefix="/api", tags=["新闻"])


@router.post(
    "/news/fetch",
    summary="抓取 Tushare 新闻并入库（排重）",
    description="按上次抓取结束时间排重，默认抓取最近 24 小时。可指定时间范围或来源。",
)
def fetch_news(
    start_date: Optional[str] = Query(
        None,
        description="开始时间，格式：2018-11-20 09:00:00。不传则使用「上次结束时间」或「当前-24h」",
    ),
    end_date: Optional[str] = Query(
        None,
        description="结束时间，格式：2018-11-20 22:00:00。不传则为当前时间",
    ),
    hours: int = Query(
        24,
        ge=1,
        le=168,
        description="当未指定 start_date 时，默认抓取最近多少小时（1~168）",
    ),
    sources: Optional[str] = Query(
        None,
        description="来源，多个用逗号分隔，如 sina,cls。不传则抓取全部来源",
    ),
):
    settings = get_settings()
    if not settings.tushare_token:
        raise HTTPException(
            status_code=500,
            detail="未配置 TUSHARE_TOKEN，请在环境变量或 .env 中设置",
        )
    src_list = [s.strip() for s in sources.split(",")] if sources else None
    results = tushare_client.fetch_news_all_sources(
        token=settings.tushare_token,
        start_date=start_date,
        end_date=end_date,
        default_hours=hours,
        sources=src_list,
        database_url=settings.database_url,
    )
    return {"success": True, "results": results}


@router.get(
    "/news/list",
    summary="查询本地新闻列表",
    description="从 newsdata 数据库中分页查询已抓取的新闻",
)
def list_news(
    src: Optional[str] = Query(None, description="来源筛选，如 sina, cls"),
    start_datetime: Optional[str] = Query(
        None, description="开始时间，格式：2018-11-20 09:00:00"
    ),
    end_datetime: Optional[str] = Query(
        None, description="结束时间，格式：2018-11-20 22:00:00"
    ),
    limit: int = Query(50, ge=1, le=500, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    settings = get_settings()
    database.init_db(settings.database_url)
    conn = database.get_connection(settings.database_url)
    try:
        items = database.list_news(
            conn,
            src=src,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            limit=limit,
            offset=offset,
        )
        return {"success": True, "data": items, "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.get(
    "/news/sources",
    summary="获取支持的新闻来源列表",
)
def get_sources():
    return {
        "success": True,
        "sources": [
            {"id": "sina", "name": "新浪财经"},
            {"id": "wallstreetcn", "name": "华尔街见闻"},
            {"id": "10jqka", "name": "同花顺"},
            {"id": "eastmoney", "name": "东方财富"},
            {"id": "yuncaijing", "name": "云财经"},
            {"id": "fenghuang", "name": "凤凰新闻"},
            {"id": "jinrongjie", "name": "金融界"},
            {"id": "cls", "name": "财联社"},
            {"id": "yicai", "name": "第一财经"},
        ],
    }


@router.get(
    "/news/fetch-log",
    summary="获取各来源上次抓取结束时间",
    description="用于排重：每次抓取会从该时间之后拉取，避免重复",
)
def get_fetch_log():
    settings = get_settings()
    database.init_db(settings.database_url)
    conn = database.get_connection(settings.database_url)
    try:
        cur = conn.execute(
            "SELECT src, last_end_datetime, updated_at FROM fetch_log ORDER BY src"
        )
        rows = cur.fetchall()
        return {
            "success": True,
            "data": [
                {
                    "src": r[0],
                    "last_end_datetime": r[1],
                    "updated_at": r[2],
                }
                for r in rows
            ],
        }
    finally:
        conn.close()
