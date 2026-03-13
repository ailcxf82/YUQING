# -*- coding: utf-8 -*-
"""向量数据库封装（LanceDB）

提供文本向量化存储与语义检索能力，
用于舆情数据的持久化与相似性搜索。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import lancedb

from core.config import get_config
from core.logger import get_logger

logger = get_logger("vector_store")


class VectorStore:
    """LanceDB 向量数据库封装"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        path = db_path or get_config().lancedb_path
        os.makedirs(path, exist_ok=True)
        self.db = lancedb.connect(path)
        self._path = path
        logger.info("LanceDB 连接成功 | path=%s", path)

    def create_table(
        self,
        name: str,
        data: List[Dict[str, Any]],
        mode: str = "overwrite",
    ) -> Any:
        """创建或覆盖向量表"""
        table = self.db.create_table(name, data=data, mode=mode)
        logger.info("向量表创建 | name=%s rows=%d mode=%s", name, len(data), mode)
        return table

    def open_table(self, name: str) -> Any:
        """打开已有向量表"""
        if name not in self.db.table_names():
            raise ValueError(f"向量表 '{name}' 不存在")
        return self.db.open_table(name)

    def get_or_create_table(
        self,
        name: str,
        data: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        """获取已有表，不存在时用初始数据创建"""
        if name in self.db.table_names():
            return self.db.open_table(name)
        if data is None:
            raise ValueError(f"表 '{name}' 不存在且未提供初始数据")
        return self.create_table(name, data)

    def add_records(self, table_name: str, records: List[Dict[str, Any]]) -> None:
        """向已有表追加记录"""
        table = self.open_table(table_name)
        table.add(records)
        logger.debug("向量表追加 | name=%s count=%d", table_name, len(records))

    def search(
        self,
        table_name: str,
        query_vector: List[float],
        limit: int = 10,
        filter_expr: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """向量相似性检索"""
        if table_name not in self.db.table_names():
            logger.warning("向量检索：表 '%s' 不存在", table_name)
            return []
        table = self.db.open_table(table_name)
        q = table.search(query_vector).limit(limit)
        if filter_expr:
            q = q.where(filter_expr)
        results = q.to_list()
        logger.debug(
            "向量检索 | table=%s limit=%d found=%d", table_name, limit, len(results)
        )
        return results

    def list_tables(self) -> List[str]:
        return self.db.table_names()

    def drop_table(self, name: str) -> None:
        if name in self.db.table_names():
            self.db.drop_table(name)
            logger.info("向量表已删除 | name=%s", name)
