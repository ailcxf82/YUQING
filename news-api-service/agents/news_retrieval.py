# -*- coding: utf-8 -*-
"""舆情数据读取智能体（NewsRetrievalAgent）

角色定位：全链路舆情数据的唯一入口。

架构重点：
  本 Agent 不再做实时网络数据采集。
  数据采集由后台定时任务（core/news_collector_job.py）完成，
  本 Agent 仅从本地 LanceDB 读取已采集并预处理好的数据。
  这将分析响应时间从 300s+ 降低到 <1s。

核心职责：
  1. 从本地 LanceDB 读取指定标的的预采集数据
  2. 按时间范围/关键词过滤
  3. 数据质量校验
  4. 输出标准化 NewsRetrievalOutput
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from core.config import SystemConfig
from core.llm import LLMClient
from core.news_collector_job import read_local_news, get_status as get_collect_status
from core.schemas import AgentStatus, NewsRetrievalOutput


class NewsRetrievalAgent(BaseAgent):
    """舆情数据读取智能体——从本地 LanceDB 读取预采集数据"""

    name = "news_retrieval"
    description = "从本地向量数据库读取已采集的舆情数据，零网络延迟"

    SYSTEM_PROMPT = (
        "你是舆情数据采集与预处理专家。\n"
        "你的唯一职责是从本地数据库读取已采集的舆情数据并结构化输出。\n"
        "你绝对不做事件分类、情绪判断、基本面分析。\n"
        "你绝对不修改舆情原文语义，仅做结构化封装。\n"
    )

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config: Optional[SystemConfig] = None,
    ) -> None:
        super().__init__(llm_client=llm_client, config=config)
        self.logger.info("NewsRetrievalAgent 初始化 (本地读取模式)")

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        task_id = state.get("task_id", "")
        symbol, name, time_range, topics = self._extract_params(state)

        self.logger.info(
            "舆情数据读取 | symbol=%s name=%s range=%s~%s",
            symbol, name, time_range.get("start"), time_range.get("end"),
        )

        local_items = read_local_news(
            symbol=symbol,
            start_time=time_range.get("start", ""),
            end_time=time_range.get("end", ""),
            limit=200,
        )

        if topics and local_items:
            local_items = self._filter_by_topics(local_items, topics)

        table_name = (
            f"news_{symbol.replace('.', '_').lower()}" if symbol else "news_general"
        )

        if not local_items:
            return self._empty_result(
                task_id, symbol, name, time_range, table_name, start
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
                "data_source": "local_lancedb",
            },
            data_quality_report={
                "raw_collected": len(local_items),
                "after_clean": len(local_items),
                "vectorized": len(local_items),
                "source_breakdown": self._source_stats(local_items),
                "note": "数据来自本地预采集，非实时抓取",
            },
            execution_log={"duration_ms": duration, "mode": "local_read"},
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
        else:
            task = state.get("task", {})
            symbol = task.get("symbol", "")
            name = task.get("name", "")
            tr = task.get("time_range", {})
            topics = task.get("topics", [])
        return symbol, name, tr, topics

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

    def _empty_result(self, task_id, symbol, name, time_range, table_name, start):
        duration = int((time.time() - start) * 1000)

        collect_status = get_collect_status()
        symbols_configured = [
            s["symbol"] for s in collect_status.get("symbols", [])
        ]

        hint = ""
        if symbol and symbol not in symbols_configured:
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
            vector_db_index_info={"table_name": f"{table_name}(empty)"},
            data_quality_report={
                "raw_collected": 0, "after_clean": 0, "vectorized": 0,
                "hint": hint,
            },
            execution_log={
                "duration_ms": duration, "reason": "本地无数据",
                "mode": "local_read",
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
