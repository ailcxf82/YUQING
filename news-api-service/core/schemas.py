# -*- coding: utf-8 -*-
"""全局数据结构与状态流转 Schema

定义 Task、AgentState、AgentOutput 等核心数据结构，
为多智能体系统提供统一的通信协议与状态管理基础。
"""

from __future__ import annotations

import operator
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ================================================================== #
#  枚举定义
# ================================================================== #

class RiskPreference(str, Enum):
    CONSERVATIVE = "保守"
    BALANCED = "稳健"
    AGGRESSIVE = "进取"


class InvestmentHorizon(str, Enum):
    SHORT = "短线"
    MID = "中线"
    LONG = "长线"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"
    SKIPPED = "skipped"


# ================================================================== #
#  任务定义
# ================================================================== #

class TimeRange(BaseModel):
    start: str = Field(..., description="起始日期 YYYY-MM-DD")
    end: str = Field(..., description="结束日期 YYYY-MM-DD")


class Task(BaseModel):
    """用户投研任务：多智能体协作的起点"""

    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    symbol: str = Field(..., description="标的代码，如 600519.SH")
    name: str = Field(..., description="标的名称，如 贵州茅台")
    industry: str = Field(default="", description="所属行业")
    topics: List[str] = Field(default_factory=list, description="关注主题")
    time_range: TimeRange = Field(..., description="分析时间范围")
    requirements: str = Field(default="", description="用户自定义分析要求")
    risk_preference: RiskPreference = Field(default=RiskPreference.BALANCED)
    investment_horizon: InvestmentHorizon = Field(default=InvestmentHorizon.MID)
    max_position_pct: float = Field(default=30.0, gt=0, le=100)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


# ================================================================== #
#  智能体标准化输入 / 输出接口
# ================================================================== #

class AgentOutput(BaseModel):
    """智能体标准化输出——所有智能体必须通过此结构返回结果"""

    agent_name: str
    status: AgentStatus = AgentStatus.PENDING
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    retries: int = 0
    duration_ms: int = 0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


class AgentInput(BaseModel):
    """智能体标准化输入——调度器为每个智能体构造此结构"""

    task: Task
    context: Dict[str, Any] = Field(default_factory=dict)
    upstream_outputs: Dict[str, AgentOutput] = Field(default_factory=dict)


# ================================================================== #
#  舆情数据标准化记录
# ================================================================== #

class NewsRecord(BaseModel):
    """结构化舆情数据记录——采集、预处理、向量化的标准输出"""

    news_id: str = Field(..., description="舆情唯一 ID")
    publish_time: str = Field(..., description="发布时间 ISO 格式")
    title: str = Field(default="", description="标题")
    content: str = Field(default="", description="正文内容")
    source: str = Field(default="", description="发布渠道")
    source_level: str = Field(default="C", description="信源等级 S/A/B/C/D")
    source_weight: float = Field(default=0.5, description="渠道权重 0-1")
    core_entity: str = Field(default="", description="核心实体")
    related_stock: str = Field(default="", description="关联标的代码+名称")
    event_type: str = Field(default="", description="事件类型预分类")
    keywords: List[str] = Field(default_factory=list, description="核心关键词")
    spread_count: int = Field(default=0, description="传播量级")
    url: str = Field(default="")
    content_hash: str = Field(default="", description="内容指纹(去重)")
    symbol: str = Field(default="", description="查询标的")
    chunk_texts: List[str] = Field(default_factory=list, description="语义分块")


# ================================================================== #
#  LangGraph 全局状态（贯穿整个多智能体调度流程）
# ================================================================== #

class AgentState(TypedDict):
    """LangGraph 全局状态。

    - 普通字段：节点返回新值时直接覆盖
    - Annotated[list, operator.add]：节点返回列表时追加到已有列表
    """

    task: dict

    # 各智能体的中间输出
    news_data: dict
    sentiment_result: dict
    research_result: dict
    strategy_result: dict

    # 全链路追踪
    agent_outputs: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]

    # 最终结果
    final_report: str
    final_json: dict

    # 流程控制
    current_step: str


