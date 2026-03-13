# -*- coding: utf-8 -*-
"""舆情数据检索与过滤模块

支持多维度检索：
  1. 关键词精准检索
  2. 语义相似度检索（基于向量）
  3. 时间范围检索
  4. 标的/行业定向检索
  5. 自定义过滤规则（渠道权重、传播量级、事件类型）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.embedding import EmbeddingClient
from core.vector_store import VectorStore
from core.logger import get_logger

logger = get_logger("news_search")


class NewsSearchEngine:
    """舆情检索引擎——融合关键词 + 语义 + 元数据过滤"""

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_client: EmbeddingClient,
    ) -> None:
        self.vs = vector_store
        self.emb = embedding_client

    def semantic_search(
        self,
        query: str,
        table_name: str,
        limit: int = 20,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """语义相似度检索"""
        query_vec = self.emb.embed(query)
        results = self.vs.search(
            table_name=table_name,
            query_vector=query_vec,
            limit=limit,
            filter_expr=filter_expr,
        )
        logger.debug(
            "语义检索 | query=%s table=%s found=%d",
            query[:30], table_name, len(results),
        )
        return results

    def keyword_search(
        self,
        keyword: str,
        table_name: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """关键词精准检索（在 LanceDB 中通过 WHERE 过滤）"""
        try:
            table = self.vs.open_table(table_name)
            df = table.to_pandas()
            mask = (
                df["title"].str.contains(keyword, case=False, na=False)
                | df["content"].str.contains(keyword, case=False, na=False)
            )
            matched = df[mask].head(limit)
            results = matched.to_dict("records")
            logger.debug(
                "关键词检索 | keyword=%s found=%d", keyword, len(results)
            )
            return results
        except Exception as e:
            logger.warning("关键词检索失败: %s", e)
            return []

    def time_range_search(
        self,
        table_name: str,
        start_time: str = "",
        end_time: str = "",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """时间范围检索"""
        try:
            table = self.vs.open_table(table_name)
            df = table.to_pandas()
            if start_time:
                df = df[df["publish_time"] >= start_time]
            if end_time:
                df = df[df["publish_time"] <= end_time]
            df = df.sort_values("publish_time", ascending=False).head(limit)
            return df.to_dict("records")
        except Exception as e:
            logger.warning("时间范围检索失败: %s", e)
            return []

    def symbol_search(
        self,
        symbol: str,
        table_name: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """标的定向检索"""
        try:
            table = self.vs.open_table(table_name)
            df = table.to_pandas()
            code = symbol.split(".")[0] if "." in symbol else symbol
            mask = (
                df["symbol"].str.contains(symbol, case=False, na=False)
                | df["related_stock"].str.contains(code, case=False, na=False)
            )
            matched = df[mask].head(limit)
            return matched.to_dict("records")
        except Exception as e:
            logger.warning("标的检索失败: %s", e)
            return []

    def filtered_search(
        self,
        table_name: str,
        query: str = "",
        symbol: str = "",
        event_types: Optional[List[str]] = None,
        min_source_weight: float = 0.0,
        min_spread_count: int = 0,
        start_time: str = "",
        end_time: str = "",
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        """组合过滤检索：支持多维度联合筛选"""
        if query:
            results = self.semantic_search(query, table_name, limit=limit * 3)
        else:
            try:
                table = self.vs.open_table(table_name)
                results = table.to_pandas().to_dict("records")
            except Exception:
                results = []

        filtered = []
        for r in results:
            if symbol:
                code = symbol.split(".")[0] if "." in symbol else symbol
                r_symbol = str(r.get("symbol", ""))
                r_stock = str(r.get("related_stock", ""))
                if code not in r_symbol and code not in r_stock:
                    continue
            if event_types:
                if r.get("event_type", "") not in event_types:
                    continue
            if min_source_weight > 0:
                if r.get("source_weight", 0) < min_source_weight:
                    continue
            if min_spread_count > 0:
                if r.get("spread_count", 0) < min_spread_count:
                    continue
            if start_time and r.get("publish_time", "") < start_time:
                continue
            if end_time and r.get("publish_time", "") > end_time:
                continue
            filtered.append(r)

        filtered.sort(
            key=lambda x: x.get("publish_time", ""), reverse=True
        )
        return filtered[:limit]
