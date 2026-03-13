import json
import time
from urllib import request as urlreq


BASE_URL = "http://localhost:8000"


def _post_json(path: str, body: dict) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urlreq.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlreq.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    with urlreq.urlopen(url, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    print("=== 1. 创建统一入口任务 (keyword 模式) ===")
    body = {
        "keyword": "浦发银行",
        "time_range": "近7天",
        "analysis_depth": "标准版",
    }
    resp = _post_json("/api/v2/analysis/entry", body)
    print("create_task resp:", json.dumps(resp, ensure_ascii=False, indent=2))

    task_id = resp.get("task_id")
    if not task_id:
        print("创建任务失败，未返回 task_id")
        return

    print(f"\n=== 2. 轮询任务状态 (task_id={task_id}) ===")
    start = time.time()
    seen_steps = set()
    while True:
        status_resp = _get(f"/api/v2/analysis/status/{task_id}")
        now = time.time()
        elapsed = int((now - start) * 1000)
        overall = status_resp.get("overall_status")
        current_step = status_resp.get("current_step")
        progress = status_resp.get("progress", {})
        timeline = status_resp.get("timeline", [])

        print(f"\n[{elapsed} ms] status={overall} current_step={current_step} "
              f"progress={progress}")

        for step in timeline:
            sid = (step.get("step"), step.get("status"))
            if sid in seen_steps:
                continue
            seen_steps.add(sid)
            msg = step.get("message", "")
            dur = step.get("duration_ms")
            ts = step.get("timestamp")
            print(
                f"  - step={step.get('step')} status={step.get('status')} "
                f"duration_ms={dur} ts={ts} msg={msg}"
            )

        if overall in ("DONE", "ERROR"):
            break

        time.sleep(5)

    print("\n=== 3. 打印最终报告是否就绪 ===")
    print(json.dumps(status_resp, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

