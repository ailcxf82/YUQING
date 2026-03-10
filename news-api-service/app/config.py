# -*- coding: utf-8 -*-
"""应用配置"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """从环境变量读取配置"""
    # Tushare token，需在 https://tushare.pro 注册获取
    tushare_token: str = ""
    # 数据库路径（相对或绝对）
    database_url: str = "sqlite:///./newsdata.db"
    # 默认抓取时间范围（小时）
    default_fetch_hours: int = 24
    # API 服务 host/port
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
