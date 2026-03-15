# -*- coding: utf-8 -*-
"""反馈迭代与模型自优化智能体（FeedbackOptimizationAgent）

角色定位：全链路闭环优化节点。
仅做复盘与优化，不参与实时投研分析流程。

核心职责：
  1. 事件结果回传与数据收集
  2. 分析效果复盘评估
  3. 偏差原因定位
  4. 模型参数与规则优化
  5. 优化效果验证
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from agents.base import BaseAgent
from core.schemas import FeedbackOptimizationOutput, FullLinkState, AgentStatus
from core.prompts import get_prompt


class FeedbackOptimizationAgent(BaseAgent):
    """反馈迭代与模型自优化智能体"""

    name = "feedback_optimization"
    description = "事件复盘、分析准确率评估、偏差定位、参数/Prompt优化"

    SYSTEM_PROMPT = get_prompt("feedback_optimization", "agent_system")
    REVIEW_PROMPT = get_prompt("feedback_optimization", "review")

    def run(self, state: FullLinkState) -> Dict[str, Any]:
        """常规链路中不执行，由 run_optimization 独立触发"""
        return {
            "full_link_execution_log": [{
                "agent_name": self.name,
                "status": "standby",
                "message": "反馈优化节点为异步执行，不阻塞实时投研",
            }],
            "current_step": "feedback_standby",
        }

    def run_optimization(
        self,
        history_report: Dict[str, Any],
        actual_result: Dict[str, Any],
        task_id: str = "",
    ) -> FeedbackOptimizationOutput:
        """独立执行：对历史任务进行复盘优化

        Args:
            history_report: 历史任务的全链路分析报告
            actual_result: 事件实际结果数据
            task_id: 历史任务 ID
        """
        start = time.time()
        self.logger.info("复盘优化启动 | task=%s", task_id)

        context = (
            f"历史分析结论：\n"
            f"  情绪指数={history_report.get('sentiment_analysis_result', {}).get('target_sentiment_index', {}).get('index', 'N/A')}\n"
            f"  影响确定性={history_report.get('fundamental_impact_report', {}).get('impact_certainty_rating', 'N/A')}\n"
            f"  策略方向={history_report.get('strategy_suggestion', {}).get('entry_exit_conditions', {}).get('direction', 'N/A')}\n"
            f"\n实际结果：\n"
            f"  实际股价变动={actual_result.get('price_change_pct', 'N/A')}%\n"
            f"  实际事件进展={actual_result.get('event_progress', 'N/A')}\n"
            f"  实际持续时间={actual_result.get('duration', 'N/A')}"
        )

        try:
            result = self.llm.chat_json(
                system_prompt=self.REVIEW_PROMPT,
                user_prompt=context,
                temperature=0.3,
            )
        except Exception as e:
            self.logger.warning("复盘LLM分析失败: %s", e)
            result = self._fallback_review()

        accuracy = result.get("accuracy", {})
        deviations = result.get("deviations", [])
        optimizations = result.get("optimizations", [])
        backtest = result.get("backtest_validation", {})

        duration = int((time.time() - start) * 1000)
        output = FeedbackOptimizationOutput(
            task_id=task_id,
            analysis_accuracy_evaluation=accuracy,
            deviation_reason_positioning=deviations,
            optimization_content={"suggestions": optimizations},
            optimization_backtest_result=backtest,
            optimization_execution_suggestion={
                "priority": "高" if accuracy.get("overall_score", 1) < 0.5 else "中",
                "auto_apply": False,
                "requires_review": True,
            },
            execution_log={"duration_ms": duration},
        )

        self.logger.info(
            "复盘优化完成 | accuracy=%.2f deviations=%d",
            accuracy.get("overall_score", 0), len(deviations),
        )
        return output

    @staticmethod
    def _fallback_review():
        return {
            "accuracy": {"overall_score": 0.5, "sentiment_accuracy": 0.5, "impact_accuracy": 0.5, "strategy_effectiveness": 0.5},
            "deviations": ["LLM分析不可用，无法完成自动复盘"],
            "optimizations": [],
            "backtest_validation": {"improved": False, "detail": "规则兜底"},
        }
