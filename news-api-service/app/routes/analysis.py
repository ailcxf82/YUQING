# -*- coding: utf-8 -*-
"""Phase 4 全链路多智能体舆情分析 API

提供：
  - /api/v2/analysis/full-link    全链路一键分析（核心接口）
  - /api/v2/analysis/quick        快捷分析（仅需标的代码+名称）
  - /api/v2/analysis/news-only    仅采集+预处理
  - /api/v2/analysis/feedback     反馈优化
  - /api/v2/analysis/system-info  系统架构信息
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v2/analysis", tags=["Phase4 全链路分析"])

# 延迟初始化避免启动时阻塞
_orchestrator = None


def _get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        from agents.orchestrator import OrchestratorAgent
        _orchestrator = OrchestratorAgent()
    return _orchestrator


# ================================================================== #
#  请求/响应模型
# ================================================================== #

class FullLinkRequest(BaseModel):
    """全链路分析请求"""
    target_type: str = Field(
        default="个股",
        description="分析目标类型：个股/行业/主题/全市场",
    )
    target_code: List[str] = Field(
        default_factory=list,
        description="标的代码列表，如 ['600000.SH']",
    )
    target_name: List[str] = Field(
        default_factory=list,
        description="标的/行业/主题名称，如 ['浦发银行']",
    )
    time_range: str = Field(
        default="近7天",
        description="舆情时间范围：近24小时/近7天/近30天/自定义",
    )
    custom_time_start: str = Field(
        default="",
        description="自定义开始时间，格式：2026-03-01",
    )
    custom_time_end: str = Field(
        default="",
        description="自定义结束时间，格式：2026-03-11",
    )
    analysis_depth: str = Field(
        default="标准版",
        description="分析深度：基础版/标准版/深度版",
    )
    user_custom_rules: Dict[str, Any] = Field(
        default_factory=dict,
        description="用户自定义分析规则/预警阈值",
    )


class QuickAnalysisRequest(BaseModel):
    """快捷分析请求——仅需标的代码+名称"""
    symbol: str = Field(..., description="标的代码，如 600000.SH")
    name: str = Field(..., description="标的名称，如 浦发银行")
    start_date: str = Field(default="", description="开始日期，如 2026-03-01")
    end_date: str = Field(default="", description="结束日期，如 2026-03-11")
    analysis_depth: str = Field(default="标准版", description="基础版/标准版/深度版")


class FeedbackRequest(BaseModel):
    """反馈优化请求"""
    task_id: str = Field(..., description="历史任务ID")
    history_report: Dict[str, Any] = Field(
        ..., description="历史任务的全链路分析报告",
    )
    actual_result: Dict[str, Any] = Field(
        ..., description="事件实际结果数据",
    )


# ================================================================== #
#  核心接口：全链路一键分析
# ================================================================== #

@router.post(
    "/full-link",
    summary="全链路一键分析（核心接口）",
    description=(
        "输入标的/行业/主题等分析目标，系统自动执行完整的"
        "「舆情采集→事件分类→情绪分析→基本面推演→产业链传导→策略生成→风控校验」"
        "全链路流程，每个环节自动进行合规校验，最终输出结构化投研报告。\n\n"
        "**执行耗时**：根据数据量和分析深度，通常需要 30-180 秒。"
    ),
)
def full_link_analysis(body: FullLinkRequest):
    if not body.target_code and not body.target_name:
        raise HTTPException(
            status_code=400,
            detail="target_code 和 target_name 至少需要填写一项。",
        )

    from core.schemas import UserRequest
    request = UserRequest(
        target_type=body.target_type,
        target_code=body.target_code,
        target_name=body.target_name,
        time_range=body.time_range,
        custom_time_start=body.custom_time_start,
        custom_time_end=body.custom_time_end,
        analysis_depth=body.analysis_depth,
        user_custom_rules=body.user_custom_rules,
    )

    try:
        orch = _get_orchestrator()
        start = time.time()
        report = orch.execute(request)
        elapsed = int((time.time() - start) * 1000)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"全链路分析执行失败: {exc}",
        ) from exc

    return {
        "success": True,
        "elapsed_ms": elapsed,
        "report": report,
    }


# ================================================================== #
#  快捷接口：仅需标的代码+名称
# ================================================================== #

@router.post(
    "/quick",
    summary="快捷分析（兼容旧接口风格）",
    description=(
        "简化版入口：仅需输入标的代码和名称，自动执行全链路分析。"
        "与旧版 /api/news/analyze 类似的调用方式，但执行完整的多智能体全链路。"
    ),
)
def quick_analysis(body: QuickAnalysisRequest):
    if not body.symbol or not body.name:
        raise HTTPException(status_code=400, detail="symbol 与 name 为必填。")

    from core.schemas import UserRequest
    request = UserRequest(
        target_type="个股",
        target_code=[body.symbol],
        target_name=[body.name],
        time_range="自定义" if body.start_date else "近7天",
        custom_time_start=body.start_date,
        custom_time_end=body.end_date,
        analysis_depth=body.analysis_depth,
    )

    try:
        orch = _get_orchestrator()
        start = time.time()
        report = orch.execute(request)
        elapsed = int((time.time() - start) * 1000)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"快捷分析执行失败: {exc}",
        ) from exc

    return {
        "success": True,
        "elapsed_ms": elapsed,
        "report": report,
    }


# ================================================================== #
#  仅采集+预处理
# ================================================================== #

@router.post(
    "/news-only",
    summary="读取本地舆情数据",
    description=(
        "从本地 LanceDB 读取已采集的舆情数据，不触发实时网络请求。\n\n"
        "**前置条件**：需先通过 `/api/v2/news-collect/add-symbol` 添加标的，"
        "并等待定时采集完成或手动调用 `/api/v2/news-collect/run-symbol`。"
    ),
)
def news_only(body: QuickAnalysisRequest):
    if not body.symbol:
        raise HTTPException(status_code=400, detail="symbol 为必填。")

    try:
        from core.news_collector_job import read_local_news
        start = time.time()
        items = read_local_news(
            symbol=body.symbol,
            start_time=body.start_date,
            end_time=body.end_date,
            limit=200,
        )
        elapsed = int((time.time() - start) * 1000)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"本地数据读取失败: {exc}",
        ) from exc

    return {
        "success": True,
        "elapsed_ms": elapsed,
        "data_source": "local_lancedb",
        "news_total_count": len(items),
        "news_data": items,
        "hint": "数据来自本地预采集。如无数据，请先配置采集标的并执行采集。" if not items else "",
    }


# ================================================================== #
#  反馈优化
# ================================================================== #

@router.post(
    "/feedback",
    summary="反馈优化与复盘",
    description="输入历史分析报告和事件实际结果，执行复盘评估与参数优化建议。",
)
def feedback_optimization(body: FeedbackRequest):
    try:
        orch = _get_orchestrator()
        result = orch.run_feedback(
            history_report=body.history_report,
            actual_result=body.actual_result,
            task_id=body.task_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"反馈优化失败: {exc}",
        ) from exc

    return {"success": True, "optimization_result": result}


# ================================================================== #
#  系统信息
# ================================================================== #

@router.get(
    "/system-info",
    summary="系统架构信息",
    description="返回 Phase 4 多智能体系统的架构概览与各智能体状态。",
)
def system_info():
    agents = [
        {
            "name": "OrchestratorAgent",
            "role": "中枢调度",
            "description": "全链路编排、任务拆解、结果聚合、异常管控",
        },
        {
            "name": "NewsRetrievalAgent",
            "role": "链路入口",
            "description": "从本地LanceDB读取预采集数据(零网络延迟)",
        },
        {
            "name": "EventClassificationAgent",
            "role": "基础分析",
            "description": "实体链接、事件分类打标、传播力量化",
        },
        {
            "name": "SentimentAnalysisAgent",
            "role": "核心分析",
            "description": "6级情绪量化、情绪指数构建、舆情评级",
        },
        {
            "name": "FundamentalImpactAgent",
            "role": "深度研究",
            "description": "基本面影响链路推演、历史事件回测",
        },
        {
            "name": "IndustryChainAgent",
            "role": "深度研究(并行)",
            "description": "产业链传导分析、受益/受损标的识别",
        },
        {
            "name": "StrategyGenerationAgent",
            "role": "策略落地",
            "description": "事件驱动策略生成、入出场条件",
        },
        {
            "name": "RiskControlAgent",
            "role": "风控校验",
            "description": "策略风险等级、止损止盈规则",
        },
        {
            "name": "ComplianceAgent",
            "role": "合规守门人",
            "description": "全链路合规校验、违规拦截、免责声明",
        },
        {
            "name": "FeedbackOptimizationAgent",
            "role": "闭环优化",
            "description": "事件复盘、偏差定位、参数优化",
        },
    ]

    pipeline = [
        "NewsRetrieval(读本地LanceDB) -> [Compliance]",
        "EventClassification -> [Compliance]",
        "SentimentAnalysis -> [Compliance]",
        "FundamentalImpact || IndustryChain -> [Compliance]",
        "StrategyGeneration -> [Compliance]",
        "RiskControl -> [Compliance]",
        "GenerateReport -> END",
    ]

    data_flow = {
        "collection": "定时后台任务(news_collector_job) -> Tushare API -> 预处理 -> LanceDB",
        "analysis": "用户请求 -> NewsRetrievalAgent(读本地) -> 全链路分析(纯LLM) -> 报告",
        "benefit": "分析链路零网络延迟，响应时间从300s+降至10-60s",
    }

    return {
        "system": "Phase 4 精细化多智能体全链路协同引擎",
        "version": "4.1",
        "architecture": "1 中枢 + 7 业务 + 2 支撑 = 10 智能体 + 异步采集调度",
        "framework": "LangGraph StateGraph",
        "data_flow": data_flow,
        "agents": agents,
        "pipeline": pipeline,
        "apis": {
            "full_link": "POST /api/v2/analysis/full-link",
            "quick": "POST /api/v2/analysis/quick",
            "news_only": "POST /api/v2/analysis/news-only",
            "feedback": "POST /api/v2/analysis/feedback",
            "system_info": "GET /api/v2/analysis/system-info",
            "collect_add": "POST /api/v2/news-collect/add-symbol",
            "collect_run": "POST /api/v2/news-collect/run-now",
            "collect_status": "GET /api/v2/news-collect/status",
        },
    }
