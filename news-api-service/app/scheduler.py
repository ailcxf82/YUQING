# -*- coding: utf-8 -*-
"""定时服务：默认每 N 分钟执行抓取 + 已注册的其他接口，支持开关与注册"""
import json
import logging
import uuid
from pathlib import Path
from typing import List, Optional, Callable, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
import httpx

from app.config import get_settings
from app import tushare_client
from app import database

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path(__file__).resolve().parent.parent / "scheduler_config.json"
_DEFAULT_INTERVAL_MINUTES = 5
_FETCH_JOB_ID = "fetch_news"
_CLEAN_JOB_ID = "cleanup_news"
_COLLECT_JOB_ID = "collect_news_for_analysis"
_TASK_JOB_PREFIX = "task_"

_scheduler: Optional[BackgroundScheduler] = None
_enabled = True
_interval_minutes = _DEFAULT_INTERVAL_MINUTES
_registered_tasks: List[dict] = []  # [{"id", "name", "url", "method", "interval_minutes"}, ...]
_registered_callables: List[dict] = []  # [{"id": str, "name": str, "callable": Callable}, ...]


def _normalize_interval(m: int) -> int:
    return max(1, min(1440, int(m)))


def _ensure_task_interval(task: dict) -> dict:
    """确保任务有 interval_minutes 字段（兼容旧配置）。"""
    if "interval_minutes" not in task:
        task["interval_minutes"] = _DEFAULT_INTERVAL_MINUTES
    else:
        task["interval_minutes"] = _normalize_interval(task["interval_minutes"])
    return task


def _load_config() -> None:
    global _enabled, _interval_minutes, _registered_tasks
    if not _CONFIG_FILE.exists():
        _enabled = True
        _interval_minutes = _DEFAULT_INTERVAL_MINUTES
        _registered_tasks = []
        return
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _enabled = data.get("enabled", True)
        _interval_minutes = _normalize_interval(data.get("interval_minutes", _DEFAULT_INTERVAL_MINUTES))
        _registered_tasks = data.get("registered_tasks", [])
        for t in _registered_tasks:
            _ensure_task_interval(t)
    except Exception:
        _enabled = True
        _interval_minutes = _DEFAULT_INTERVAL_MINUTES
        _registered_tasks = []


def _save_config() -> None:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "enabled": _enabled,
                "interval_minutes": _interval_minutes,
                "registered_tasks": _registered_tasks,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def _run_fetch() -> dict:
    """执行内置抓取任务（直接调逻辑，不经过服务开关）。"""
    settings = get_settings()
    if not settings.tushare_token:
        return {"task": "fetch_news", "ok": False, "error": "未配置 TUSHARE_TOKEN"}
    try:
        results = tushare_client.fetch_news_all_sources(
            token=settings.tushare_token,
            default_hours=settings.default_fetch_hours,
            database_url=settings.database_url,
        )
        return {"task": "fetch_news", "ok": True, "results": results}
    except Exception as e:
        logger.exception("scheduled fetch_news failed")
        return {"task": "fetch_news", "ok": False, "error": str(e)}


def _run_registered_url(task: dict) -> dict:
    """对已注册的 URL 发起 HTTP 请求。"""
    tid = task.get("id", "")
    name = task.get("name", tid)
    url = task.get("url", "")
    method = (task.get("method") or "GET").upper()
    if not url:
        return {"task": name, "ok": False, "error": "url 为空"}
    try:
        with httpx.Client(timeout=30.0) as client:
            if method == "GET":
                r = client.get(url)
            elif method == "POST":
                r = client.post(url)
            elif method == "PUT":
                r = client.put(url)
            else:
                r = client.request(method, url)
        return {"task": name, "ok": r.is_success, "status_code": r.status_code}
    except Exception as e:
        logger.exception("scheduled url task %s failed", name)
        return {"task": name, "ok": False, "error": str(e)}


def _run_registered_callable(entry: dict) -> dict:
    """执行通过 register_callable 注册的 Python 可调用对象。"""
    name = entry.get("name", "callable")
    try:
        cb = entry.get("callable")
        if callable(cb):
            cb()
        return {"task": name, "ok": True}
    except Exception as e:
        logger.exception("scheduled callable %s failed", name)
        return {"task": name, "ok": False, "error": str(e)}


def _fetch_job() -> None:
    """内置抓取任务：仅执行新闻抓取。"""
    if not _enabled:
        return
    logger.info("fetch_news job running")
    settings = get_settings()
    database.init_db(settings.database_url)
    started_at = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    outcome = _run_fetch()
    finished_at = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = database.get_connection(settings.database_url)
        database.insert_scheduler_run(
            conn=conn,
            run_type="fetch_news",
            task_id="",
            task_name="fetch_news",
            url="",
            method="",
            started_at=started_at,
            finished_at=finished_at,
            ok=bool(outcome.get("ok")),
            status_code=None,
            error=str(outcome.get("error", "") or ""),
        )
        conn.close()
    except Exception:
        logger.exception("write scheduler run(fetch_news) failed")
    logger.info("fetch_news job finished: %s", outcome)


