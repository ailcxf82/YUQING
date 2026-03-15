# 测试文件说明

本目录包含 v1/v2 全部接口的测试文件和自动化验证脚本。

## 文件清单

| 文件 | 用途 | 运行方式 |
|------|------|----------|
| `test_news.json` | v1 阶段1 舆情分析请求体（5条多信源舆情） | `curl -d @test_news.json` |
| `test_research.json` | v1 阶段2 基本面分析请求体 | `curl -d @test_research.json` |
| `test_v2_api.py` | **Phase4 v2 全链路自动化测试**（推荐） | `python test_v2_api.py` |
| `quick_verify.py` | Phase4 快速冒烟测试 | `python quick_verify.py` |
| `test_pipeline_api.py` | **分步调用 API 自动化测试** | `python test_pipeline_api.py` |
| `news_result.json` | v1 阶段1 输出缓存（自动生成） | — |
| `research_result.json` | v1 阶段2 输出缓存（自动生成） | — |
| `signal_result.json` | v1 阶段3 输出缓存（自动生成） | — |
| `strategy_result.json` | v1 阶段4 输出缓存（自动生成） | — |
| `phase2_result.json` | Phase2 验证输出（自动生成） | — |
| `phase3_result.json` | Phase3 验证输出（自动生成） | — |

## 前提条件

```cmd
REM 1. 启动服务
cd /d D:\lianghuatouzi\yuqing0309\news-api-service
uvicorn app.main:app --host 0.0.0.0 --port 8000

REM 2. 确保 .env 已配置
REM    TUSHARE_TOKEN=...
REM    LLM_PROVIDER=deepseek
REM    DEEPSEEK_API_KEY=...
```

---

## 🌐 Web 测试页面（推荐）

服务启动后，可通过浏览器访问以下测试页面：

### 1. 分步调用 API 测试页面
**地址:** `http://localhost:8000/static/pipeline_test.html`

**功能:**
- 左侧导航栏显示所有步骤
- 支持按顺序逐步执行每个 API
- 自动传递 task_id 和 keyword
- 实时显示进度条
- 结果格式化显示（JSON 语法高亮）

**使用流程:**
1. 输入关键词，点击"创建任务"
2. 按顺序执行步骤 2-10
3. 查看每步的返回结果

### 2. 任务状态管理页面
**地址:** `http://localhost:8000/static/task_manager.html`

**功能:**
- 查询任务状态和进度
- 获取最终报告
- 重置/删除任务
- 查看步骤信息（预计耗时、外部请求等）

### 3. 全链路一键分析页面
**地址:** `http://localhost:8000/static/analysis_test.html`

**功能:**
- 全链路一键分析
- 快捷分析
- 仅采集新闻
- 历史记录查看
- 进度动画展示

---

## 🔧 分步调用 API 测试（Pipeline）

分步调用 API 将全链路拆分为独立步骤，支持前端逐步执行、进度可视化、中断恢复。

### 步骤概览

| 步骤 | API 路径 | 外部请求 | 预计耗时 |
|------|----------|---------|---------|
| 1 | `/api/v2/pipeline/task/create` | ❌ 本地 | <10ms |
| 2 | `/api/v2/pipeline/step/keyword-analysis` | ✅ LLM | ~2s |
| 3 | `/api/v2/pipeline/step/news-retrieval` | ❌ 本地 | <100ms |
| 4 | `/api/v2/pipeline/step/event-classification` | ✅ LLM | ~96s |
| 5 | `/api/v2/pipeline/step/sentiment-analysis` | ✅ LLM | ~91s |
| 6 | `/api/v2/pipeline/step/fundamental-impact` | ✅ LLM | ~127s |
| 7 | `/api/v2/pipeline/step/industry-chain` | ✅ LLM | ~53s |
| 8 | `/api/v2/pipeline/step/strategy-generation` | ✅ LLM | ~12s |
| 9 | `/api/v2/pipeline/step/risk-control` | ✅ LLM | ~15s |
| 10 | `/api/v2/pipeline/step/generate-report` | ❌ 本地 | <100ms |

### CMD 分步测试