# ================================================================== #
#  Phase 4: 精细化多智能体全链路协同 — 标准化 I/O
# ================================================================== #

class UserRequest(BaseModel):
    """用户请求标准化结构体"""
    target_type: str = Field(default="个股", description="分析目标类型：个股/行业/主题/全市场")
    target_code: List[str] = Field(default_factory=list, description="标的代码列表")
    target_name: List[str] = Field(default_factory=list, description="标的/行业/主题名称")
    keyword: str = Field(
        default="",
        description="自然语言关键词：公司名/行业/主题/事件描述等，用于语义解析目标标的",
    )
    time_range: str = Field(default="近7天", description="舆情时间范围")
    custom_time_start: str = Field(default="", description="自定义开始时间")
    custom_time_end: str = Field(default="", description="自定义结束时间")
    analysis_depth: str = Field(default="标准版", description="分析深度：基础版/标准版/深度版")
    user_custom_rules: Dict[str, Any] = Field(default_factory=dict, description="用户自定义规则/阈值")


class NewsRetrievalOutput(BaseModel):
    """舆情采集智能体标准化输出"""
    task_id: str = ""
    news_total_count: int = 0
    news_structured_data: List[Dict[str, Any]] = Field(default_factory=list)
    vector_db_index_info: Dict[str, Any] = Field(default_factory=dict)
    data_quality_report: Dict[str, Any] = Field(default_factory=dict)
    execution_log: Dict[str, Any] = Field(default_factory=dict)


class EventClassificationOutput(BaseModel):
    """事件分类智能体标准化输出"""
    task_id: str = ""
    entity_linking_result: List[Dict[str, Any]] = Field(default_factory=list)
    event_classification_result: List[Dict[str, Any]] = Field(default_factory=list)
    influence_score_result: List[Dict[str, Any]] = Field(default_factory=list)
    core_news_list: List[Dict[str, Any]] = Field(default_factory=list)
    execution_log: Dict[str, Any] = Field(default_factory=dict)


class SentimentAnalysisOutput(BaseModel):
    """情绪量化智能体标准化输出"""
    task_id: str = ""
    news_sentiment_detail: List[Dict[str, Any]] = Field(default_factory=list)
    target_sentiment_index: Dict[str, Any] = Field(default_factory=dict)
    sentiment_consistency_report: Dict[str, Any] = Field(default_factory=dict)
    news_comprehensive_rating: List[Dict[str, Any]] = Field(default_factory=list)
    execution_log: Dict[str, Any] = Field(default_factory=dict)


class FundamentalImpactOutput(BaseModel):
    """基本面推演智能体标准化输出"""
    task_id: str = ""
    impact_logic_breakdown: Dict[str, Any] = Field(default_factory=dict)
    impact_cycle_and_scale: Dict[str, Any] = Field(default_factory=dict)
    historical_event_backtest: Dict[str, Any] = Field(default_factory=dict)
    impact_certainty_rating: str = "中确定性"
    full_impact_link_report: Dict[str, Any] = Field(default_factory=dict)
    execution_log: Dict[str, Any] = Field(default_factory=dict)


class IndustryChainOutput(BaseModel):
    """产业链传导智能体标准化输出"""
    task_id: str = ""
    industry_chain_mapping: Dict[str, Any] = Field(default_factory=dict)
    conduction_logic_breakdown: Dict[str, Any] = Field(default_factory=dict)
    benefit_damage_target_list: List[Dict[str, Any]] = Field(default_factory=list)
    cross_industry_conduction_forecast: Dict[str, Any] = Field(default_factory=dict)
    industry_boom_change_judgment: Dict[str, Any] = Field(default_factory=dict)
    execution_log: Dict[str, Any] = Field(default_factory=dict)


class StrategyGenerationOutput(BaseModel):
    """策略生成智能体标准化输出"""
    task_id: str = ""
    strategy_adaptability_judgment: Dict[str, Any] = Field(default_factory=dict)
    core_strategy_logic: str = ""
    entry_exit_conditions: Dict[str, Any] = Field(default_factory=dict)
    reference_position_range: str = ""
    core_focus_indicators: List[str] = Field(default_factory=list)
    execution_log: Dict[str, Any] = Field(default_factory=dict)


