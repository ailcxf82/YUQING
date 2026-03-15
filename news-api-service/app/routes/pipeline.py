# -*- coding: utf-8 -*-
"""分步调用 API — 支持前端逐步执行全链路分析

设计目标：
  1. 将全链路拆分为独立步骤，每步可单独调用
  2. 支持进度查询、中断恢复
  3. 外部请求（LLM/数据采集）独立暴露
  4. 前端可实时展示进度和中间结果

工作流程：
  Step 1: 创建任务 → 返回 task_id
  Step 2: 关键词语义分析（可选，LLM调用）
  Step 3: 新闻检索（本地读取，无外部请求）
  Step 4: 事件分类（LLM调用）
  Step 5: 情绪分析（LLM调用）
  Step 6: 基本面影响分析（LLM调用）
  Step 7: 产业链分析（LLM调用，可与Step6并行）
  Step 8: 策略生成（LLM调用）
  Step 9: 风控校验（LLM调用）
  Step 10: 生成报告（本地处理）

外部请求节点（耗时较长）：
  - Step 2: 关键词语义分析 (~2s)
  - Step 4: 事件分类 (~96s)
  - Step 5: 情绪分析 (~91s)
  - Step 6: 基本面影响 (~127s)
  - Step 7: 产业链分析 (~53s)
  - Step 8: 策略生成 (~12s)
  - Step 9: 风控校验 (~15s)
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import task_store

router = APIRouter(prefix="/api/v2/pipeline", tags=["分步调用API"])


# ================================================================== #
#  请求/响应模型
# ================================================================== #

class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    target_type: str = Field(default="个股", description="分析目标类型：个股/行业/主题/全市场")
    target_code: List[str] = Field(default_factory=list, description="标的代码列表")
    target_name: List[str] = Field(default_factory=list, description="标的名称列表")
    keyword: str = Field(default="", description="自然语言关键词")
    time_range: str = Field(default="近7天", description="舆情时间范围")
    custom_time_start: str = Field(default="", description="自定义开始时间")
    custom_time_end: str = Field(default="", description="自定义结束时间")
    analysis_depth: str = Field(default="标准版", description="分析深度")
    user_custom_rules: Dict[str, Any] = Field(default_factory=dict, description="用户自定义规则")


class KeywordAnalysisRequest(BaseModel):
    """关键词语义分析请求"""
    task_id: str = Field(..., description="任务ID")
    keyword: str = Field(..., description="待分析的关键词")


class ExecuteStepRequest(BaseModel):
    """执行单步请求"""
    task_id: str = Field(..., description="任务ID")
    step_name: str = Field(..., description="步骤名称")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="步骤输入数据（可选）")


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    success: bool
    task_id: str
    status: str
    current_step: str
    progress: Dict[str, Any]
    steps_completed: List[str]
    steps_pending: List[str]
    can_resume: bool
    error: Optional[str] = None


STEP_ORDER = [
    "keyword_analysis",
    "news_retrieval",
    "event_classification",
    "sentiment_analysis",
    "fundamental_impact",
    "industry_chain",
    "strategy_generation",
    "risk_control",
    "generate_report",
]

STEP_DESCRIPTIONS = {
    "keyword_analysis": "关键词语义分析",
    "news_retrieval": "新闻数据检索",
    "event_classification": "事件分类识别",
    "sentiment_analysis": "情绪量化分析",
    "fundamental_impact": "基本面影响推演",
    "industry_chain": "产业链传导分析",
    "strategy_generation": "策略生成",
    "risk_control": "风控校验",
    "generate_report": "生成研究报告",
}

STEP_EXTERNAL_REQUESTS = {
    "keyword_analysis": True,
    "news_retrieval": False,
    "event_classification": True,
    "sentiment_analysis": True,
    "fundamental_impact": True,
    "industry_chain": True,
    "strategy_generation": True,
    "risk_control": True,
    "generate_report": False,
}

STEP_ESTIMATED_TIME = {
    "keyword_analysis": 2,
    "news_retrieval": 1,
    "event_classification": 96,
    "sentiment_analysis": 91,
    "fundamental_impact": 127,
    "industry_chain": 53,
    "strategy_generation": 12,
    "risk_control": 15,
    "generate_report": 1,
}


# ================================================================== #
#  Step 1: 创建任务
# ================================================================== #

@router.post(
    "/task/create",
    summary="创建分析任务",
    description="创建新的分析任务，返回 task_id，后续步骤通过 task_id 关联",
)
def create_task(body: CreateTaskRequest):
    task_id = uuid.uuid4().hex[:8]

    task_data = {
        "task_id": task_id,
        "task_base_info": {
            "target_type": body.target_type,
            "target_code": body.target_code,
            "target_name": body.target_name,
            "keyword": body.keyword,
            "time_range": body.time_range,
            "custom_time_start": body.custom_time_start,
            "custom_time_end": body.custom_time_end,
            "analysis_depth": body.analysis_depth,
            "user_custom_rules": body.user_custom_rules,
        },
        "status": "CREATED",
        "current_step": "init",
        "steps_completed": [],
        "steps_pending": STEP_ORDER.copy(),
        "step_outputs": {},
        "created_at": time.time(),
        "updated_at": time.time(),
        "error": None,
    }

    task_store.init_task(task_id, base_info=task_data)

    return {
        "success": True,
        "task_id": task_id,
        "status": "CREATED",
        "message": "任务创建成功，请按顺序执行各步骤",
        "steps": STEP_ORDER,
        "step_descriptions": STEP_DESCRIPTIONS,
        "external_request_steps": [k for k, v in STEP_EXTERNAL_REQUESTS.items() if v],
        "estimated_total_time_seconds": sum(STEP_ESTIMATED_TIME.values()),
    }


# ================================================================== #
#  Step 2: 关键词语义分析
# ================================================================== #

@router.post(
    "/step/keyword-analysis",
    summary="关键词语义分析",
    description="调用 LLM 分析关键词语义，提取核心搜索词。耗时约 2 秒。",
)
def step_keyword_analysis(body: KeywordAnalysisRequest):
    task = task_store.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    start = time.time()

    try:
        from core.llm import LLMClient
        from core.prompts import get_prompt

        llm = LLMClient()
        prompt_template = get_prompt("keyword", "keyword_analysis")
        prompt = prompt_template.format(keyword=body.keyword)
        result = llm.chat_json(
            system_prompt="你是金融舆情语义分析专家。",
            user_prompt=prompt,
            temperature=0.1,
        )

        duration = int((time.time() - start) * 1000)

        task_store.update_task(
            body.task_id,
            status="IN_PROGRESS",
            current_step="keyword_analysis",
            append_steps_completed=["keyword_analysis"],
            update_step_output={"keyword_analysis": result},
        )

        return {
            "success": True,
            "task_id": body.task_id,
            "step": "keyword_analysis",
            "step_description": STEP_DESCRIPTIONS["keyword_analysis"],
            "duration_ms": duration,
            "output": result,
            "next_step": "news_retrieval",
        }

    except Exception as e:
        task_store.update_task(
            body.task_id,
            status="ERROR",
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"关键词语义分析失败: {e}")


# ================================================================== #
#  Step 3: 新闻检索
# ================================================================== #

@router.post(
    "/step/news-retrieval",
    summary="新闻数据检索",
    description="从本地数据库检索新闻数据，无外部请求，响应极快（<100ms）。",
)
def step_news_retrieval(body: ExecuteStepRequest):
    task = task_store.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_base = task.get("task_base_info", {})
    step_outputs = task.get("step_outputs", {})
    keyword_analysis = step_outputs.get("keyword_analysis", {}) or body.input_data.get("keyword_analysis", {})
    start = time.time()

    try:
        from agents.news_retrieval import NewsRetrievalAgent

        agent = NewsRetrievalAgent()

        state = {
            "task_id": body.task_id,
            "task_base_info": task_base,
        }

        if keyword_analysis:
            state["keyword_analysis"] = keyword_analysis

        result = agent.run(state)
        output = result.get("news_retrieval_output", {})

        duration = int((time.time() - start) * 1000)

        task_store.update_task(
            body.task_id,
            status="IN_PROGRESS",
            current_step="news_retrieval",
            append_steps_completed=["news_retrieval"],
            update_step_output={"news_retrieval": output},
        )

        return {
            "success": True,
            "task_id": body.task_id,
            "step": "news_retrieval",
            "step_description": STEP_DESCRIPTIONS["news_retrieval"],
            "duration_ms": duration,
            "output": output,
            "news_count": output.get("news_total_count", 0),
            "next_step": "event_classification",
        }

    except Exception as e:
        task_store.update_task(body.task_id, status="ERROR", error=str(e))
        raise HTTPException(status_code=500, detail=f"新闻检索失败: {e}")


# ================================================================== #
#  Step 4: 事件分类
# ================================================================== #

@router.post(
    "/step/event-classification",
    summary="事件分类识别",
    description="调用 LLM 对新闻进行事件分类。耗时约 96 秒（2次 LLM 调用）。",
)
def step_event_classification(body: ExecuteStepRequest):
    task = task_store.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_base = task.get("task_base_info", {})
    step_outputs = task.get("step_outputs", {})
    news_output = step_outputs.get("news_retrieval", {}) or body.input_data.get("news_retrieval", {})

    if not news_output:
        raise HTTPException(status_code=400, detail="请先执行新闻检索步骤")

    start = time.time()

    try:
        from agents.event_classification import EventClassificationAgent

        agent = EventClassificationAgent()

        state = {
            "task_id": body.task_id,
            "task_base_info": task_base,
            "news_retrieval_output": news_output,
        }

        result = agent.run(state)
        output = result.get("event_classification_output", {})

        duration = int((time.time() - start) * 1000)

        task_store.update_task(
            body.task_id,
            status="IN_PROGRESS",
            current_step="event_classification",
            append_steps_completed=["event_classification"],
            update_step_output={"event_classification": output},
        )

        return {
            "success": True,
            "task_id": body.task_id,
            "step": "event_classification",
            "step_description": STEP_DESCRIPTIONS["event_classification"],
            "duration_ms": duration,
            "output": output,
            "next_step": "sentiment_analysis",
        }

    except Exception as e:
        task_store.update_task(body.task_id, status="ERROR", error=str(e))
        raise HTTPException(status_code=500, detail=f"事件分类失败: {e}")


# ================================================================== #
#  Step 5: 情绪分析
# ================================================================== #

@router.post(
    "/step/sentiment-analysis",
    summary="情绪量化分析",
    description="调用 LLM 进行情绪量化分析。耗时约 91 秒（1次 LLM 调用）。",
)
def step_sentiment_analysis(body: ExecuteStepRequest):
    task = task_store.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_base = task.get("task_base_info", {})
    step_outputs = task.get("step_outputs", {})
    news_output = step_outputs.get("news_retrieval", {}) or body.input_data.get("news_retrieval", {})
    event_output = step_outputs.get("event_classification", {}) or body.input_data.get("event_classification", {})

    if not news_output:
        raise HTTPException(status_code=400, detail="请先执行新闻检索步骤")

    start = time.time()

    try:
        from agents.sentiment_analysis import SentimentAnalysisAgent

        agent = SentimentAnalysisAgent()

        state = {
            "task_id": body.task_id,
            "task_base_info": task_base,
            "news_retrieval_output": news_output,
            "event_classification_output": event_output,
        }

        result = agent.run(state)
        output = result.get("sentiment_analysis_output", {})

        duration = int((time.time() - start) * 1000)

        task_store.update_task(
            body.task_id,
            status="IN_PROGRESS",
            current_step="sentiment_analysis",
            append_steps_completed=["sentiment_analysis"],
            update_step_output={"sentiment_analysis": output},
        )

        return {
            "success": True,
            "task_id": body.task_id,
            "step": "sentiment_analysis",
            "step_description": STEP_DESCRIPTIONS["sentiment_analysis"],
            "duration_ms": duration,
            "output": output,
            "next_step": "fundamental_impact",
        }

    except Exception as e:
        task_store.update_task(body.task_id, status="ERROR", error=str(e))
        raise HTTPException(status_code=500, detail=f"情绪分析失败: {e}")


# ================================================================== #
#  Step 6: 基本面影响分析
# ================================================================== #

@router.post(
    "/step/fundamental-impact",
    summary="基本面影响推演",
    description="调用 LLM 推演基本面影响。耗时约 127 秒（多次 LLM 调用）。",
)
def step_fundamental_impact(body: ExecuteStepRequest):
    task = task_store.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_base = task.get("task_base_info", {})
    step_outputs = task.get("step_outputs", {})
    news_output = step_outputs.get("news_retrieval", {}) or body.input_data.get("news_retrieval", {})
    event_output = step_outputs.get("event_classification", {}) or body.input_data.get("event_classification", {})
    sentiment_output = step_outputs.get("sentiment_analysis", {}) or body.input_data.get("sentiment_analysis", {})

    start = time.time()

    try:
        from agents.fundamental_impact import FundamentalImpactAgent

        agent = FundamentalImpactAgent()

        state = {
            "task_id": body.task_id,
            "task_base_info": task_base,
            "news_retrieval_output": news_output,
            "event_classification_output": event_output,
            "sentiment_analysis_output": sentiment_output,
        }

        result = agent.run(state)
        output = result.get("fundamental_impact_output", {})

        duration = int((time.time() - start) * 1000)

        task_store.update_task(
            body.task_id,
            status="IN_PROGRESS",
            current_step="fundamental_impact",
            append_steps_completed=["fundamental_impact"],
            update_step_output={"fundamental_impact": output},
        )

        return {
            "success": True,
            "task_id": body.task_id,
            "step": "fundamental_impact",
            "step_description": STEP_DESCRIPTIONS["fundamental_impact"],
            "duration_ms": duration,
            "output": output,
            "next_step": "industry_chain",
        }

    except Exception as e:
        task_store.update_task(body.task_id, status="ERROR", error=str(e))
        raise HTTPException(status_code=500, detail=f"基本面影响分析失败: {e}")


# ================================================================== #
#  Step 7: 产业链分析
# ================================================================== #

@router.post(
    "/step/industry-chain",
    summary="产业链传导分析",
    description="调用 LLM 分析产业链传导。耗时约 53 秒。可与基本面分析并行执行。",
)
def step_industry_chain(body: ExecuteStepRequest):
    task = task_store.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_base = task.get("task_base_info", {})
    step_outputs = task.get("step_outputs", {})
    news_output = step_outputs.get("news_retrieval", {}) or body.input_data.get("news_retrieval", {})
    event_output = step_outputs.get("event_classification", {}) or body.input_data.get("event_classification", {})

    start = time.time()

    try:
        from agents.industry_chain import IndustryChainAgent

        agent = IndustryChainAgent()

        state = {
            "task_id": body.task_id,
            "task_base_info": task_base,
            "news_retrieval_output": news_output,
            "event_classification_output": event_output,
        }

        result = agent.run(state)
        output = result.get("industry_chain_output", {})

        duration = int((time.time() - start) * 1000)

        task_store.update_task(
            body.task_id,
            status="IN_PROGRESS",
            current_step="industry_chain",
            append_steps_completed=["industry_chain"],
            update_step_output={"industry_chain": output},
        )

        return {
            "success": True,
            "task_id": body.task_id,
            "step": "industry_chain",
            "step_description": STEP_DESCRIPTIONS["industry_chain"],
            "duration_ms": duration,
            "output": output,
            "next_step": "strategy_generation",
        }

    except Exception as e:
        task_store.update_task(body.task_id, status="ERROR", error=str(e))
        raise HTTPException(status_code=500, detail=f"产业链分析失败: {e}")


# ================================================================== #
#  Step 8: 策略生成
# ================================================================== #

@router.post(
    "/step/strategy-generation",
    summary="策略生成",
    description="调用 LLM 生成投资策略。耗时约 12 秒。",
)
def step_strategy_generation(body: ExecuteStepRequest):
    task = task_store.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_base = task.get("task_base_info", {})
    step_outputs = task.get("step_outputs", {})

    start = time.time()

    try:
        from agents.strategy_generation import StrategyGenerationAgent

        agent = StrategyGenerationAgent()

        state = {
            "task_id": body.task_id,
            "task_base_info": task_base,
            "news_retrieval_output": step_outputs.get("news_retrieval", {}),
            "event_classification_output": step_outputs.get("event_classification", {}),
            "sentiment_analysis_output": step_outputs.get("sentiment_analysis", {}),
            "fundamental_impact_output": step_outputs.get("fundamental_impact", {}),
            "industry_chain_output": step_outputs.get("industry_chain", {}),
        }

        result = agent.run(state)
        output = result.get("strategy_generation_output", {})

        duration = int((time.time() - start) * 1000)

        task_store.update_task(
            body.task_id,
            status="IN_PROGRESS",
            current_step="strategy_generation",
            append_steps_completed=["strategy_generation"],
            update_step_output={"strategy_generation": output},
        )

        return {
            "success": True,
            "task_id": body.task_id,
            "step": "strategy_generation",
            "step_description": STEP_DESCRIPTIONS["strategy_generation"],
            "duration_ms": duration,
            "output": output,
            "next_step": "risk_control",
        }

    except Exception as e:
        task_store.update_task(body.task_id, status="ERROR", error=str(e))
        raise HTTPException(status_code=500, detail=f"策略生成失败: {e}")


# ================================================================== #
#  Step 9: 风控校验
# ================================================================== #

@router.post(
    "/step/risk-control",
    summary="风控校验",
    description="调用 LLM 进行风控校验。耗时约 15 秒。",
)
def step_risk_control(body: ExecuteStepRequest):
    task = task_store.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_base = task.get("task_base_info", {})
    step_outputs = task.get("step_outputs", {})

    start = time.time()

    try:
        from agents.risk_control import RiskControlAgent

        agent = RiskControlAgent()

        state = {
            "task_id": body.task_id,
            "task_base_info": task_base,
            "strategy_generation_output": step_outputs.get("strategy_generation", {}),
        }

        result = agent.run(state)
        output = result.get("risk_control_output", {})

        duration = int((time.time() - start) * 1000)

        task_store.update_task(
            body.task_id,
            status="IN_PROGRESS",
            current_step="risk_control",
            append_steps_completed=["risk_control"],
            update_step_output={"risk_control": output},
        )

        return {
            "success": True,
            "task_id": body.task_id,
            "step": "risk_control",
            "step_description": STEP_DESCRIPTIONS["risk_control"],
            "duration_ms": duration,
            "output": output,
            "next_step": "generate_report",
        }

    except Exception as e:
        task_store.update_task(body.task_id, status="ERROR", error=str(e))
        raise HTTPException(status_code=500, detail=f"风控校验失败: {e}")


# ================================================================== #
#  Step 10: 生成报告
# ================================================================== #

@router.post(
    "/step/generate-report",
    summary="生成研究报告",
    description="聚合所有步骤结果，生成最终研究报告。无外部请求，响应极快。",
)
def step_generate_report(body: ExecuteStepRequest):
    task = task_store.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_base = task.get("task_base_info", {})
    step_outputs = task.get("step_outputs", {})

    start = time.time()

    try:
        from agents.compliance import COMPLIANCE_DISCLAIMER

        report = {
            "task_base_info": task_base,
            "news_summary": step_outputs.get("news_retrieval", {}),
            "event_classification_result": step_outputs.get("event_classification", {}),
            "sentiment_analysis_result": step_outputs.get("sentiment_analysis", {}),
            "fundamental_impact_report": step_outputs.get("fundamental_impact", {}),
            "industry_chain_analysis_result": step_outputs.get("industry_chain", {}),
            "strategy_suggestion": step_outputs.get("strategy_generation", {}),
            "risk_control_rules": step_outputs.get("risk_control", {}),
            "compliance_disclaimer": COMPLIANCE_DISCLAIMER,
            "full_link_log": {
                "task_id": body.task_id,
                "status": "已完成",
                "steps_completed": task.get("steps_completed", []),
            },
        }

        duration = int((time.time() - start) * 1000)

        task_store.update_task(
            body.task_id,
            status="COMPLETED",
            current_step="generate_report",
            append_steps_completed=["generate_report"],
            update_step_output={"final_report": report},
            final_report=report,
        )

        return {
            "success": True,
            "task_id": body.task_id,
            "step": "generate_report",
            "step_description": STEP_DESCRIPTIONS["generate_report"],
            "duration_ms": duration,
            "report": report,
            "status": "COMPLETED",
            "message": "全链路分析已完成",
        }

    except Exception as e:
        task_store.update_task(body.task_id, status="ERROR", error=str(e))
        raise HTTPException(status_code=500, detail=f"报告生成失败: {e}")


# ================================================================== #
#  任务状态查询
# ================================================================== #

@router.get(
    "/task/{task_id}",
    summary="查询任务状态",
    description="查询任务当前状态、已完成的步骤、待执行的步骤",
)
def get_task_status(task_id: str):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    steps_completed = task.get("steps_completed", [])
    steps_pending = [s for s in STEP_ORDER if s not in steps_completed]

    total_steps = len(STEP_ORDER)
    completed_steps = len(steps_completed)
    progress_percent = int((completed_steps / total_steps) * 100)

    return {
        "success": True,
        "task_id": task_id,
        "status": task.get("status"),
        "current_step": task.get("current_step"),
        "progress": {
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "progress_percent": progress_percent,
        },
        "steps_completed": steps_completed,
        "steps_pending": steps_pending,
        "step_outputs": task.get("step_outputs", {}),
        "can_resume": task.get("status") in ["CREATED", "IN_PROGRESS", "ERROR"],
        "error": task.get("error"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }


@router.get(
    "/task/{task_id}/report",
    summary="获取最终报告",
    description="获取任务完成后的最终研究报告",
)
def get_task_report(task_id: str):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.get("status") != "COMPLETED":
        raise HTTPException(status_code=400, detail="任务尚未完成")

    return {
        "success": True,
        "task_id": task_id,
        "report": task.get("final_report"),
    }


# ================================================================== #
#  任务管理
# ================================================================== #

@router.delete(
    "/task/{task_id}",
    summary="删除任务",
    description="删除任务及其所有中间数据",
)
def delete_task(task_id: str):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_store.delete_task(task_id)

    return {
        "success": True,
        "task_id": task_id,
        "message": "任务已删除",
    }


@router.post(
    "/task/{task_id}/reset",
    summary="重置任务",
    description="重置任务状态，清除已完成的步骤，可重新执行",
)
def reset_task(task_id: str):
    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_store.update_task(
        task_id,
        status="CREATED",
        current_step="init",
        steps_completed=[],
        steps_pending=STEP_ORDER.copy(),
        step_outputs={},
        error=None,
    )

    return {
        "success": True,
        "task_id": task_id,
        "message": "任务已重置，可重新执行各步骤",
    }


# ================================================================== #
#  步骤信息查询
# ================================================================== #

@router.get(
    "/steps/info",
    summary="获取步骤信息",
    description="获取所有步骤的描述、预计耗时、是否需要外部请求",
)
def get_steps_info():
    return {
        "success": True,
        "steps": [
            {
                "name": step,
                "description": STEP_DESCRIPTIONS[step],
                "has_external_request": STEP_EXTERNAL_REQUESTS[step],
                "estimated_time_seconds": STEP_ESTIMATED_TIME[step],
            }
            for step in STEP_ORDER
        ],
        "total_estimated_time_seconds": sum(STEP_ESTIMATED_TIME.values()),
        "parallel_steps": {
            "fundamental_impact": ["industry_chain"],
            "note": "基本面分析和产业链分析可以并行执行",
        },
    }
