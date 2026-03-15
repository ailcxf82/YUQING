# -*- coding: utf-8 -*-
"""策略风控与止损止盈规则智能体（RiskControlAgent）

角色定位：策略落地的风险守门人。
仅做风控校验、规则生成、风险提示，不修改策略核心逻辑。

核心职责：
  1. 策略风险等级划分（低/中低/中/中高/高）
  2. 策略合规性与合理性校验
  3. 止损止盈规则细化
  4. 核心风险点提示
  5. 风控执行建议
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from agents.base import BaseAgent
from core.schemas import RiskControlOutput, FullLinkState, AgentStatus
from core.prompts import get_prompt


class RiskControlAgent(BaseAgent):
    """策略风控与止损止盈规则智能体"""

    name = "risk_control"
    description = "策略风险校验、止损止盈规则、仓位管控、风险等级划分"

    SYSTEM_PROMPT = get_prompt("risk_control", "agent_system")
    RISK_PROMPT = get_prompt("risk_control", "risk_check")

    def run(self, state: FullLinkState) -> Dict[str, Any]:
        start = time.time()
        task_id = state.get("task_id", "")
        strategy_output = state.get("strategy_generation_output", {})
        sentiment_output = state.get("sentiment_analysis_output", {})
        fundamental_output = state.get("fundamental_impact_output", {})

        if not strategy_output.get("core_strategy_logic"):
            return self._empty_output(task_id, start, "无策略输入")

        self.logger.info("风控校验启动 | task=%s", task_id)

        context = (
            f"策略方向：{strategy_output.get('entry_exit_conditions', {}).get('direction', '观望')}\n"
            f"策略逻辑：{strategy_output.get('core_strategy_logic', '')}\n"
            f"仓位区间：{strategy_output.get('reference_position_range', '')}\n"
            f"入场条件：{strategy_output.get('entry_exit_conditions', {})}\n"
            f"情绪指数：{sentiment_output.get('target_sentiment_index', {}).get('index', 50)}\n"
            f"影响确定性：{fundamental_output.get('impact_certainty_rating', '中确定性')}"
        )

        try:
            result = self.llm.chat_json(
                system_prompt=self.RISK_PROMPT,
                user_prompt=context,
                temperature=0.2,
            )
        except Exception as e:
            self.logger.warning("风控LLM分析失败: %s", e)
            result = self._fallback_risk(strategy_output, sentiment_output)

        risk_level = result.get("risk_level", "中风险")
        rationality = result.get("rationality_check", {})
        enhanced = result.get("enhanced_rules", {})
        risk_points = result.get("risk_points", [])
        monitoring = result.get("monitoring", {})

        risk_points.extend([
            "舆情分析基于历史数据与AI模型，存在固有偏差风险",
            "市场情绪可能快速反转，策略有效性可能下降",
            "以上分析仅供参考，不构成任何投资建议",
        ])

        duration = int((time.time() - start) * 1000)
        output = RiskControlOutput(
            task_id=task_id,
            strategy_risk_level=risk_level,
            strategy_rationality_check_report=rationality,
            stop_loss_stop_profit_rules=enhanced,
            core_risk_points_prompt=risk_points,
            risk_control_execution_suggestion=monitoring,
            execution_log={"duration_ms": duration},
        )

        agent_out = self._make_output(
            AgentStatus.SUCCESS, data=output.model_dump(), duration_ms=duration
        )
        self.logger.info("风控校验完成 | risk_level=%s", risk_level)
        return {
            "risk_control_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "risk_control_done",
        }

    @staticmethod
    def _fallback_risk(strategy, sentiment):
        idx = sentiment.get("target_sentiment_index", {}).get("index", 50)
        risk = "高风险" if abs(idx - 50) > 30 else "中风险" if abs(idx - 50) > 15 else "低风险"
        return {
            "risk_level": risk,
            "rationality_check": {"corrections": ["规则兜底，建议人工复核"]},
            "enhanced_rules": {"dynamic_stop_loss": "设置5%硬止损", "extreme_scenario": "极端行情立即平仓"},
            "risk_points": ["LLM风控分析不可用，仅基于规则兜底"],
            "monitoring": {"frequency": "每日", "key_metrics": ["情绪指数", "成交量"]},
        }

    def _empty_output(self, task_id, start, reason):
        duration = int((time.time() - start) * 1000)
        output = RiskControlOutput(task_id=task_id, execution_log={"reason": reason})
        agent_out = self._make_output(AgentStatus.SKIPPED, data={"reason": reason}, duration_ms=duration)
        return {"risk_control_output": output.model_dump(), "full_link_execution_log": [agent_out], "current_step": "risk_control_skipped"}
