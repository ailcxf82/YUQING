# -*- coding: utf-8 -*-
"""Phase 4 多智能体系统：10 个单一职责智能体 + 中枢调度

架构：1 中枢 + 7 核心业务 + 2 支撑保障
"""

from agents.base import BaseAgent
from agents.compliance import ComplianceAgent
from agents.event_classification import EventClassificationAgent
from agents.feedback_optimization import FeedbackOptimizationAgent
from agents.fundamental_impact import FundamentalImpactAgent
from agents.industry_chain import IndustryChainAgent
from agents.news_retrieval import NewsRetrievalAgent
from agents.orchestrator import OrchestratorAgent
from agents.risk_control import RiskControlAgent
from agents.sentiment_analysis import SentimentAnalysisAgent
from agents.strategy_generation import StrategyGenerationAgent

__all__ = [
    "BaseAgent",
    "OrchestratorAgent",
    "NewsRetrievalAgent",
    "EventClassificationAgent",
    "SentimentAnalysisAgent",
    "FundamentalImpactAgent",
    "IndustryChainAgent",
    "StrategyGenerationAgent",
    "RiskControlAgent",
    "ComplianceAgent",
    "FeedbackOptimizationAgent",
]
