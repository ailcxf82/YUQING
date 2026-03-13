# -*- coding: utf-8 -*-
"""任务编排与调度中枢智能体（OrchestratorAgent）

角色定位：全链路唯一大脑与调度中心。
不执行任何具体的业务分析操作，仅做调度、管控、聚合。

核心职责：
  1. 用户请求解析与任务拆解
  2. 全链路流程编排（LangGraph 状态机）
  3. 节点调度与状态管理
  4. 多智能体结果聚合
  5. 异常管控与熔断机制
  6. 全链路日志与可追溯管理

执行时序：
  NewsRetrieval → [合规] → EventClassification → [合规] →
  SentimentAnalysis → [合规] → FundamentalImpact ‖ IndustryChain →
  [合规] → StrategyGeneration → [合规] → RiskControl → [合规] →
  GenerateReport → END
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Optional

from langgraph.graph import END, StateGraph

from agents.base import BaseAgent
from agents.compliance import ComplianceAgent, COMPLIANCE_DISCLAIMER
from agents.event_classification import EventClassificationAgent
from agents.feedback_optimization import FeedbackOptimizationAgent
from agents.fundamental_impact import FundamentalImpactAgent
from agents.industry_chain import IndustryChainAgent
from agents.news_retrieval import NewsRetrievalAgent
from agents.risk_control import RiskControlAgent
from agents.sentiment_analysis import SentimentAnalysisAgent
from agents.strategy_generation import StrategyGenerationAgent
from core.config import SystemConfig, get_config
from core.llm import LLMClient
from core.schemas import (
    AgentStatus,
    ComplianceCheckOutput,
    FinalResearchReport,
    FullLinkState,
    UserRequest,
)

# ── 异常处理常量 ──
MAX_COMPLIANCE_REJECTIONS = 2
MAX_NODE_RETRIES = 3


class OrchestratorAgent(BaseAgent):
    """全链路中枢调度智能体——基于 LangGraph 的多智能体编排引擎"""

    name = "orchestrator"
    description = "全链路中枢调度、任务拆解、节点编排、结果聚合、异常管控"

    SYSTEM_PROMPT = (
        "你是全链路中枢调度系统。\n"
        "你的唯一职责是调度各业务智能体、管控执行流程、聚合结果。\n"
        "你绝对不做舆情采集、情绪分析、基本面推演、策略生成等业务操作。\n"
        "你绝对不篡改任何业务智能体的输出结果，仅做整合。\n"
    )

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config: Optional[SystemConfig] = None,
    ) -> None:
        super().__init__(llm_client=llm_client, config=config)

        shared_llm = self.llm
        shared_cfg = self.config

        self.compliance_agent = ComplianceAgent(
            llm_client=shared_llm, config=shared_cfg
        )
        self.news_agent = NewsRetrievalAgent(
            llm_client=shared_llm, config=shared_cfg
        )
        self.event_agent = EventClassificationAgent(
            llm_client=shared_llm, config=shared_cfg
        )
        self.sentiment_agent = SentimentAnalysisAgent(
            llm_client=shared_llm, config=shared_cfg
        )
        self.fundamental_agent = FundamentalImpactAgent(
            llm_client=shared_llm, config=shared_cfg
        )
        self.industry_agent = IndustryChainAgent(
            llm_client=shared_llm, config=shared_cfg
        )
        self.strategy_agent = StrategyGenerationAgent(
            llm_client=shared_llm, config=shared_cfg
        )
        self.risk_agent = RiskControlAgent(
            llm_client=shared_llm, config=shared_cfg
        )
        self.feedback_agent = FeedbackOptimizationAgent(
            llm_client=shared_llm, config=shared_cfg
        )

        self._graph = self._build_graph()
        self.logger.info("中枢调度引擎初始化完成 | 全链路 LangGraph 已编译")

    # ================================================================ #
    #  LangGraph 图构建
    # ================================================================ #

    def _build_graph(self):
        builder = StateGraph(FullLinkState)

        builder.add_node(
            "news_retrieval",
            self._wrap_node(self.news_agent, "news_retrieval_output"),
        )
        builder.add_node(
            "event_classification",
            self._wrap_node(self.event_agent, "event_classification_output"),
        )
        builder.add_node(
            "sentiment_analysis",
            self._wrap_node(self.sentiment_agent, "sentiment_analysis_output"),
        )
        builder.add_node(
            "parallel_deep_analysis",
            self._node_parallel_analysis,
        )
        builder.add_node(
            "strategy_generation",
            self._wrap_node(self.strategy_agent, "strategy_generation_output"),
        )
        builder.add_node(
            "risk_control",
            self._wrap_node(self.risk_agent, "risk_control_output"),
        )
        builder.add_node("generate_report", self._node_generate_report)

        builder.set_entry_point("news_retrieval")

        builder.add_conditional_edges(
            "news_retrieval", _fuse_check,
            {"next": "event_classification", "fuse": "generate_report"},
        )
        builder.add_conditional_edges(
            "event_classification", _fuse_check,
            {"next": "sentiment_analysis", "fuse": "generate_report"},
        )
        builder.add_conditional_edges(
            "sentiment_analysis", _fuse_check,
            {"next": "parallel_deep_analysis", "fuse": "generate_report"},
        )
        builder.add_conditional_edges(
            "parallel_deep_analysis", _fuse_check,
            {"next": "strategy_generation", "fuse": "generate_report"},
        )
        builder.add_conditional_edges(
            "strategy_generation", _fuse_check,
            {"next": "risk_control", "fuse": "generate_report"},
        )
        builder.add_conditional_edges(
            "risk_control", _fuse_check,
            {"next": "generate_report", "fuse": "generate_report"},
        )
        builder.add_edge("generate_report", END)

        return builder.compile()

    # ================================================================ #
    #  节点包装器：业务执行 + 合规校验
    # ================================================================ #

    def _wrap_node(
        self, agent: BaseAgent, output_key: str
    ) -> Callable[[FullLinkState], Dict[str, Any]]:
        """通用节点包装：agent.safe_run → 合规校验 → 状态更新"""

        def node_fn(state: FullLinkState) -> Dict[str, Any]:
            if state.get("fuse_triggered"):
                return {}

            step_start = time.time()
            result = agent.safe_run(state)
            agent_output = result.get(output_key, {})

            comp = self.compliance_agent.check(
                agent.name, agent_output, state.get("task_id", "")
            )

            update: Dict[str, Any] = {
                output_key: agent_output,
                "compliance_check_records": [comp.model_dump()],
                "full_link_execution_log": result.get(
                    "full_link_execution_log", []
                ),
                "current_step": result.get("current_step", ""),
            }

            if comp.fuse_trigger:
                update["fuse_triggered"] = True
                update["errors"] = [
                    f"合规熔断@{agent.name}: "
                    + "; ".join(comp.violation_details)
                ]
                update["task_status"] = "熔断"
                self.logger.error("合规熔断 | agent=%s", agent.name)
            elif comp.check_result == "修正后通过":
                update[output_key] = comp.corrected_content
                self.logger.info(
                    "合规修正 | agent=%s corrections=%d",
                    agent.name,
                    comp.execution_log.get("corrections_count", 0),
                )

            step_dur = int((time.time() - step_start) * 1000)
            update["full_link_execution_log"] = update.get(
                "full_link_execution_log", []
            ) + [{"step": agent.name, "duration_ms": step_dur, "compliance": comp.check_result}]

            return update

        return node_fn

    # ── 并行节点：基本面 + 产业链（ThreadPoolExecutor 真并行）──

    def _node_parallel_analysis(
        self, state: FullLinkState
    ) -> Dict[str, Any]:
        """真并行执行基本面推演 + 产业链传导，合规校验后合并"""
        if state.get("fuse_triggered"):
            return {}

        step_start = time.time()
        task_id = state.get("task_id", "")

        fund_result: Dict[str, Any] = {}
        ind_result: Dict[str, Any] = {}

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="deep") as pool:
            future_fund = pool.submit(self.fundamental_agent.safe_run, state)
            future_ind = pool.submit(self.industry_agent.safe_run, state)

            for future in as_completed([future_fund, future_ind]):
                try:
                    result = future.result()
                    if future is future_fund:
                        fund_result = result
                    else:
                        ind_result = result
                except Exception as exc:
                    self.logger.error("并行节点异常: %s", exc)
                    if future is future_fund:
                        fund_result = {"errors": [str(exc)]}
                    else:
                        ind_result = {"errors": [str(exc)]}

        fund_output = fund_result.get("fundamental_impact_output", {})
        fund_comp = self.compliance_agent.check(
            "fundamental_impact", fund_output, task_id
        )

        ind_output = ind_result.get("industry_chain_output", {})
        ind_comp = self.compliance_agent.check(
            "industry_chain", ind_output, task_id
        )

        final_fund = (
            fund_comp.corrected_content
            if fund_comp.check_result == "修正后通过"
            else fund_output
        )
        final_ind = (
            ind_comp.corrected_content
            if ind_comp.check_result == "修正后通过"
            else ind_output
        )

        logs = (
            fund_result.get("full_link_execution_log", [])
            + ind_result.get("full_link_execution_log", [])
        )

        step_dur = int((time.time() - step_start) * 1000)
        fund_dur = fund_result.get("full_link_execution_log", [{}])[-1].get("duration_ms", 0) if fund_result.get("full_link_execution_log") else 0
        ind_dur = ind_result.get("full_link_execution_log", [{}])[-1].get("duration_ms", 0) if ind_result.get("full_link_execution_log") else 0
        self.logger.info(
            "并行深度分析完成 | total=%dms fund=%dms ind=%dms saved=%dms",
            step_dur, fund_dur, ind_dur, max(0, fund_dur + ind_dur - step_dur),
        )

        update: Dict[str, Any] = {
            "fundamental_impact_output": final_fund,
            "industry_chain_output": final_ind,
            "compliance_check_records": [
                fund_comp.model_dump(),
                ind_comp.model_dump(),
            ],
            "full_link_execution_log": logs + [
                {
                    "step": "parallel_deep_analysis",
                    "mode": "thread_pool",
                    "duration_ms": step_dur,
                    "fund_duration_ms": fund_dur,
                    "ind_duration_ms": ind_dur,
                    "time_saved_ms": max(0, fund_dur + ind_dur - step_dur),
                    "fund_compliance": fund_comp.check_result,
                    "ind_compliance": ind_comp.check_result,
                }
            ],
            "current_step": "parallel_analysis_done",
        }

        if fund_comp.fuse_trigger or ind_comp.fuse_trigger:
            update["fuse_triggered"] = True
            update["errors"] = ["合规熔断@深度分析层"]
            update["task_status"] = "熔断"
            self.logger.error("合规熔断 | 深度分析层")

        return update

    # ── 最终报告生成 ──

    def _node_generate_report(
        self, state: FullLinkState
    ) -> Dict[str, Any]:
        """聚合全链路结果，生成最终投研报告"""
        task_info = state.get("task_base_info", {})
        fused = state.get("fuse_triggered", False)
        status = "熔断" if fused else "已完成"

        report = FinalResearchReport(
            task_base_info=task_info,
            news_summary=_safe_summary(
                state.get("news_retrieval_output", {})
            ),
            event_classification_result=_safe_summary(
                state.get("event_classification_output", {})
            ),
            sentiment_analysis_result=_safe_summary(
                state.get("sentiment_analysis_output", {})
            ),
            fundamental_impact_report=_safe_summary(
                state.get("fundamental_impact_output", {})
            ),
            industry_chain_analysis_result=_safe_summary(
                state.get("industry_chain_output", {})
            ),
            strategy_suggestion=_safe_summary(
                state.get("strategy_generation_output", {})
            ),
            risk_control_rules=_safe_summary(
                state.get("risk_control_output", {})
            ),
            compliance_disclaimer=COMPLIANCE_DISCLAIMER,
            full_link_log={
                "task_id": state.get("task_id", ""),
                "status": status,
                "compliance_records_count": len(
                    state.get("compliance_check_records", [])
                ),
                "errors": state.get("errors", []),
            },
        )

        self.logger.info(
            "投研报告生成完成 | task=%s status=%s",
            state.get("task_id"), status,
        )
        return {
            "final_research_report": report.model_dump(),
            "task_status": status,
            "current_step": "report_generated",
        }

    # ================================================================ #
    #  对外接口
    # ================================================================ #

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """BaseAgent 接口实现——直接运行已有的 FullLinkState"""
        return dict(self._graph.invoke(state))

    def execute(self, request: UserRequest) -> Dict[str, Any]:
        """高层 API：从 UserRequest 到最终报告的一键执行入口"""
        task_id = uuid.uuid4().hex[:8]
        self.logger.info(
            "全链路任务启动 | task_id=%s targets=%s",
            task_id, request.target_name,
        )

        initial_state: FullLinkState = {
            "task_id": task_id,
            "task_base_info": request.model_dump(),
            "task_status": "执行中",
            "news_retrieval_output": {},
            "event_classification_output": {},
            "sentiment_analysis_output": {},
            "fundamental_impact_output": {},
            "industry_chain_output": {},
            "strategy_generation_output": {},
            "risk_control_output": {},
            "compliance_check_records": [],
            "full_link_execution_log": [
                {
                    "step": "orchestrator_init",
                    "task_id": task_id,
                    "timestamp": time.time(),
                }
            ],
            "errors": [],
            "final_research_report": {},
            "current_step": "initialized",
            "retry_counts": {},
            "fuse_triggered": False,
        }

        try:
            final_state = self._graph.invoke(initial_state)
        except Exception as exc:
            self.logger.error("全链路执行异常: %s", exc)
            return {
                "task_id": task_id,
                "task_status": "失败",
                "error": str(exc),
                "compliance_disclaimer": COMPLIANCE_DISCLAIMER,
            }

        return final_state.get("final_research_report", {})

    def run_feedback(
        self,
        history_report: Dict[str, Any],
        actual_result: Dict[str, Any],
        task_id: str = "",
    ) -> Dict[str, Any]:
        """异步触发反馈优化——不阻塞实时任务"""
        self.logger.info("触发反馈优化 | task_id=%s", task_id)
        result = self.feedback_agent.run_optimization(
            history_report, actual_result, task_id
        )
        return result.model_dump()


# ── 辅助函数 ──

def _fuse_check(state: FullLinkState) -> str:
    """LangGraph 条件边函数：检查是否触发熔断"""
    return "fuse" if state.get("fuse_triggered") else "next"


def _safe_summary(data: Any) -> Dict[str, Any]:
    """安全地从状态字段提取摘要字典"""
    if isinstance(data, dict):
        return data
    return {}
