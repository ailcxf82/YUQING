# -*- coding: utf-8 -*-
"""产业链传导与关联标的分析智能体（IndustryChainAgent）

角色定位：深度投研并行节点。
仅做产业链上下游影响分析、关联标的识别，不做单标的基本面推演、策略生成。

核心职责：
  1. 产业链上下游映射
  2. 跨环节传导逻辑拆解
  3. 受益/受损标的清单输出
  4. 跨行业风险传导预判
  5. 产业链景气度变化判断
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from agents.base import BaseAgent
from core.impact_analyzer import ImpactAnalyzer
from core.schemas import IndustryChainOutput, FullLinkState, AgentStatus
from core.prompts import get_prompt


class IndustryChainAgent(BaseAgent):
    """产业链传导与关联标的分析智能体"""

    name = "industry_chain"
    description = "产业链上下游传导分析、受益/受损标的识别、跨行业传导预判"

    SYSTEM_PROMPT = get_prompt("industry_chain", "agent_system")
    CHAIN_PROMPT = get_prompt("industry_chain", "chain_analyze")

    TOP_N_EVENTS = 5

    def run(self, state: FullLinkState) -> Dict[str, Any]:
        start = time.time()
        task_id = state.get("task_id", "")
        task_info = state.get("task_base_info", {})
        event_output = state.get("event_classification_output", {})
        sentiment_output = state.get("sentiment_analysis_output", {})

        core_news = event_output.get("core_news_list", [])
        if not core_news:
            return self._empty_output(task_id, start, "无核心舆情")

        names = task_info.get("target_name", [])
        company = names[0] if names else ""
        industry = task_info.get("user_custom_rules", {}).get("industry", "")

        top_events = core_news[:self.TOP_N_EVENTS]
        self.logger.info(
            "产业链分析启动 | task=%s company=%s events=%d(top%d)",
            task_id, company, len(core_news), len(top_events),
        )

        event_lines = self._build_event_summary(top_events)

        try:
            result = self.llm.chat_json(
                system_prompt=self.CHAIN_PROMPT,
                user_prompt=(
                    f"涉及公司：{company}\n"
                    f"所属行业：{industry or '未知'}\n"
                    f"核心舆情事件共{len(core_news)}条，以下为影响力最高的{len(top_events)}条：\n\n"
                    f"{event_lines}"
                ),
                temperature=0.2,
            )
        except Exception as e:
            self.logger.warning("产业链LLM分析失败: %s", e)
            result = {}

        chain_mapping = result.get("chain_mapping", {})
        conduction = result.get("conduction_logic", [])
        beneficiaries = result.get("beneficiaries", [])
        losers = result.get("losers", [])
        cross_sector = result.get("cross_sector", [])
        boom = result.get("boom_change", {})

        benefit_damage = []
        for b in beneficiaries:
            benefit_damage.append({"target": b.get("target", ""), "impact": "受益", "reason": b.get("reason", "")})
        for l in losers:
            benefit_damage.append({"target": l.get("target", ""), "impact": "受损", "reason": l.get("reason", "")})

        duration = int((time.time() - start) * 1000)
        output = IndustryChainOutput(
            task_id=task_id,
            industry_chain_mapping=chain_mapping,
            conduction_logic_breakdown={"conduction_paths": conduction},
            benefit_damage_target_list=benefit_damage,
            cross_industry_conduction_forecast={"risks": cross_sector},
            industry_boom_change_judgment=boom,
            execution_log={
                "duration_ms": duration,
                "events_analyzed": len(top_events),
                "events_total": len(core_news),
            },
        )

        agent_out = self._make_output(
            AgentStatus.SUCCESS, data=output.model_dump(), duration_ms=duration
        )
        self.logger.info(
            "产业链分析完成 | events_used=%d beneficiaries=%d losers=%d",
            len(top_events), len(beneficiaries), len(losers),
        )
        return {
            "industry_chain_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "industry_chain_done",
        }

    @staticmethod
    def _build_event_summary(events: List[Dict[str, Any]]) -> str:
        """将多条核心新闻聚合为 LLM 可读的编号摘要"""
        lines = []
        for i, ev in enumerate(events, 1):
            title = ev.get("title", "")
            content = ev.get("content", ev.get("text", ""))[:150]
            category = ev.get("event_category", "")
            sub_label = ev.get("sub_label", "")
            score = ev.get("influence_score", 0)
            tag = f"[{category}/{sub_label}]" if category else ""
            lines.append(
                f"事件{i} {tag} (影响力{score:.0f}): {title} | {content}"
            )
        return "\n".join(lines)

    def _empty_output(self, task_id, start, reason):
        duration = int((time.time() - start) * 1000)
        output = IndustryChainOutput(
            task_id=task_id, execution_log={"reason": reason}
        )
        agent_out = self._make_output(
            AgentStatus.SKIPPED, data={"reason": reason}, duration_ms=duration
        )
        return {
            "industry_chain_output": output.model_dump(),
            "full_link_execution_log": [agent_out],
            "current_step": "industry_chain_skipped",
        }
