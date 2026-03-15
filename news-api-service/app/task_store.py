from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

_lock = threading.RLock()
_tasks: Dict[str, Dict[str, Any]] = {}


def init_task(task_id: str, base_info: Dict[str, Any]) -> None:
    now = time.time()
    with _lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "status": base_info.get("status", "PENDING"),
            "current_step": base_info.get("current_step", "initialized"),
            "steps": base_info.get("steps", []),
            "steps_completed": base_info.get("steps_completed", []),
            "steps_pending": base_info.get("steps_pending", []),
            "step_outputs": base_info.get("step_outputs", {}),
            "partial_report": {},
            "final_report": None,
            "error": None,
            "created_at": base_info.get("created_at", now),
            "updated_at": base_info.get("updated_at", now),
            "task_base_info": base_info.get("task_base_info", {}),
        }


def update_task(
    task_id: str,
    *,
    status: str | None = None,
    current_step: str | None = None,
    append_logs: list | None = None,
    append_steps_completed: List[str] | None = None,
    update_step_output: Dict[str, Any] | None = None,
    final_report: Dict[str, Any] | None = None,
    error: str | None = None,
    steps_pending: List[str] | None = None,
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
        if append_steps_completed:
            existing = set(task.get("steps_completed", []))
            for step in append_steps_completed:
                if step not in existing:
                    task.setdefault("steps_completed", []).append(step)
        if update_step_output:
            task.setdefault("step_outputs", {}).update(update_step_output)
        if final_report is not None:
            task["final_report"] = final_report
        if error is not None:
            task["error"] = error
        if steps_pending is not None:
            task["steps_pending"] = steps_pending
        task["updated_at"] = now


def get_task(task_id: str) -> Dict[str, Any] | None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return None
        return dict(task)


def delete_task(task_id: str) -> bool:
    with _lock:
        if task_id in _tasks:
            del _tasks[task_id]
            return True
        return False


def list_tasks(
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    with _lock:
        tasks = list(_tasks.values())
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        tasks.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return tasks[:limit]


def compute_progress(task: Dict[str, Any]) -> Dict[str, int]:
    steps = task.get("steps") or []
    finished = len([s for s in steps if s.get("status") in ("success", "partial", "skipped", "error")])
    total = max(finished, 7)
    return {"total_steps": total, "finished_steps": finished}
