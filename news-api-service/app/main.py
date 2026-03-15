# -*- coding: utf-8 -*-
"""FastAPI 入口 — Phase 4 多智能体舆情分析系统"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.config import get_settings
from app import database
from app import service_switch
from app import scheduler
from app.routes import news
from app.routes import internal
from app.routes import admin
from app.routes import debug
from app.routes import research
from app.routes import signal
from app.routes import strategy
from app.routes import analysis
from app.routes import news_collect
from app.routes import pipeline

app = FastAPI(
    title="机构级金融舆情分析系统",
    description=(
        "Phase 4 精细化多智能体全链路协同引擎。\n\n"
        "**架构**：1 中枢调度 + 7 核心业务 + 2 支撑保障 = 10 个单一职责智能体\n\n"
        "**数据流**：舆情采集(定时后台) -> 本地LanceDB -> 分析链路(秒级响应)\n\n"
        "**核心接口**：\n"
        "- `POST /api/v2/analysis/full-link` — 全链路一键分析\n"
        "- `POST /api/v2/analysis/quick` — 快捷分析\n\n"
        "**数据采集管理**：\n"
        "- `POST /api/v2/news-collect/add-symbol` — 添加采集标的\n"
        "- `POST /api/v2/news-collect/run-now` — 立即采集\n"
        "- `GET  /api/v2/news-collect/status` — 采集状态\n\n"
        "**旧版接口**（v1，仍可用但建议迁移至 v2）：\n"
        "- `/api/news/analyze`, `/api/research/analyze`, "
        "`/api/signal/validate`, `/api/strategy/generate`"
    ),
    version="4.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Phase 4 新接口
app.include_router(analysis.router)
app.include_router(news_collect.router)
app.include_router(pipeline.router)

# 基础数据接口（保留）
app.include_router(news.router)
app.include_router(internal.router)
app.include_router(admin.router)
app.include_router(debug.router)

# 旧版分析接口（v1，保留向后兼容）
app.include_router(research.router)
app.include_router(signal.router)
app.include_router(strategy.router)


class SwitchBody(BaseModel):
    enabled: bool


@app.get("/api/service/switch", tags=["服务开关"])
def get_service_switch():
    """获取服务开关状态"""
    return {"enabled": service_switch.is_enabled()}


@app.put("/api/service/switch", tags=["服务开关"])
def set_service_switch(body: SwitchBody):
    """设置服务开关"""
    service_switch.set_enabled(body.enabled)
    return {"enabled": service_switch.is_enabled()}


@app.on_event("startup")
def startup():
    settings = get_settings()
    database.init_db(settings.database_url)
    scheduler.start_scheduler()


@app.on_event("shutdown")
def shutdown():
    scheduler.stop_scheduler()


@app.get("/")
def root():
    return {
        "service": "机构级金融舆情分析系统 v4.0",
        "architecture": "Phase 4 精细化多智能体全链路协同引擎",
        "docs": "/docs",
        "redoc": "/redoc",
        "core_api": "/api/v2/analysis/full-link",
        "system_info": "/api/v2/analysis/system-info",
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": "4.0.0"}
