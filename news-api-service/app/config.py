# -*- coding: utf-8 -*-
"""应用配置"""
from enum import Enum
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class LLMProvider(str, Enum):
    """LLM 提供商枚举"""
    DEEPSEEK = "deepseek"
    ZHIPU = "zhipu"
    OPENAI = "openai"


class LLMConfig:
    """LLM 配置封装类"""
    def __init__(
        self,
        provider: LLMProvider,
        api_key: str,
        model: str,
        api_url: str,
        timeout: int,
    ):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.api_url = api_url
        self.timeout = timeout


class Settings(BaseSettings):
    """从环境变量读取配置"""
    # Tushare token，需在 https://tushare.pro 注册获取
    tushare_token: str = ""
    
    # LLM 提供商选择: deepseek, zhipu, openai
    llm_provider: str = "deepseek"
    
    # DeepSeek 配置
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_api_url: str = "https://api.deepseek.com/v1/chat/completions"
    
    # 智谱 GLM 配置
    zhipu_api_key: str = ""
    zhipu_model: str = "glm-4.7"
    zhipu_api_url: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    
    # OpenAI 配置
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_api_url: str = "https://api.openai.com/v1/chat/completions"
    
    # 兼容旧配置（已废弃，优先使用新配置）
    zai_api_key: str = ""
    zai_model: str = "glm-4"
    
    # 数据库路径（相对或绝对）
    database_url: str = "sqlite:///./newsdata.db"
    # 默认抓取时间范围（小时）
    default_fetch_hours: int = 24
    # API 服务 host/port
    host: str = "0.0.0.0"
    port: int = 8000
    # LLM API 超时配置（秒）
    llm_timeout: int = 120

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def get_llm_config(self) -> LLMConfig:
        """获取当前 LLM 配置"""
        provider_str = self.llm_provider.lower()
        
        if provider_str == LLMProvider.DEEPSEEK.value:
            api_key = self.deepseek_api_key
            model = self.deepseek_model
            api_url = self.deepseek_api_url
            provider = LLMProvider.DEEPSEEK
        elif provider_str == LLMProvider.ZHIPU.value:
            api_key = self.zhipu_api_key or self.zai_api_key
            model = self.zhipu_model or self.zai_model
            api_url = self.zhipu_api_url
            provider = LLMProvider.ZHIPU
        elif provider_str == LLMProvider.OPENAI.value:
            api_key = self.openai_api_key
            model = self.openai_model
            api_url = self.openai_api_url
            provider = LLMProvider.OPENAI
        else:
            raise ValueError(f"不支持的 LLM 提供商: {self.llm_provider}，可选值: deepseek, zhipu, openai")
        
        if not api_key:
            raise ValueError(f"未配置 {provider.value} 的 API Key，请设置环境变量")
        
        return LLMConfig(
            provider=provider,
            api_key=api_key,
            model=model,
            api_url=api_url,
            timeout=self.llm_timeout,
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