def _collect_news_job() -> None:
    """舆情深度采集任务：采集+预处理+向量化+LanceDB 存储，供分析链路读取"""
    if not _enabled:
        return
    logger.info("collect_news_for_analysis job running")
    try:
        from core.news_collector_job import collect_all
        outcome = collect_all()
        logger.info("collect_news_for_analysis finished: %s", outcome)
    except Exception:
        logger.exception("collect_news_for_analysis failed")


def _cleanup_job() -> None:
    """清理旧新闻数据（默认 48 小时前），每小时运行一次。"""
    if not _enabled:
        return
    logger.info("cleanup_news job running")
    settings = get_settings()
    database.init_db(settings.database_url)
    started_at = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    outcome = {"ok": True}
    try:
        conn = database.get_connection(settings.database_url)
        info = database.cleanup_old_news(conn, hours=48)
        conn.close()
        outcome.update(info)
    except Exception as e:
        logger.exception("scheduled cleanup_news failed")
        outcome["ok"] = False
        outcome["error"] = str(e)
    finished_at = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = database.get_connection(settings.database_url)
        database.insert_scheduler_run(
            conn=conn,
            run_type="cleanup_news",
            task_id="",
            task_name="cleanup_news_48h",
            url="",
            method="",
            started_at=started_at,
            finished_at=finished_at,
            ok=bool(outcome.get("ok")),
            status_code=None,
            error=str(outcome.get("error", "") or ""),
        )
        conn.close()
    except Exception:
        logger.exception("write scheduler run(cleanup_news) failed")
    logger.info("cleanup_news job finished: %s", outcome)


def _make_task_job(task_id: str):
    """返回针对单个 URL 任务的 job 函数（闭包绑定 task_id）。"""
    def _job() -> None:
        if not _enabled:
            return
        task = next((t for t in _registered_tasks if t.get("id") == task_id), None)
        if not task:
            return
        logger.info("task job %s running", task.get("name", task_id))
        settings = get_settings()
        database.init_db(settings.database_url)
        started_at = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        outcome = _run_registered_url(task)
        finished_at = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            conn = database.get_connection(settings.database_url)
            database.insert_scheduler_run(
                conn=conn,
                run_type="url_task",
                task_id=task.get("id", "") or "",
                task_name=task.get("name", "") or "",
                url=task.get("url", "") or "",
                method=(task.get("method", "") or "").upper(),
                started_at=started_at,
                finished_at=finished_at,
                ok=bool(outcome.get("ok")),
                status_code=outcome.get("status_code"),
                error=str(outcome.get("error", "") or ""),
            )
            conn.close()
        except Exception:
            logger.exception("write scheduler run(url_task) failed")
        logger.info("task job %s finished: %s", task.get("name", task_id), outcome)
    return _job


def is_enabled() -> bool:
    return _enabled


def set_enabled(enabled: bool) -> bool:
    global _enabled
    _enabled = bool(enabled)
    _save_config()
    return _enabled


def get_interval_minutes() -> int:
    return _interval_minutes


def set_interval_minutes(minutes: int) -> int:
    global _interval_minutes
    _interval_minutes = _normalize_interval(minutes)
    _save_config()
    if _scheduler and _scheduler.running:
        _scheduler.reschedule_job(_FETCH_JOB_ID, trigger="interval", minutes=_interval_minutes)
    return _interval_minutes


def get_registered_tasks() -> List[dict]:
    """返回已注册的 URL 任务（含各任务 next_run_time）的副本。"""
    result = []
    for t in _registered_tasks:
        out = t.copy()
        if _scheduler and _scheduler.running:
            job = _scheduler.get_job(_TASK_JOB_PREFIX + t.get("id", ""))
            if job and job.next_run_time:
                out["next_run_time"] = job.next_run_time.isoformat()
            else:
                out["next_run_time"] = None
        else:
            out["next_run_time"] = None
        result.append(out)
    return result


def register_task(
    name: str,
    url: str,
    method: str = "GET",
    interval_minutes: int = _DEFAULT_INTERVAL_MINUTES,
) -> dict:
    """注册一个定时调用的接口（URL），可配置该任务的定时间隔。返回新建任务信息。"""
    task_id = str(uuid.uuid4())[:8]
    interval_minutes = _normalize_interval(interval_minutes)
    task = {
        "id": task_id,
        "name": name,
        "url": url.strip(),
        "method": (method or "GET").upper(),
        "interval_minutes": interval_minutes,
    }
    _registered_tasks.append(task)
    _save_config()
    if _scheduler and _scheduler.running:
        _scheduler.add_job(
            _make_task_job(task_id),
            trigger="interval",
            minutes=interval_minutes,
            id=_TASK_JOB_PREFIX + task_id,
            replace_existing=True,
        )
    return task.copy()


