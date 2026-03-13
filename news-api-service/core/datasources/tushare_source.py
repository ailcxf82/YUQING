# -*- coding: utf-8 -*-
"""Tushare 数据源实现

覆盖 Tushare 可用的舆情数据接口：
  1. pro.news() — 多源新闻短讯（sina/cls/yicai/eastmoney 等）
  2. pro.major_news() — 长新闻/深度报道（需较高积分）
  3. pro.anns() — 上市公司公告（需较高积分）
自动降级：高积分接口不可用时跳过，不中断流程。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import tushare as ts

from core.config import get_config
from core.datasources.base import BaseDataSource, TUSHARE_SOURCE_LEVELS, SOURCE_WEIGHTS

TUSHARE_NEWS_SOURCES = [
    "sina", "wallstreetcn", "10jqka", "eastmoney",
    "yuncaijing", "fenghuang", "jinrongjie", "cls", "yicai",
]


class TushareNewsSource(BaseDataSource):
    """Tushare 舆情数据源"""

    name = "tushare"
    description = "Tushare 新闻短讯 + 长新闻 + 公告"

    def __init__(self) -> None:
        super().__init__()
        self._pro: Optional[Any] = None

    @staticmethod
    def _bypass_proxy():
        """确保 Tushare API 请求不走本地代理"""
        import os
        for key in ("NO_PROXY", "no_proxy"):
            if os.environ.get(key, ""):
                if "*" not in os.environ[key]:
                    os.environ[key] += ",api.tushare.pro,api.waditu.com"
            else:
                os.environ[key] = "api.tushare.pro,api.waditu.com,*"

    def _get_pro(self) -> Any:
        if self._pro is None:
            self._bypass_proxy()
            token = get_config().tushare_token
            if not token:
                raise EnvironmentError("未配置 TUSHARE_TOKEN")
            self._pro = ts.pro_api(token)
        return self._pro

    def get_source_level(self, raw_source: str) -> str:
        return TUSHARE_SOURCE_LEVELS.get(raw_source, "B")

    # ── 核心采集 ──

    def fetch(
        self,
        symbol: str = "",
        name: str = "",
        keywords: Optional[List[str]] = None,
        start_date: str = "",
        end_date: str = "",
        sources: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """采集 Tushare 新闻数据，返回标准化字典列表。"""
        results: List[Dict[str, Any]] = []

        results.extend(
            self._fetch_news(symbol, name, keywords, start_date, end_date, sources)
        )
        results.extend(
            self._fetch_major_news(start_date, end_date)
        )

        self.logger.info(
            "Tushare 采集完成 | total=%d symbol=%s", len(results), symbol
        )
        return results

    def _fetch_news(
        self,
        symbol: str,
        name: str,
        keywords: Optional[List[str]],
        start_date: str,
        end_date: str,
        sources: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """pro.news() 多源新闻短讯"""
        pro = self._get_pro()
        src_list = sources or TUSHARE_NEWS_SOURCES
        all_items: List[Dict[str, Any]] = []

        sd = self._fmt_date(start_date)
        ed = self._fmt_date(end_date)
        if not sd or not ed:
            now = datetime.now()
            ed = ed or now.strftime("%Y-%m-%d %H:%M:%S")
            sd = sd or (now - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")

        for src in src_list:
            try:
                df = pro.news(src=src, start_date=sd, end_date=ed)
                if df is None or df.empty:
                    continue
                for _, row in df.iterrows():
                    title = str(row.get("title", "") or "").strip()
                    content = str(row.get("content", "") or "").strip()
                    if not content and not title:
                        continue

                    raw_time = str(row.get("datetime", ""))
                    level = self.get_source_level(src)
                    item = {
                        "title": title,
                        "content": content,
                        "publish_time": raw_time,
                        "source": src,
                        "source_level": level,
                        "source_weight": SOURCE_WEIGHTS.get(level, 0.5),
                        "url": "",
                        "channels": str(row.get("channels", "") or ""),
                        "_raw_source": "tushare_news",
                    }
                    all_items.append(item)
                self.logger.debug("news(%s) 获取 %d 条", src, len(df))
            except Exception as e:
                self.logger.warning("news(%s) 失败: %s", src, e)

        # 标的/关键词过滤
        if symbol or name or keywords:
            all_items = self._filter_by_relevance(all_items, symbol, name, keywords)

        return all_items

    def _fetch_major_news(
        self,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """pro.major_news() 长新闻（需较高积分，不可用时降级跳过）"""
        try:
            pro = self._get_pro()
            sd = self._fmt_date(start_date) or ""
            ed = self._fmt_date(end_date) or ""
            fields = "title,content,pub_time,src,url"
            df = pro.major_news(
                start_date=sd[:10].replace("-", "") if sd else "",
                end_date=ed[:10].replace("-", "") if ed else "",
                fields=fields,
            )
            if df is None or df.empty:
                return []

            items = []
            for _, row in df.iterrows():
                title = str(row.get("title", "") or "").strip()
                content = str(row.get("content", "") or "").strip()
                if not content and not title:
                    continue
                src_name = str(row.get("src", "") or "").strip()
                level = self.get_source_level(src_name) if src_name else "B"
                items.append({
                    "title": title,
                    "content": content,
                    "publish_time": str(row.get("pub_time", "")),
                    "source": src_name or "major_news",
                    "source_level": level,
                    "source_weight": SOURCE_WEIGHTS.get(level, 0.7),
                    "url": str(row.get("url", "") or ""),
                    "channels": "",
                    "_raw_source": "tushare_major_news",
                })
            self.logger.debug("major_news 获取 %d 条", len(items))
            return items
        except Exception as e:
            self.logger.info("major_news 接口不可用(降级跳过): %s", e)
            return []

    # ── 工具方法 ──

    @staticmethod
    def _fmt_date(s: str) -> str:
        if not s:
            return ""
        s = s.strip()
        if len(s) == 10:
            return s + " 00:00:00"
        return s

    @staticmethod
    def _filter_by_relevance(
        items: List[Dict[str, Any]],
        symbol: str,
        name: str,
        keywords: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """按标的名称/代码/关键词过滤相关新闻"""
        search_terms: List[str] = []
        if name:
            search_terms.append(name)
        if symbol:
            code = symbol.split(".")[0] if "." in symbol else symbol
            search_terms.append(code)
        if keywords:
            search_terms.extend(keywords)

        if not search_terms:
            return items

        filtered = []
        for item in items:
            text = (item.get("title", "") + item.get("content", "")).lower()
            for term in search_terms:
                if term.lower() in text:
                    filtered.append(item)
                    break
        return filtered
