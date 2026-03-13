# -*- coding: utf-8 -*-
"""多源数据源对接层"""

from core.datasources.base import BaseDataSource, SourceLevel, SOURCE_WEIGHTS
from core.datasources.tushare_source import TushareNewsSource

__all__ = [
    "BaseDataSource",
    "SourceLevel",
    "SOURCE_WEIGHTS",
    "TushareNewsSource",
]
