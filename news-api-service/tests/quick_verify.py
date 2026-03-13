# -*- coding: utf-8 -*-
"""Phase 4 API Quick Verify"""
import os, json, time
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"
import urllib.request

BASE = "http://127.0.0.1:8000"
P = F = 0

def get(p):
    try:
        r = urllib.request.urlopen(BASE + p, timeout=10)
        return json.loads(r.read())
    except Exception as e:
        return {"_err": str(e)}

def post(p, d):
    b = json.dumps(d).encode()
    req = urllib.request.Request(BASE + p, data=b, headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=600)
        return json.loads(r.read())
    except Exception as e:
        return {"_err": str(e)}

def ok(n, r):
    global P, F
    if "_err" in r:
        F += 1
        print("  [FAIL] %s: %s" % (n, str(r["_err"])[:100]))
    else:
        P += 1
        print("  [PASS] %s" % n)

print("=" * 50)
print("  Phase4 API Quick Verify")
print("=" * 50)

r = get("/health")
ok("health", r)

r = get("/")
ok("root", r)

r = get("/api/v2/analysis/system-info")
ok("system-info", r)
print("    agents=%d" % len(r.get("agents", [])))

r = get("/internal/debug/config")
ok("debug/config", r)

r = get("/internal/debug/llm?ping=false")
ok("debug/llm", r)
print("    provider=%s has_key=%s" % (r.get("provider"), r.get("has_key")))

print("\n--- news-only test ---")
r = post("/api/v2/analysis/news-only", {"symbol": "600000.SH", "name": "test"})
ok("news-only", r)
print("    count=%s" % r.get("news_total_count", "?"))

print("\n--- quick analysis test ---")
print("    [WAIT] Full pipeline running (30-300s)...")
t0 = time.time()
r = post("/api/v2/analysis/quick", {
    "symbol": "600000.SH",
    "name": "pufa",
    "start_date": "2026-03-04",
    "end_date": "2026-03-11",
})
t1 = time.time()
print("    [TIME] %dms" % int((t1 - t0) * 1000))
ok("quick-analysis", r)
if "report" in r:
    rpt = r["report"]
    st = rpt.get("full_link_log", {}).get("status", "?")
    print("    status=%s" % st)
    if rpt.get("compliance_disclaimer"):
        print("    [OK] compliance disclaimer present")

print("\n" + "=" * 50)
print("  PASS=%d FAIL=%d" % (P, F))
if F == 0:
    print("  All tests passed!")
print("=" * 50)
