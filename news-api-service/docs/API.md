# 机构级金融舆情分析系统 API 文档 (v4.0)

Phase 4 精细化多智能体全链路协同引擎。

---

## 目录

- [1. 概述](#1-概述)
- [2. 通用说明](#2-通用说明)
- [Phase 4 核心接口](#phase-4-核心接口)
  - [P1. 全链路一键分析（核心）](#p1-全链路一键分析核心)
  - [P2. 快捷分析](#p2-快捷分析)
  - [P3. 仅舆情采集](#p3-仅舆情采集)
  - [P4. 反馈优化](#p4-反馈优化)
  - [P5. 系统架构信息](#p5-系统架构信息)
  - [P6. CMD 调用示例](#p6-cmd-调用示例)
- [基础数据接口（保留）](#基础数据接口保留)
  - [3. 抓取新闻（排重）](#3-抓取新闻排重)
  - [3.5 开启新闻自动抓取（业务接口）](#35-开启新闻自动抓取业务接口)
  - [3.6 清理过期新闻数据](#36-清理过期新闻数据)
  - [4. 查询新闻列表](#4-查询新闻列表)
  - [5. 获取支持的新闻来源](#5-获取支持的新闻来源)
  - [6. 获取抓取记录（上次结束时间）](#6-获取抓取记录上次结束时间)
  - [7. 服务开关（开启/关闭）](#7-服务开关开启关闭)
  - [8. 定时服务（内部接口）](#8-定时服务内部接口)
  - [9. 健康检查](#9-健康检查)
  - [10. API 调用示例汇总](#10-api-调用示例汇总)
  - [11. LLM 语义搜索新闻快讯](#11-llm-语义搜索新闻快讯)
- [旧版分析接口（v1，向后兼容）](#旧版分析接口v1向后兼容)
  - [12. 舆情信息炼化与结构化解析](#12-舆情信息炼化与结构化解析)
  - [13. 多维度金融数据与基本面分析](#13-多维度金融数据与基本面分析)
  - [14. 三维度交叉验证与信号过滤](#14-三维度交叉验证与信号过滤)
  - [15. 交易策略生成与参数精细化](#15-交易策略生成与参数精细化)

---

## 1. 概述

| 项目 | 说明 |
|------|------|
| 服务名称 | 机构级金融舆情分析系统 |
| 版本 | v4.0 — Phase 4 精细化多智能体全链路协同引擎 |
| 默认地址 | `http://localhost:8000` |
| 交互方式 | REST JSON |
| 数据存储 | SQLite + LanceDB (向量库) |
| 核心架构 | 1 中枢调度 + 7 核心业务 + 2 支撑保障 = 10 个单一职责智能体 |
| 调度框架 | LangGraph StateGraph |
| LLM 支持 | 智谱GLM / DeepSeek / OpenAI |

### 系统架构

```
用户请求 → OrchestratorAgent（中枢调度）
  → NewsRetrievalAgent（舆情采集） → [合规校验]
  → EventClassificationAgent（事件分类） → [合规校验]
  → SentimentAnalysisAgent（情绪量化） → [合规校验]
  → FundamentalImpactAgent ‖ IndustryChainAgent（并行深度分析） → [合规校验]
  → StrategyGenerationAgent（策略生成） → [合规校验]
  → RiskControlAgent（风控校验） → [合规校验]
  → 最终投研报告
```

---

## Phase 4 核心接口

### P1. 全链路一键分析（核心）

| 项目 | 值 |
|------|-----|
| 路径 | `POST /api/v2/analysis/full-link` |
| 说明 | 输入标的/行业/主题或自然语言 keyword，自动执行完整的全链路流程（同步阻塞返回完整报告） |
| 耗时 | 30-180 秒（取决于数据量与分析深度） |

#### 请求 Body

```json
{
  "target_type": "个股",
  "target_code": ["600000.SH"],
  "target_name": ["浦发银行"],
  "keyword": "",
  "time_range": "近7天",
  "custom_time_start": "",
  "custom_time_end": "",
  "analysis_depth": "标准版",
  "user_custom_rules": {}
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| target_type | string | 否 | 个股/行业/主题/全市场，默认"个股" |
| target_code | string[] | 条件 | 标的代码列表；与 `target_name` / `keyword` 至少填一项 |
| target_name | string[] | 条件 | 标的/行业/主题名称；与 `target_code` / `keyword` 至少填一项 |
| keyword | string | 条件 | 自然语言关键词：公司名/行业/主题/事件描述；与 `target_code` / `target_name` 至少填一项 |
| time_range | string | 否 | 近24小时/近7天/近30天/自定义 |
| custom_time_start | string | 否 | 自定义开始时间 |
| custom_time_end | string | 否 | 自定义结束时间 |
| analysis_depth | string | 否 | 基础版/标准版/深度版 |
| user_custom_rules | object | 否 | 自定义规则/阈值 |

#### 响应

```json
{
  "success": true,
  "elapsed_ms": 85000,
  "report": {
    "task_base_info": { ... },
    "news_summary": { "news_total_count": 15, ... },
    "event_classification_result": { "core_news_list": [...], ... },
    "sentiment_analysis_result": { "target_sentiment_index": { "index": 72.5 }, ... },
    "fundamental_impact_report": { "impact_certainty_rating": "中确定性", ... },
    "industry_chain_analysis_result": { "benefit_damage_target_list": [...], ... },
    "strategy_suggestion": { "core_strategy_logic": "...", ... },
    "risk_control_rules": { "strategy_risk_level": "中风险", ... },
    "compliance_disclaimer": "【免责声明】...",
    "full_link_log": { "status": "已完成", ... }
  }
}
```

---

### P2. 快捷分析

| 项目 | 值 |
|------|-----|
| 路径 | `POST /api/v2/analysis/quick` |
| 说明 | 简化版入口，兼容旧接口调用风格 |

#### 请求 Body

```json
{
  "symbol": "600000.SH",
  "name": "浦发银行",
  "start_date": "2026-03-01",
  "end_date": "2026-03-11",
  "analysis_depth": "标准版"
}
```

---

### P3. 仅舆情采集

| 项目 | 值 |
|------|-----|
| 路径 | `POST /api/v2/analysis/news-only` |
| 说明 | 仅执行 NewsRetrievalAgent，用于调试数据采集质量 |

请求 Body 同 P2（symbol + name + dates）。

---

### P4. 反馈优化

| 项目 | 值 |
|------|-----|
| 路径 | `POST /api/v2/analysis/feedback` |
| 说明 | 事件结束后的复盘优化 |

#### 请求 Body

```json
{
  "task_id": "历史任务ID",
  "history_report": { "sentiment_analysis_result": {}, ... },
  "actual_result": { "price_change_pct": 5.3, "event_progress": "业绩兑现" }
}
```

---

### P5. 系统架构信息

| 项目 | 值 |
|------|-----|
| 路径 | `GET /api/v2/analysis/system-info` |
| 说明 | 返回系统架构、智能体列表、执行流程 |

---

### P6. 统一入口：异步全链路分析 + 进度查询

#### P6.1 创建任务

| 项目 | 值 |
|------|-----|
| 路径 | `POST /api/v2/analysis/entry` |
| 说明 | 推荐入口：支持 keyword / target_code / target_name，多形式语义查询，立即返回 task_id，后续通过 status 接口查看分步进度与结果 |

**请求 Body 示例：**

```json
{
  "keyword": "浦发银行",
  "target_type": "个股",
  "target_code": [],
  "target_name": [],
  "time_range": "近7天",
  "custom_time_start": "",
  "custom_time_end": "",
  "analysis_depth": "标准版",
  "user_custom_rules": {}
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 条件 | 自然语言关键词：公司名/行业/主题/事件描述；与 `target_code` / `target_name` 至少填一项 |
| target_type | string | 否 | 个股/行业/主题/全市场，默认"个股" |
| target_code | string[] | 条件 | 标的代码列表，如 `["600000.SH"]`；与 `target_name` / `keyword` 至少填一项 |
| target_name | string[] | 条件 | 标的/行业/主题名称，如 `["浦发银行"]`；与 `target_code` / `keyword` 至少填一项 |
| time_range | string | 否 | 近24小时/近7天/近30天/自定义 |
| custom_time_start | string | 否 | 自定义开始时间 |
| custom_time_end | string | 否 | 自定义结束时间 |
| analysis_depth | string | 否 | 基础版/标准版/深度版 |
| user_custom_rules | object | 否 | 自定义规则/阈值 |

**响应：**

```json
{
  "success": true,
  "task_id": "ab12cd34",
  "status": "PENDING"
}
```

#### P6.2 查询任务状态

| 项目 | 值 |
|------|-----|
| 路径 | `GET /api/v2/analysis/status/{task_id}` |
| 说明 | 轮询该接口，查看任务当前进度、各节点耗时与最终结果是否就绪 |

**响应示例：**

```json
{
  "success": true,
  "task_id": "ab12cd34",
  "overall_status": "RUNNING",
  "current_step": "sentiment_analysis",
  "progress": {
    "total_steps": 7,
    "finished_steps": 3
  },
  "timeline": [
    {
      "step": "orchestrator_init",
      "status": "running",
      "message": "全链路任务已初始化，准备执行。",
      "timestamp": 1731400000.123,
      "duration_ms": null
    },
    {
      "step": "full_link_finished",
      "status": "success",
      "message": "全链路分析已完成。",
      "timestamp": 1731400123.456,
      "duration_ms": null
    }
  ],
  "final_report_ready": false,
  "error": null
}
```

> 说明：`overall_status` 取值包括 `PENDING` / `RUNNING` / `DONE` / `ERROR`，前端可据此控制轮询与展示；`timeline` 中的每个 `step` 包含人类可读的 `message` 与可选的 `duration_ms`/`timestamp`，用于向用户展示“当前在想什么、做什么”。

---

### P7. CMD 调用示例

**全链路一键分析**：

```cmd
curl -X POST "http://localhost:8000/api/v2/analysis/full-link" -H "Content-Type: application/json" -d "{\"target_type\":\"个股\",\"target_code\":[\"\"],\"target_name\":[\"\"],\"keyword\":\"今天a股怎么跳水了\",\"time_range\":\"近7天\",\"analysis_depth\":\"标准版\"}"
```

**快捷分析**：

```cmd
curl -X POST "http://localhost:8000/api/v2/analysis/quick" -H "Content-Type: application/json" -d "{\"symbol\":\"600000.SH\",\"name\":\"浦发银行\",\"start_date\":\"2026-03-01\",\"end_date\":\"2026-03-11\"}"
```

**仅舆情采集**：

```cmd
curl -X POST "http://localhost:8000/api/v2/analysis/news-only" -H "Content-Type: application/json" -d "{\"symbol\":\"600000.SH\",\"name\":\"浦发银行\"}"
```

**系统信息**：

```cmd
curl "http://localhost:8000/api/v2/analysis/system-info"
```

**调试-智能体健康检查**：

```cmd
curl "http://localhost:8000/internal/debug/agents"
```

**调试-LLM连通性**：

```cmd
curl "http://localhost:8000/internal/debug/llm?ping=true"

**统一入口（keyword 模式）+ 进度查询示例**：

```cmd
REM 1) 创建任务
curl -X POST "http://localhost:8000/api/v2/analysis/entry" ^
  -H "Content-Type: application/json" ^
  -d "{\"keyword\":\"浦发银行\",\"time_range\":\"近7天\",\"analysis_depth\":\"标准版\"}"

REM 2) 查询任务状态（将 {task_id} 替换为上一步返回的 task_id）
curl "http://localhost:8000/api/v2/analysis/status/{task_id}"
```
```

**调试-配置检查**：

```cmd
curl "http://localhost:8000/internal/debug/config"
```

---

## 基础数据接口（保留）

---

## 2. 通用说明

- **Base URL**：`http://localhost:8000`（部署时替换为实际域名或 IP）。
- **Content-Type**：请求体为 JSON 时使用 `application/json`；查询接口多为 GET，参数在 Query。
- **响应**：成功时业务字段包含 `success: true`；列表类接口通常包含 `data` 数组。
- **后端管理页**：提供一个不进入 OpenAPI 文档的管理页面，用于查看定时任务运行情况与数据库明细：`/admin`。
- **外部依赖**：
  - 抓取新闻需配置 `TUSHARE_TOKEN`。
  - 使用 LLM 语义搜索需配置 `DEEPSEEK_API_KEY`（以及可选的 `DEEPSEEK_MODEL`，默认 `deepseek-chat`）。

---

## 3. 抓取新闻（排重）

触发从 Tushare 拉取新闻并写入本地 `newsdata` 数据库。**排重原则**：先查该来源的「上次抓取结束时间」，本次若不传开始时间则从该时间之后开始抓，避免重复时间段。

### 3.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/api/news/fetch` |
| 方法 | `POST` |
| 说明 | 抓取 Tushare 新闻并入库，默认 24 小时内、按上次结束时间排重 |

### 3.2 请求参数（Query）

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `start_date` | string | 否 | 开始时间，格式：`2018-11-20 09:00:00`。不传则使用「上次结束时间」或「当前时间 - hours」 |
| `end_date` | string | 否 | 结束时间，格式：`2018-11-20 22:00:00`。不传则为当前时间 |
| `hours` | integer | 否 | 当未传 `start_date` 时，默认抓取最近多少小时；默认 `24`，范围 1~168 |
| `sources` | string | 否 | 来源，多个用英文逗号分隔，如 `sina,cls`。不传则抓取全部来源 |

### 3.3 响应 body

```json
{
  "success": true,
  "results": [
    {
      "src": "sina",
      "fetched": 120,
      "inserted": 118,
      "start_date": "2025-03-09 10:00:00",
      "end_date": "2025-03-10 10:00:00"
    },
    {
      "src": "cls",
      "fetched": 0,
      "inserted": 0,
      "start_date": "2025-03-10 09:00:00",
      "end_date": "2025-03-10 10:00:00",
      "skip_reason": "last_fetch_end >= end_date, no new range"
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `results[].src` | 来源标识 |
| `results[].fetched` | 当次从 Tushare 拉取条数 |
| `results[].inserted` | 实际写入本地库条数（去重后） |
| `results[].start_date` / `end_date` | 本次请求使用的时间范围 |
| `results[].skip_reason` | 若因排重跳过抓取，会给出原因 |

### 3.4 调用示例

**cURL（默认 24 小时、全部来源）：**

```bash
curl -X POST "http://localhost:8000/api/news/fetch"
```

**cURL（指定最近 12 小时）：**

```bash
curl -X POST "http://localhost:8000/api/news/fetch?hours=12"
```

**cURL（指定时间范围与来源）：**

```bash
curl -X POST "http://localhost:8000/api/news/fetch?start_date=2025-03-09%2000:00:00&end_date=2025-03-10%2000:00:00&sources=sina,cls"
```

**Python（requests）：**

```python
import requests

# 默认：24 小时内、全部来源
r = requests.post("http://localhost:8000/api/news/fetch")
print(r.json())

# 仅抓 sina、cls，最近 12 小时
r = requests.post(
    "http://localhost:8000/api/news/fetch",
    params={"hours": 12, "sources": "sina,cls"},
)
print(r.json())
```

### 3.5 开启新闻自动抓取（业务接口）

通过**业务接口**一键将新闻抓取设为定时执行（默认每 5 分钟调用一次抓取逻辑），无需直接调用内部定时配置接口。

| 项目 | 值 |
|------|-----|
| 路径 | `/api/news/schedule` |
| 方法 | `POST` |
| Content-Type | `application/json`（可选） |

**请求 body（可选）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `interval_minutes` | integer | 否 | 抓取间隔（分钟），默认 5，范围 1～1440 |

不传 body 时按默认每 5 分钟执行。

**响应示例：**

```json
{
  "success": true,
  "message": "已开启新闻自动抓取，每 5 分钟执行一次",
  "enabled": true,
  "interval_minutes": 5,
  "fetch_next_run_time": "2025-03-10T10:05:00"
}
```

**调用示例：**

```bash
# 默认每 5 分钟抓取
curl -X POST "http://localhost:8000/api/news/schedule"

# 指定每 10 分钟抓取
curl -X POST "http://localhost:8000/api/news/schedule" -H "Content-Type: application/json" -d "{\"interval_minutes\": 10}"
```

```python
import requests
# 开启每 5 分钟自动抓取
r = requests.post("http://localhost:8000/api/news/schedule")
print(r.json())
```

### 3.6 清理过期新闻数据

删除本地数据库中过期的新闻，仅保留最近 N 小时的数据，可用于控制数据库大小。

#### 3.6.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/api/news/cleanup` |
| 方法 | `POST` |
| 说明 | 删除早于指定小时数的新闻数据，默认清理 48 小时之前的数据 |

#### 3.6.2 请求参数（Query）

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `hours` | integer | 否 | 保留最近多少小时的数据，默认 `48`，范围 `1`～`720` |

#### 3.6.3 响应 body

```json
{
  "success": true,
  "deleted_count": 123,
  "kept_hours": 48
}
```

> 实际字段以实现为准，一般会包含删除条数等信息。

#### 3.6.4 调用示例

```bash
# 使用默认 48 小时
curl -X POST "http://localhost:8000/api/news/cleanup"

# 仅保留最近 72 小时
curl -X POST "http://localhost:8000/api/news/cleanup?hours=72"
```

---

## 4. 查询新闻列表

从本地 `newsdata` 数据库中分页查询已抓取的新闻。

### 4.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/api/news/list` |
| 方法 | `GET` |
| 说明 | 分页查询本地新闻，可按来源、时间筛选 |

### 4.2 请求参数（Query）

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `src` | string | 否 | 来源筛选，如 `sina`、`cls` |
| `start_datetime` | string | 否 | 开始时间，格式：`2018-11-20 09:00:00` |
| `end_datetime` | string | 否 | 结束时间，格式：`2018-11-20 22:00:00` |
| `limit` | integer | 否 | 每页条数，默认 50，最大 500 |
| `offset` | integer | 否 | 偏移量，默认 0 |

### 4.3 响应 body

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "src": "sina",
      "datetime": "2025-03-10 09:30:00",
      "title": "某财经快讯标题",
      "content": "新闻内容摘要",
      "channels": "财经",
      "created_at": "2025-03-10 10:00:00"
    }
  ],
  "limit": 50,
  "offset": 0
}
```

### 4.4 调用示例

**cURL：**

```bash
curl "http://localhost:8000/api/news/list?limit=10&offset=0"
curl "http://localhost:8000/api/news/list?src=sina&start_datetime=2025-03-09%2000:00:00&end_datetime=2025-03-10%2023:59:59"
```

**Python：**

```python
import requests

r = requests.get(
    "http://localhost:8000/api/news/list",
    params={"src": "cls", "limit": 20, "offset": 0},
)
print(r.json())
```

---

## 5. 获取支持的新闻来源

返回可用的 Tushare 新闻来源列表，用于 `sources` 参数取值。

### 5.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/api/news/sources` |
| 方法 | `GET` |

### 5.2 响应 body

```json
{
  "success": true,
  "sources": [
    { "id": "sina", "name": "新浪财经" },
    { "id": "wallstreetcn", "name": "华尔街见闻" },
    { "id": "10jqka", "name": "同花顺" },
    { "id": "eastmoney", "name": "东方财富" },
    { "id": "yuncaijing", "name": "云财经" },
    { "id": "fenghuang", "name": "凤凰新闻" },
    { "id": "jinrongjie", "name": "金融界" },
    { "id": "cls", "name": "财联社" },
    { "id": "yicai", "name": "第一财经" }
  ]
}
```

### 5.3 调用示例

```bash
curl "http://localhost:8000/api/news/sources"
```

---

## 6. 获取抓取记录（上次结束时间）

返回各来源的「上次抓取结束时间」，用于理解排重逻辑或排查问题。

### 6.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/api/news/fetch-log` |
| 方法 | `GET` |
| 说明 | 各来源的 last_end_datetime 即下次抓取时的起始时间参考 |

### 6.2 响应 body

```json
{
  "success": true,
  "data": [
    {
      "src": "sina",
      "last_end_datetime": "2025-03-10 10:00:00",
      "updated_at": "2025-03-10 10:01:00"
    }
  ]
}
```

### 6.3 调用示例

```bash
curl "http://localhost:8000/api/news/fetch-log"
```

---

## 7. 服务开关（开启/关闭）

通过开关可临时关闭「抓取」能力：关闭后，`POST /api/news/fetch` 会返回 503，查询、来源、fetch-log 等只读接口不受影响。状态会持久化到项目根目录下的 `service_switch.json`，重启服务后仍生效。

### 7.1 获取开关状态

| 项目 | 值 |
|------|-----|
| 路径 | `/api/service/switch` |
| 方法 | `GET` |

**响应示例：**

```json
{ "enabled": true }
```

### 7.2 设置开关

| 项目 | 值 |
|------|-----|
| 路径 | `/api/service/switch` |
| 方法 | `PUT` |
| Content-Type | `application/json` |

**请求 body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `enabled` | boolean | 是 | `true` 开启，`false` 关闭 |

**响应示例：**

```json
{ "enabled": false }
```

**调用示例：**

```bash
# 获取状态
curl "http://localhost:8000/api/service/switch"

# 关闭服务
curl -X PUT "http://localhost:8000/api/service/switch" -H "Content-Type: application/json" -d "{\"enabled\": false}"

# 开启服务
curl -X PUT "http://localhost:8000/api/service/switch" -H "Content-Type: application/json" -d "{\"enabled\": true}"
```

```python
import requests

# 关闭
r = requests.put("http://localhost:8000/api/service/switch", json={"enabled": False})
print(r.json())  # {"enabled": False}

# 开启
r = requests.put("http://localhost:8000/api/service/switch", json={"enabled": True})
```

---

## 8. 定时服务（内部接口）

以下为**内部接口**，不在 Swagger/ReDoc 中展示，仅运维或内部系统按需调用。路径统一为 `/internal/scheduler/`。

定时服务包含：**内置新闻抓取**（使用全局间隔）、**已注册的 URL 任务**（每任务可单独配置间隔）。配置持久化在 `scheduler_config.json`，重启后生效。

### 8.1 获取定时服务状态

| 项目 | 值 |
|------|-----|
| 路径 | `/internal/scheduler/status` |
| 方法 | `GET` |

**响应字段说明：**

| 字段 | 说明 |
|------|------|
| `enabled` | 定时服务总开关 |
| `fetch_interval_minutes` | 内置抓取任务的间隔（分钟） |
| `fetch_next_run_time` | 内置抓取下次执行时间（ISO） |
| `registered_tasks` | 已注册的 URL 任务列表，每项含 `interval_minutes`、`next_run_time` |

**响应示例：**

```json
{
  "enabled": true,
  "fetch_interval_minutes": 5,
  "fetch_next_run_time": "2025-03-10T10:05:00",
  "registered_tasks": [
    {
      "id": "a1b2c3d4",
      "name": "自定义任务",
      "url": "http://localhost:8000/health",
      "method": "GET",
      "interval_minutes": 10,
      "next_run_time": "2025-03-10T10:10:00"
    }
  ]
}
```

### 8.2 定时服务开关

| 项目 | 值 |
|------|-----|
| 路径 | `/internal/scheduler/switch` |
| 方法 | `PUT` |
| Content-Type | `application/json` |

**请求 body：** `{"enabled": true}` 或 `{"enabled": false}`

### 8.3 设置抓取任务定时间隔

仅影响**内置新闻抓取**的间隔，不影响已注册 URL 任务的各自间隔。

| 项目 | 值 |
|------|-----|
| 路径 | `/internal/scheduler/interval` |
| 方法 | `PUT` |
| Content-Type | `application/json` |

**请求 body：** `{"interval_minutes": 5}`，范围 1～1440（分钟）。

### 8.4 注册定时调用的接口（可配置该任务间隔）

每个 URL 任务有**独立的定时间隔**，注册时指定 `interval_minutes`，不传则默认 5 分钟。

| 项目 | 值 |
|------|-----|
| 路径 | `/internal/scheduler/tasks` |
| 方法 | `POST` |
| Content-Type | `application/json` |

**请求 body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 任务名称，便于识别 |
| `url` | string | 是 | 定时请求的完整 URL |
| `method` | string | 否 | 请求方法，默认 `GET` |
| `interval_minutes` | integer | 否 | 该任务的定时间隔（分钟），默认 5，范围 1～1440 |

**响应示例：** `{"success": true, "task": {"id": "a1b2c3d4", "name": "xxx", "url": "http://...", "method": "GET", "interval_minutes": 10}}`

### 8.5 更新某任务的定时间隔

| 项目 | 值 |
|------|-----|
| 路径 | `/internal/scheduler/tasks/{task_id}` |
| 方法 | `PUT` |
| Content-Type | `application/json` |

**请求 body：** `{"interval_minutes": 10}`，范围 1～1440。

**响应：** `{"success": true, "task": { ... }}` 含更新后的任务（含 `next_run_time`）。

### 8.6 移除已注册的定时接口

| 项目 | 值 |
|------|-----|
| 路径 | `/internal/scheduler/tasks/{task_id}` |
| 方法 | `DELETE` |

**路径参数：** `task_id` 为注册时返回的 `task.id`。

### 8.7 调用示例（内部）

```bash
# 查看状态
curl "http://localhost:8000/internal/scheduler/status"

# 关闭定时
curl -X PUT "http://localhost:8000/internal/scheduler/switch" -H "Content-Type: application/json" -d "{\"enabled\": false}"

# 设置抓取任务为每 10 分钟
curl -X PUT "http://localhost:8000/internal/scheduler/interval" -H "Content-Type: application/json" -d "{\"interval_minutes\": 10}"

# 注册接口并指定该任务每 15 分钟执行
curl -X POST "http://localhost:8000/internal/scheduler/tasks" -H "Content-Type: application/json" -d "{\"name\": \"健康检查\", \"url\": \"http://localhost:8000/health\", \"method\": \"GET\", \"interval_minutes\": 15}"

# 更新某任务的间隔为 30 分钟（替换为实际 task_id）
curl -X PUT "http://localhost:8000/internal/scheduler/tasks/a1b2c3d4" -H "Content-Type: application/json" -d "{\"interval_minutes\": 30}"

# 移除任务
curl -X DELETE "http://localhost:8000/internal/scheduler/tasks/a1b2c3d4"
```

---

## 9. 健康检查

用于探测服务是否存活。

### 9.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/health` |
| 方法 | `GET` |

### 9.2 响应示例

```json
{ "status": "ok" }
```

```bash
curl "http://localhost:8000/health"
```

---

## 10. API 调用示例汇总

| 能力 | 方法 | 路径 | 典型用法 |
|------|------|------|----------|
| 抓取新闻（排重） | POST | `/api/news/fetch` | 不传参即抓 24 小时内全部来源；可传 `hours`、`sources`、`start_date`、`end_date` |
| 开启新闻自动抓取（业务） | POST | `/api/news/schedule` | Body 可选：`{"interval_minutes": 5}`，默认每 5 分钟 |
| 清理过期新闻数据 | POST | `/api/news/cleanup` | Query: `hours`（保留最近 N 小时，默认 48） |
| 查询新闻列表 | GET | `/api/news/list` | 传 `src`、`start_datetime`、`end_datetime`、`limit`、`offset` |
| 新闻来源列表 | GET | `/api/news/sources` | 无参数 |
| 抓取记录 | GET | `/api/news/fetch-log` | 无参数 |
| LLM 语义搜索新闻快讯 | POST | `/api/news/semantic-search` | Body: `{"keyword": "...", "limit": 50, "offset": 0}` |
| 舆情信息炼化与结构化解析 | POST | `/api/news/analyze` | Body: 对单个标的的多条舆情进行结构化事件抽取与情绪量化 |
| 多维度金融数据与基本面分析 | POST | `/api/research/analyze` | Body: 阶段1事件清单 + 标的代码/名称/时间范围，返回财务/行情/交叉验证/估值 |
| 三维度交叉验证与信号过滤 | POST | `/api/signal/validate` | Body: 阶段1 news_result + 阶段2 research_result，返回信号分级与回测报告 |
| 交易策略生成与参数精细化 | POST | `/api/strategy/generate` | Body: 阶段3 signal_result + 风险偏好 + 投资周期 + 仓位上限，返回结构化策略 |
| 服务开关-查询 | GET | `/api/service/switch` | 无参数 |
| 服务开关-设置 | PUT | `/api/service/switch` | Body: `{"enabled": true/false}` |
| 定时服务（内部，不暴露） | GET | `/internal/scheduler/status` | 无参数 |
| 定时服务-开关 | PUT | `/internal/scheduler/switch` | Body: `{"enabled": true/false}` |
| 定时服务-间隔 | PUT | `/internal/scheduler/interval` | Body: `{"interval_minutes": 5}` |
| 定时服务-注册/更新/移除任务 | POST/PUT/DELETE | `/internal/scheduler/tasks[...]` | 见第 8 节 |
| 健康检查 | GET | `/health` | 无参数 |

**快速自测（需先配置 TUSHARE_TOKEN 并启动服务）：**

```bash
# 1. 抓取（默认 24 小时）
curl -X POST "http://localhost:8000/api/news/fetch"

# 2. 看抓取记录
curl "http://localhost:8000/api/news/fetch-log"

# 3. 查本地新闻
curl "http://localhost:8000/api/news/list?limit=5"
```

---

## 11. LLM 语义搜索新闻快讯

基于 Deepseek LLM 的语义检索能力：输入用户自然语言关键词，先由 LLM 提取更聚焦的核心关键词，再在本地新闻库中做模糊匹配，返回最近的相关新闻快讯。

> 使用该能力前，请确保已正确配置 `DEEPSEEK_API_KEY` 环境变量（以及可选的 `DEEPSEEK_MODEL`）。

### 11.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/api/news/semantic-search` |
| 方法 | `POST` |
| Content-Type | `application/json` |

### 11.2 请求 body

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 是 | 原始搜索词或问题描述，例如“今日央行降息影响” |
| `limit` | integer | 否 | 返回条数上限，默认 `50` |
| `offset` | integer | 否 | 偏移量，用于翻页，默认 `0` |

### 11.3 响应 body

```json
{
  "success": true,
  "query": "今日央行降息影响",
  "core_keyword": "央行 降息 影响",
  "limit": 20,
  "offset": 0,
  "count": 3,
  "items": [
    {
      "id": 123,
      "src": "cls",
      "datetime": "2025-03-10 09:30:00",
      "title": "央行宣布下调利率...",
      "content": "央行今日宣布...",
      "channels": "宏观经济",
      "created_at": "2025-03-10 09:31:00"
    }
  ]
}
```

`items` 字段结构与普通 `/api/news/list` 返回的单条新闻结构一致，仅增加了 `query`、`core_keyword` 等字段帮助理解搜索过程。

---

## 12. 舆情信息炼化与结构化解析

基于 Deepseek LLM 的 News Agent 能力：对单个标的的一组舆情文本进行**信源评级、事件抽取、情绪量化与影响评估**，输出结构化事件清单和整体情绪视角。

> 使用该能力前，请确保已正确配置 `DEEPSEEK_API_KEY` 环境变量（以及可选的 `DEEPSEEK_MODEL`，对应 `deepseek_model`）。

### 12.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/api/news/analyze` |
| 方法 | `POST` |
| Content-Type | `application/json` |

### 12.2 请求 body

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 是 | 标的代码，如 `600000.SH` |
| `name` | string | 是 | 标的名称，如 `浦发银行` |
| `start_date` | string | 是 | 舆情分析起始日期，格式自由文本，推荐 `YYYY-MM-DD` |
| `end_date` | string | 是 | 舆情分析结束日期，格式自由文本，推荐 `YYYY-MM-DD` |
| `news_items` | array | 是 | 舆情文本列表，至少一条 |

`news_items` 列表内每项字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 该条舆情在调用方系统内的唯一标识 |
| `source_name` | string | 是 | 信源名称，如 `上交所公告`、`某权威财经媒体`、`XXX社交账号` |
| `published_at` | string | 是 | 舆情发布时间，推荐 ISO 字符串，如 `2026-03-10T09:30:00+08:00` |
| `text` | string | 是 | 舆情正文文本（建议为主要内容，过长时可适度截断） |
| `url` | string | 否 | 原文链接（可选，用于溯源） |

**示例请求：**

```json
{
  "symbol": "600000.SH",
  "name": "浦发银行",
  "start_date": "2026-03-01",
  "end_date": "2026-03-10",
  "news_items": [
    {
      "id": "N1",
      "source_name": "某权威财经媒体",
      "published_at": "2026-03-05T09:30:00+08:00",
      "text": "浦发银行发布最新年度财报，净利润同比增长，多个业务条线表现稳健。",
      "url": "https://example.com/news1"
    },
    {
      "id": "N2",
      "source_name": "某社交媒体匿名账号",
      "published_at": "2026-03-06T14:20:00+08:00",
      "text": "听说浦发银行有些业务线压力比较大，大家自己留意一下，消息未证实。",
      "url": "https://example.com/post1"
    }
  ]
}
```

### 12.3 响应 body

成功时返回结构如下（内容示例为简化版，实际字段更完整）：

```json
{
  "success": true,
  "report_md": "## 一、舆情分析总览\\n- **标的**：浦发银行（600000.SH）...（Markdown 省略）",
  "result": {
    "meta": {
      "module_name": "news_sentiment_agent",
      "version": "0.1.0",
      "run_timestamp": "2026-03-11T10:00:00+08:00",
      "data_sources": ["user_provided_news_texts"]
    },
    "inputs": {
      "symbol": "600000.SH",
      "name": "浦发银行",
      "time_window": {
        "start": "2026-03-01",
        "end": "2026-03-10"
      },
      "news_items": [
        {
          "id": "N1",
          "source_name": "某权威财经媒体",
          "published_at": "2026-03-05T09:30:00+08:00",
          "text": "浦发银行发布最新年度财报...",
          "url": "https://example.com/news1"
        }
      ]
    },
    "events": [
      {
        "event_id": "E1",
        "from_news_ids": ["N1"],
        "event_category": "基本面事件",
        "event_subtype": "财报发布",
        "core_summary": "浦发银行发布年度财报，净利润同比增长。",
        "entity": "浦发银行",
        "occur_time": "2026-03-05",
        "source_level": "A",
        "source_name": "某权威财经媒体",
        "evidence_snippets": ["……原文片段……"],
        "sentiment": "利好",
        "sentiment_score": 7.5,
        "sentiment_rationale": "财报显示利润增长，报道整体用词积极。",
        "impact_scope": "公司级",
        "impact_horizon": "中期（1-3个月）",
        "propagation_path": {
          "current_stage": "发酵期",
          "stages": ["起点：财报发布", "发酵期：媒体解读与机构研报跟进", "高潮期：后续业绩验证", "拐点：实际表现与预期偏离时"],
          "catalysts": ["后续业绩持续超预期", "管理层上调指引"],
          "decay_factors": ["同行竞争加剧", "宏观环境恶化"]
        }
      }
    ],
    "aggregated_view": {
      "overall_sentiment": "偏利好",
      "overall_sentiment_score": 6.5,
      "high_value_signals": [
        {
          "event_id": "E1",
          "reason": "A/S级信源、与公司基本面高度相关。"
        }
      ],
      "high_risk_noise_event_ids": [],
      "watchlist_event_ids": ["E1"]
    },
    "constraints_and_risks": {
      "not_investment_advice": true,
      "capital_guarantee": false,
      "disclaimers": [
        "本结果仅基于用户提供的舆情文本及公开信息，由大模型进行结构化提取和归纳，不构成任何证券投资建议或收益承诺。",
        "舆情本身可能存在偏见、噪音或错误，尤其是低等级信源内容，仅作为风险提示使用。",
        "投资决策需结合财务数据、估值、风险承受能力等多维因素，最终决策责任由用户自行承担。"
      ]
    }
  }
}
```

### 12.4 调用示例

**完整测试请求（5条多信源舆情，CMD 可直接复制运行）：**

先将测试 JSON 写入文件，再用 `curl -d @文件名` 发送（推荐方式，可读性好）：

**步骤1 — 生成测试数据文件 `test_news.json`：**

```json
{
  "symbol": "600519.SH",
  "name": "贵州茅台",
  "start_date": "2026-03-01",
  "end_date": "2026-03-11",
  "news_items": [
    {
      "id": "N1",
      "source_name": "上海证券交易所公告",
      "published_at": "2026-03-03T08:00:00+08:00",
      "text": "贵州茅台酒股份有限公司发布2025年度业绩快报：全年实现营业总收入1738.04亿元，同比增长15.34%；归属于上市公司股东的净利润862.82亿元，同比增长15.38%。公司表示，报告期内高端白酒市场需求稳健，直销渠道占比进一步提升至42%，海外市场收入同比增长28%。",
      "url": "https://example.com/maotai-annual-report"
    },
    {
      "id": "N2",
      "source_name": "财新网",
      "published_at": "2026-03-05T10:15:00+08:00",
      "text": "据财新记者独家获悉，贵州茅台计划于2026年二季度推出新一代高端系列酒产品，定价区间在2000-3000元之间，主要面向年轻高净值消费群体。多位渠道经销商证实已收到相关产品推介通知。分析人士认为，此举有望进一步拓宽茅台的产品矩阵，提升非飞天系列产品的营收占比。",
      "url": "https://example.com/maotai-new-product"
    },
    {
      "id": "N3",
      "source_name": "路透社",
      "published_at": "2026-03-06T14:30:00+08:00",
      "text": "中国国务院办公厅印发《关于进一步促进消费扩容提质的若干意见》，明确提出支持高品质消费品供给，鼓励传统名优品牌创新发展。市场分析人士认为，该政策对高端白酒行业构成长期利好，茅台、五粮液等龙头企业将直接受益。",
      "url": "https://example.com/consumption-policy"
    },
    {
      "id": "N4",
      "source_name": "第一财经",
      "published_at": "2026-03-07T09:00:00+08:00",
      "text": "北向资金连续5个交易日净买入贵州茅台，累计净买入额达45.6亿元，为近三个月最大规模的持续流入。香港多家机构同期上调贵州茅台目标价，高盛将目标价从2100元上调至2350元，维持买入评级。",
      "url": "https://example.com/maotai-northbound"
    },
    {
      "id": "N5",
      "source_name": "雪球用户",
      "published_at": "2026-03-08T20:00:00+08:00",
      "text": "听朋友说茅台要搞股票回购了，金额可能有100亿以上，近期大概率会公告。不知道真假，先建个底仓看看。",
      "url": "https://example.com/xueqiu-rumor"
    }
  ]
}
```

将以上内容保存为 `test_news.json`，然后在 CMD 中运行：

**步骤2 — CMD 调用：**

```cmd
curl -X POST "http://localhost:8000/api/news/analyze" -H "Content-Type: application/json" -d @test_news.json
```

**CMD 单行版本（无需文件，直接粘贴到 CMD 运行）：**

```cmd
curl -X POST "http://localhost:8000/api/news/analyze" -H "Content-Type: application/json" -d "{\"symbol\":\"600519.SH\",\"name\":\"贵州茅台\",\"start_date\":\"2026-03-01\",\"end_date\":\"2026-03-11\",\"news_items\":[{\"id\":\"N1\",\"source_name\":\"上海证券交易所公告\",\"published_at\":\"2026-03-03T08:00:00+08:00\",\"text\":\"贵州茅台酒股份有限公司发布2025年度业绩快报：全年实现营业总收入1738.04亿元，同比增长15.34%；归属于上市公司股东的净利润862.82亿元，同比增长15.38%。公司表示，报告期内高端白酒市场需求稳健，直销渠道占比进一步提升至42%，海外市场收入同比增长28%。\",\"url\":\"https://example.com/maotai-annual-report\"},{\"id\":\"N2\",\"source_name\":\"财新网\",\"published_at\":\"2026-03-05T10:15:00+08:00\",\"text\":\"据财新记者独家获悉，贵州茅台计划于2026年二季度推出新一代高端系列酒产品，定价区间在2000-3000元之间，主要面向年轻高净值消费群体。多位渠道经销商证实已收到相关产品推介通知。分析人士认为，此举有望进一步拓宽茅台的产品矩阵，提升非飞天系列产品的营收占比。\",\"url\":\"https://example.com/maotai-new-product\"},{\"id\":\"N3\",\"source_name\":\"路透社\",\"published_at\":\"2026-03-06T14:30:00+08:00\",\"text\":\"中国国务院办公厅印发《关于进一步促进消费扩容提质的若干意见》，明确提出支持高品质消费品供给，鼓励传统名优品牌创新发展。市场分析人士认为，该政策对高端白酒行业构成长期利好，茅台、五粮液等龙头企业将直接受益。\",\"url\":\"https://example.com/consumption-policy\"},{\"id\":\"N4\",\"source_name\":\"第一财经\",\"published_at\":\"2026-03-07T09:00:00+08:00\",\"text\":\"北向资金连续5个交易日净买入贵州茅台，累计净买入额达45.6亿元，为近三个月最大规模的持续流入。香港多家机构同期上调贵州茅台目标价，高盛将目标价从2100元上调至2350元，维持买入评级。\",\"url\":\"https://example.com/maotai-northbound\"},{\"id\":\"N5\",\"source_name\":\"雪球用户\",\"published_at\":\"2026-03-08T20:00:00+08:00\",\"text\":\"听朋友说茅台要搞股票回购了，金额可能有100亿以上，近期大概率会公告。不知道真假，先建个底仓看看。\",\"url\":\"https://example.com/xueqiu-rumor\"}]}"
```

**测试数据设计说明：**

| 新闻ID | 信源 | 预期信源等级 | 事件类型 | 预期情绪 | 设计目的 |
|--------|------|------------|----------|----------|----------|
| N1 | 上交所公告 | S级 | 基本面事件（财报发布） | 利好(8-9分) | 高权威信源+明确业绩增长，应产出高确定性信号 |
| N2 | 财新网 | A级 | 基本面事件（核心产品变动） | 利好(7-8分) | 权威媒体+新品战略，应产出中/高确定性信号 |
| N3 | 路透社 | A级 | 政策事件（产业扶持政策） | 利好(7分) | 权威外媒+政策利好，测试行业级影响识别 |
| N4 | 第一财经 | A级 | 市场事件（北向资金异动） | 利好(7-8分) | 测试资金面信号，与阶段3资金面验证联动 |
| N5 | 雪球用户 | C/D级 | 传闻 | 应标记为高风险噪音 | 测试低信源过滤机制，不应产出有效信号 |

---

## 13. 多维度金融数据与基本面分析

对应 ValueCell 的 **Research Agent**：基于阶段1的舆情事件清单，**统一使用 Tushare** 获取标的财务、行情、每日指标与股票基本信息，进行舆情-基本面交叉验证、行业与估值分析。

> 依赖：需配置 `TUSHARE_TOKEN`，并安装 `tushare`、`pandas`。数据来源：**仅 Tushare**（日线 daily、每日指标 daily_basic、利润表/资产负债表/现金流量表、股票列表 stock_basic）。不依赖 LLM。

### 13.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/api/research/analyze` |
| 方法 | `POST` |
| Content-Type | `application/json` |

### 13.2 请求 body

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 是 | 标的代码，如 `600000.SH`、`000001.SZ` |
| `name` | string | 是 | 标的名称，如 `浦发银行` |
| `start_date` | string | 是 | 分析起始日期，推荐 `YYYY-MM-DD` |
| `end_date` | string | 是 | 分析结束日期，推荐 `YYYY-MM-DD` |
| `events` | array | 是 | 阶段1输出的结构化事件列表（可来自 `/api/news/analyze` 的 `result.events`） |

`events` 中每项建议包含：`event_id`、`event_category`、`core_summary`、`sentiment`、`impact_scope` 等，以便交叉验证。

**示例请求（与阶段1联动）：**

先调用 `POST /api/news/analyze` 得到 `result.events`，再将该 `events` 与标的、时间范围一并传入：

```json
{
  "symbol": "600000.SH",
  "name": "浦发银行",
  "start_date": "2026-01-01",
  "end_date": "2026-03-10",
  "events": [
    {
      "event_id": "E1",
      "event_category": "基本面事件",
      "event_subtype": "财报发布",
      "core_summary": "浦发银行发布年度财报，净利润同比增长。",
      "sentiment": "利好",
      "impact_scope": "公司级"
    }
  ]
}
```

### 13.3 响应 body

成功时返回：

```json
{
  "success": true,
  "report_md": "## 一、基本面分析总览\n...（Markdown 报告）",
  "result": {
    "meta": {
      "module_name": "research_agent",
      "version": "0.1.0",
      "run_timestamp": "2026-03-11T12:00:00+08:00",
      "data_sources": ["tushare"]
    },
    "inputs": {
      "symbol": "600000.SH",
      "name": "浦发银行",
      "time_window": { "start": "2026-01-01", "end": "2026-03-10" },
      "events_count": 1
    },
    "core_data": {
      "financial": { "source": "Tushare-财务报表", "profit": [], "balance": [], "cashflow": [], "error": null },
      "market_hist": { "source": "Tushare-日线行情", "current_price": 8.5, "pct_1m": 2.1, "pct_3m": -1.2, "pct_1y": 5.3, "error": null },
      "individual_info": { "source": "Tushare-每日指标与股票列表", "total_mv": "2500万元", "industry": "银行", "pe": 5.2, "pb": 0.6, "error": null }
    },
    "valuation": {
      "methods_used": ["PE", "PB"],
      "current_pe": 5.2,
      "current_pb": 0.6,
      "conclusion": "偏低估值",
      "assumptions": ["PE/PB 来自 Tushare 每日指标，未做行业可比调整。"],
      "risk_note": "估值受盈利波动与市场情绪影响，请勿作为唯一决策依据。"
    },
    "event_cross_validation": [
      {
        "event_id": "E1",
        "event_category": "基本面事件",
        "impact_level": "需结合财报明细判断",
        "logic_changed": null,
        "priced_in": "需对比事件时点与涨跌时点判断",
        "evidence": "已获取 Tushare 利润表数据，可对照业绩变动验证。已有 Tushare 日线数据，可观察事件前后涨跌幅与成交量是否异动。"
      }
    ],
    "constraints_and_risks": {
      "not_investment_advice": true,
      "capital_guarantee": false,
      "disclaimers": ["本模块输出仅基于公开金融数据与阶段1舆情事件的交叉验证，不构成任何投资建议..."]
    }
  }
}
```

### 13.4 调用示例

**CMD 直接运行：**

```cmd
curl -X POST "http://localhost:8000/api/research/analyze" -H "Content-Type: application/json" -d "{\"symbol\":\"600519.SH\",\"name\":\"贵州茅台\",\"start_date\":\"2026-03-01\",\"end_date\":\"2026-03-11\",\"events\":[{\"event_id\":\"N1\",\"event_category\":\"基本面事件\",\"event_subtype\":\"财报发布\",\"core_summary\":\"贵州茅台2025年度业绩快报：营收1738亿同比增15.34%，净利润862亿同比增15.38%\",\"sentiment\":\"利好\",\"sentiment_score\":9,\"impact_scope\":\"公司级\",\"impact_horizon\":\"中期（1-3个月）\",\"source_level\":\"S\",\"occur_time\":\"2026-03-03\",\"published_at\":\"2026-03-03\"},{\"event_id\":\"N2\",\"event_category\":\"基本面事件\",\"event_subtype\":\"核心产品变动\",\"core_summary\":\"茅台计划推出2000-3000元新高端系列酒产品\",\"sentiment\":\"利好\",\"sentiment_score\":8,\"impact_scope\":\"公司级\",\"impact_horizon\":\"中期（1-3个月）\",\"source_level\":\"A\",\"occur_time\":\"2026-03-05\",\"published_at\":\"2026-03-05\"},{\"event_id\":\"N3\",\"event_category\":\"政策事件\",\"event_subtype\":\"产业扶持政策\",\"core_summary\":\"国务院印发促消费意见，支持高品质消费品供给\",\"sentiment\":\"利好\",\"sentiment_score\":7,\"impact_scope\":\"行业级\",\"impact_horizon\":\"长期（3个月以上）\",\"source_level\":\"A\",\"occur_time\":\"2026-03-06\",\"published_at\":\"2026-03-06\"},{\"event_id\":\"N4\",\"event_category\":\"市场事件\",\"event_subtype\":\"北向资金异动\",\"core_summary\":\"北向资金连续5日净买入茅台累计45.6亿元\",\"sentiment\":\"利好\",\"sentiment_score\":7,\"impact_scope\":\"公司级\",\"impact_horizon\":\"短期（1-5个交易日）\",\"source_level\":\"A\",\"occur_time\":\"2026-03-07\",\"published_at\":\"2026-03-07\"}]}"
```

> 说明：`events` 字段应使用阶段1 `/api/news/analyze` 返回的 `result.events`，上例为模拟数据以便独立测试。

---

## 14. 三维度交叉验证与信号过滤

对应 ValueCell 的**交叉验证引擎**：基于阶段1舆情结果与阶段2基本面结果，执行「基本面-舆情-资金面」三维校验，完成噪音过滤、历史相似事件回测、信号确定性分级（高/中/低）与市场定价充分性判断，是策略生成前的核心校验环节。

> 依赖：`TUSHARE_TOKEN`（行情与每日指标数据）。不依赖 LLM。

### 14.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/api/signal/validate` |
| 方法 | `POST` |
| Content-Type | `application/json` |

### 14.2 三维校验标准（严格执行，不可放宽）

| 维度 | 通过条件 |
|------|---------|
| 舆情维度 | 信源等级 ≥ A 级；利好信号情绪强度 ≥ 7 分，利空 ≤ 3 分；有明确事件主体与发生时间 |
| 基本面维度 | 阶段2交叉验证显示事件有财报/行情数据支撑，且对核心经营逻辑有实质影响（中性事件自动不通过） |
| 资金面维度 | 事件发生日前后 3 个交易日，成交量或换手率 ≥ 近 30 日均值 1.5 倍 |

### 14.3 信号确定性分级

| 分级 | 条件 | 可用于策略 |
|------|------|-----------|
| 高确定性信号 | 三维完全匹配 + 历史相似事件T+5胜率 ≥ 70% + 情绪强度极端（≥8或≤2） | ✅ |
| 中确定性信号 | 三维基本匹配 + 历史胜率 50%~70% | ✅（需人工确认） |
| 低确定性信号 | 三维存在分歧 + 历史胜率 < 50% | ❌（仅风险提示） |
| 噪音信号 | 三维校验未通过 | ❌（直接过滤） |

### 14.4 请求 body

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 是 | 标的代码，如 `600000.SH` |
| `name` | string | 是 | 标的名称，如 `浦发银行` |
| `news_result` | object | 是 | 阶段1 `POST /api/news/analyze` 返回的 `result` 字段（完整 JSON） |
| `research_result` | object | 是 | 阶段2 `POST /api/research/analyze` 返回的 `result` 字段（完整 JSON） |

### 14.5 响应 body（结构说明）

```json
{
  "success": true,
  "report_md": "## 一、交叉验证总览\n...（Markdown 报告，含四部分）",
  "result": {
    "meta": {
      "module_name": "signal_validator",
      "version": "0.1.0",
      "run_timestamp": "2026-03-11T15:00:00+08:00",
      "data_sources": ["tushare"]
    },
    "inputs": {
      "symbol": "600000.SH",
      "name": "浦发银行",
      "total_events": 2
    },
    "summary": {
      "valid_signal_count": 1,
      "noise_signal_count": 1,
      "high_grade_count": 0,
      "mid_grade_count": 1,
      "low_grade_count": 0
    },
    "validation_matrix": [
      {
        "signal_id": "E1",
        "event_category": "基本面事件",
        "event_summary": "浦发银行发布年度财报，净利润同比增长。",
        "signal_type": "有效信号",
        "filter_reason": null,
        "dim_sentiment": { "passed": true, "source_level": "A", "sentiment": "利好", "sentiment_score": 7.5, "reason": "通过" },
        "dim_fundamental": { "passed": true, "impact_level": "需结合财报明细判断", "reason": "..." },
        "dim_capital": { "passed": true, "volume_anomaly": true, "avg_vol_ratio": 2.1, "reason": "成交量放大约 2.1 倍" }
      }
    ],
    "graded_signals": [
      {
        "signal_id": "E1",
        "signal_type": "有效信号",
        "backtest": {
          "method": "Tushare-日线历史成交量异动代理法",
          "sample_count": 15,
          "backtest": {
            "t1": { "win_rate": 60.0, "avg_return": 0.8, "max_drawdown": -2.1, "count": 15 },
            "t5": { "win_rate": 60.0, "avg_return": 1.5, "max_drawdown": -3.2, "count": 15 },
            "t10": { "win_rate": 55.0, "avg_return": 1.1, "max_drawdown": -4.5, "count": 14 },
            "t30": { "win_rate": 52.0, "avg_return": 2.0, "max_drawdown": -8.0, "count": 13 }
          },
          "win_rate_t5": 60.0,
          "conclusion": "近3年共找到 15 个类似资金异动样本；T+5历史胜率中等（60%），平均涨跌幅1.5%。"
        },
        "grade": {
          "grade": "中确定性信号",
          "grade_code": 2,
          "reason": "三维度基本匹配；T+5历史胜率60%（50%~70%）...",
          "strategy_eligible": true
        },
        "pricing_adequacy": {
          "adequacy": "定价部分充分（中性）",
          "current_cumulative_pct": 3.2,
          "reason": "事件后累计涨幅3.2%，定价部分反映..."
        }
      }
    ],
    "noise_signals": [],
    "constraints_and_risks": {
      "not_investment_advice": true,
      "capital_guarantee": false,
      "disclaimers": ["..."]
    }
  }
}
```

### 14.6 调用示例（四阶段联动流程，CMD 可直接运行）

以贵州茅台（600519.SH）为例的完整四阶段流程：

```cmd
REM 第一步：阶段1 舆情结构化（使用 test_news.json 测试文件）
curl -X POST "http://localhost:8000/api/news/analyze" -H "Content-Type: application/json" -d @test_news.json -o news_result.json

REM 第二步：阶段2 基本面分析（使用 test_research.json 测试文件）
curl -X POST "http://localhost:8000/api/research/analyze" -H "Content-Type: application/json" -d @test_research.json -o research_result.json

REM 第三步：阶段3 三维交叉验证（使用 test_signal.json 测试文件）
curl -X POST "http://localhost:8000/api/signal/validate" -H "Content-Type: application/json" -d @test_signal.json -o signal_result.json

REM 第四步：阶段4 策略生成（使用 test_strategy.json 测试文件）
curl -X POST "http://localhost:8000/api/strategy/generate" -H "Content-Type: application/json" -d @test_strategy.json -o strategy_result.json
```

> **说明**：每个阶段的请求体中需要嵌入上一阶段返回的 `result` 字段。建议流程：
> 1. 运行阶段1 → 打开 `news_result.json` → 取出 `result` 字段
> 2. 构造阶段2请求体（`events` 用阶段1返回的 `result.events`）→ 运行阶段2
> 3. 构造阶段3请求体（`news_result` 和 `research_result` 分别对应阶段1/2的 `result`）→ 运行阶段3
> 4. 构造阶段4请求体（`signal_result` 用阶段3返回的 `result`）→ 运行阶段4
>
> 各阶段可独立测试的请求文件模板见 `tests/` 目录。

---

## 15. 交易策略生成与参数精细化

对应 ValueCell 的 Strategy Agent，基于阶段3验证后的有效信号，结合用户风险偏好与投资周期，生成结构化、可执行、参数明确的交易策略。

### 15.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `POST /api/strategy/generate` |
| Content-Type | `application/json` |
| 前置依赖 | 阶段3 `/api/signal/validate` 的 `result` 字段 |
| 数据源 | Tushare（行情、均线、支撑/阻力等市场数据） |

### 15.2 请求体

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 是 | 标的代码，如 `600000.SH` |
| `name` | string | 是 | 标的名称，如 `浦发银行` |
| `signal_result` | object | 是 | 阶段3 `/api/signal/validate` 返回的 `result` 字段完整 JSON |
| `risk_preference` | string | 是 | 用户风险偏好：`保守` / `稳健` / `进取` |
| `investment_horizon` | string | 是 | 投资周期：`短线` / `中线` / `长线` |
| `max_position_pct` | number | 是 | 单票最大仓位上限(%)，范围 (0, 100] |

### 15.3 策略核心逻辑锚定规则

| 信号属性 | 策略类型 | 方向 | 适配周期 |
|----------|----------|------|----------|
| 高确定性 + 中长期影响 | 基本面价值策略 | 做多 | 中线/长线 |
| 中确定性 + 短期影响 | 事件驱动策略 | 做多 | 短线 |
| 利空信号 | 风险规避策略 | 做空/观望 | 视情况 |
| 已充分定价 | 观望策略 | 观望 | — |

### 15.4 风险偏好 → 参数映射

| 参数 | 保守 | 稳健 | 进取 |
|------|------|------|------|
| 总仓位上限 | 30% | 50% | 80% |
| 首次建仓比例 | 总仓位×50% | 总仓位×50% | 总仓位×50% |
| 止损线 | -3% | -5% | -8% |
| 最大回撤限制 | 5% | 8% | 12% |
| 止盈档位 | +5%/+8%/+12% | +8%/+15%/+25% | +10%/+20%/+35% |

### 15.5 策略参数全清单

每个策略必须包含以下所有参数，无模糊表述：

1. **策略方向**：做多 / 做空 / 观望（严格三选一）
2. **标的信息**：标的代码、交易市场、合约类型（现货/期货/期权）
3. **仓位管理方案**：总仓位上限、首次建仓比例、分批加仓条件与比例
4. **入场条件**：明确价格区间、触发条件、入场时间窗口、确认信号
5. **止盈方案**：分档位目标价、对应减仓比例、触发条件
6. **止损方案**：止损价、硬止损价、最大回撤限制、执行方式
7. **策略有效期**：持仓周期、失效条件、最迟退出时间

### 15.6 极端行情应对方案

| 场景 | 触发条件 | 执行动作 |
|------|----------|----------|
| 黑天鹅事件 | 标的当日跌幅>7%或大盘跌幅>3% | 立即减仓50%，紧急止损 |
| 大盘连续暴跌 | 沪指连续3日累计跌幅>5% | 降至半仓，暂停建仓 |
| 舆情反转 | S/A级信源反向消息 | 暂停加仓，评估后72小时内清仓 |
| 一字跌停 | 标的跌停无法卖出 | 挂卖单排队，评估期权对冲 |
| 一字涨停 | 标的涨停 | 持仓者持有，未建仓者不追涨 |
| 利空对冲 | 利空确认且持有多头 | 认沽期权/行业ETF对冲/直接减仓 |

### 15.7 盈亏比测算说明

- **盈亏比** = 加权预期收益 / 止损幅度，≥3 优秀，≥2 良好，≥1 一般
- **历史胜率**来自阶段3回测数据（成交量异动代理法），非精确事件匹配
- **核心假设**：止盈档位均被触发、未含交易成本与滑点、市场正常流动性
- **不确定性风险**：宏观政策突变、个股基本面意外变化、流动性不足

### 15.8 响应格式

```json
{
  "success": true,
  "report_md": "## 一、策略总览\n...",
  "result": {
    "meta": {
      "module_name": "strategy_agent",
      "version": "0.1.0",
      "run_timestamp": "2026-03-11T15:30:00+08:00",
      "data_sources": ["tushare"]
    },
    "inputs": {
      "symbol": "600000.SH",
      "name": "浦发银行",
      "risk_preference": "稳健",
      "investment_horizon": "中线",
      "max_position_pct": 30,
      "eligible_signal_count": 1
    },
    "strategies": [
      {
        "signal_id": "E1",
        "anchor": {
          "strategy_type": "基本面价值",
          "direction": "做多",
          "core_logic": "高确定性信号...",
          "revenue_source": "基本面改善驱动的估值修复与盈利增长",
          "core_risk": "基本面预期落空..."
        },
        "target": {
          "ts_code": "600000.SH",
          "name": "浦发银行",
          "market": "SH",
          "contract_type": "现货（A股）"
        },
        "position_plan": {
          "total_position_pct": 30,
          "first_build_pct": 15.0,
          "add_positions": [
            {"seq": 1, "pct": 9.0, "condition": "..."},
            {"seq": 2, "pct": 6.0, "condition": "..."}
          ]
        },
        "entry_conditions": {
          "direction": "做多",
          "entry_trigger": "股价回调至 X.XX-X.XX 元区间...",
          "entry_price_range": {"low": 10.50, "high": 10.80},
          "time_window": "自发布起 10-60 个交易日内",
          "confirmation_signal": "..."
        },
        "take_profit": [
          {"tier": "一档", "target_price": 11.66, "target_pct": 8, "reduce_ratio": 0.3, "reduce_pct": 30, "trigger_condition": "..."},
          {"tier": "二档", "target_price": 12.42, "target_pct": 15, "reduce_ratio": 0.4, "reduce_pct": 40, "trigger_condition": "..."},
          {"tier": "三档", "target_price": 13.50, "target_pct": 25, "reduce_ratio": 0.3, "reduce_pct": 30, "trigger_condition": "..."}
        ],
        "stop_loss": {
          "stop_loss_price": 10.26,
          "hard_stop_price": 10.05,
          "stop_loss_pct": 5.0,
          "max_drawdown_pct": 8.0,
          "trigger_condition": "...",
          "execution": "...",
          "note": "..."
        },
        "validity": {
          "hold_period": "10-60个交易日",
          "hold_days_range": {"min": 10, "max": 60},
          "exit_deadline": "最迟在第 60 个交易日收盘前全部清仓",
          "invalidation_conditions": ["..."]
        },
        "contingency_plans": [
          {"scenario": "黑天鹅事件", "trigger": "...", "action": "...", "execution": "...", "priority": "最高"}
        ],
        "pnl_estimation": {
          "risk_reward_ratio": 2.88,
          "risk_reward_label": "2.88:1（良好）",
          "expected_gain_weighted_pct": 14.4,
          "max_potential_gain_pct": 25,
          "max_potential_loss_pct": 5.0,
          "historical_win_rate_t5": 62.5,
          "historical_win_rate_t10": 68.0,
          "historical_avg_return_t5": 1.85,
          "historical_max_drawdown": -3.2,
          "assumptions": ["..."],
          "uncertainties": ["..."]
        },
        "price_context": {
          "current_close": 10.80,
          "ma5": 10.75,
          "ma20": 10.60,
          "recent_high_20d": 11.20,
          "recent_low_20d": 10.35
        }
      }
    ],
    "constraints_and_risks": {
      "not_investment_advice": true,
      "capital_guarantee": false,
      "disclaimers": ["..."]
    }
  }
}
```

### 15.9 Markdown 报告结构

| 章节 | 内容 |
|------|------|
| 一、策略总览 | 一句话总结每个策略的方向、盈亏比、核心风险 |
| 二、标准化策略参数表 | 所有必填参数，无模糊表述，可直接执行 |
| 三、策略执行节奏表 | 建仓→加仓→止盈→止损→到期退出的触发条件与执行顺序 |
| 四、极端行情应对方案 | 黑天鹅、暴跌、舆情反转、涨跌停应对 |
| 盈亏比与胜率测算 | 盈亏比、历史胜率、核心假设与不确定性 |
| 五、机器可读 JSON 说明 | JSON 字段说明 |

### 15.10 调用示例

**CMD 直接运行（使用测试文件）：**

```cmd
curl -X POST "http://localhost:8000/api/strategy/generate" -H "Content-Type: application/json" -d @test_strategy.json
```

**CMD 单行版本（最小化测试，`signal_result` 需替换为阶段3实际返回的 `result` 字段）：**

```cmd
curl -X POST "http://localhost:8000/api/strategy/generate" -H "Content-Type: application/json" -d "{\"symbol\":\"600519.SH\",\"name\":\"贵州茅台\",\"signal_result\":{...阶段3的result字段...},\"risk_preference\":\"稳健\",\"investment_horizon\":\"中线\",\"max_position_pct\":30}"
```

### 15.11 禁止项

- **禁止**生成与有效信号偏离的策略，所有策略逻辑必须完全基于前序模块的验证结果
- **禁止**生成超出用户风险偏好、仓位上限的策略，必须严格遵守用户预设的风险规则
- **禁止**使用模糊表述（如「逢低买入」「适当减仓」），所有参数必须明确、可执行、可验证
- **禁止**承诺收益，必须明确标注策略的所有潜在风险与最大回撤

---

*文档版本：1.2，与 API 服务 v1.0.0 对应。*
