# -*- coding: utf-8 -*-
"""管理后台页面：定时运行情况/明细、数据库明细"""
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app import database
from app import scheduler

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/admin", tags=["管理后台"], include_in_schema=False)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def admin_index(request: Request):
    settings = get_settings()
    database.init_db(settings.database_url)
    conn = database.get_connection(settings.database_url)
    try:
        runs = database.list_scheduler_runs(conn, limit=50, offset=0)
        news_latest = database.list_news(conn, limit=20, offset=0)
    finally:
        conn.close()

    status = scheduler.get_status()
    return templates.TemplateResponse(
        "admin_index.html",
        {
            "request": request,
            "status": status,
            "runs": runs,
            "news_latest": news_latest,
        },
    )


@router.get("/runs", response_class=HTMLResponse)
def admin_runs(
    request: Request,
    run_type: str = Query(None, description="fetch_news/url_task"),
    task_id: str = Query(None, description="URL 任务 id"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    settings = get_settings()
    database.init_db(settings.database_url)
    conn = database.get_connection(settings.database_url)
    try:
        runs = database.list_scheduler_runs(
            conn,
            run_type=run_type or None,
            task_id=task_id or None,
            limit=limit,
            offset=offset,
        )
    finally:
        conn.close()

    return templates.TemplateResponse(
        "admin_runs.html",
        {
            "request": request,
            "runs": runs,
            "filters": {"run_type": run_type or "", "task_id": task_id or "", "limit": limit, "offset": offset},
        },
    )


@router.get("/logs", response_class=HTMLResponse)
def admin_logs(
    request: Request,
    run_type: str = Query(None, description="fetch_news/cleanup_news/url_task"),
    task_id: str = Query(None, description="URL 任务 id"),
    refresh: int = Query(5, ge=0, le=60, description="自动刷新秒数，0 为不刷新"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """日志页：展示所有定时任务（抓取/清理/URL任务）的运行记录。"""
    settings = get_settings()
    database.init_db(settings.database_url)
    conn = database.get_connection(settings.database_url)
    try:
        runs = database.list_scheduler_runs(
            conn,
            run_type=run_type or None,
            task_id=task_id or None,
            limit=limit,
            offset=offset,
        )
    finally:
        conn.close()

    return templates.TemplateResponse(
        "admin_logs.html",
        {
            "request": request,
            "runs": runs,
            "filters": {
                "run_type": run_type or "",
                "task_id": task_id or "",
                "refresh": refresh,
                "limit": limit,
                "offset": offset,
            },
        },
    )


@router.get("/news", response_class=HTMLResponse)
def admin_news(
    request: Request,
    src: str = Query(None),
    start_datetime: str = Query(None),
    end_datetime: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    settings = get_settings()
    database.init_db(settings.database_url)
    conn = database.get_connection(settings.database_url)
    try:
        items = database.list_news(
            conn,
            src=src or None,
            start_datetime=start_datetime or None,
            end_datetime=end_datetime or None,
            limit=limit,
            offset=offset,
        )
        cur = conn.execute("SELECT src, last_end_datetime, updated_at FROM fetch_log ORDER BY src")
        fetch_log = cur.fetchall()
    finally:
        conn.close()

    return templates.TemplateResponse(
        "admin_news.html",
        {
            "request": request,
            "items": items,
            "fetch_log": fetch_log,
            "filters": {
                "src": src or "",
                "start_datetime": start_datetime or "",
                "end_datetime": end_datetime or "",
                "limit": limit,
                "offset": offset,
            },
        },
    )

