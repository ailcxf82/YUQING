# -*- coding: utf-8 -*-
"""多维度金融数据查询与基本面分析 API（Research Agent）"""
from typing import List, Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import research_agent

router = APIRouter(prefix="/api", tags=["研报与基本面"])


class ResearchAnalyzeBody(BaseModel):
    """Research Agent 请求体：阶段1事件清单 + 标的与时间范围。"""
    symbol: str
    name: str
    start_date: str
    end_date: str
    events: List[Dict[str, Any]]


@router.post(
    "/research/analyze",
    summary="多维度金融数据与基本面分析",
    description=(
        "基于阶段1的舆情事件清单，拉取标的财务/行情/个股数据，"
        "进行舆情-基本面交叉验证、行业与估值分析，返回结构化报告与 JSON。"
    ),
)
def research_analyze(body: ResearchAnalyzeBody):
    """Research Agent：基本面与数据交叉验证入口。"""
    if not body.symbol or not body.name:
        raise HTTPException(status_code=400, detail="symbol 与 name 为必填。")
    if not body.start_date or not body.end_date:
        raise HTTPException(status_code=400, detail="start_date 与 end_date 为必填。")
    if not isinstance(body.events, list):
        raise HTTPException(status_code=400, detail="events 必须为数组（阶段1的结构化事件列表）。")

    try:
        agent = research_agent.ResearchAgent()
        result = agent.analyze(
            symbol=body.symbol,
            name=body.name,
            start_date=body.start_date,
            end_date=body.end_date,
            events=body.events,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"基本面分析失败: {e}") from e

    return {
        "success": True,
        "report_md": result.report_md,
        "result": result.result_json,
    }
