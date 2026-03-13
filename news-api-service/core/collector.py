# -*- coding: utf-8 -*-
"""定向化舆情数据采集器

功能：
  1. 标的精准采集（股票代码/名称 → 全量相关舆情）
  2. 行业/主题关键词定向采集
  3. 内容指纹去重，避免重复采集
  4. 实时增量 + 定时全量 双模式
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from core.datasources.base import BaseDataSource
from core.logger import get_logger

logger = get_logger("collector")


def content_fingerprint(title: str, content: str) -> str:
    """基于标题+正文前200字生成内容指纹，用于去重"""
    text = (title.strip() + content[:200].strip()).lower()
    return hashlib.md5(text.encode("utf-8")).hexdigest()


class NewsCollector:
    """舆情数据采集器——聚合多数据源、去重、标准化输出"""

    def __init__(self, data_sources: Optional[List[BaseDataSource]] = None) -> None:
        self.data_sources: List[BaseDataSource] = data_sources or []
        self._seen_hashes: Set[str] = set()
        self.logger = logger

    def add_source(self, source: BaseDataSource) -> None:
        self.data_sources.append(source)

    def collect(
        self,
        symbol: str = "",
        name: str = "",
        keywords: Optional[List[str]] = None,
        start_date: str = "",
        end_date: str = "",
        deduplicate: bool = True,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """从所有数据源采集并汇总。

        Returns:
            标准化字典列表，每条包含 news_id, title, content, publish_time,
            source, source_level, source_weight, url, content_hash
        """
        all_items: List[Dict[str, Any]] = []

        for ds in self.data_sources:
            try:
                raw = ds.fetch(
                    symbol=symbol,
                    name=name,
                    keywords=keywords,
                    start_date=start_date,
                    end_date=end_date,
                    **kwargs,
                )
                self.logger.info(
                    "数据源 [%s] 返回 %d 条", ds.name, len(raw)
                )
                all_items.extend(raw)
            except Exception as e:
                self.logger.warning("数据源 [%s] 采集失败: %s", ds.name, e)

        if deduplicate:
            before = len(all_items)
            all_items = self._deduplicate(all_items)
            removed = before - len(all_items)
            if removed > 0:
                self.logger.info("去重移除 %d 条 (剩余 %d)", removed, len(all_items))

        standardized = []
        for item in all_items:
            rec = self._standardize(item, symbol)
            standardized.append(rec)

        standardized.sort(key=lambda x: x.get("publish_time", ""), reverse=True)
        self.logger.info(
            "采集完成 | symbol=%s total=%d sources=%d",
            symbol, len(standardized), len(self.data_sources),
        )
        return standardized

    def collect_incremental(
        self,
        symbol: str = "",
        name: str = "",
        keywords: Optional[List[str]] = None,
        last_fetch_time: str = "",
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """增量采集：从 last_fetch_time 到当前时间。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self.collect(
            symbol=symbol,
            name=name,
            keywords=keywords,
            start_date=last_fetch_time,
            end_date=now,
            **kwargs,
        )

    def reset_seen(self) -> None:
        """清空已知指纹缓存（新一轮全量采集时调用）"""
        self._seen_hashes.clear()

    # ── 内部方法 ──

    def _deduplicate(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique: List[Dict[str, Any]] = []
        for item in items:
            fp = content_fingerprint(
                item.get("title", ""), item.get("content", "")
            )
            if fp not in self._seen_hashes:
                self._seen_hashes.add(fp)
                item["content_hash"] = fp
                unique.append(item)
        return unique

    @staticmethod
    def _standardize(item: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """将原始数据标准化为统一字段格式"""
        if "content_hash" not in item:
            item["content_hash"] = content_fingerprint(
                item.get("title", ""), item.get("content", "")
            )
        return {
            "news_id": f"N-{uuid.uuid4().hex[:8]}",
            "title": item.get("title", ""),
            "content": item.get("content", ""),
            "publish_time": item.get("publish_time", ""),
            "source": item.get("source", ""),
            "source_level": item.get("source_level", "C"),
            "source_weight": item.get("source_weight", 0.5),
            "url": item.get("url", ""),
            "content_hash": item["content_hash"],
            "channels": item.get("channels", ""),
            "symbol": symbol,
            "_raw_source": item.get("_raw_source", ""),
        }
