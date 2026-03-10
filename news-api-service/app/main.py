# -*- coding: utf-8 -*-
"""FastAPI 入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app import database
from app.routes import news

app = FastAPI(
    title="Tushare 新闻抓取 API",
    description="抓取 Tushare 新闻接口数据并存入本地 newsdata 数据库，支持按上次抓取时间排重。",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(news.router)


@app.on_event("startup")
def startup():
    settings = get_settings()
    database.init_db(settings.database_url)


@app.get("/")
def root():
    return {
        "service": "Tushare 新闻抓取 API",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
