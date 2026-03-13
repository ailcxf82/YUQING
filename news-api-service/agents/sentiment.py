# -*- coding: utf-8 -*-
"""舆情分析智能体（SentimentAgent）—— Phase 3 完整实现

全流程：
  基础要素识别 → 事件分类 → 影响力评分 → 细粒度情感分析 →
  动态情绪指数 → 一致性校验 → 噪音过滤 → 风险预警

输入：结构化舆情数据集（来自 NewsRetrievalAgent）
输出：舆情分析报告、情绪量化指标、事件标签、预警信号
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from core.alert_system import AlertSystem
from core.entity_linker import EntityLinker
from core.event_classifier import EventClassifier
from core.influence_scorer import InfluenceScorer
from core.schemas import AgentState, AgentStatus
from core.sentiment_engine import SentimentEngine


class SentimentAgent(BaseAgent):
    """舆情分析核心智能体——集成全部 Phase 3 分析引擎"""

    name = "sentiment"
    description = "舆情要素识别、事件分类、细粒度情绪量化、影响力评估、风险预警"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.entity_linker = EntityLinker(self.llm)
        self.event_classifier = EventClassifier(self.llm)
        self.sentiment_engine = SentimentEngine(self.llm)
        self.influence_scorer = InfluenceScorer()
        self.alert_system = AlertSystem()

    def run(self, state: AgentState) -> Dict[str, Any]:
        start = time.time()
        task = state["task"]
        news_data = state.get("news_data", {})
        news_items = news_data.get("news_items", [])

        if not news_items:
            return self._skip_result(start, "无舆情数据输入")

        symbol = task.get("symbol", "")
        name = task.get("name", "")
        self.logger.info(
            "舆情分析启动 | symbol=%s name=%s news=%d",
            symbol, name, len(news_items),
        )

        # ── 1. 实体链接与标的关联 ──
        entity_results = self._extract_entities(news_items)

        # ── 2. 事件分类 ──
        classification_results = self._classify_events(news_items)

        # ── 3. 细粒度情感分析 ──
        sentiment_results = self._analyze_sentiment(news_items)

        # ── 4. 合并结果 + 影响力评分 ──
        events = self._merge_results(
            news_items, entity_results, classification_results, sentiment_results
        )

        # ── 5. 传播力分析 ──
        events = InfluenceScorer.classify_propagation(events)
        timestamps = [e.get("published_at", "") for e in events if e.get("published_at")]
        spread_info = InfluenceScorer.track_spread_velocity(timestamps)

        # ── 6. 噪音过滤 ──
        events = SentimentEngine.filter_noise(events)
        effective_events = [e for e in events if not e.get("is_noise", False)]

        # ── 7. 动态情绪指数 ──
        weights = [e.get("source_weight", 0.5) for e in effective_events]
        emotion_index = SentimentEngine.build_emotion_index(
            effective_events, weights
        )

        # ── 8. 一致性校验 ──
        consistency = SentimentEngine.check_consistency(effective_events)

        # ── 9. 风险预警 ──
        alert_result = self.alert_system.evaluate(
            effective_events, emotion_index
        )

        # ── 构建输出 ──
        duration = int((time.time() - start) * 1000)
        sentiment_result = {
            "symbol": symbol,
            "name": name,
            "events": events,
            "effective_event_count": len(effective_events),
            "noise_filtered_count": len(events) - len(effective_events),
            "emotion_index": emotion_index,
            "consistency": consistency,
            "spread_analysis": spread_info,
            "alerts": alert_result,
            "overall_sentiment": self._compute_overall(emotion_index),
            "overall_score": emotion_index.get("index", 50.0),
            "news_count": len(news_items),
        }

        output = self._make_output(
            AgentStatus.SUCCESS, data=sentiment_result, duration_ms=duration
        )
        self.logger.info(
            "舆情分析完成 | events=%d emotion=%.1f trend=%s risk=%s duration=%dms",
            len(events), emotion_index.get("index", 50),
            emotion_index.get("trend", "平稳"),
            alert_result.get("risk_level", "低风险"),
            duration,
        )
        return {
            "sentiment_result": sentiment_result,
            "agent_outputs": [output],
            "current_step": "sentiment_done",
        }

    # ── 分析子流程 ──

    def _extract_entities(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """逐条提取实体"""
        results = []
        for item in items[:30]:
            title = item.get("title", "")
            content = item.get("text", item.get("content", ""))
            r = self.entity_linker.extract_entities(title, content)
            results.append(r)
        while len(results) < len(items):
            results.append({})
        return results

    def _classify_events(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """逐条事件分类"""
        results = []
        for i, item in enumerate(items):
            title = item.get("title", "")
            content = item.get("text", item.get("content", ""))
            if i < 30:
                r = self.event_classifier.classify(title, content)
            else:
                r = EventClassifier._rule_classify(title + content)
            results.append(r)
        return results

    def _analyze_sentiment(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """逐条情感分析"""
        results = []
        for i, item in enumerate(items):
            title = item.get("title", "")
            content = item.get("text", item.get("content", ""))
            if i < 30:
                r = self.sentiment_engine.analyze(title, content)
            else:
                r = SentimentEngine._rule_sentiment(title + content)
            results.append(r)
        return results

    def _merge_results(
        self,
        news_items: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
        classifications: List[Dict[str, Any]],
        sentiments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """合并所有分析结果，计算影响力评分"""
        events = []
        for i, item in enumerate(news_items):
            ent = entities[i] if i < len(entities) else {}
            cls = classifications[i] if i < len(classifications) else {}
            sent = sentiments[i] if i < len(sentiments) else {}

            event = {
                "event_id": item.get("id", f"E{i+1}"),
                "title": item.get("title", ""),
                "core_summary": item.get("text", item.get("content", ""))[:200],
                "published_at": item.get("published_at", item.get("publish_time", "")),
                "source_name": item.get("source_name", item.get("source", "")),
                "source_level": item.get("source_level", "C"),
                "source_weight": float(item.get("source_weight", 0.5)),
                "url": item.get("url", ""),
                # 实体
                "primary_company": ent.get("primary_company", ""),
                "primary_stock_code": ent.get("primary_stock_code", ""),
                "related_companies": ent.get("related_companies", []),
                "entities": ent.get("entities", []),
                # 事件分类
                "event_category": cls.get("category", "中性事件"),
                "sub_label": cls.get("sub_label", "无实质影响"),
                "classification_confidence": cls.get("confidence", 0.5),
                "impact_level": cls.get("impact_level", "公司级"),
                "classification_reason": cls.get("reason", ""),
                # 情感分析
                "polarity": sent.get("polarity", "中性"),
                "score": sent.get("score", 50.0),
                "sentiment_driver": sent.get("driver", ""),
                "sentiment_reasoning": sent.get("reasoning", ""),
                "complexity": sent.get("complexity", "simple"),
                "key_phrases": sent.get("key_phrases", []),
                # 从 item 继承
                "spread_count": int(item.get("spread_count", 0)),
                "keywords": item.get("keywords", []),
                "content_hash": item.get("content_hash", ""),
            }

            event["influence_score"] = self.influence_scorer.score(
                source_weight=event["source_weight"],
                spread_count=event["spread_count"],
                event_sub_label=event["sub_label"],
                impact_level=event["impact_level"],
                confidence=event["classification_confidence"],
            )

            event["risk_level"] = self.alert_system.grade_event_risk(event)

            events.append(event)

        events.sort(key=lambda e: e.get("influence_score", 0), reverse=True)
        return events

    @staticmethod
    def _compute_overall(emotion_index: Dict[str, Any]) -> str:
        idx = emotion_index.get("index", 50.0)
        if idx >= 65:
            return "利好"
        elif idx <= 35:
            return "利空"
        else:
            return "中性"

    def _skip_result(self, start: float, reason: str) -> Dict[str, Any]:
        duration = int((time.time() - start) * 1000)
        output = self._make_output(
            AgentStatus.SKIPPED,
            data={"reason": reason},
            duration_ms=duration,
        )
        return {
            "sentiment_result": {"reason": reason},
            "agent_outputs": [output],
            "current_step": "sentiment_skipped",
        }
