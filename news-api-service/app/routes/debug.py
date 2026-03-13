# -*- coding: utf-8 -*-
"""内部调试接口：LLM 连通性、系统状态、智能体健康检查"""

from __future__ import annotations

from typing import Any, Dict

import httpx
from fastapi import APIRouter

from app.config import get_settings


router = APIRouter(prefix="/internal/debug", tags=["内部-调试"], include_in_schema=False)


@router.get("/llm")
def debug_llm(ping: bool = True) -> Dict[str, Any]:
    """检查 LLM 配置与连通性"""
    settings = get_settings()

    result: Dict[str, Any] = {
        "provider": settings.llm_provider,
        "model": None,
        "api_url": None,
        "has_key": False,
        "ping_ok": None,
        "error": None,
    }

    try:
        llm_config = settings.get_llm_config()
        result["model"] = llm_config.model
        result["api_url"] = llm_config.api_url
        result["has_key"] = bool(llm_config.api_key)
        api_key = llm_config.api_key
        model = llm_config.model
        api_url = llm_config.api_url
    except ValueError as e:
        result["error"] = str(e)
        result["ping_ok"] = False
        return result

    if not ping:
        return result

    if not result["has_key"]:
        result["ping_ok"] = False
        result["error"] = "no_api_key_configured"
        return result

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "temperature": 0.0,
        "max_tokens": 4,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(api_url, headers=headers, json=data)
        resp.raise_for_status()
        result["ping_ok"] = True
    except Exception as exc:
        result["ping_ok"] = False
        result["error"] = str(exc)

    return result


@router.get("/agents")
def debug_agents() -> Dict[str, Any]:
    """检查 Phase 4 各智能体初始化状态"""
    agent_classes = [
        ("ComplianceAgent", "agents.compliance"),
        ("EventClassificationAgent", "agents.event_classification"),
        ("SentimentAnalysisAgent", "agents.sentiment_analysis"),
        ("FundamentalImpactAgent", "agents.fundamental_impact"),
        ("IndustryChainAgent", "agents.industry_chain"),
        ("StrategyGenerationAgent", "agents.strategy_generation"),
        ("RiskControlAgent", "agents.risk_control"),
        ("FeedbackOptimizationAgent", "agents.feedback_optimization"),
        ("NewsRetrievalAgent", "agents.news_retrieval"),
    ]

    results = {}
    for cls_name, module_path in agent_classes:
        try:
            mod = __import__(module_path, fromlist=[cls_name])
            cls = getattr(mod, cls_name)
            instance = cls()
            results[cls_name] = {
                "status": "ok",
                "name": instance.name,
            }
        except Exception as exc:
            results[cls_name] = {
                "status": "error",
                "error": str(exc)[:200],
            }

    all_ok = all(v["status"] == "ok" for v in results.values())
    return {
        "all_agents_ok": all_ok,
        "total": len(agent_classes),
        "agents": results,
    }


@router.get("/config")
def debug_config() -> Dict[str, Any]:
    """检查系统配置（不泄露密钥）"""
    settings = get_settings()
    try:
        from core.config import get_config
        sys_config = get_config()
        provider = sys_config.llm_provider
        has_tushare = bool(sys_config.tushare_token)
    except Exception:
        provider = settings.llm_provider
        has_tushare = bool(settings.tushare_token)

    return {
        "llm_provider": provider,
        "has_tushare_token": has_tushare,
        "has_deepseek_key": bool(settings.deepseek_api_key),
        "has_zhipu_key": bool(settings.zhipu_api_key or settings.zai_api_key),
        "has_openai_key": bool(settings.openai_api_key),
        "database_url": settings.database_url,
    }
