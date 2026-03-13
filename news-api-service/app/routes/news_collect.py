# -*- coding: utf-8 -*-
"""舆情数据定时采集管理 API

将舆情采集从分析链路中解耦为独立的后台定时任务。
用户通过本组接口管理采集标的、查看采集状态、手动触发采集。

接口：
  POST /api/v2/news-collect/add-symbol     添加采集标的
  POST /api/v2/news-collect/remove-symbol  移除采集标的
  POST /api/v2/news-collect/run-now        立即执行一次采集
  POST /api/v2/news-collect/run-symbol     立即采集指定标的
  GET  /api/v2/news-collect/status         采集状态与本地数据概览
  PUT  /api/v2/news-collect/settings       更新采集配置
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v2/news-collect", tags=["舆情定时采集管理"])

_running_task: Optional[str] = None


class AddSymbolRequest(BaseModel):
    symbol: str = Field(..., description="标的代码，如 600000.SH")
    name: str = Field(default="", description="标的名称，如 浦发银行")


class RemoveSymbolRequest(BaseModel):
    symbol: str = Field(..., description="要移除的标的代码")


class RunSymbolRequest(BaseModel):
    symbol: str = Field(..., description="标的代码")
    name: str = Field(default="", description="标的名称")
    hours: int = Field(default=24, description="回溯小时数")


class SettingsRequest(BaseModel):
    interval_minutes: Optional[int] = Field(
        default=None, description="采集间隔(分钟)，范围 5~1440"
    )
    fetch_hours: Optional[int] = Field(
        default=None, description="每次采集回溯小时数"
    )
    enabled: Optional[bool] = Field(
        default=None, description="是否启用定时采集"
    )


@router.post(
    "/add-symbol",
    summary="添加采集标的",
    description="将标的加入定时采集列表。下次定时任务执行时会自动采集该标的的舆情数据。",
)
def add_symbol(body: AddSymbolRequest):
    from core.news_collector_job import add_symbol as _add
    cfg = _add(body.symbol, body.name)
    return {
        "success": True,
        "message": f"标的 {body.symbol} 已加入采集列表",
        "symbols": cfg.get("symbols", []),
    }


@router.post(
    "/remove-symbol",
    summary="移除采集标的",
)
def remove_symbol(body: RemoveSymbolRequest):
    from core.news_collector_job import remove_symbol as _rm
    cfg = _rm(body.symbol)
    return {
        "success": True,
        "message": f"标的 {body.symbol} 已移除",
        "symbols": cfg.get("symbols", []),
    }


@router.post(
    "/run-now",
    summary="立即执行全量采集",
    description=(
        "对所有已配置的标的立即执行一次完整采集流程（采集+预处理+向量化+存储）。\n\n"
        "**注意**：此操作为后台异步执行，接口立即返回。通过 GET /status 查看进度。"
    ),
)
def run_now():
    global _running_task
    if _running_task:
        return {
            "success": False,
            "message": f"已有采集任务正在执行: {_running_task}",
        }

    from core.news_collector_job import get_config_data
    cfg = get_config_data()
    if not cfg.get("symbols"):
        raise HTTPException(
            status_code=400,
            detail="无配置标的，请先调用 /add-symbol 添加。",
        )

    def _bg():
        global _running_task
        _running_task = "全量采集中"
        try:
            from core.news_collector_job import collect_all
            collect_all()
        finally:
            _running_task = None

    t = threading.Thread(target=_bg, daemon=True)
    t.start()

    return {
        "success": True,
        "message": "全量采集任务已启动（后台执行），通过 GET /status 查看进度",
        "symbols": cfg.get("symbols", []),
    }


@router.post(
    "/run-symbol",
    summary="立即采集指定标的",
    description="对指定标的执行一次完整采集。此接口为同步执行，会等待采集完成。",
)
def run_symbol(body: RunSymbolRequest):
    from core.news_collector_job import collect_for_symbol

    start = time.time()
    try:
        result = collect_for_symbol(body.symbol, body.name, body.hours)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"采集失败: {exc}"
        ) from exc

    elapsed = int((time.time() - start) * 1000)
    return {
        "success": True,
        "elapsed_ms": elapsed,
        "result": result,
    }


@router.get(
    "/status",
    summary="采集状态与本地数据概览",
    description="返回当前采集配置、上次执行结果、本地 LanceDB 数据表信息。",
)
def get_status():
    from core.news_collector_job import get_status as _status
    status = _status()
    status["running_task"] = _running_task
    return status


@router.put(
    "/settings",
    summary="更新采集配置",
)
def update_settings(body: SettingsRequest):
    from core.news_collector_job import (
        set_interval,
        set_enabled,
        get_config_data,
    )

    updated = {}
    if body.interval_minutes is not None:
        updated["interval_minutes"] = set_interval(body.interval_minutes)
    if body.enabled is not None:
        updated["enabled"] = set_enabled(body.enabled)
    if body.fetch_hours is not None:
        cfg = get_config_data()
        cfg["fetch_hours"] = max(1, min(168, body.fetch_hours))
        from core.news_collector_job import _save_config
        _save_config(cfg)
        updated["fetch_hours"] = cfg["fetch_hours"]

    return {"success": True, "updated": updated, "config": get_config_data()}
