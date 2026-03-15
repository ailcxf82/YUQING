# -*- coding: utf-8 -*-
"""事件驱动策略生成智能体（StrategyGenerationAgent）

角色定位：策略落地核心节点。
仅做策略逻辑生成，不做风控校验、合规校验。

核心职责：
  1. 策略适配性判断
  2. 核心策略逻辑生成
  3. 入场与出场条件设定
  4. 参考仓位区间建议
  5. 策略核心关注指标
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from agents.base import BaseAgent
from core.schemas import StrategyGenerationOutput, FullLinkState, AgentStatus
from core.prompts import get_prompt


class StrategyGenerationAgent(BaseAgent):
    """事件驱动策略生成智能体"""

    name = "strategy_generation"
    description = "基于舆情结论生成事件驱动策略、入场/出场条件、仓位建议"

    SYSTEM_PROMPT = get_prompt("strategy_generation", "agent_system")
    STRATEGY_PROMPT = get_prompt("strategy_generation", "strategy")

    def run(self, state: FullLinkState) -> Dict[str, Any]:
        start = time.time()
        task_id = state.get("task_id", "")
        task_info = state.get("task_base_info", {})
        event_output = state.get("event_classification_output", {})
        sentiment_output = state.get("sentiment_analysis_output", {})
        fundamental_output = state.get("fundamental_impact_output", {})
        industry_output = state.get("industry_chain_output", {})

        core_news = event_output.get("core_news_list", [])
        if not core_news:
            return self._empty_output(task_id, start, "无核心舆情")

        self.logger.info("策略生成启动 | task=%s", task_id)

        context = self._build_context(
            task_info, event_output, sentiment_output,
            fundamental_output, industry_output,
        )

        try:
            result = self.llm.chat_json(
                system_prompt=self.STRATEGY_PROMPT,
                user_prompt=context,
                temperature=0.2,
            )
        except Exception as e:
            self.logger.warning("策略LLM生成失败: %s", e)
            result = self._fallback_strategy(sentiment_output, fundamental_output)

        adaptability = result.get("adaptability", {})
        core_logic = result.get("core_logic", "")
        direction = result.get("direction", "观望")
        entry = result.get("entry_conditions", [])
        tp = result.get("take_profit", [])
        sl = result.get("stop_loss", [])
        position = result.get("position_range", "")
        period = result.get("holding_period", "")
        focus = result.get("focus_indicators", [])

        duration = int((time.time() - start) * 1000)
        output = StrategyGenerationOutput(
            task_id=task_id,
            strategy_adaptability_judgment=adaptability,
            core_strategy_logic=f"{core_logic}（仅供参考，不构成投资建议）",
            entry_exit_conditions={
                "direction": direction,
                "entry": entry,
                "take_profit": tp,
                "stop_loss": sl,
                "holding_period": period,
            },
            reference_position_range=f"{position}（仅供参考）",
            core_focus_indicators=focus,
            execution_log={"duration_ms": duration},
        )

        agent_out = self._make_output(
            AgentStatus.SUCCESS, data=output.model_dump(), duration_ms=duration
        )
        self.logger.info("策略生成完成 | direction=%s", direction)
        return {
            "strategy_generation_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "strategy_generation_done",
        }

    @staticmethod
    def _build_context(task_info, event, sentiment, fundamental, industry) -> str:
        idx = sentiment.get("target_sentiment_index", {}).get("index", 50)
        certainty = fundamental.get("impact_certainty_rating", "中确定性")
        targets = task_info.get("target_name", [])
        name = targets[0] if targets else ""
        core_news = event.get("core_news_list", [])
        top_events = [n.get("title", "") for n in core_news[:3]]

        return (
            f"标的：{name}\n"
            f"核心事件：{'；'.join(top_events)}\n"
            f"情绪指数：{idx}\n"
            f"影响确定性：{certainty}\n"
            f"产业链景气度：{industry.get('industry_boom_change_judgment', {}).get('direction', '未知')}\n"
            f"分析深度：{task_info.get('analysis_depth', '标准版')}"
        )

    @staticmethod
    def _fallback_strategy(sentiment, fundamental):
        idx = sentiment.get("target_sentiment_index", {}).get("index", 50)
        direction = "做多" if idx >= 60 else "做空" if idx <= 40 else "观望"
        return {
            "adaptability": {"suitable": idx != 50, "type": "事件驱动", "reason": "规则兜底"},
            "core_logic": f"基于情绪指数{idx}的方向性判断",
            "direction": direction,
            "entry_conditions": [],
            "take_profit": [],
            "stop_loss": [],
            "position_range": "5%-10%",
            "holding_period": "1-5个交易日",
            "focus_indicators": ["情绪指数变化", "成交量变化"],
        }

    def _empty_output(self, task_id, start, reason):
        duration = int((time.time() - start) * 1000)
        output = StrategyGenerationOutput(task_id=task_id, execution_log={"reason": reason})
        agent_out = self._make_output(AgentStatus.SKIPPED, data={"reason": reason}, duration_ms=duration)
        return {"strategy_generation_output": output.model_dump(), "full_link_execution_log": [agent_out], "current_step": "strategy_generation_skipped"}
