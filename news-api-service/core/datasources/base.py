# -*- coding: utf-8 -*-
"""数据源抽象基类

所有数据源统一继承 BaseDataSource，支持用户自定义新增数据源。
内置信源分级权重配置。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from core.logger import get_logger


class SourceLevel(str, Enum):
    S = "S"  # 交易所公告、证监会文件、上市公司官方财报
    A = "A"  # 权威财经媒体（财新、路透、彭博、第一财经、财联社）
    B = "B"  # 行业垂直媒体、知名财经 KOL
    C = "C"  # 社交媒体、论坛、股吧 UGC
    D = "D"  # 无明确信源的传闻、小道消息


SOURCE_WEIGHTS: Dict[str, float] = {
    SourceLevel.S: 1.0,
    SourceLevel.A: 0.85,
    SourceLevel.B: 0.70,
    SourceLevel.C: 0.50,
    SourceLevel.D: 0.30,
}

# Tushare news src → 信源等级映射
TUSHARE_SOURCE_LEVELS: Dict[str, str] = {
    "cls": "A",        # 财联社
    "yicai": "A",      # 第一财经
    "wallstreetcn": "A",  # 华尔街见闻
    "sina": "B",       # 新浪财经
    "10jqka": "B",     # 同花顺
    "eastmoney": "B",  # 东方财富
    "yuncaijing": "B", # 云财经
    "fenghuang": "B",  # 凤凰财经
    "jinrongjie": "B", # 金融界
}


class BaseDataSource(ABC):
    """数据源抽象基类——所有数据源必须继承此类"""

    name: str = "base"
    description: str = ""

    def __init__(self) -> None:
        self.logger = get_logger(f"datasource.{self.name}")

    @abstractmethod
    def fetch(
        self,
        symbol: str = "",
        name: str = "",
        keywords: Optional[List[str]] = None,
        start_date: str = "",
        end_date: str = "",
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """采集原始数据。

        返回字典列表，每项至少包含：
          title, content, publish_time, source, source_level, url
        """
        ...

    @abstractmethod
    def get_source_level(self, raw_source: str) -> str:
        """将原始数据源标识映射为信源等级 S/A/B/C/D"""
        ...

    def get_source_weight(self, level: str) -> float:
        return SOURCE_WEIGHTS.get(level, 0.5)
