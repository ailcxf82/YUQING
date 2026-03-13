# -*- coding: utf-8 -*-
"""Phase 4 API V2 自动化测试脚本（Python 版，绕过代理）"""

import json
import os
import sys
import time
import urllib.request

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0


def get(path):
    url = f"{BASE}{path}"
    try:
        r = urllib.request.urlopen(url, timeout=10)
        return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def post(path, data):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        r = urllib.request.urlopen(req, timeout=300)
        return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": str(e), "detail": body}
    except Exception as e:
        return {"error": str(e)}


def check(name, result, key="success"):
    global PASS, FAIL
    if "error" in result and key != "error":
        FAIL += 1
        err = result.get("error") or result.get("detail") or ""
        print(f"  [FAIL] {name}: {str(err)[:100]}")
        return False
    PASS += 1
    print(f"  [PASS] {name}")
    return True


def main():
    print()
    print("=" * 60)
    print("  Phase 4 API V2 Test Suite")
    print("=" * 60)

    # 1. Health
    print("\n--- 1. Health Check ---")
    r = get("/health")
    check("GET /health", r, "status")
    print(f"       status={r.get('status')} version={r.get('version')}")

    # 2. Root
    print("\n--- 2. Root ---")
    r = get("/")
    check("GET /", r, "service")
    print(f"       service={r.get('service', '')[:40]}")

    # 3. System Info
    print("\n--- 3. System Info ---")
    r = get("/api/v2/analysis/system-info")
    check("GET /api/v2/analysis/system-info", r, "system")
    agents = r.get("agents", [])
    print(f"       agents={len(agents)} version={r.get('version')}")

    # 4. Debug Config
    print("\n--- 4. Debug Config ---")
    r = get("/internal/debug/config")
    check("GET /internal/debug/config", r, "llm_provider")
    print(f"       provider={r.get('llm_provider')} tushare={r.get('has_tushare_token')}")

    # 5. Debug LLM (skip ping to avoid proxy timeout)
    print("\n--- 5. Debug LLM ---")
    r = get("/internal/debug/llm?ping=false")
    check("GET /internal/debug/llm", r, "provider")
    print(f"       provider={r.get('provider')} has_key={r.get('has_key')}")

    # 6. News Only
    print("\n--- 6. News Only (news-only) ---")
    r = post("/api/v2/analysis/news-only", {
        "symbol": "600000.SH",
        "name": "浦发银行",
    })
    if "error" not in r:
        check("POST /api/v2/analysis/news-only", r)
        print(f"       news_count={r.get('news_total_count', 0)}")
    else:
        check("POST /api/v2/analysis/news-only", r)

    # 7. Quick Analysis
    print("\n--- 7. Quick Analysis (full-link) ---")
    print("       [WAIT] Executing full pipeline (30-180s)...")
    start = time.time()
    r = post("/api/v2/analysis/quick", {
        "symbol": "600000.SH",
        "name": "浦发银行",
        "start_date": "2026-03-04",
        "end_date": "2026-03-11",
        "analysis_depth": "标准版",
    })
    elapsed = int((time.time() - start) * 1000)
    print(f"       [TIME] Elapsed: {elapsed}ms")

    if "error" not in r:
        check("POST /api/v2/analysis/quick", r)
        report = r.get("report", {})
        status = report.get("full_link_log", {}).get("status", "unknown")
        print(f"       status={status}")
        if report.get("compliance_disclaimer"):
            print("       [PASS] compliance_disclaimer present")
    else:
        check("POST /api/v2/analysis/quick", r)

    # Summary
    print()
    print("=" * 60)
    print(f"  Results: PASS={PASS} FAIL={FAIL}")
    print("=" * 60)
    if FAIL == 0:
        print("  All API tests passed!")
    else:
        print(f"  {FAIL} tests failed.")
    print()


if __name__ == "__main__":
    main()
