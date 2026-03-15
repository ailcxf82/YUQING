# -*- coding: utf-8 -*-
"""金融情绪量化与舆情评级智能体（SentimentAnalysisAgent）

角色定位：舆情分析核心业务节点。
仅做情绪量化、评级、指数构建，不做基本面推演、策略生成。

性能优化：
  - 批量聚合调用：30条/批 → 1次LLM
  - 200条核心舆情仅需 7 次 LLM 调用（原来 200 次）
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from agents.base import BaseAgent
from core.schemas import SentimentAnalysisOutput, FullLinkState, AgentStatus
from core.sentiment_engine import SentimentEngine
from core.prompts import get_prompt


class SentimentAnalysisAgent(BaseAgent):
    """金融情绪量化与舆情评级智能体——批量聚合模式"""

    name = "sentiment_analysis"
    description = "批量情绪判断、情绪指数构建、舆情评级"

    SYSTEM_PROMPT = get_prompt("sentiment", "agent_system")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.engine = SentimentEngine(self.llm)

    def run(self, state: FullLinkState) -> Dict[str, Any]:
        start = time.time()
        task_id = state.get("task_id", "")
        event_output = state.get("event_classification_output", {})
        core_news = event_output.get("core_news_list", [])

        if not core_news:
            return self._empty_output(task_id, start, "无核心舆情")

        self.logger.info(
            "情绪分析启动(批量模式) | task=%s core_news=%d", task_id, len(core_news)
        )

        # 上游 core_news 已限制在 30 条以内，1 次批量 LLM 即可
        detail = self.engine.analyze_aggregate(core_news, batch_size=30)
        llm_calls = (len(core_news) + 29) // 30
        self.logger.info("批量情感LLM完成 | items=%d llm_calls=%d", len(core_news), llm_calls)

        for i, item in enumerate(core_news):
            if i < len(detail):
                detail[i]["news_id"] = item.get("news_id", f"N{i}")
                detail[i]["influence_score"] = item.get("influence_score", 0)
                detail[i]["source_weight"] = item.get("source_weight", 0.5)

        self.logger.info("批量情感分析完成 | llm_calls=%d", llm_calls)

        # 2. 动态情绪指数
        weights = [d.get("source_weight", 0.5) for d in detail]
        sentiment_index = SentimentEngine.build_emotion_index(detail, weights)

        # 3. 一致性校验
        consistency = SentimentEngine.check_consistency(detail)

        # 4. 噪音过滤
        detail = SentimentEngine.filter_noise(detail)

        # 5. 综合评级
        ratings = self._compute_ratings(detail, sentiment_index)

        duration = int((time.time() - start) * 1000)
        output = SentimentAnalysisOutput(
            task_id=task_id,
            news_sentiment_detail=detail,
            target_sentiment_index=sentiment_index,
            sentiment_consistency_report=consistency,
            news_comprehensive_rating=ratings,
            execution_log={
                "duration_ms": duration,
                "analyzed": len(detail),
                "llm_calls": llm_calls,
                "mode": "batch_aggregate",
            },
        )

        agent_out = self._make_output(
            AgentStatus.SUCCESS, data=output.model_dump(), duration_ms=duration
        )
        self.logger.info(
            "情绪分析完成 | index=%.1f trend=%s llm_calls=%d duration=%dms",
            sentiment_index.get("index", 50), sentiment_index.get("trend", ""),
            llm_calls, duration,
        )
        return {
            "sentiment_analysis_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "sentiment_analysis_done",
        }

    @staticmethod
    def _compute_ratings(
        sentiments: List[Dict[str, Any]],
        index: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        idx = index.get("index", 50.0)
        overall = (
            "积极" if idx >= 70 else
            "谨慎乐观" if idx >= 55 else
            "中性" if idx >= 45 else
            "谨慎" if idx >= 30 else
            "负面"
        )

        ratings = []
        for s in sentiments:
            score = s.get("score", 50)
            influence = s.get("influence_score", 0)
            combined = score * 0.6 + influence * 0.4
            rating = (
                "积极" if combined >= 70 else
                "谨慎乐观" if combined >= 55 else
                "中性" if combined >= 45 else
                "谨慎" if combined >= 30 else
                "负面"
            )
            ratings.append({
                "news_id": s.get("news_id", ""),
                "polarity": s.get("polarity", "中性"),
                "score": score,
                "influence_score": influence,
                "combined_score": round(combined, 1),
                "rating": rating,
            })

        ratings.append({
            "news_id": "_overall",
            "overall_rating": overall,
            "emotion_index": idx,
        })
        return ratings

    def _empty_output(self, task_id: str, start: float, reason: str) -> Dict[str, Any]:
        duration = int((time.time() - start) * 1000)
        output = SentimentAnalysisOutput(
            task_id=task_id,
            execution_log={"duration_ms": duration, "reason": reason},
        )
        agent_out = self._make_output(
            AgentStatus.SKIPPED, data={"reason": reason}, duration_ms=duration
        )
        return {
            "sentiment_analysis_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "sentiment_analysis_skipped",
        }
