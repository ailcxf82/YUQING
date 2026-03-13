# -*- coding: utf-8 -*-
"""基本面影响链路推演智能体（FundamentalImpactAgent）

角色定位：深度投研核心节点。
仅做舆情对标的基本面的影响分析，不做产业链传导、策略生成。

性能优化：
  - 将多个事件合并为单次综合推演 LLM 调用
  - 原来 5 事件 = 5 次 LLM → 现在合并为 1 次
  - 历史回测保留 1 次单独调用
  - 总计从 6-7 次 LLM 降至 2-3 次
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from agents.base import BaseAgent
from core.impact_analyzer import ImpactAnalyzer
from core.schemas import FundamentalImpactOutput, FullLinkState, AgentStatus


class FundamentalImpactAgent(BaseAgent):
    """基本面影响链路推演智能体——批量综合推演模式"""

    name = "fundamental_impact"
    description = "多事件综合基本面影响推演、历史回测"

    SYSTEM_PROMPT = (
        "你是机构级投研分析师。\n"
        "你的唯一职责是分析舆情事件对标的基本面的影响。\n"
        "你绝对不做产业链传导分析、关联标的识别。\n"
        "你绝对不生成交易策略、买卖点位、仓位建议。\n"
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pro: Optional[Any] = None
        self._analyzer: Optional[ImpactAnalyzer] = None

    def _get_pro(self) -> Any:
        if self._pro is None:
            import tushare as ts
            from core.datasources.tushare_source import TushareNewsSource
            TushareNewsSource._bypass_proxy()
            token = self.config.tushare_token
            if token:
                self._pro = ts.pro_api(token)
        return self._pro

    def _get_analyzer(self) -> ImpactAnalyzer:
        if self._analyzer is None:
            self._analyzer = ImpactAnalyzer(self.llm, self._get_pro())
        return self._analyzer

    def run(self, state: FullLinkState) -> Dict[str, Any]:
        start = time.time()
        task_id = state.get("task_id", "")
        task_info = state.get("task_base_info", {})
        event_output = state.get("event_classification_output", {})
        sentiment_output = state.get("sentiment_analysis_output", {})

        core_news = event_output.get("core_news_list", [])
        classifications = event_output.get("event_classification_result", [])
        sentiments = sentiment_output.get("news_sentiment_detail", [])

        if not core_news:
            return self._empty_output(task_id, start, "无核心舆情")

        targets = task_info.get("target_code", [])
        names = task_info.get("target_name", [])
        ts_code = targets[0] if targets else ""
        company = names[0] if names else ""

        self.logger.info(
            "基本面推演启动(批量模式) | task=%s ts_code=%s events=%d",
            task_id, ts_code, len(core_news),
        )

        analyzer = self._get_analyzer()
        events_for_analysis = self._build_events(core_news, classifications, sentiments)
        financials = self._fetch_financials(ts_code)

        # 1. 综合批量影响分析（1次LLM，替代原来5次）
        batch_impact = analyzer.analyze_impact_batch(
            events_for_analysis[:10], company, financials, ts_code
        )
        self.logger.info("综合影响分析完成(1次LLM调用)")

        # 2. 历史回测（仅1次LLM）
        backtest = {}
        key_events = [
            e for e in events_for_analysis
            if e.get("event_category") in ("正向事件", "负向事件")
        ]
        if key_events:
            ev = key_events[0]
            backtest = analyzer.historical_backtest(
                ev.get("core_summary", ""),
                ev.get("event_category", ""),
                ev.get("sub_label", ""),
                company, ts_code,
            )
            self.logger.info("历史回测完成(1次LLM调用)")

        # 3. 影响确定性评级（纯计算）
        certainty = self._rate_certainty(events_for_analysis, sentiment_output)

        # 4. 周期与量级（从批量结果提取）
        combined = batch_impact.get("combined_assessment", {})
        cycle_scale = {
            "short_term_probability": combined.get("short_term", {}).get("probability", 0.5),
            "mid_term_probability": combined.get("mid_term", {}).get("probability", 0.3),
            "long_term_probability": combined.get("long_term", {}).get("probability", 0.2),
            "dominant_cycle": "短期" if combined.get("short_term", {}).get("probability", 0) > 0.5 else "中期",
        }

        duration = int((time.time() - start) * 1000)
        llm_calls = 1 + (1 if key_events else 0)

        output = FundamentalImpactOutput(
            task_id=task_id,
            impact_logic_breakdown={
                "batch_impact": batch_impact,
                "financials": financials,
            },
            impact_cycle_and_scale=cycle_scale,
            historical_event_backtest=backtest,
            impact_certainty_rating=certainty,
            full_impact_link_report={
                "company": company, "ts_code": ts_code,
                "events_analyzed": len(events_for_analysis[:10]),
                "llm_calls": llm_calls,
                "mode": "batch_aggregate",
            },
            execution_log={"duration_ms": duration, "llm_calls": llm_calls},
        )

        agent_out = self._make_output(
            AgentStatus.SUCCESS, data=output.model_dump(), duration_ms=duration
        )
        self.logger.info(
            "基本面推演完成 | events=%d llm_calls=%d certainty=%s duration=%dms",
            len(events_for_analysis[:10]), llm_calls, certainty, duration,
        )
        return {
            "fundamental_impact_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "fundamental_impact_done",
        }

    def _fetch_financials(self, ts_code: str) -> Dict[str, Any]:
        try:
            pro = self._get_pro()
            if not pro:
                return {}
            df = pro.daily_basic(
                ts_code=ts_code,
                fields="ts_code,trade_date,pe,pe_ttm,pb,total_mv"
            )
            if df is not None and not df.empty:
                latest = df.sort_values("trade_date", ascending=False).iloc[0]
                return {
                    "pe": round(float(latest.get("pe", 0) or 0), 2),
                    "pb": round(float(latest.get("pb", 0) or 0), 2),
                    "total_mv": round(float(latest.get("total_mv", 0) or 0), 2),
                }
        except Exception as e:
            self.logger.warning("基本面数据获取失败: %s", e)
        return {}

    @staticmethod
    def _build_events(news, cls_list, sentiments):
        events = []
        sent_map = {s.get("news_id", ""): s for s in sentiments}
        cls_map = {c.get("news_id", ""): c for c in cls_list}
        for item in news:
            nid = item.get("news_id", "")
            cls = cls_map.get(nid, {})
            sent = sent_map.get(nid, {})
            events.append({
                "news_id": nid,
                "core_summary": item.get("title", "") + " " + item.get("content", item.get("text", ""))[:200],
                "event_category": cls.get("category", item.get("event_category", "")),
                "sub_label": cls.get("sub_label", item.get("sub_label", "")),
                "polarity": sent.get("polarity", "中性"),
                "score": sent.get("score", 50),
            })
        return events

    @staticmethod
    def _rate_certainty(events, sentiment_output):
        idx = sentiment_output.get("target_sentiment_index", {}).get("index", 50)
        strong = sum(
            1 for e in events
            if e.get("polarity") in ("强正向", "强负向")
            and e.get("event_category") in ("正向事件", "负向事件")
        )
        if strong >= 3 and abs(idx - 50) > 20:
            return "高确定性"
        elif strong >= 1 and abs(idx - 50) > 10:
            return "中确定性"
        elif any(e.get("event_category") == "不确定性事件" for e in events):
            return "不确定性"
        return "低确定性"

    def _empty_output(self, task_id, start, reason):
        duration = int((time.time() - start) * 1000)
        output = FundamentalImpactOutput(task_id=task_id, execution_log={"reason": reason})
        agent_out = self._make_output(AgentStatus.SKIPPED, data={"reason": reason}, duration_ms=duration)
        return {
            "fundamental_impact_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "fundamental_impact_skipped",
        }
