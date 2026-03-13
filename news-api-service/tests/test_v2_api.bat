@echo off
chcp 65001 >nul 2>&1
echo ============================================================
echo   Phase 4 API V2 测试脚本
echo   确保服务已启动: python -m uvicorn app.main:app --port 8000
echo ============================================================
echo.

set BASE=http://localhost:8000
set NO_PROXY=localhost,127.0.0.1

echo [1] 健康检查
curl -s "%BASE%/health"
echo.
echo.

echo [2] 系统架构信息
curl -s "%BASE%/api/v2/analysis/system-info"
echo.
echo.

echo [3] 调试-配置检查
curl -s "%BASE%/internal/debug/config"
echo.
echo.

echo [4] 调试-LLM连通性
curl -s "%BASE%/internal/debug/llm?ping=true"
echo.
echo.

echo [5] 快捷分析 (浦发银行)
echo     注意: 此请求需要30-180秒，请耐心等待...
curl -s -X POST "%BASE%/api/v2/analysis/quick" -H "Content-Type: application/json" -d "{\"symbol\":\"600000.SH\",\"name\":\"浦发银行\",\"start_date\":\"2026-03-01\",\"end_date\":\"2026-03-11\"}"
echo.
echo.

echo ============================================================
echo   测试完成
echo ============================================================
pause
