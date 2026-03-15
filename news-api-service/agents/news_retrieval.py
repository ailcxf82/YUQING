# -*- coding: utf-8 -*-
"""舆情数据读取智能体（NewsRetrievalAgent）

角色定位：全链路舆情数据的唯一入口。

架构重点：
  本 Agent 不再做实时网络数据采集。
  数据采集由后台定时任务（core/news_collector_job.py）完成，
  本 Agent 仅从本地数据库读取已采集并预处理好的数据。
  这将分析响应时间从 300s+ 降低到 <1s。

核心职责：
  1. 从本地数据库读取指定标的的预采集数据
  2. 按时间范围/关键词过滤
  3. 支持 keyword 语义搜索（LLM 分析 + 数据库搜索）
  4. 数据质量校验
  5. 输出标准化 NewsRetrievalOutput
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from core.config import SystemConfig
from core.llm import LLMClient
from core.news_collector_job import read_local_news, get_status as get_collect_status
from core.schemas import AgentStatus, NewsRetrievalOutput
from core.prompts import get_prompt
from app.config import get_settings
from app import database


class NewsRetrievalAgent(BaseAgent):
    """舆情数据读取智能体——从本地数据库读取预采集数据"""

    name = "news_retrieval"
    description = "从本地数据库读取已采集的舆情数据，支持标的/关键词检索"

    SYSTEM_PROMPT = get_prompt("news_retrieval", "agent_system")

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config: Optional[SystemConfig] = None,
    ) -> None:
        super().__init__(llm_client=llm_client, config=config)
        self._keyword_llm: Optional[LLMClient] = None
        self.logger.info("NewsRetrievalAgent 初始化 (本地读取模式)")

    def _get_llm(self) -> LLMClient:
        if self._keyword_llm is None:
            self._keyword_llm = LLMClient(self.config)
        return self._keyword_llm

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        task_id = state.get("task_id", "")
        symbol, name, time_range, topics, keyword = self._extract_params(state)

        self.logger.info(
            "舆情数据读取 | symbol=%s name=%s keyword=%s range=%s~%s",
            symbol, name, keyword[:20] if keyword else "", time_range.get("start"), time_range.get("end"),
        )

        local_items = []
        table_name = "news_general"
        keyword_analysis = state.get("keyword_analysis")

        if symbol:
            table_name = f"news_{symbol.replace('.', '_').lower()}"
            local_items = read_local_news(
                symbol=symbol,
                start_time=time_range.get("start", ""),
                end_time=time_range.get("end", ""),
                limit=200,
            )
            if topics and local_items:
                local_items = self._filter_by_topics(local_items, topics)
        elif keyword:
            table_name = "news_keyword_search"
            if not keyword_analysis:
                keyword_analysis = self._analyze_keyword_with_llm(keyword)
            if keyword_analysis:
                local_items = self._search_by_analyzed_keywords(
                    keyword_analysis=keyword_analysis,
                    start_time=time_range.get("start", ""),
                    end_time=time_range.get("end", ""),
                    limit=200,
                )

        if not local_items:
            return self._empty_result(
                task_id, symbol, name, keyword, keyword_analysis, time_range, table_name, start
            )

        news_items = self._to_output_items(local_items)
        duration = int((time.time() - start) * 1000)

        output = NewsRetrievalOutput(
            task_id=task_id,
            news_total_count=len(news_items),
            news_structured_data=news_items,
            vector_db_index_info={
                "table_name": table_name,
                "record_count": len(news_items),
                "data_source": "local_database",
                "keyword_analysis": keyword_analysis,
            },
            data_quality_report={
                "raw_collected": len(local_items),
                "after_clean": len(local_items),
                "vectorized": len(local_items),
                "source_breakdown": self._source_stats(local_items),
                "note": "数据来自本地数据库，非实时抓取",
            },
            execution_log={
                "duration_ms": duration,
                "mode": "keyword_search" if keyword else "local_read",
                "keyword_analysis": keyword_analysis,
            },
        )

        agent_out = self._make_output(
            AgentStatus.SUCCESS, data=output.model_dump(), duration_ms=duration
        )
        self.logger.info(
            "舆情数据读取完成 | total=%d table=%s duration=%dms",
            len(news_items), table_name, duration,
        )
        return {
            "news_retrieval_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "news_retrieval_done",
        }

    @staticmethod
    def _extract_params(state: Dict[str, Any]):
        task_base = state.get("task_base_info", {})
        if task_base:
            codes = task_base.get("target_code", [])
            names = task_base.get("target_name", [])
            symbol = codes[0] if codes else ""
            name = names[0] if names else ""
            tr = {
                "start": task_base.get("custom_time_start", ""),
                "end": task_base.get("custom_time_end", ""),
            }
            topics = list(task_base.get("user_custom_rules", {}).get("topics", []))
            keyword = task_base.get("keyword", "")
        else:
            task = state.get("task", {})
            symbol = task.get("symbol", "")
            name = task.get("name", "")
            tr = task.get("time_range", {})
            topics = task.get("topics", [])
            keyword = task.get("keyword", "")
        return symbol, name, tr, topics, keyword

    def _analyze_keyword_with_llm(self, keyword: str) -> Optional[Dict[str, Any]]:
        """调用 LLM 分析关键词，提取核心语义词"""
        try:
            llm = self._get_llm()
            prompt_template = get_prompt("keyword", "keyword_analysis")
            prompt = prompt_template.format(keyword=keyword)
            result = llm.chat_json(
                system_prompt="你是金融舆情语义分析专家，擅长提取关键词的核心语义。",
                user_prompt=prompt,
                temperature=0.1,
            )
            self.logger.info(
                "关键词语义分析 | keyword=%s | intent=%s | core=%s | search=%s | entities=%s",
                keyword[:30],
                result.get("intent_type", ""),
                result.get("core_keywords", []),
                result.get("search_keywords", []),
                result.get("related_entities", []),
            )
            return result
        except Exception as e:
            self.logger.warning("关键词语义分析失败: %s，使用原始关键词搜索", e)
            return {
                "intent_type": "主题",
                "core_keywords": [keyword],
                "search_keywords": [keyword],
                "related_entities": [],
                "time_sensitivity": "中",
                "semantic_description": f"搜索包含「{keyword}」的相关新闻",
            }

    def _search_by_analyzed_keywords(
        self,
        keyword_analysis: Dict[str, Any],
        start_time: str = "",
        end_time: str = "",
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """基于 LLM 分析结果搜索新闻"""
        #search_keywords = keyword_analysis.get("search_keywords", [])
        core_keywords = keyword_analysis.get("core_keywords", [])
        related_entities = keyword_analysis.get("related_entities", [])
        all_keywords = list(set(core_keywords + related_entities))

        if not all_keywords:
            return []

        settings = get_settings()
        database.init_db(settings.database_url)
        conn = database.get_connection(settings.database_url)

        try:
            all_items = []
            seen_ids = set()

            for kw in all_keywords[:15]:
                items = database.search_news_by_keyword(
                    conn, keyword=kw, limit=limit, offset=0
                )
                for item in items:
                    item_id = item.get("id")
                    if item_id not in seen_ids:
                        seen_ids.add(item_id)
                        all_items.append(item)

            if start_time:
                all_items = [i for i in all_items if i.get("datetime", "") >= start_time]
            if end_time:
                all_items = [i for i in all_items if i.get("datetime", "") <= end_time]

            all_items.sort(key=lambda x: x.get("datetime", ""), reverse=True)
            all_items = all_items[:limit]

            self.logger.info(
                "关键词搜索完成 | keywords=%s | found=%d",
                all_keywords[:3], len(all_items)
            )
            return self._convert_sqlite_items(all_items)
        except Exception as e:
            self.logger.warning("关键词搜索失败: %s", e)
            return []
        finally:
            conn.close()

    @staticmethod
    def _convert_sqlite_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将 SQLite 格式转换为统一格式"""
        result = []
        for item in items:
            result.append({
                "news_id": f"sqlite_{item.get('id', '')}",
                "source": item.get("src", ""),
                "source_level": "C",
                "source_weight": 0.5,
                "publish_time": item.get("datetime", ""),
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "url": "",
                "core_entity": "",
                "related_stock": "",
                "event_type": "",
                "keywords": [],
                "spread_count": 0,
            })
        return result

    @staticmethod
    def _filter_by_topics(
        items: List[Dict[str, Any]], topics: List[str]
    ) -> List[Dict[str, Any]]:
        """按用户自定义主题关键词过滤"""
        filtered = []
        for item in items:
            text = f"{item.get('title', '')} {item.get('content', '')}".lower()
            for topic in topics:
                if topic.lower() in text:
                    filtered.append(item)
                    break
        return filtered if filtered else items

    @staticmethod
    def _to_output_items(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items = []
        for p in records:
            items.append({
                "news_id": p.get("news_id", ""),
                "source_name": p.get("source", ""),
                "source_level": p.get("source_level", "C"),
                "source_weight": p.get("source_weight", 0.5),
                "publish_time": p.get("publish_time", ""),
                "title": p.get("title", ""),
                "content": p.get("content", ""),
                "text": f"{p.get('title', '')}\n{p.get('content', '')}".strip(),
                "url": p.get("url", ""),
                "core_entity": p.get("core_entity", ""),
                "related_stock": p.get("related_stock", ""),
                "event_type": p.get("event_type", ""),
                "keywords": p.get("keywords", []),
                "spread_count": p.get("spread_count", 0),
            })
        return items

    @staticmethod
    def _source_stats(items: List[Dict[str, Any]]) -> Dict[str, int]:
        stats: Dict[str, int] = {}
        for item in items:
            src = item.get("source", "unknown")
            stats[src] = stats.get(src, 0) + 1
        return stats

    def _empty_result(
        self,
        task_id: str,
        symbol: str,
        name: str,
        keyword: str,
        keyword_analysis: Optional[Dict[str, Any]],
        time_range: Dict[str, str],
        table_name: str,
        start: float,
    ) -> Dict[str, Any]:
        duration = int((time.time() - start) * 1000)

        collect_status = get_collect_status()
        symbols_configured = [
            s["symbol"] for s in collect_status.get("symbols", [])
        ]

        hint = ""
        if keyword and not symbol:
            search_kw = []
            if keyword_analysis:
                search_kw = keyword_analysis.get("search_keywords", [])
            kw_desc = keyword_analysis.get("semantic_description", keyword) if keyword_analysis else keyword
            hint = (
                f"关键词语义分析：{kw_desc}。"
                f"搜索词：{search_kw}。"
                f"在本地新闻库中未找到匹配数据，请先通过 POST /api/news/fetch 抓取新闻数据。"
            )
        elif symbol and symbol not in symbols_configured:
            hint = (
                f"标的 {symbol} 尚未配置定时采集。"
                f"请先调用 POST /api/v2/news-collect/add-symbol 添加，"
                f"再调用 POST /api/v2/news-collect/run-now 立即采集。"
            )
        elif not symbols_configured:
            hint = "当前无任何采集标的配置，请先配置后再分析。"
        else:
            hint = "本地暂无匹配数据，可能定时采集尚未执行或时间范围内无数据。"

        output = NewsRetrievalOutput(
            task_id=task_id,
            news_total_count=0,
            news_structured_data=[],
            vector_db_index_info={
                "table_name": f"{table_name}(empty)",
                "keyword_analysis": keyword_analysis,
            },
            data_quality_report={
                "raw_collected": 0,
                "after_clean": 0,
                "vectorized": 0,
                "hint": hint,
            },
            execution_log={
                "duration_ms": duration,
                "reason": "本地无数据",
                "mode": "keyword_search" if keyword else "local_read",
                "keyword_analysis": keyword_analysis,
            },
        )
        agent_out = self._make_output(
            AgentStatus.PARTIAL, data=output.model_dump(), duration_ms=duration
        )
        return {
            "news_retrieval_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "news_retrieval_done",
        }
