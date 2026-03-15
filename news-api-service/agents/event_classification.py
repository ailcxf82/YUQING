# -*- coding: utf-8 -*-
"""舆情要素识别与事件分类智能体（EventClassificationAgent）

性能策略（两阶段漏斗）：
  阶段1：规则引擎粗分类（200条 → 0次LLM，<100ms）
  阶段2：LLM 精分析 Top20 高价值条目（1次批量LLM调用，~30s）
  总计：从200+次LLM → 1次，耗时从450s → 30s
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from agents.base import BaseAgent
from core.entity_linker import EntityLinker
from core.event_classifier import EventClassifier
from core.influence_scorer import InfluenceScorer
from core.schemas import (
    EventClassificationOutput, FullLinkState, AgentStatus,
)
from core.prompts import get_prompt

LLM_TOP_N = 20


class EventClassificationAgent(BaseAgent):
    """舆情要素识别与事件分类智能体——两阶段漏斗"""

    name = "event_classification"
    description = "规则粗筛+LLM精分析Top20，极速事件分类"

    SYSTEM_PROMPT = get_prompt("event_classification", "agent_system")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.entity_linker = EntityLinker(self.llm)
        self.event_classifier = EventClassifier(self.llm)

    def run(self, state: FullLinkState) -> Dict[str, Any]:
        start = time.time()
        task_id = state.get("task_id", "")
        news_output = state.get("news_retrieval_output", {})
        news_items = news_output.get("news_structured_data", [])

        if not news_items:
            return self._empty_output(task_id, start, "无舆情数据")

        self.logger.info("事件分类启动 | task=%s news=%d", task_id, len(news_items))

        # ── 阶段1：全量规则粗分类（0次LLM，<100ms）──
        rule_results = []
        for item in news_items:
            text = item.get("title", "") + item.get("content", item.get("text", ""))
            rule_results.append(EventClassifier._rule_classify(text))

        # 粗排序：按规则置信度 × 信源权重 × 传播量
        scored_indices = []
        for i, item in enumerate(news_items):
            rc = rule_results[i]
            raw_score = (
                rc.get("confidence", 0.5) * 40
                + item.get("source_weight", 0.5) * 30
                + min(item.get("spread_count", 0) / 100, 1.0) * 30
            )
            if rc.get("category") in ("正向事件", "负向事件", "不确定性事件"):
                raw_score += 20
            scored_indices.append((i, raw_score))

        scored_indices.sort(key=lambda x: x[1], reverse=True)
        top_indices = set(idx for idx, _ in scored_indices[:LLM_TOP_N])

        # ── 阶段2：LLM 精分析 Top20（1次批量调用）──
        top_items = [news_items[i] for i in sorted(top_indices)]
        llm_calls = 0

        if top_items:
            try:
                llm_results = self.event_classifier.classify_aggregate(
                    top_items, batch_size=LLM_TOP_N
                )
                llm_calls = 1
                self.logger.info("LLM精分析完成 | top=%d", len(top_items))
            except Exception as e:
                self.logger.warning("LLM精分析失败: %s", e)
                llm_results = []

            sorted_top = sorted(top_indices)
            for j, orig_idx in enumerate(sorted_top):
                if j < len(llm_results):
                    rule_results[orig_idx] = llm_results[j]

        # ── 实体提取（仅Top20，1次批量LLM）──
        entity_results: List[Dict[str, Any]] = []
        if top_items:
            try:
                top_entities = self.entity_linker.extract_entities_batch(
                    top_items, batch_size=LLM_TOP_N
                )
                llm_calls += 1
            except Exception:
                top_entities = []

            top_entity_map = {}
            sorted_top = sorted(top_indices)
            for j, orig_idx in enumerate(sorted_top):
                if j < len(top_entities):
                    top_entity_map[orig_idx] = top_entities[j]

            for i, item in enumerate(news_items):
                if i in top_entity_map:
                    entity_results.append(top_entity_map[i])
                else:
                    entity_results.append({
                        "news_id": item.get("news_id", f"N{i}"),
                        "entities": [],
                        "primary_company": "",
                        "primary_stock_code": "",
                    })
        else:
            for i, item in enumerate(news_items):
                entity_results.append({
                    "news_id": item.get("news_id", f"N{i}"),
                    "entities": [],
                    "primary_company": "",
                    "primary_stock_code": "",
                })

        # ── 影响力评分（纯计算）──
        influence_results = []
        classification_results = rule_results
        for i, item in enumerate(news_items):
            cls = classification_results[i] if i < len(classification_results) else {}
            inf_score = InfluenceScorer.score(
                source_weight=item.get("source_weight", 0.5),
                spread_count=item.get("spread_count", 0),
                event_sub_label=cls.get("sub_label", ""),
                impact_level=cls.get("impact_level", "公司级"),
                confidence=cls.get("confidence", 0.5),
            )
            influence_results.append({
                "news_id": item.get("news_id", f"N{i}"),
                "influence_score": inf_score,
                "sub_label": cls.get("sub_label", ""),
                "impact_level": cls.get("impact_level", "公司级"),
            })

        # ── 核心舆情筛选 ──
        core_news = self._select_core_news(
            news_items, classification_results, influence_results
        )

        duration = int((time.time() - start) * 1000)
        output = EventClassificationOutput(
            task_id=task_id,
            entity_linking_result=entity_results,
            event_classification_result=classification_results,
            influence_score_result=influence_results,
            core_news_list=core_news,
            execution_log={
                "duration_ms": duration,
                "total": len(news_items),
                "llm_top_n": LLM_TOP_N,
                "llm_calls": llm_calls,
                "mode": "rule_first_llm_top_n",
            },
        )

        agent_out = self._make_output(
            AgentStatus.SUCCESS, data=output.model_dump(), duration_ms=duration
        )
        self.logger.info(
            "事件分类完成 | total=%d core=%d llm_calls=%d duration=%dms",
            len(news_items), len(core_news), llm_calls, duration,
        )
        return {
            "event_classification_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "event_classification_done",
        }

    @staticmethod
    def _select_core_news(
        news: List[Dict], classifications: List[Dict], influences: List[Dict]
    ) -> List[Dict[str, Any]]:
        merged = []
        for i, item in enumerate(news):
            cls = classifications[i] if i < len(classifications) else {}
            inf = influences[i] if i < len(influences) else {}
            merged.append({
                **item,
                "event_category": cls.get("category", "中性事件"),
                "sub_label": cls.get("sub_label", "无实质影响"),
                "classification_confidence": cls.get("confidence", 0.5),
                "impact_level": cls.get("impact_level", "公司级"),
                "influence_score": inf.get("influence_score", 0),
            })
        merged.sort(key=lambda x: x.get("influence_score", 0), reverse=True)
        threshold = 25.0
        core = [m for m in merged if m.get("influence_score", 0) >= threshold]
        if len(core) > 30:
            core = core[:30]
        return core or merged[:5]

    def _empty_output(self, task_id: str, start: float, reason: str) -> Dict[str, Any]:
        duration = int((time.time() - start) * 1000)
        output = EventClassificationOutput(
            task_id=task_id,
            execution_log={"duration_ms": duration, "reason": reason},
        )
        agent_out = self._make_output(
            AgentStatus.SKIPPED, data={"reason": reason}, duration_ms=duration
        )
        return {
            "event_classification_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "event_classification_skipped",
        }
