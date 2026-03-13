# -*- coding: utf-8 -*-
"""三维度交叉验证与信号过滤 API（Signal Validator）"""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import signal_validator

router = APIRouter(prefix="/api", tags=["信号验证"])


class SignalValidateBody(BaseModel):
    """Signal Validator 请求体：阶段1 + 阶段2 完整 result + 标的信息。"""

    symbol: str
    name: str
    # 阶段1 /api/news/analyze 返回的 result 字段（完整 JSON）
    news_result: Dict[str, Any]
    # 阶段2 /api/research/analyze 返回的 result 字段（完整 JSON）
    research_result: Dict[str, Any]


@router.post(
    "/signal/validate",
    summary="三维度交叉验证与信号过滤",
    description=(
        "输入阶段1舆情结果与阶段2基本面结果，进行基本面-舆情-资金面三维校验，"
        "完成噪音过滤、历史相似事件回测、信号确定性分级与市场定价充分性判断。"
    ),
)
def signal_validate(body: SignalValidateBody):
    """Signal Validator：三维交叉验证主入口。"""
    if not body.symbol or not body.name:
        raise HTTPException(status_code=400, detail="symbol 与 name 为必填。")
    if not body.news_result:
        raise HTTPException(status_code=400, detail="news_result 为必填（阶段1的 result 字段）。")
    if not body.research_result:
        raise HTTPException(status_code=400, detail="research_result 为必填（阶段2的 result 字段）。")

    try:
        validator = signal_validator.SignalValidator()
        result = validator.validate(
            symbol=body.symbol,
            name=body.name,
            news_result=body.news_result,
            research_result=body.research_result,
        )
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"信号验证失败: {e}") from e

    return {
        "success": True,
        "report_md": result.report_md,
        "result": result.result_json,
    }