def unregister_task(task_id: str) -> bool:
    """根据 id 移除已注册的 URL 任务，并移除其定时 job。"""
    global _registered_tasks
    for i, t in enumerate(_registered_tasks):
        if t.get("id") == task_id:
            _registered_tasks.pop(i)
            _save_config()
            if _scheduler and _scheduler.running:
                try:
                    _scheduler.remove_job(_TASK_JOB_PREFIX + task_id)
                except Exception:
                    pass
            return True
    return False


def update_task_interval(task_id: str, interval_minutes: int) -> bool:
    """更新某任务的定时间隔并重新调度。"""
    for t in _registered_tasks:
        if t.get("id") == task_id:
            t["interval_minutes"] = _normalize_interval(interval_minutes)
            _save_config()
            if _scheduler and _scheduler.running:
                _scheduler.reschedule_job(
                    _TASK_JOB_PREFIX + task_id,
                    trigger="interval",
                    minutes=t["interval_minutes"],
                )
            return True
    return False


def register_callable(name: str, fn: Callable[[], Any]) -> str:
    """注册一个定时执行的 Python 可调用对象（仅内存，不持久化）。返回 id。"""
    cid = str(uuid.uuid4())[:8]
    _registered_callables.append({"id": cid, "name": name, "callable": fn})
    return cid


def unregister_callable(callable_id: str) -> bool:
    """根据 id 移除已注册的 callable。"""
    global _registered_callables
    for i, entry in enumerate(_registered_callables):
        if entry.get("id") == callable_id:
            _registered_callables.pop(i)
            return True
    return False


def get_status() -> dict:
    """返回定时服务状态：是否开启、抓取/清理下次运行时间、已注册任务列表。"""
    fetch_next_run = None
    clean_next_run = None
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job(_FETCH_JOB_ID)
        if job and job.next_run_time:
            fetch_next_run = job.next_run_time.isoformat()
        job_c = _scheduler.get_job(_CLEAN_JOB_ID)
        if job_c and job_c.next_run_time:
            clean_next_run = job_c.next_run_time.isoformat()
    collect_next_run = None
    if _scheduler and _scheduler.running:
        job_col = _scheduler.get_job(_COLLECT_JOB_ID)
        if job_col and job_col.next_run_time:
            collect_next_run = job_col.next_run_time.isoformat()

    return {
        "enabled": _enabled,
        "fetch_interval_minutes": _interval_minutes,
        "fetch_next_run_time": fetch_next_run,
        "cleanup_interval_minutes": 60,
        "cleanup_next_run_time": clean_next_run,
        "news_collect_next_run_time": collect_next_run,
        "registered_tasks": get_registered_tasks(),
    }


def start_scheduler() -> None:
    """启动定时器（在应用 startup 时调用）：抓取任务按全局间隔、清理任务每小时，每个 URL 任务按自身间隔。"""
    global _scheduler
    _load_config()
    if _scheduler is not None:
        return
    jobstores = {"default": MemoryJobStore()}
    _scheduler = BackgroundScheduler(jobstores=jobstores)
    _scheduler.add_job(
        _fetch_job,
        trigger="interval",
        minutes=_interval_minutes,
        id=_FETCH_JOB_ID,
        replace_existing=True,
    )
    _scheduler.add_job(
        _cleanup_job,
        trigger="interval",
        minutes=60,
        id=_CLEAN_JOB_ID,
        replace_existing=True,
    )

    # 舆情深度采集（为分析链路准备本地数据）
    try:
        from core.news_collector_job import get_config_data
        collect_cfg = get_config_data()
        collect_interval = collect_cfg.get("interval_minutes", 30)
        if collect_cfg.get("enabled", True):
            _scheduler.add_job(
                _collect_news_job,
                trigger="interval",
                minutes=collect_interval,
                id=_COLLECT_JOB_ID,
                replace_existing=True,
            )
            logger.info("舆情采集定时任务已注册 | interval=%d min", collect_interval)
    except Exception:
        logger.exception("注册舆情采集定时任务失败")

    for t in _registered_tasks:
        _ensure_task_interval(t)
        _scheduler.add_job(
            _make_task_job(t["id"]),
            trigger="interval",
            minutes=t["interval_minutes"],
            id=_TASK_JOB_PREFIX + t["id"],
            replace_existing=True,
        )
    _scheduler.start()
    logger.info(
        "scheduler started: fetch every %s min, %s url task(s)",
        _interval_minutes,
        len(_registered_tasks),
    )


def stop_scheduler() -> None:
    """停止定时器（在应用 shutdown 时调用）。"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    logger.info("scheduler stopped")
