# -*- coding: utf-8 -*-
"""全链路日志系统

支持分级日志输出（DEBUG / INFO / WARNING / ERROR / CRITICAL），
同时输出到控制台和按日期轮转的文件。
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

_LOGGER_NAME = "agent_system"
_initialized = False


def setup_logger(
    level: str = "INFO",
    log_dir: str = "./logs",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """初始化全局日志：控制台 + 文件双通道"""
    global _initialized

    logger = logging.getLogger(_LOGGER_NAME)
    if _initialized:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, f"agent_{today}.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    _initialized = True
    logger.info("日志系统初始化完成 | level=%s dir=%s", level, log_dir)
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取子 logger，首次调用时自动初始化"""
    base = logging.getLogger(_LOGGER_NAME)
    if not _initialized:
        setup_logger()
    return base.getChild(name) if name else base