```cmd
REM 步骤1：创建任务
curl -X POST "http://localhost:8000/api/v2/pipeline/task/create" ^
  -H "Content-Type: application/json" ^
  -d "{\"target_type\":\"主题\",\"keyword\":\"今天a股怎么跳水了\",\"time_range\":\"近7天\",\"analysis_depth\":\"标准版\"}"

REM 记录返回的 task_id，例如：a1b2c3d4

REM 步骤2：关键词语义分析（LLM）
curl -X POST "http://localhost:8000/api/v2/pipeline/step/keyword-analysis" ^
  -H "Content-Type: application/json" ^
  -d "{\"task_id\":\"YOUR_TASK_ID\",\"keyword\":\"今天a股怎么跳水了\"}"

REM 步骤3：新闻数据检索
curl -X POST "http://localhost:8000/api/v2/pipeline/step/news-retrieval" ^
  -H "Content-Type: application/json" ^
  -d "{\"task_id\":\"YOUR_TASK_ID\",\"step_name\":\"news_retrieval\",\"input_data\":{}}"

REM 步骤4：事件分类识别（LLM）
curl -X POST "http://localhost:8000/api/v2/pipeline/step/event-classification" ^
  -H "Content-Type: application/json" ^
  -d "{\"task_id\":\"YOUR_TASK_ID\",\"step_name\":\"event_classification\",\"input_data\":{}}"

REM 步骤5：情绪量化分析（LLM）
curl -X POST "http://localhost:8000/api/v2/pipeline/step/sentiment-analysis" ^
  -H "Content-Type: application/json" ^
  -d "{\"task_id\":\"YOUR_TASK_ID\",\"step_name\":\"sentiment_analysis\",\"input_data\":{}}"

REM 步骤6：基本面影响推演（LLM）
curl -X POST "http://localhost:8000/api/v2/pipeline/step/fundamental-impact" ^
  -H "Content-Type: application/json" ^
  -d "{\"task_id\":\"YOUR_TASK_ID\",\"step_name\":\"fundamental_impact\",\"input_data\":{}}"

REM 步骤7：产业链传导分析（LLM，可与步骤6并行）
curl -X POST "http://localhost:8000/api/v2/pipeline/step/industry-chain" ^
  -H "Content-Type: application/json" ^
  -d "{\"task_id\":\"YOUR_TASK_ID\",\"step_name\":\"industry_chain\",\"input_data\":{}}"

REM 步骤8：策略生成（LLM）
curl -X POST "http://localhost:8000/api/v2/pipeline/step/strategy-generation" ^
  -H "Content-Type: application/json" ^
  -d "{\"task_id\":\"YOUR_TASK_ID\",\"step_name\":\"strategy_generation\",\"input_data\":{}}"

REM 步骤9：风控校验（LLM）
curl -X POST "http://localhost:8000/api/v2/pipeline/step/risk-control" ^
  -H "Content-Type: application/json" ^
  -d "{\"task_id\":\"YOUR_TASK_ID\",\"step_name\":\"risk_control\",\"input_data\":{}}"

REM 步骤10：生成研究报告
curl -X POST "http://localhost:8000/api/v2/pipeline/step/generate-report" ^
  -H "Content-Type: application/json" ^
  -d "{\"task_id\":\"YOUR_TASK_ID\",\"step_name\":\"generate_report\",\"input_data\":{}}"
```

### 任务管理接口

```cmd
REM 查询任务状态
curl "http://localhost:8000/api/v2/pipeline/task/YOUR_TASK_ID"

REM 获取最终报告
curl "http://localhost:8000/api/v2/pipeline/task/YOUR_TASK_ID/report"

REM 重置任务（清除进度，可重新执行）
curl -X POST "http://localhost:8000/api/v2/pipeline/task/YOUR_TASK_ID/reset"

REM 删除任务
curl -X DELETE "http://localhost:8000/api/v2/pipeline/task/YOUR_TASK_ID"

REM 获取步骤信息
curl "http://localhost:8000/api/v2/pipeline/steps/info"
```

### 自动化测试脚本