class RiskControlOutput(BaseModel):
    """风控智能体标准化输出"""
    task_id: str = ""
    strategy_risk_level: str = "中风险"
    strategy_rationality_check_report: Dict[str, Any] = Field(default_factory=dict)
    stop_loss_stop_profit_rules: Dict[str, Any] = Field(default_factory=dict)
    core_risk_points_prompt: List[str] = Field(default_factory=list)
    risk_control_execution_suggestion: Dict[str, Any] = Field(default_factory=dict)
    execution_log: Dict[str, Any] = Field(default_factory=dict)


class ComplianceCheckOutput(BaseModel):
    """合规校验智能体标准化输出"""
    task_id: str = ""
    agent_name: str = ""
    check_result: str = "通过"
    corrected_content: Dict[str, Any] = Field(default_factory=dict)
    violation_details: List[str] = Field(default_factory=list)
    fuse_trigger: bool = False
    compliance_disclaimer: str = (
        "【免责声明】本分析报告由AI系统自动生成，仅供投资研究参考，"
        "不构成任何投资建议。投资有风险，决策需谨慎。"
        "本工具不对任何投资损益承担责任。"
    )
    execution_log: Dict[str, Any] = Field(default_factory=dict)


class FeedbackOptimizationOutput(BaseModel):
    """反馈优化智能体标准化输出"""
    task_id: str = ""
    analysis_accuracy_evaluation: Dict[str, Any] = Field(default_factory=dict)
    deviation_reason_positioning: List[str] = Field(default_factory=list)
    optimization_content: Dict[str, Any] = Field(default_factory=dict)
    optimization_backtest_result: Dict[str, Any] = Field(default_factory=dict)
    optimization_execution_suggestion: Dict[str, Any] = Field(default_factory=dict)
    execution_log: Dict[str, Any] = Field(default_factory=dict)


class FinalResearchReport(BaseModel):
    """最终投研报告标准化结构体"""
    task_base_info: Dict[str, Any] = Field(default_factory=dict)
    news_summary: Dict[str, Any] = Field(default_factory=dict)
    event_classification_result: Dict[str, Any] = Field(default_factory=dict)
    sentiment_analysis_result: Dict[str, Any] = Field(default_factory=dict)
    fundamental_impact_report: Dict[str, Any] = Field(default_factory=dict)
    industry_chain_analysis_result: Dict[str, Any] = Field(default_factory=dict)
    strategy_suggestion: Dict[str, Any] = Field(default_factory=dict)
    risk_control_rules: Dict[str, Any] = Field(default_factory=dict)
    compliance_disclaimer: str = ""
    full_link_log: Dict[str, Any] = Field(default_factory=dict)


# ================================================================== #
#  Phase 4: 全链路状态机（LangGraph）
# ================================================================== #

class FullLinkState(TypedDict):
    """全链路全局状态机——每个智能体仅可修改自己负责的字段"""

    # 任务基础（仅 OrchestratorAgent 可修改）
    task_id: str
    task_base_info: dict
    task_status: str

    # 各节点输出（每个智能体仅修改对应字段）
    news_retrieval_output: dict
    event_classification_output: dict
    sentiment_analysis_output: dict
    fundamental_impact_output: dict
    industry_chain_output: dict
    strategy_generation_output: dict
    risk_control_output: dict

    # 合规记录（Annotated list 追加）
    compliance_check_records: Annotated[list, operator.add]

    # 全链路日志（Annotated list 追加）
    full_link_execution_log: Annotated[list, operator.add]

    # 错误追踪（Annotated list 追加）
    errors: Annotated[list, operator.add]

    # 最终输出（仅 OrchestratorAgent 可修改）
    final_research_report: dict

    # 流程控制
    current_step: str
    retry_counts: dict
    fuse_triggered: bool
