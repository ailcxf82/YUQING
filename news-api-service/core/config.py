# -*- coding: utf-8 -*-
"""系统配置管理

基于 Pydantic BaseSettings，支持 .env 文件加载与环境变量覆盖。
提供配置热更新能力，无需重启即可重新读取。
"""

from __future__ import annotations

import threading
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import Field
from pydantic_settings import BaseSettings

from core.logger import get_logger

logger = get_logger("config")


class LLMProvider(str, Enum):
    DEEPSEEK = "deepseek"
    ZHIPU = "zhipu"
    OPENAI = "openai"


class SystemConfig(BaseSettings):
    """系统全局配置——单一来源管理所有参数"""

    # ── LLM ──
    llm_provider: str = Field(default="deepseek", description="deepseek / zhipu / openai")

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_api_url: str = "https://api.deepseek.com/v1/chat/completions"

    zhipu_api_key: str = ""
    zhipu_model: str = "glm-4"
    zhipu_api_url: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_api_url: str = "https://api.openai.com/v1/chat/completions"

    zai_api_key: str = ""
    zai_model: str = "glm-4"

    llm_timeout: int = Field(default=120, description="LLM 超时(秒)")
    llm_max_retries: int = Field(default=3, description="LLM 最大重试")
    llm_temperature: float = Field(default=0.2)
    llm_max_tokens: int = Field(default=4096)

    # ── 数据源 ──
    tushare_token: str = ""

    # ── 向量数据库与 Embedding ──
    # 注意: Embedding 独立于 llm_provider, 因为 DeepSeek/OpenAI 不提供中文向量化服务
    # 如需切换后端, 在 .env 中设置 EMBEDDING_BACKEND=local 或 EMBEDDING_BACKEND=hash
    lancedb_path: str = Field(default="./data/lancedb")
    embedding_backend: str = Field(
        default="zhipu",
        description="embedding 后端: zhipu / local / hash (独立于 llm_provider)",
    )
    embedding_model: str = Field(
        default="embedding-3",
        description="zhipu=embedding-3, local=BAAI/bge-small-zh-v1.5",
    )
    embedding_dim: int = Field(default=1024)

    # ── 系统 ──
    log_level: str = Field(default="INFO")
    log_dir: str = Field(default="./logs")
    database_url: str = "sqlite:///./newsdata.db"
    host: str = "0.0.0.0"
    port: int = 8000

    # ── 信号阈值 ──
    sentiment_bullish_min: float = 7.0
    sentiment_bearish_max: float = 3.0
    volume_anomaly_ratio: float = 1.5

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_llm_params(self) -> Dict[str, Any]:
        """返回当前 LLM 提供商的完整调用参数"""
        provider = self.llm_provider.lower()
        providers: Dict[str, Dict[str, Any]] = {
            "deepseek": {
                "api_key": self.deepseek_api_key,
                "model": self.deepseek_model,
                "api_url": self.deepseek_api_url,
            },
            "zhipu": {
                "api_key": self.zhipu_api_key or self.zai_api_key,
                "model": self.zhipu_model or self.zai_model,
                "api_url": self.zhipu_api_url,
            },
            "openai": {
                "api_key": self.openai_api_key,
                "model": self.openai_model,
                "api_url": self.openai_api_url,
            },
        }
        params = providers.get(provider)
        if not params:
            raise ValueError(
                f"不支持的 LLM 提供商: {provider}，可选: deepseek / zhipu / openai"
            )
        if not params["api_key"]:
            raise ValueError(f"未配置 {provider} 的 API Key")

        params.update({
            "provider": provider,
            "timeout": self.llm_timeout,
            "max_retries": self.llm_max_retries,
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
        })
        return params


# ── 全局单例 ──

_config: Optional[SystemConfig] = None
_lock = threading.Lock()


def get_config() -> SystemConfig:
    """获取全局配置（线程安全单例）"""
    global _config
    if _config is None:
        with _lock:
            if _config is None:
                _config = SystemConfig()
                logger.info(
                    "系统配置加载完成 | provider=%s tushare=%s",
                    _config.llm_provider,
                    "已配置" if _config.tushare_token else "未配置",
                )
    return _config


def reload_config() -> SystemConfig:
    """热更新：重新读取 .env 文件，无需重启"""
    global _config
    with _lock:
        _config = SystemConfig()
        logger.info("系统配置已热更新 | provider=%s", _config.llm_provider)
    return _config
