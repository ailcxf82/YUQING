from __future__ import annotations

import threading
import time
from typing import Any, Dict

_lock = threading.RLock()
_tasks: Dict[str, Dict[str, Any]] = {}


def init_task(task_id: str, base_info: Dict[str, Any]) -> None:
    now = time.time()
    with _lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "status": "PENDING",
            "current_step": "initialized",
            "steps": [],
            "partial_report": {},
            "final_report": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "base_info": base_info,
        }


def update_task(
    task_id: str,
    *,
    status: str | None = None,
    current_step: str | None = None,
    append_logs: list | None = None,
    final_report: Dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    now = time.time()
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        if status is not None:
            task["status"] = status
        if current_step is not None:
            task["current_step"] = current_step
        if append_logs:
            task.setdefault("steps", []).extend(append_logs)
        if final_report is not None:
            task["final_report"] = final_report
        if error is not None:
            task["error"] = error
        task["updated_at"] = now


def get_task(task_id: str) -> Dict[str, Any] | None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return None
        # 返回浅拷贝，避免外部修改内部状态
        return dict(task)


def compute_progress(task: Dict[str, Any]) -> Dict[str, int]:
    """根据步骤日志估算进度。"""
    steps = task.get("steps") or []
    finished = len([s for s in steps if s.get("status") in ("success", "partial", "skipped", "error")])
    total = max(finished, 7)  # 约定全链路 ~7 个主要阶段
    return {"total_steps": total, "finished_steps": finished}

