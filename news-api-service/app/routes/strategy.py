# -*- coding: utf-8 -*-
"""交易策略生成与参数精细化 API（Strategy Agent）"""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import strategy_agent

router = APIRouter(prefix="/api", tags=["策略生成"])


class StrategyGenerateBody(BaseModel):
    """Strategy Agent 请求体。"""

    symbol: str = Field(..., description="标的代码，如 600000.SH")
    name: str = Field(..., description="标的名称，如 浦发银行")
    signal_result: Dict[str, Any] = Field(
        ...,
        description="阶段3 /api/signal/validate 返回的 result 字段（完整 JSON）",
    )
    risk_preference: str = Field(
        ...,
        description="用户风险偏好：保守 / 稳健 / 进取",
    )
    investment_horizon: str = Field(
        ...,
        description="投资周期：短线 / 中线 / 长线",
    )
    max_position_pct: float = Field(
        ...,
        gt=0,
        le=100,
        description="单票最大仓位上限（%），如 30 表示 30%",
    )


@router.post(
    "/strategy/generate",
    summary="交易策略生成与参数精细化",
    description=(
        "输入阶段3信号验证结果与用户风险偏好，生成结构化交易策略，"
        "包含仓位管理、入场条件、止盈止损、极端行情应对方案与盈亏比测算。"
    ),
)
def strategy_generate(body: StrategyGenerateBody):
    """Strategy Agent：策略生成主入口。"""
    if not body.symbol or not body.name:
        raise HTTPException(status_code=400, detail="symbol 与 name 为必填。")
    if not body.signal_result:
        raise HTTPException(
            status_code=400,
            detail="signal_result 为必填（阶段3的 result 字段）。",
        )
    if body.risk_preference not in ("保守", "稳健", "进取"):
        raise HTTPException(
            status_code=400,
            detail="risk_preference 须为：保守 / 稳健 / 进取。",
        )
    if body.investment_horizon not in ("短线", "中线", "长线"):
        raise HTTPException(
            status_code=400,
            detail="investment_horizon 须为：短线 / 中线 / 长线。",
        )

    try:
        agent = strategy_agent.StrategyAgent()
        result = agent.generate(
            symbol=body.symbol,
            name=body.name,
            signal_result=body.signal_result,
            risk_preference=body.risk_preference,
            investment_horizon=body.investment_horizon,
            max_position_pct=body.max_position_pct,
        )
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"策略生成失败: {e}"
        ) from e

    return {
        "success": True,
        "report_md": result.report_md,
        "result": result.result_json,
    }