```cmd
cd /d D:\lianghuatouzi\yuqing0309\news-api-service\tests
python test_pipeline_api.py
```

---

## Phase 4 (v2) 测试流程（推荐）

Phase4 采用「采集→本地存储→分析」解耦架构，测试分三步：

### 步骤1：添加采集标的 + 首次采集

```cmd
REM 添加标的到采集列表
curl -X POST "http://localhost:8000/api/v2/news-collect/add-symbol" ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"600000.SH\",\"name\":\"浦发银行\"}"

REM 执行首次采集（同步，约2-3分钟）
curl -X POST "http://localhost:8000/api/v2/news-collect/run-symbol" ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"600000.SH\",\"name\":\"浦发银行\",\"hours\":72}"

REM 查看采集状态
curl "http://localhost:8000/api/v2/news-collect/status"
```

### 步骤2：运行全链路分析

```cmd
REM 快捷分析（约7分钟）
curl -X POST "http://localhost:8000/api/v2/analysis/quick" ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"600000.SH\",\"name\":\"浦发银行\"}"
```

### 步骤3：自动化测试脚本（一键验证全部接口）

```cmd
cd /d D:\lianghuatouzi\yuqing0309\news-api-service\tests
python test_v2_api.py
```

`test_v2_api.py` 自动验证以下接口：

| # | 接口 | 说明 |
|---|------|------|
| 1 | `GET /health` | 健康检查 |
| 2 | `GET /` | 服务信息 |
| 3 | `GET /api/v2/analysis/system-info` | 系统架构（10个Agent） |
| 4 | `GET /internal/debug/config` | LLM 配置检查 |
| 5 | `GET /internal/debug/llm?ping=false` | LLM 连接状态 |
| 6 | `POST /api/v2/analysis/news-only` | 本地舆情读取 |
| 7 | `POST /api/v2/analysis/quick` | **全链路分析**（耗时最长） |

---

## Phase 4 (v2) 采集管理接口单独测试

```cmd
REM 添加采集标的
curl -X POST "http://localhost:8000/api/v2/news-collect/add-symbol" ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"600519.SH\",\"name\":\"贵州茅台\"}"

REM 移除采集标的
curl -X POST "http://localhost:8000/api/v2/news-collect/remove-symbol" ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"600519.SH\"}"

REM 立即全量采集（异步后台执行）
curl -X POST "http://localhost:8000/api/v2/news-collect/run-now"

REM 立即采集指定标的（同步等待）
curl -X POST "http://localhost:8000/api/v2/news-collect/run-symbol" ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"600000.SH\",\"name\":\"浦发银行\",\"hours\":48}"

REM 查看采集状态
curl "http://localhost:8000/api/v2/news-collect/status"

REM 修改采集间隔为60分钟
curl -X PUT "http://localhost:8000/api/v2/news-collect/settings" ^
  -H "Content-Type: application/json" ^
  -d "{\"interval_minutes\":60}"
```

---

## Phase 4 (v2) 全链路分析接口详细测试

```cmd
REM 全链路一键分析（完整参数）
curl -X POST "http://localhost:8000/api/v2/analysis/full-link" ^
  -H "Content-Type: application/json" ^
  -d "{\"target_type\":\"个股\",\"target_code\":[\"600000.SH\"],\"target_name\":[\"浦发银行\"],\"time_range\":\"近7天\",\"analysis_depth\":\"标准版\"}"

REM 快捷分析（最简参数）
curl -X POST "http://localhost:8000/api/v2/analysis/quick" ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"600000.SH\",\"name\":\"浦发银行\"}"

REM 快捷分析（指定时间范围）
curl -X POST "http://localhost:8000/api/v2/analysis/quick" ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"600000.SH\",\"name\":\"浦发银行\",\"start_date\":\"2026-03-04\",\"end_date\":\"2026-03-11\",\"analysis_depth\":\"标准版\"}"

REM 仅读取本地舆情（不触发分析，毫秒级）
curl -X POST "http://localhost:8000/api/v2/analysis/news-only" ^
  -H "Content-Type: application/json" ^
  -d "{\"symbol\":\"600000.SH\",\"name\":\"浦发银行\"}"

REM 系统架构信息
curl "http://localhost:8000/api/v2/analysis/system-info"
```

