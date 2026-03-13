# -*- coding: utf-8 -*-
"""深度投研智能体（DeepResearchAgent）—— Phase 3 完整实现

全流程：
  基本面数据获取 → 事件影响链路拆解 → 产业链传导分析 →
  历史同类事件回测 → 综合价值评估

输入：舆情分析结果（SentimentAgent 输出）、标的基本面数据
输出：深度分析报告（影响链路图、产业链传导、历史回测、受益/受损清单）
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from core.impact_analyzer import ImpactAnalyzer
from core.schemas import AgentState, AgentStatus


class DeepResearchAgent(BaseAgent):
    """深度投研智能体——集成影响链路推演 + 产业链分析 + 历史回测"""

    name = "deep_research"
    description = "舆情-基本面影响链路推演、产业链传导、历史回测、价值判断"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pro: Optional[Any] = None
        self._impact: Optional[ImpactAnalyzer] = None

    def _get_pro(self) -> Any:
        if self._pro is None:
            import tushare as ts
            token = self.config.tushare_token
            if not token:
                raise EnvironmentError("未配置 TUSHARE_TOKEN")
            self._pro = ts.pro_api(token)
        return self._pro

    def _get_impact_analyzer(self) -> ImpactAnalyzer:
        if self._impact is None:
            try:
                pro = self._get_pro()
            except Exception:
                pro = None
            self._impact = ImpactAnalyzer(self.llm, pro)
        return self._impact

    def run(self, state: AgentState) -> Dict[str, Any]:
        start = time.time()
        task = state["task"]
        sentiment = state.get("sentiment_result", {})
        events = sentiment.get("events", [])

        if not events:
            return self._skip_result(start, "无舆情事件输入")

        symbol = task.get("symbol", "")
        name = task.get("name", "")
        industry = task.get("industry", "")
        ts_code = symbol.strip().upper()

        self.logger.info(
            "深度投研启动 | symbol=%s name=%s events=%d",
            ts_code, name, len(events),
        )

        # ── 1. 获取基本面数据 ──
        financials = self._fetch_financials(ts_code)

        # ── 2. 筛选重点事件进行深度分析 ──
        key_events = self._select_key_events(events)
        self.logger.info("筛选重点事件 %d/%d 条进行深度分析", len(key_events), len(events))

        # ── 3. 全维度深度分析 ──
        analyzer = self._get_impact_analyzer()
        analysis = analyzer.full_analysis(
            events=key_events,
            company_name=name,
            ts_code=ts_code,
            industry=industry,
            financials=financials,
        )

        # ── 4. 综合价值评估 ──
        value_assessment = self._assess_value(
            events, financials, analysis, sentiment
        )

        # ── 构建输出 ──
        duration = int((time.time() - start) * 1000)
        research_result = {
            "symbol": symbol,
            "name": name,
            "industry": industry,
            "financials": financials,
            "key_event_count": len(key_events),
            "impact_chains": analysis.get("impact_chains", []),
            "industry_analysis": analysis.get("industry_analysis", {}),
            "backtest_results": analysis.get("backtest_results", []),
            "value_assessment": value_assessment,
            "emotion_context": {
                "overall_score": sentiment.get("overall_score", 50),
                "emotion_index": sentiment.get("emotion_index", {}),
                "risk_level": sentiment.get("alerts", {}).get("risk_level", "低风险"),
            },
        }

        output = self._make_output(
            AgentStatus.SUCCESS, data=research_result, duration_ms=duration
        )
        self.logger.info(
            "深度投研完成 | chains=%d backtests=%d assessment=%s duration=%dms",
            len(analysis.get("impact_chains", [])),
            len(analysis.get("backtest_results", [])),
            value_assessment.get("conclusion", ""),
            duration,
        )
        return {
            "research_result": research_result,
            "agent_outputs": [output],
            "current_step": "deep_research_done",
        }

    # ── 基本面数据获取 ──

    def _fetch_financials(self, ts_code: str) -> Dict[str, Any]:
        """获取标的基本面数据（PE/PB/市值/现金流等）"""
        result: Dict[str, Any] = {}
        try:
            pro = self._get_pro()

            df_basic = pro.daily_basic(
                ts_code=ts_code,
                fields="ts_code,trade_date,pe,pe_ttm,pb,total_mv,circ_mv,turnover_rate"
            )
            if df_basic is not None and not df_basic.empty:
                latest = df_basic.sort_values("trade_date", ascending=False).iloc[0]
                result.update({
                    "pe": self._safe_float(latest.get("pe")),
                    "pe_ttm": self._safe_float(latest.get("pe_ttm")),
                    "pb": self._safe_float(latest.get("pb")),
                    "total_mv": self._safe_float(latest.get("total_mv")),
                    "circ_mv": self._safe_float(latest.get("circ_mv")),
                    "turnover_rate": self._safe_float(latest.get("turnover_rate")),
                    "trade_date": str(latest.get("trade_date", "")),
                })

            df_income = pro.income(
                ts_code=ts_code,
                fields="end_date,revenue,n_income,n_income_attr_p,total_profit"
            )
            if df_income is not None and not df_income.empty:
                latest_inc = df_income.sort_values("end_date", ascending=False).iloc[0]
                result["income"] = {
                    "end_date": str(latest_inc.get("end_date", "")),
                    "revenue": self._safe_float(latest_inc.get("revenue")),
                    "net_income": self._safe_float(latest_inc.get("n_income_attr_p")),
                    "total_profit": self._safe_float(latest_inc.get("total_profit")),
                }

        except Exception as e:
            self.logger.warning("基本面数据获取失败: %s", e)

        return result

    # ── 重点事件筛选 ──

    @staticmethod
    def _select_key_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """筛选重点事件进行深度分析

        优先级：影响力分数 > 情感强度 > 事件类别
        """
        scored = []
        for e in events:
            priority = e.get("influence_score", 0)
            polarity = e.get("polarity", "中性")
            if polarity in ("强正向", "强负向"):
                priority += 20
            elif polarity in ("弱正向", "弱负向"):
                priority += 10
            category = e.get("event_category", "")
            if category in ("正向事件", "负向事件"):
                priority += 15
            elif category == "不确定性事件":
                priority += 5
            scored.append((priority, e))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:8]]

    # ── 综合价值评估 ──

    def _assess_value(
        self,
        events: List[Dict[str, Any]],
        financials: Dict[str, Any],
        analysis: Dict[str, Any],
        sentiment: Dict[str, Any],
    ) -> Dict[str, Any]:
        """综合所有分析维度给出价值评估"""
        pos_events = sum(
            1 for e in events if e.get("event_category") == "正向事件"
        )
        neg_events = sum(
            1 for e in events if e.get("event_category") == "负向事件"
        )
        emotion_idx = sentiment.get("emotion_index", {}).get("index", 50)
        risk_level = sentiment.get("alerts", {}).get("risk_level", "低风险")

        impact_chains = analysis.get("impact_chains", [])
        positive_impacts = sum(
            1 for c in impact_chains
            for d in c.get("impact_dimensions", [])
            if d.get("direction") == "正向"
        )
        negative_impacts = sum(
            1 for c in impact_chains
            for d in c.get("impact_dimensions", [])
            if d.get("direction") == "负向"
        )

        pe = financials.get("pe", 0)
        pb = financials.get("pb", 0)
        valuation_signal = "合理"
        if pe and pe > 0:
            if pe < 15:
                valuation_signal = "偏低"
            elif pe > 50:
                valuation_signal = "偏高"

        score = 50
        score += (pos_events - neg_events) * 5
        score += (positive_impacts - negative_impacts) * 3
        score += (emotion_idx - 50) * 0.3
        if valuation_signal == "偏低":
            score += 5
        elif valuation_signal == "偏高":
            score -= 5
        if risk_level in ("高风险", "重大风险"):
            score -= 15

        score = max(0, min(100, score))

        if score >= 70:
            conclusion = "正面——舆情与基本面共振向好，存在投资价值"
        elif score >= 55:
            conclusion = "偏正面——整体偏积极但需关注部分风险因素"
        elif score >= 45:
            conclusion = "中性——多空因素交织，需进一步观察"
        elif score >= 30:
            conclusion = "偏负面——风险因素占主导，建议谨慎"
        else:
            conclusion = "负面——重大风险信号，建议回避或减仓"

        return {
            "score": round(score, 1),
            "conclusion": conclusion,
            "positive_events": pos_events,
            "negative_events": neg_events,
            "positive_impacts": positive_impacts,
            "negative_impacts": negative_impacts,
            "emotion_index": emotion_idx,
            "risk_level": risk_level,
            "valuation_signal": valuation_signal,
            "pe": pe,
            "pb": pb,
        }

    # ── 工具方法 ──

    @staticmethod
    def _safe_float(val: Any) -> float:
        try:
            f = float(val)
            return round(f, 4) if f == f else 0.0  # NaN check
        except (TypeError, ValueError):
            return 0.0

    def _skip_result(self, start: float, reason: str) -> Dict[str, Any]:
        duration = int((time.time() - start) * 1000)
        output = self._make_output(
            AgentStatus.SKIPPED,
            data={"reason": reason},
            duration_ms=duration,
        )
        return {
            "research_result": {"reason": reason},
            "agent_outputs": [output],
            "current_step": "deep_research_skipped",
        }
