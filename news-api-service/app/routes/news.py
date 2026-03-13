# -*- coding: utf-8 -*-
"""新闻抓取与查询 API"""
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from app.config import get_settings
from app import database
from app import tushare_client
from app import service_switch
from app import scheduler
from app import llm_client
from app import news_agent

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
    if not service_switch.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="服务已关闭，请先通过 PUT /api/service/switch 开启服务",
        )
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


class ScheduleBody(BaseModel):
    interval_minutes: int = 5


@router.post(
    "/news/schedule",
    summary="开启新闻自动抓取（定时）",
    description="将 /api/news/fetch 设为按指定间隔定时执行，默认每 5 分钟一次。会开启定时服务并设置抓取间隔。",
)
def enable_news_schedule(body: ScheduleBody = ScheduleBody()):
    """业务接口：一键开启新闻每 N 分钟自动抓取，默认 5 分钟。"""
    interval = max(1, min(1440, body.interval_minutes))
    scheduler.set_interval_minutes(interval)
    scheduler.set_enabled(True)
    status = scheduler.get_status()
    return {
        "success": True,
        "message": f"已开启新闻自动抓取，每 {interval} 分钟执行一次",
        "enabled": True,
        "interval_minutes": interval,
        "fetch_next_run_time": status.get("fetch_next_run_time"),
    }


@router.post(
    "/news/cleanup",
    summary="清理过期新闻数据",
    description="删除早于指定小时数的新闻数据，默认清理 48 小时之前的数据。",
)
def cleanup_news(
    hours: int = Query(
        48,
        ge=1,
        le=24 * 30,
        description="保留最近多少小时的数据，默认 48 小时（最小 1，最大 720）",
    )
):
    settings = get_settings()
    database.init_db(settings.database_url)
    conn = database.get_connection(settings.database_url)
    try:
        info = database.cleanup_old_news(conn, hours=hours)
        return {"success": True, **info}
    finally:
        conn.close()


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


class LlmSearchBody(BaseModel):
    keyword: str
    limit: int = 50
    offset: int = 0


@router.post(
    "/news/semantic-search",
    summary="LLM 语义搜索新闻快讯",
    description=(
        "输入一个关键词，先交给 Deepseek LLM 汇总成核心关键词，"
        "再在本地 news 数据库中按标题与内容模糊匹配，返回带时间与出处的新闻快讯列表。"
    ),
)
def news_semantic_search(body: LlmSearchBody):
    """LLM 语义搜索：keyword -> Deepseek 核心词 -> 本地模糊匹配。"""
    raw = (body.keyword or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="keyword 不能为空")

    core = llm_client.summarize_keyword(raw)

    settings = get_settings()
    database.init_db(settings.database_url)
    conn = database.get_connection(settings.database_url)
    try:
        items = database.search_news_by_keyword(
            conn, keyword=core, limit=body.limit, offset=body.offset
        )
    finally:
        conn.close()

    # 只要出时间与出处，其余字段一并返回
    return {
        "success": True,
        "query": raw,
        "core_keyword": core,
        "limit": body.limit,
        "offset": body.offset,
        "count": len(items),
        "items": items,
    }


class AnalyzeNewsItem(BaseModel):
    """舆情结构化解析单条新闻输入。"""

    id: str
    source_name: str
    published_at: str
    text: str
    url: Optional[str] = None


class AnalyzeNewsBody(BaseModel):
    """舆情结构化解析请求体。"""

    symbol: str
    name: str
    start_date: str
    end_date: str
    news_items: List[AnalyzeNewsItem]


@router.post(
    "/news/analyze",
    summary="舆情信息炼化与结构化解析",
    description=(
        "对指定标的的舆情文本进行信源评级、事件抽取、情绪量化和影响评估，"
        "返回结构化事件清单、整体情绪视角及风险提示。"
    ),
)
def analyze_news(body: AnalyzeNewsBody):
    """News Agent：舆情结构化解析入口。"""
    if not body.symbol or not body.name:
        raise HTTPException(status_code=400, detail="symbol 与 name 为必填。")
    if not body.news_items:
        raise HTTPException(status_code=400, detail="news_items 至少需要一条舆情文本。")
    if not body.start_date or not body.end_date:
        raise HTTPException(status_code=400, detail="start_date 与 end_date 为必填。")

    # 转换为内部 NewsItem 结构
    items: List[news_agent.NewsItem] = [
        news_agent.NewsItem(
            id=item.id,
            source_name=item.source_name,
            published_at=item.published_at,
            text=item.text,
            url=item.url,
        )
        for item in body.news_items
    ]

    try:
        agent = news_agent.NewsSentimentAgent()
        result = agent.analyze(
            symbol=body.symbol,
            name=body.name,
            news_items=items,
            start_date=body.start_date,
            end_date=body.end_date,
        )
    except EnvironmentError as exc:
        # Deepseek 未配置等环境问题
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"舆情结构化解析失败: {exc}") from exc

    return {
        "success": True,
        "report_md": result.report_md,
        "result": result.result_json,
    }