---

## v1 旧版接口测试流程（向后兼容）

> v1 接口仍可用，但建议迁移至 v2。v1 四个阶段必须按顺序串行调用。

```cmd
cd /d D:\lianghuatouzi\yuqing0309\news-api-service\tests

REM 阶段1：舆情结构化
curl -X POST "http://localhost:8000/api/news/analyze" ^
  -H "Content-Type: application/json" -d @test_news.json -o news_result.json

REM 阶段2：基本面分析
curl -X POST "http://localhost:8000/api/research/analyze" ^
  -H "Content-Type: application/json" -d @test_research.json -o research_result.json

REM 阶段3：用 Python 组装请求 + 信号验证
python -c "import json; n=json.load(open('news_result.json',encoding='utf-8')); r=json.load(open('research_result.json',encoding='utf-8')); body={'symbol':'600519.SH','name':'贵州茅台','news_result':n['result'],'research_result':r['result']}; json.dump(body,open('test_signal.json','w',encoding='utf-8'),ensure_ascii=False)"
curl -X POST "http://localhost:8000/api/signal/validate" ^
  -H "Content-Type: application/json" -d @test_signal.json -o signal_result.json

REM 阶段4：用 Python 组装请求 + 策略生成
python -c "import json; s=json.load(open('signal_result.json',encoding='utf-8')); body={'symbol':'600519.SH','name':'贵州茅台','signal_result':s['result'],'risk_preference':'稳健','investment_horizon':'中线','max_position_pct':30}; json.dump(body,open('test_strategy.json','w',encoding='utf-8'),ensure_ascii=False)"
curl -X POST "http://localhost:8000/api/strategy/generate" ^
  -H "Content-Type: application/json" -d @test_strategy.json -o strategy_result.json

REM 查看最终策略结果
type strategy_result.json
```

---

## 调试接口

```cmd
REM 查看 LLM 配置（不触发调用）
curl "http://localhost:8000/internal/debug/config"

REM 查看 LLM 状态
curl "http://localhost:8000/internal/debug/llm?ping=false"

REM 查看所有 Agent 状态
curl "http://localhost:8000/internal/debug/agents"

REM 服务开关
curl "http://localhost:8000/api/service/switch"
curl -X PUT "http://localhost:8000/api/service/switch" ^
  -H "Content-Type: application/json" -d "{\"enabled\":true}"
```

---

## 预期耗时参考

| 操作 | 预估耗时 | LLM 调用次数 |
|------|----------|-------------|
| 首次采集（单标的72h） | 2-3 min | 0 |
| 本地舆情读取 (news-only) | <100ms | 0 |
| 全链路分析 (quick/full-link) | 5-8 min | ~8 |
| 分步调用 - 创建任务 | <10ms | 0 |
| 分步调用 - 关键词分析 | ~2s | 1 |
| 分步调用 - 新闻检索 | <100ms | 0 |
| 分步调用 - 事件分类 | ~96s | 1 |
| 分步调用 - 情绪分析 | ~91s | 1 |
| 分步调用 - 基本面影响 | ~127s | 1 |
| 分步调用 - 产业链分析 | ~53s | 1 |
| 分步调用 - 策略生成 | ~12s | 1 |
| 分步调用 - 风控校验 | ~15s | 1 |
| 分步调用 - 生成报告 | <100ms | 0 |
| v1 阶段1 舆情分析 | 1-2 min | 1 |
| v1 阶段2 基本面分析 | 10-30s | 0 |
| v1 阶段3 信号验证 | 10-30s | 0 |
| v1 阶段4 策略生成 | 10-30s | 0 |

---

## 测试页面文件位置

| 文件 | 路径 | 访问地址 |
|------|------|----------|
| 分步调用测试 | `app/static/pipeline_test.html` | `/static/pipeline_test.html` |
| 任务状态管理 | `app/static/task_manager.html` | `/static/task_manager.html` |
| 全链路分析 | `app/static/analysis_test.html` | `/static/analysis_test.html` |
