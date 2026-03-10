# Tushare 新闻抓取 API 文档

本文档描述「Tushare 新闻抓取 API 服务」的接口说明，支持目录跳转、参数解析与调用示例。

---

## 目录（跳转）

- [1. 概述](#1-概述)
- [2. 通用说明](#2-通用说明)
- [3. 抓取新闻（排重）](#3-抓取新闻排重)
- [4. 查询新闻列表](#4-查询新闻列表)
- [5. 获取支持的新闻来源](#5-获取支持的新闻来源)
- [6. 获取抓取记录（上次结束时间）](#6-获取抓取记录上次结束时间)
- [7. 健康检查](#7-健康检查)
- [8. API 调用示例汇总](#8-api-调用示例汇总)

---

## 1. 概述

| 项目 | 说明 |
|------|------|
| 服务名称 | Tushare 新闻抓取 API |
| 默认地址 | `http://localhost:8000` |
| 交互方式 | REST JSON |
| 数据存储 | 本地 SQLite 数据库 `newsdata.db` |
| 排重规则 | 按「上次抓取结束时间」校验，不重复抓取已覆盖的时间段 |

---

## 2. 通用说明

- **Base URL**：`http://localhost:8000`（部署时替换为实际域名或 IP）。
- **Content-Type**：请求体为 JSON 时使用 `application/json`；查询接口多为 GET，参数在 Query。
- **响应**：成功时业务字段包含 `success: true`；列表类接口通常包含 `data` 数组。

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
    { "id": "cls", "name": "财联社" }
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

## 7. 健康检查

用于探测服务是否存活。

### 7.1 接口信息

| 项目 | 值 |
|------|-----|
| 路径 | `/health` |
| 方法 | `GET` |

### 7.2 响应示例

```json
{ "status": "ok" }
```

```bash
curl "http://localhost:8000/health"
```

---

## 8. API 调用示例汇总

| 能力 | 方法 | 路径 | 典型用法 |
|------|------|------|----------|
| 抓取新闻（排重） | POST | `/api/news/fetch` | 不传参即抓 24 小时内全部来源；可传 `hours`、`sources`、`start_date`、`end_date` |
| 查询新闻列表 | GET | `/api/news/list` | 传 `src`、`start_datetime`、`end_datetime`、`limit`、`offset` |
| 新闻来源列表 | GET | `/api/news/sources` | 无参数 |
| 抓取记录 | GET | `/api/news/fetch-log` | 无参数 |
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

*文档版本：1.0，与 API 服务 v1.0.0 对应。*
