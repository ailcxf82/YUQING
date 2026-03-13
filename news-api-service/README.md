# Tushare 新闻抓取 API 服务

从 Tushare 新闻接口抓取数据并写入本地 `newsdata` 数据库，按「上次抓取结束时间」排重，默认抓取 24 小时内数据。

## 环境要求

- Python 3.8+
- Tushare 账号并开通「新闻快讯」接口权限：<https://tushare.pro/document/2?doc_id=143>

## 安装与运行

```bash
cd news-api-service
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
# source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 TUSHARE_TOKEN
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- API 文档（Swagger）：<http://localhost:8000/docs>
- ReDoc：<http://localhost:8000/redoc>
- 后端管理页（定时运行情况/数据库明细）：<http://localhost:8000/admin>
- 详细 API 说明（含目录跳转与示例）：见 [docs/API.md](docs/API.md)

## 定时服务

- **业务接口**：`POST /api/news/schedule` 一键开启新闻自动抓取，默认每 5 分钟执行一次（可传 body `{"interval_minutes": 10}` 修改间隔）。
- 定时配置为**内部接口**，不在 Swagger/ReDoc 展示，路径为 `/internal/scheduler/`（状态、开关、间隔、注册/更新/移除任务），详见 [docs/API.md](docs/API.md) 第 8 节。
- 配置持久化在 `scheduler_config.json`。

## 排重说明

- 每次抓取会记录每个来源的「上次抓取结束时间」到表 `fetch_log`。
- 下次抓取时，若不传 `start_date`，则从「上次结束时间」开始拉取，到当前时间（或你指定的 `end_date`）结束，从而不重复抓取同一时间段。
- 若指定了 `start_date` / `end_date`，则按指定范围抓取（仍会更新该来源的 last_end 为本次的 end_date）。

## 数据库

- 默认使用 SQLite，库文件：项目根目录下 `newsdata.db`。
- 表：`news`（新闻）、`fetch_log`（各来源上次抓取结束时间）、`scheduler_runs`（定时任务运行记录）。
