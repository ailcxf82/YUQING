# -*- coding: utf-8 -*-
"""策略落地智能体（StrategyAgent）

核心职责：事件驱动策略触发、风险预警、止损止盈规则生成。
输入：舆情分析结果、深度研报
输出：策略建议、预警信号、风控规则

Phase 1 为骨架实现：基于规则引擎生成基础策略框架。
后续阶段将完善参数精细化与回测验证逻辑。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from agents.base import BaseAgent
from core.schemas import AgentState, AgentStatus

RISK_PROFILES = {
    "保守": {"position_pct": 30, "stop_loss_pct": 3, "tp_tiers": [5, 8, 12]},
    "稳健": {"position_pct": 50, "stop_loss_pct": 5, "tp_tiers": [8, 15, 25]},
    "进取": {"position_pct": 80, "stop_loss_pct": 8, "tp_tiers": [10, 20, 35]},
}


class StrategyAgent(BaseAgent):
    """策略落地智能体"""

    name = "strategy"
    description = "事件驱动策略触发、风险预警、止损止盈规则生成"

    def _determine_direction(self, research: Dict) -> str:
        bullish = research.get("bullish_count", 0)
        bearish = research.get("bearish_count", 0)
        if bullish > bearish:
            return "做多"
        if bearish > bullish:
            return "做空"
        return "观望"

    def _build_strategy(
        self,
        task: Dict,
        sentiment: Dict,
        research: Dict,
    ) -> Dict[str, Any]:
        risk_pref = task.get("risk_preference", "稳健")
        profile = RISK_PROFILES.get(risk_pref, RISK_PROFILES["稳健"])
        max_pos = min(profile["position_pct"], task.get("max_position_pct", 30))
        direction = self._determine_direction(research)
        horizon = task.get("investment_horizon", "中线")

        overall_score = sentiment.get("overall_score", 5)
        assessment = research.get("value_assessment", "")

        strategy = {
            "direction": direction,
            "strategy_type": (
                "基本面价值" if direction == "做多" and horizon in ("中线", "长线")
                else "事件驱动" if direction == "做多"
                else "风险规避" if direction == "做空"
                else "观望"
            ),
            "core_logic": (
                f"综合情绪得分 {overall_score}，{assessment}。"
                f"策略方向为{direction}，匹配{horizon}投资周期。"
            ),
            "position": {
                "total_pct": max_pos,
                "first_build_pct": round(max_pos * 0.5, 1),
            },
            "stop_loss_pct": profile["stop_loss_pct"],
            "take_profit_tiers": profile["tp_tiers"],
            "validity": f"{'1-10' if horizon == '短线' else '10-60' if horizon == '中线' else '60-250'}个交易日",
            "risk_warnings": [
                "本策略基于历史数据与模型假设，不保证未来表现",
                "所有策略须配合人工判断，最终决策责任由用户承担",
            ],
        }
        return strategy

    def run(self, state: AgentState) -> Dict[str, Any]:
        start = time.time()
        task = state["task"]
        sentiment = state.get("sentiment_result", {})
        research = state.get("research_result", {})

        if not sentiment and not research:
            duration = int((time.time() - start) * 1000)
            output = self._make_output(
                AgentStatus.SKIPPED,
                data={"reason": "无舆情与投研数据"},
                duration_ms=duration,
            )
            return {
                "strategy_result": {},
                "agent_outputs": [output],
                "current_step": "strategy_skipped",
            }

        self.logger.info("策略生成 | symbol=%s", task.get("symbol"))
        strategy = self._build_strategy(task, sentiment, research)

        strategy_result = {
            "symbol": task.get("symbol"),
            "name": task.get("name"),
            "strategy": strategy,
        }

        duration = int((time.time() - start) * 1000)
        output = self._make_output(
            AgentStatus.SUCCESS, data=strategy_result, duration_ms=duration
        )
        return {
            "strategy_result": strategy_result,
            "agent_outputs": [output],
            "current_step": "strategy_done",
        }
