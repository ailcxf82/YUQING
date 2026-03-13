# -*- coding: utf-8 -*-
"""内部接口：定时服务配置，不对外暴露（不在 API 文档中展示）"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import scheduler

# 不加入 OpenAPI 文档：include_in_schema=False
router = APIRouter(prefix="/internal/scheduler", tags=["内部-定时"], include_in_schema=False)


@router.get("/status")
def get_scheduler_status():
    return scheduler.get_status()


class SchedulerSwitchBody(BaseModel):
    enabled: bool


@router.put("/switch")
def set_scheduler_switch(body: SchedulerSwitchBody):
    scheduler.set_enabled(body.enabled)
    return {"enabled": scheduler.is_enabled()}


class SchedulerIntervalBody(BaseModel):
    interval_minutes: int


@router.put("/interval")
def set_scheduler_interval(body: SchedulerIntervalBody):
    minutes = scheduler.set_interval_minutes(body.interval_minutes)
    return {"interval_minutes": minutes}


class RegisterTaskBody(BaseModel):
    name: str
    url: str
    method: str = "GET"
    interval_minutes: int = 5


@router.post("/tasks")
def register_task(body: RegisterTaskBody):
    task = scheduler.register_task(
        name=body.name,
        url=body.url,
        method=body.method or "GET",
        interval_minutes=body.interval_minutes,
    )
    return {"success": True, "task": task}


class UpdateTaskIntervalBody(BaseModel):
    interval_minutes: int


@router.put("/tasks/{task_id}")
def update_task_interval(task_id: str, body: UpdateTaskIntervalBody):
    ok = scheduler.update_task_interval(task_id, body.interval_minutes)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    tasks = [t for t in scheduler.get_registered_tasks() if t.get("id") == task_id]
    return {"success": True, "task": tasks[0] if tasks else None}


@router.delete("/tasks/{task_id}")
def unregister_task(task_id: str):
    ok = scheduler.unregister_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True}
