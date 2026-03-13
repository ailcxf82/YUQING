# -*- coding: utf-8 -*-
"""多厂商 LLM 统一调用客户端

支持 DeepSeek / 智谱 GLM / OpenAI，
内置指数退避重试、超时控制、JSON 响应解析。
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import httpx

from core.config import SystemConfig, get_config
from core.logger import get_logger

logger = get_logger("llm")


class LLMClient:
    """统一 LLM 调用客户端"""

    def __init__(self, config: Optional[SystemConfig] = None) -> None:
        cfg = config or get_config()
        params = cfg.get_llm_params()
        self.provider: str = params["provider"]
        self.api_key: str = params["api_key"]
        self.model: str = params["model"]
        self.api_url: str = params["api_url"]
        self.timeout: int = params["timeout"]
        self.max_retries: int = params["max_retries"]
        self.default_temperature: float = params["temperature"]
        self.default_max_tokens: int = params["max_tokens"]

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """调用 LLM 返回纯文本。内置指数退避重试。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": (
                temperature if temperature is not None else self.default_temperature
            ),
            "max_tokens": max_tokens or self.default_max_tokens,
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "LLM 调用 | provider=%s model=%s attempt=%d/%d",
                    self.provider, self.model, attempt, self.max_retries,
                )
                with httpx.Client(timeout=float(self.timeout)) as client:
                    resp = client.post(self.api_url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if not content:
                    raise ValueError("LLM 返回内容为空")
                logger.debug("LLM 调用成功 | chars=%d", len(content))
                return content
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "LLM 调用失败 | attempt=%d/%d error=%s",
                    attempt, self.max_retries, exc,
                )
                if attempt < self.max_retries:
                    wait = min(2 ** attempt, 30)
                    time.sleep(wait)

        raise RuntimeError(
            f"LLM 在 {self.max_retries} 次重试后仍失败: {last_error}"
        ) from last_error

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """调用 LLM 并从响应中提取 JSON 对象"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self.chat(messages, temperature=temperature)
        return self._extract_json(content)

    def chat_json_list(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """调用 LLM 并从响应中提取 JSON 数组"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self.chat(messages, temperature=temperature)
        return self._extract_json_list(content)

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1:
            raise ValueError(f"LLM 响应中未找到 JSON: {text[:200]}")

        json_str = text[first : last + 1]
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败: {exc}; 片段: {json_str[:300]}") from exc

        if not isinstance(result, dict):
            raise ValueError(
                f"JSON 根节点类型错误，期望 dict，实际 {type(result).__name__}"
            )
        return result

    @staticmethod
    def _extract_json_list(text: str) -> List[Dict[str, Any]]:
        """从 LLM 响应中提取 JSON 数组，兼容多种格式"""
        # 优先尝试找 [...] 数组
        arr_start = text.find("[")
        arr_end = text.rfind("]")
        if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
            json_str = text[arr_start : arr_end + 1]
            try:
                result = json.loads(json_str)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        # 兜底：LLM 可能返回逗号分隔的 {...}, {...} 而没有外层 []
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1:
            wrapped = "[" + text[first_brace : last_brace + 1] + "]"
            try:
                result = json.loads(wrapped)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        raise ValueError(f"无法从响应中提取 JSON 数组: {text[:300]}")
