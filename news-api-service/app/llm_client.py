# -*- coding: utf-8 -*-
"""LLM 客户端：用于将用户关键词归一成"核心关键词"

支持多 LLM 提供商切换，通过 Settings.llm_provider 配置。
"""
from typing import Optional

import httpx

from app.config import get_settings


def summarize_keyword(raw_keyword: str) -> str:
    """调用 LLM，将用户输入归一成一个核心检索关键词。

    若未配置 API Key 或调用失败，则直接返回原始关键词。
    """
    raw_keyword = (raw_keyword or "").strip()
    if not raw_keyword:
        return raw_keyword

    settings = get_settings()
    try:
        llm_config = settings.get_llm_config()
    except ValueError:
        return raw_keyword

    headers = {
        "Authorization": f"Bearer {llm_config.api_key}",
        "Content-Type": "application/json",
    }
    prompt = (
        "你是一个关键词归一助手。我会给你一个用户输入的中文或英文关键词，"
        "请你只返回一个最适合作为数据库检索的【核心关键词】或短语，不要解释，不要添加任何标点或其他文字。"
    )
    data = {
        "model": llm_config.model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": raw_keyword},
        ],
        "temperature": 0.3,
        "max_tokens": 16,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(llm_config.api_url, headers=headers, json=data)
        resp.raise_for_status()
        js = resp.json()
        content = (
            js.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return content or raw_keyword
    except Exception:
        return raw_keyword
