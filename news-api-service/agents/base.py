# -*- coding: utf-8 -*-
"""智能体抽象基类

所有业务智能体必须继承 BaseAgent 并实现 run() 方法。
提供统一的 LLM 调用接口、日志记录、错误重试、超时控制。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from core.config import SystemConfig, get_config
from core.llm import LLMClient
from core.logger import get_logger
from core.schemas import AgentOutput, AgentStatus


class BaseAgent(ABC):
    """多智能体系统的抽象基类。

    子类必须：
      1. 设置 name 类属性（唯一标识）
      2. 实现 run(state) -> dict 方法
    """

    name: str = "base_agent"
    description: str = ""
    max_retries: int = 2

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config: Optional[SystemConfig] = None,
    ) -> None:
        self.config = config or get_config()
        self.llm = llm_client or LLMClient(self.config)
        self.logger = get_logger(self.name)

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行智能体核心逻辑。

        Args:
            state: LangGraph 全局状态（兼容 AgentState / FullLinkState）

        Returns:
            状态更新字典，仅包含本智能体负责的字段。
        """
        ...

    # ── 对外安全调用入口 ──

    def safe_run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """带异常捕获 + 自动重试的运行包装，供 LangGraph 节点调用。"""
        last_error: Optional[Exception] = None
        start = time.time()

        for attempt in range(1, self.max_retries + 1):
            start = time.time()
            try:
                self.logger.info(
                    "开始执行 | attempt=%d/%d", attempt, self.max_retries
                )
                result = self.run(state)
                duration = int((time.time() - start) * 1000)
                self.logger.info("执行完成 | duration=%dms", duration)
                return result
            except Exception as exc:
                last_error = exc
                duration = int((time.time() - start) * 1000)
                self.logger.error(
                    "执行失败 | attempt=%d/%d duration=%dms error=%s",
                    attempt, self.max_retries, duration, exc,
                )
                if attempt < self.max_retries:
                    wait = min(2 ** attempt, 15)
                    self.logger.info("等待 %d 秒后重试…", wait)
                    time.sleep(wait)

        duration = int((time.time() - start) * 1000)
        output = self._make_output(
            AgentStatus.ERROR,
            error=str(last_error),
            duration_ms=duration,
            retries=self.max_retries,
        )
        return {
            "full_link_execution_log": [output],
            "errors": [f"[{self.name}] {last_error}"],
            "current_step": f"{self.name}_error",
        }

    # ── 辅助方法 ──

    def _make_output(
        self,
        status: AgentStatus,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        duration_ms: int = 0,
        retries: int = 0,
    ) -> Dict[str, Any]:
        return AgentOutput(
            agent_name=self.name,
            status=status,
            data=data or {},
            error=error,
            duration_ms=duration_ms,
            retries=retries,
        ).model_dump()
