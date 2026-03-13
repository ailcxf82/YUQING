# 机构级金融舆情分析系统 — 代码级架构文档

> 版本 4.1 | 更新日期 2026-03-12

---

## 目录

- [1. 系统总览](#1-系统总览)
- [2. 目录结构](#2-目录结构)
- [3. 数据流全景](#3-数据流全景)
- [4. 核心层 core/](#4-核心层-core)
- [5. 智能体层 agents/](#5-智能体层-agents)
- [6. 应用层 app/](#6-应用层-app)
- [7. API 路由一览](#7-api-路由一览)
- [8. 配置体系](#8-配置体系)
- [9. 全链路执行序列](#9-全链路执行序列)
- [10. 性能优化策略](#10-性能优化策略)
- [11. 依赖清单](#11-依赖清单)
- [12. 部署与启动](#12-部署与启动)

---

## 1. 系统总览

```
┌───────────────────────────────────────────────────────────────────┐
│                    机构级金融舆情分析系统 v4.1                       │
│                                                                   │
│  架构：1 中枢调度 + 7 核心业务 + 2 支撑保障 = 10 个单一职责智能体       │
│  框架：FastAPI + LangGraph + LanceDB + Pydantic                   │
│  LLM ：DeepSeek / 智谱GLM（可切换）                                 │
│  数据：Tushare 金融数据 + 定时异步采集                                │
└───────────────────────────────────────────────────────────────────┘
```

### 设计原则

| 原则 | 实现 |
|---|---|
| 采集与分析解耦 | 定时后台采集 → JSON 本地存储 → 分析纯读本地（18ms） |
| 单一职责 | 每个 Agent 只做一件事，通过 Orchestrator 编排 |
| 合规先行 | 每个业务节点后强制合规校验，违规自动熔断 |
| 数据可追溯 | 全链路日志 + Pydantic 严格类型 + FullLinkState 状态机 |
| 两阶段漏斗 | 规则引擎粗筛全量 → LLM 只精分析 Top N |

---

## 2. 目录结构

```
news-api-service/
├── app/                          # 应用层（FastAPI、调度、旧版Agent）
│   ├── main.py                   # FastAPI 入口 + 中间件 + 生命周期
│   ├── config.py                 # 应用层配置（Settings, LLMConfig）
│   ├── database.py               # SQLite 数据库操作（news/fetch_log/scheduler_runs）
│   ├── scheduler.py              # APScheduler 定时任务管理
│   ├── service_switch.py         # 全局服务开关
│   ├── tushare_client.py         # Tushare 旧版采集客户端
│   ├── llm_client.py             # 旧版 LLM 客户端（v1 兼容）
│   ├── news_agent.py             # 旧版 NewsAgent（v1 兼容）
│   ├── research_agent.py         # 旧版 ResearchAgent（v1 兼容）
│   ├── signal_validator.py       # 旧版信号验证器（v1 兼容）
│   ├── strategy_agent.py         # 旧版策略生成器（v1 兼容）
│   ├── routes/
│   │   ├── analysis.py           # Phase4 全链路分析 API（/api/v2/analysis/*）
│   │   ├── news_collect.py       # 舆情采集管理 API（/api/v2/news-collect/*）
│   │   ├── news.py               # 基础新闻数据 API
│   │   ├── debug.py              # 内部调试端点
│   │   ├── admin.py              # 管理后台
│   │   ├── internal.py           # 内部接口
│   │   ├── research.py           # v1 研究分析
│   │   ├── signal.py             # v1 信号验证
│   │   └── strategy.py           # v1 策略生成
│   ├── templates/                # Jinja2 管理后台模板
│   └── static/                   # 静态资源
│
├── agents/                       # 多智能体层（Phase 4）
│   ├── __init__.py               # 导出全部 10 个 Agent
│   ├── base.py                   # BaseAgent 抽象基类
│   ├── orchestrator.py           # OrchestratorAgent — LangGraph 中枢
│   ├── news_retrieval.py         # NewsRetrievalAgent — 本地数据读取
│   ├── event_classification.py   # EventClassificationAgent — 两阶段事件分类
│   ├── sentiment_analysis.py     # SentimentAnalysisAgent — 批量情绪量化
│   ├── fundamental_impact.py     # FundamentalImpactAgent — 综合基本面推演
│   ├── industry_chain.py         # IndustryChainAgent — 产业链传导分析
│   ├── strategy_generation.py    # StrategyGenerationAgent — 策略生成
│   ├── risk_control.py           # RiskControlAgent — 风控校验
│   ├── compliance.py             # ComplianceAgent — 合规守门人
│   └── feedback_optimization.py  # FeedbackOptimizationAgent — 闭环优化
│
├── core/                         # 核心引擎层
│   ├── config.py                 # 系统全局配置（SystemConfig, LLMProvider）
│   ├── schemas.py                # Pydantic 数据模型（全部 I/O + FullLinkState）
│   ├── logger.py                 # 统一日志（agent_system.*）
│   ├── llm.py                    # LLMClient — 多厂商统一调用 + JSON 解析
│   ├── embedding.py              # EmbeddingClient — 文本向量化（智谱/本地/哈希）
│   ├── vector_store.py           # VectorStore — LanceDB 向量数据库封装
│   ├── collector.py              # NewsCollector — 多数据源聚合采集器
│   ├── preprocessor.py           # PreprocessPipeline — 清洗/结构化/分块
│   ├── news_collector_job.py     # 定时采集 Job（采集→预处理→JSON存储）
│   ├── news_search.py            # NewsSearchEngine — 语义+关键词+时间检索
│   ├── entity_linker.py          # EntityLinker — NER + 股票代码映射
│   ├── event_classifier.py       # EventClassifier — 事件分类（批量+规则+LLM）
│   ├── sentiment_engine.py       # SentimentEngine — 情绪量化（批量+指数+一致性）
│   ├── impact_analyzer.py        # ImpactAnalyzer — 影响链路推演+历史回测
│   ├── influence_scorer.py       # InfluenceScorer — 传播力评分
│   ├── alert_system.py           # 预警系统
│   └── datasources/
│       ├── base.py               # BaseDataSource — 数据源抽象基类 + 信源分级
│       └── tushare_source.py     # TushareNewsSource — Tushare 数据源实现
│
├── data/
│   ├── news_store/               # 定时采集的 JSON 文件存储
│   │   └── news_600000_sh.json   # 按标的命名，如 news_{symbol}.json
│   └── lancedb/                  # LanceDB 向量数据库（可选）
│
├── docs/
│   ├── API.md                    # API 接口文档
│   └── ARCHITECTURE.md           # 本文档
│
├── tests/                        # 测试脚本
├── logs/                         # 运行日志
├── .env                          # 环境变量（API Key 等）
├── requirements.txt              # Python 依赖
└── scheduler_config.json         # 定时任务持久化配置
```

---

## 3. 数据流全景

```
                        ┌─────────────────────────────┐
                        │     后台定时采集（每30min）     │
                        │  scheduler.py → collector_job │
                        └──────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │    Tushare API（多源新闻）     │
                    │ sina/cls/yicai/eastmoney/... │
                    └──────────────┬──────────────┘
                                   │ 原始新闻 800+条
                    ┌──────────────▼──────────────┐
                    │   NewsCollector — 聚合+去重    │
                    │   PreprocessPipeline — 清洗    │
                    └──────────────┬──────────────┘
                                   │ 清洗后 720条
                    ┌──────────────▼──────────────┐
                    │  data/news_store/*.json       │
                    │  本地 JSON 文件（零API依赖）    │
                    └──────────────┬──────────────┘
                                   │ 读取 18ms
┌──────────────────────────────────▼────────────────────────────────┐
│                    全链路分析管线 (LangGraph)                       │
│                                                                   │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────┐  │
│  │ NewsRead │→│EventClass │→│Sentiment  │→│Fund ‖ Industry│  │
│  │  18ms    │  │ 96s(2LLM) │  │ 91s(1LLM) │  │127s+53s(3LLM)│  │
│  └──────────┘  └───────────┘  └───────────┘  └───────┬───────┘  │
│                                                       │          │
│  ┌──────────┐  ┌───────────┐                ┌────────▼────────┐ │
│  │  Report  │←│ RiskCtrl  │←──────────────│ StrategyGen     │ │
│  │   END    │  │  15s(1LLM)│                │  12s(1LLM)      │ │
│  └──────────┘  └───────────┘                └─────────────────┘ │
│                                                                   │
│  [Compliance] 合规校验插入在每个业务节点之后                          │
└───────────────────────────────────────────────────────────────────┘
```

---

## 4. 核心层 core/

### 4.1 config.py — 系统全局配置

```python
class LLMProvider(str, Enum):
    DEEPSEEK = "deepseek"
    ZHIPU    = "zhipu"
    OPENAI   = "openai"

class SystemConfig(BaseSettings):
    """从 .env 自动加载，支持 reload_config() 热更新"""
    llm_provider: LLMProvider
    deepseek_api_key: str
    deepseek_model: str           # 默认 "deepseek-chat"
    zai_api_key: str              # 智谱 API Key
    zhipu_model: str              # 默认 "glm-4"
    tushare_token: str
    lancedb_path: str             # 默认 "./data/lancedb"
    embedding_backend: str        # "zhipu" / "local" / "hash"
    embedding_model: str          # "embedding-3"
    embedding_dim: int            # 1024

    def get_llm_params(self) -> Dict[str, Any]:
        """根据 provider 返回 {api_key, model, api_url, timeout, ...}"""
```

**使用方式：**
```python
from core.config import get_config
cfg = get_config()
token = cfg.tushare_token
params = cfg.get_llm_params()
```

### 4.2 llm.py — 统一 LLM 调用客户端

```python
class LLMClient:
    def __init__(self, config: Optional[SystemConfig] = None)

    def chat(self, messages: List[Dict], temperature=None, max_tokens=None) -> str
        """纯文本调用，内置指数退避重试（默认3次）"""

    def chat_json(self, system_prompt, user_prompt, temperature=None) -> Dict
        """调用 LLM 并提取 JSON 对象 {...}"""

    def chat_json_list(self, system_prompt, user_prompt, temperature=None) -> List[Dict]
        """调用 LLM 并提取 JSON 数组 [{...}, {...}]
        兼容格式：
        - 标准 JSON 数组 [...]
        - 逗号分隔的 {...}, {...}（自动包装为数组）
        """

    @staticmethod
    def _extract_json(text: str) -> Dict           # 提取 {...}
    @staticmethod
    def _extract_json_list(text: str) -> List[Dict] # 提取 [...] 或 {...}, {...}
```

**关键设计：**
- 所有 LLM 调用统一经过此客户端，自动处理重试、超时、JSON 解析
- `chat_json_list` 是批量优化的核心基础设施，兼容 LLM 返回格式不规范的情况

### 4.3 schemas.py — 全局数据结构

```python
# ── 枚举 ──
class AgentStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED  = "failed"
    SKIPPED = "skipped"

# ── 用户请求 ──
class UserRequest(BaseModel):
    target_type: str          # "个股" / "行业" / "主题" / "全市场"
    target_code: List[str]    # ["600000.SH"]
    target_name: List[str]    # ["浦发银行"]
    time_range: str           # "近7天" / "自定义"
    custom_time_start: str
    custom_time_end: str
    analysis_depth: str       # "基础版" / "标准版" / "深度版"
    user_custom_rules: Dict

# ── 各 Agent 输出模型（均继承 BaseModel）──
class NewsRetrievalOutput:          task_id, news_total_count, news_structured_data, ...
class EventClassificationOutput:    task_id, entity_linking_result, event_classification_result, ...
class SentimentAnalysisOutput:      task_id, news_sentiment_detail, target_sentiment_index, ...
class FundamentalImpactOutput:      task_id, impact_logic_breakdown, historical_event_backtest, ...
class IndustryChainOutput:          task_id, industry_chain_map, beneficiaries, losers, ...
class StrategyGenerationOutput:     task_id, strategy_type, entry_conditions, exit_conditions, ...
class RiskControlOutput:            task_id, risk_level, stop_loss_rules, take_profit_rules, ...
class ComplianceCheckOutput:        task_id, check_result, violation_details, fuse_trigger, ...
class FeedbackOptimizationOutput:   task_id, accuracy_report, optimization_suggestions, ...
class FinalResearchReport:          task_base_info, news_summary, ..., compliance_disclaimer

# ── LangGraph 中枢状态 ──
class FullLinkState(TypedDict):
    task_id: str
    task_base_info: dict
    task_status: str                              # "执行中" / "已完成" / "熔断" / "失败"
    news_retrieval_output: dict
    event_classification_output: dict
    sentiment_analysis_output: dict
    fundamental_impact_output: dict
    industry_chain_output: dict
    strategy_generation_output: dict
    risk_control_output: dict
    compliance_check_records: Annotated[list, operator.add]   # 追加模式
    full_link_execution_log: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]
    final_research_report: dict
    current_step: str
    retry_counts: dict
    fuse_triggered: bool
```

### 4.4 collector.py — 多数据源聚合采集器

```python
class NewsCollector:
    def __init__(self, data_sources: Optional[List[BaseDataSource]] = None)
    def add_source(self, source: BaseDataSource)

    def collect(self, symbol, name, keywords, start_date, end_date, deduplicate=True)
        -> List[Dict[str, Any]]
        """从所有数据源采集 → 去重(content_fingerprint) → 标准化输出
        每条记录包含: news_id, title, content, publish_time,
                      source, source_level, source_weight, url, content_hash
        """

    def collect_incremental(self, symbol, name, keywords, last_fetch_time)
        """增量采集：从 last_fetch_time 到当前时间"""

    def reset_seen(self)
        """清空指纹缓存（新一轮全量采集时调用）"""
```

### 4.5 news_collector_job.py — 定时采集 Job

```python
# 配置文件: news_collect_config.json
# 数据目录: data/news_store/

def add_symbol(symbol: str, name: str) -> Dict        # 添加采集标的
def remove_symbol(symbol: str) -> Dict                 # 移除采集标的
def set_interval(minutes: int) -> int                  # 设置采集间隔
def set_enabled(enabled: bool) -> bool                 # 启停采集
def get_status() -> Dict                               # 采集状态

def collect_for_symbol(symbol, name, hours=24) -> Dict
    """单标的完整采集流程:
    TushareNewsSource.fetch() → NewsCollector.collect() → PreprocessPipeline.process()
    → _save_to_json() → data/news_store/news_{symbol}.json
    无 Embedding API 依赖，确保采集永不因限流失败
    """

def collect_all() -> Dict
    """对配置中所有标的执行一次采集"""

def read_local_news(symbol, start_time, end_time, limit=200) -> List[Dict]
    """从本地 JSON 读取数据 — 分析链路唯一入口
    纯文件读取，响应 <10ms，不触发任何网络请求
    """
```

**JSON 存储格式：**
```json
{
  "symbol": "600000.SH",
  "name": "浦发银行",
  "collected_at": "2026-03-12 15:55:37",
  "count": 720,
  "items": [
    {
      "news_id": "N-abc12345",
      "title": "...",
      "content": "...",
      "publish_time": "2026-03-11 23:58:05",
      "source": "cls",
      "source_level": "A",
      "source_weight": 0.85,
      "keywords": ["银行", "业绩"],
      ...
    }
  ]
}
```

### 4.6 preprocessor.py — 三阶段预处理流水线

```python
class TextCleaner:
    @staticmethod
    def clean(text: str) -> str     # HTML标签/多余空白/特殊字符清除
    @staticmethod
    def is_valid(text: str) -> bool # 长度>15字符检查

class TextChunker:
    @staticmethod
    def chunk(text, max_length=500, overlap=50) -> List[str]

class StructuredExtractor:
    def __init__(self, llm_client)
    def extract(self, title, content) -> Dict
        """LLM 提取: core_entity, related_stock, event_type, keywords"""
    def extract_batch(self, items, max_llm_calls=50) -> List

class PreprocessPipeline:
    def __init__(self, llm_client=None, max_llm_calls=50)
    def process(self, items: List[Dict]) -> List[Dict]
        """阶段1: TextCleaner.clean() + is_valid() 过滤
        阶段2: StructuredExtractor.extract_batch() 结构化
        阶段3: TextChunker.chunk() 分块
        """
```

### 4.7 event_classifier.py — 事件分类引擎

```python
EVENT_TAXONOMY = {
    "正向事件": ["业绩超预期", "重大订单落地", "政策扶持", ...],   # 10个
    "负向事件": ["业绩暴雷", "监管处罚", "诉讼仲裁", ...],       # 11个
    "中性事件": ["常规公告", "例行信息披露", ...],                 # 6个
    "不确定性事件": ["政策草案", "业绩预告", "行业传闻", ...],     # 6个
}

class EventClassifier:
    SYSTEM_PROMPT    = "..."  # 单条分类 Few-Shot Prompt
    BATCH_SYSTEM_PROMPT = "..."  # 批量分类 Prompt（返回JSON数组）

    def classify(self, title, content) -> Dict
        """单条LLM分类 + 规则验证 + 兜底"""

    def classify_aggregate(self, items, batch_size=50) -> List[Dict]
        """批量聚合分类: N条/批 → 1次 chat_json_list 调用
        失败时逐条规则兜底"""

    @staticmethod
    def _rule_classify(text) -> Dict
        """关键词规则兜底: _KEYWORD_MAP 匹配"""

    @staticmethod
    def _validate_label(category, sub_label) -> bool
        """校验分类结果是否在 EVENT_TAXONOMY 内"""
```

### 4.8 sentiment_engine.py — 情绪量化引擎

```python
POLARITY_MAP = {
    "强正向": {"min_score": 80, "max_score": 100},
    "弱正向": {"min_score": 60, "max_score": 79},
    "中性":   {"min_score": 40, "max_score": 59},
    "弱负向": {"min_score": 20, "max_score": 39},
    "强负向": {"min_score": 0,  "max_score": 19},
    "不确定性": {"min_score": 40, "max_score": 60},
}

class SentimentEngine:
    SYSTEM_PROMPT       = "..."  # 单条情感 Few-Shot
    BATCH_SYSTEM_PROMPT = "..."  # 批量情感 Prompt

    def analyze(self, title, content) -> Dict
        """单条: polarity, score(0-100), driver, reasoning"""

    def analyze_aggregate(self, items, batch_size=30) -> List[Dict]
        """批量聚合: 30条/批 → 1次 chat_json_list"""

    @staticmethod
    def build_emotion_index(sentiments, source_weights) -> Dict
        """加权情绪指数: index(0-100), trend, std_dev, polarity_distribution"""

    @staticmethod
    def check_consistency(sentiments) -> Dict
        """一致性检验: 强共识/弱共识/明显分歧/温和分歧"""

    @staticmethod
    def filter_noise(sentiments, min_influence=15.0) -> List
        """噪音过滤: 情绪极端但影响力低的标记为 is_noise=True"""

    @staticmethod
    def _rule_sentiment(text) -> Dict
        """规则兜底: 正面/负面关键词计数"""
```

### 4.9 impact_analyzer.py — 影响链路推演

```python
class ImpactAnalyzer:
    IMPACT_SYSTEM_PROMPT      = "..."  # 事件影响拆解
    CHAIN_SYSTEM_PROMPT       = "..."  # 产业链传导
    BACKTEST_SYSTEM_PROMPT    = "..."  # 历史回测
    BATCH_IMPACT_SYSTEM_PROMPT = "..."  # 批量综合推演

    def analyze_impact_chain(self, event_summary, event_category, company, financials) -> Dict
        """单事件影响链路: dimensions, timeline(short/mid/long), earnings_impact"""

    def analyze_impact_batch(self, events, company, financials, ts_code) -> Dict
        """综合批量推演: 所有关键事件合并为1次LLM调用
        返回: event_impacts[], combined_assessment, earnings_impact"""

    def analyze_industry_chain(self, event_summary, company, industry) -> Dict
        """产业链传导: upstream_impact, downstream_impact, beneficiaries, losers"""

    def historical_backtest(self, event_summary, category, sub_label, company, ts_code) -> Dict
        """历史回测: similar_events, pattern_summary, reference_range"""
```

### 4.10 entity_linker.py — 实体链接

```python
class EntityLinker:
    NER_SYSTEM_PROMPT   = "..."  # 单条NER
    BATCH_NER_PROMPT    = "..."  # 批量NER

    def __init__(self, llm_client, tushare_pro=None)
        """加载 Tushare stock_basic 建立 name→code 映射缓存"""

    def extract_entities(self, title, content) -> Dict
        """单条: entities, primary_company, primary_stock_code, industry_chain"""

    def extract_entities_batch(self, items, batch_size=50) -> List[Dict]
        """批量: 50条/批 → 1次 chat_json_list"""

    def link_to_stock(self, company_name) -> str
        """公司名→股票代码（精确+模糊匹配）"""
```

### 4.11 influence_scorer.py — 传播力评分

```python
class InfluenceScorer:
    @staticmethod
    def score(source_weight, spread_count, event_sub_label,
              impact_level, confidence) -> float
        """综合评分(0-100):
        = 信源权重×30 + 传播量×25 + 事件类型×25 + 影响级别×10 + 置信度×10
        """

    @staticmethod
    def score_batch(items) -> List[Dict]

    @staticmethod
    def track_spread_velocity(timestamps) -> Dict
        """传播速度: 每小时传播量、峰值时刻"""

    @staticmethod
    def classify_propagation(items) -> List[Dict]
        """区分源头报道 vs 二次传播"""
```

### 4.12 datasources/base.py — 数据源基类与信源分级

```python
class SourceLevel(str, Enum):
    S = "S"   # 交易所公告、证监会、官方财报      权重 1.0
    A = "A"   # 财新/路透/彭博/财联社/第一财经     权重 0.85
    B = "B"   # 行业垂直媒体、知名KOL              权重 0.70
    C = "C"   # 社交媒体、论坛、股吧UGC            权重 0.50
    D = "D"   # 无明确信源的传闻                    权重 0.30

TUSHARE_SOURCE_LEVELS = {
    "cls": "A", "yicai": "A", "wallstreetcn": "A",
    "sina": "B", "10jqka": "B", "eastmoney": "B", ...
}

class BaseDataSource(ABC):
    @abstractmethod
    def fetch(self, symbol, name, keywords, start_date, end_date) -> List[Dict]
    @abstractmethod
    def get_source_level(self, raw_source: str) -> str
```

### 4.13 embedding.py — 文本向量化

```python
class EmbeddingClient:
    """三后端自动降级: zhipu API → sentence-transformers → hash"""
    def __init__(self, backend=None, model_name=None)
    def embed(self, text: str) -> List[float]       # 单条
    def embed_batch(self, texts) -> List[List[float]] # 批量
    @property
    def dim(self) -> int                              # 向量维度（默认1024）
```

---

## 5. 智能体层 agents/

### 5.1 BaseAgent — 抽象基类

```python
class BaseAgent(ABC):
    name: str = "base"
    description: str = ""
    max_retries: int = 2

    def __init__(self, llm_client=None, config=None):
        self.llm = llm_client or LLMClient(config)
        self.config = config or get_config()
        self.logger = get_logger(f"agent_system.{self.name}")

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]: ...

    def safe_run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """自动重试 + 异常捕获，错误写入 full_link_execution_log"""

    def _make_output(self, status, data, error, duration_ms, retries) -> Dict
```

### 5.2 OrchestratorAgent — 中枢调度

```python
class OrchestratorAgent(BaseAgent):
    """基于 LangGraph StateGraph 的全链路编排"""

    def __init__(self):
        # 初始化 9 个子 Agent（共享 LLM 实例）
        self.compliance_agent  = ComplianceAgent(...)
        self.news_agent        = NewsRetrievalAgent(...)
        self.event_agent       = EventClassificationAgent(...)
        self.sentiment_agent   = SentimentAnalysisAgent(...)
        self.fundamental_agent = FundamentalImpactAgent(...)
        self.industry_agent    = IndustryChainAgent(...)
        self.strategy_agent    = StrategyGenerationAgent(...)
        self.risk_agent        = RiskControlAgent(...)
        self.feedback_agent    = FeedbackOptimizationAgent(...)
        self._graph = self._build_graph()

    def _build_graph(self):
        """LangGraph 节点与边:
        news_retrieval → event_classification → sentiment_analysis
        → parallel_deep_analysis(fund ‖ industry) → strategy_generation
        → risk_control → generate_report → END
        每个节点后有条件边: fuse_check → fuse=generate_report / next=下一节点
        """

    def execute(self, request: UserRequest) -> Dict:
        """一键入口: UserRequest → FullLinkState → graph.invoke → 报告"""

    def run_feedback(self, history_report, actual_result, task_id) -> Dict
```

### 5.3 NewsRetrievalAgent — 数据读取

```python
class NewsRetrievalAgent(BaseAgent):
    """从本地 JSON 读取预采集数据，零网络延迟（18ms）"""

    def run(self, state):
        symbol, name, time_range, topics = self._extract_params(state)
        items = read_local_news(symbol, start_time, end_time, limit=200)
        # 可选: _filter_by_topics() 按主题关键词过滤
        return {"news_retrieval_output": ..., "current_step": "news_retrieval_done"}
```

### 5.4 EventClassificationAgent — 两阶段事件分类

```python
class EventClassificationAgent(BaseAgent):
    """两阶段漏斗策略:
    阶段1: 规则引擎粗分类全部200条（0次LLM，<100ms）
    阶段2: LLM精分析Top20高价值条目（2次LLM，~60s）
    """

    LLM_TOP_N = 20  # 只对前20条做LLM精分析

    def run(self, state):
        # 1. 全量规则粗分类
        rule_results = [EventClassifier._rule_classify(text) for ...]

        # 2. 按 置信度×信源×传播量+事件类型 排序，选Top20
        top_indices = sort_and_select(scored_indices, LLM_TOP_N)

        # 3. LLM批量精分类（classify_aggregate）+ 批量实体提取
        llm_results = self.event_classifier.classify_aggregate(top_items)
        top_entities = self.entity_linker.extract_entities_batch(top_items)

        # 4. 合并 + 影响力评分 + 核心舆情筛选（限制≤30条）
        core_news = self._select_core_news(...)  # 影响力≥25分，最多30条
```

### 5.5 SentimentAnalysisAgent — 批量情绪量化

```python
class SentimentAnalysisAgent(BaseAgent):
    """上游 core_news 限制在30条，1次批量LLM调用"""

    def run(self, state):
        core_news = state["event_classification_output"]["core_news_list"]  # ≤30
        detail = self.engine.analyze_aggregate(core_news, batch_size=30)    # 1次LLM
        sentiment_index = SentimentEngine.build_emotion_index(detail)       # 纯计算
        consistency = SentimentEngine.check_consistency(detail)             # 纯计算
        ratings = self._compute_ratings(detail, sentiment_index)           # 纯计算
```

### 5.6 FundamentalImpactAgent — 综合基本面推演

```python
class FundamentalImpactAgent(BaseAgent):
    """多事件合并为单次LLM综合推演 + 1次历史回测 = 2次LLM"""

    def run(self, state):
        events = self._build_events(core_news, classifications, sentiments)
        financials = self._fetch_financials(ts_code)  # Tushare daily_basic

        batch_impact = analyzer.analyze_impact_batch(events[:10], ...)  # 1次LLM
        backtest = analyzer.historical_backtest(key_event, ...)         # 1次LLM
        certainty = self._rate_certainty(events, sentiment_output)     # 纯计算
```

### 5.7 ComplianceAgent — 合规守门人

```python
class ComplianceAgent(BaseAgent):
    FORBIDDEN_PHRASES = ["必涨", "稳赚", "保证收益", "必买", ...]
    WARNING_PHRASES   = ["建议买入", "推荐", "看好", ...]
    COMPLIANCE_DISCLAIMER = "【免责声明】本分析报告由AI系统自动生成..."

    def check(self, agent_name, agent_output, task_id) -> ComplianceCheckOutput:
        """合规校验流程:
        1. 提取所有文本内容
        2. 检查禁止用语 → fuse_trigger=True（严重违规熔断）
        3. 检查警告用语 → 修正后通过
        4. 检查绝对化预测语句
        5. 注入免责声明
        返回: check_result="通过"/"修正后通过"/"驳回"
        """
```

### 5.8 其余 Agent

| Agent | 核心方法 | LLM调用 | 说明 |
|---|---|---|---|
| `IndustryChainAgent` | `run(state)` | 1次 | 调用 `ImpactAnalyzer.analyze_industry_chain()` |
| `StrategyGenerationAgent` | `run(state)` | 1次 | 整合全链路结果生成策略 |
| `RiskControlAgent` | `run(state)` | 1次 | 策略风控+止损止盈 |
| `FeedbackOptimizationAgent` | `run_optimization()` | 1次 | 独立流程，不参与实时链路 |

---

## 6. 应用层 app/

### 6.1 main.py — FastAPI 入口

```python
app = FastAPI(title="机构级金融舆情分析系统", version="4.0.0")

# 路由注册顺序
app.include_router(analysis.router)      # /api/v2/analysis/*
app.include_router(news_collect.router)  # /api/v2/news-collect/*
app.include_router(news.router)          # /api/news/*
app.include_router(internal.router)      # /internal/*
app.include_router(admin.router)         # /admin/*
app.include_router(debug.router)         # /internal/debug/*
app.include_router(research.router)      # /api/research/*  (v1)
app.include_router(signal.router)        # /api/signal/*    (v1)
app.include_router(strategy.router)      # /api/strategy/*  (v1)

@app.on_event("startup")    # → database.init_db() + scheduler.start_scheduler()
@app.on_event("shutdown")   # → scheduler.stop_scheduler()
```

### 6.2 scheduler.py — 定时任务管理

```python
# 三类定时任务:
_FETCH_JOB_ID   = "fetch_news"            # 旧版Tushare采集（每5分钟）
_CLEAN_JOB_ID   = "cleanup_news"          # SQLite旧数据清理（每60分钟）
_COLLECT_JOB_ID = "collect_news_for_analysis"  # Phase4 深度采集（每30分钟）

# 管理接口:
def start_scheduler()        # 启动 APScheduler
def stop_scheduler()
def set_enabled(enabled)     # 全局开关
def set_interval_minutes(m)  # 修改采集间隔
def register_task(name, url, method, interval)  # 注册URL任务
def get_status() -> Dict     # 所有任务状态
```

---

## 7. API 路由一览

### 核心接口（Phase 4）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v2/analysis/full-link` | 全链路一键分析（核心接口） |
| POST | `/api/v2/analysis/quick` | 快捷分析（symbol+name） |
| POST | `/api/v2/analysis/news-only` | 仅读取本地舆情数据 |
| POST | `/api/v2/analysis/feedback` | 反馈优化与复盘 |
| GET | `/api/v2/analysis/system-info` | 系统架构信息 |

### 采集管理接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v2/news-collect/add-symbol` | 添加采集标的 |
| POST | `/api/v2/news-collect/remove-symbol` | 移除采集标的 |
| POST | `/api/v2/news-collect/run-now` | 立即全量采集（异步） |
| POST | `/api/v2/news-collect/run-symbol` | 同步采集指定标的 |
| GET | `/api/v2/news-collect/status` | 采集状态+本地数据 |
| PUT | `/api/v2/news-collect/settings` | 更新采集配置 |

### 基础接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |
| GET/PUT | `/api/service/switch` | 服务开关 |
| GET | `/api/news/list` | 新闻列表 |
| POST | `/api/news/fetch` | 手动触发旧版采集 |
| GET | `/internal/debug/agents` | Agent状态 |
| GET | `/internal/debug/config` | 配置信息 |

### 旧版 v1 接口（向后兼容）

| POST | `/api/news/analyze` | v1 舆情分析 |
| POST | `/api/research/analyze` | v1 投研分析 |
| POST | `/api/signal/validate` | v1 信号验证 |
| POST | `/api/strategy/generate` | v1 策略生成 |

---

## 8. 配置体系

### .env 文件

```env
TUSHARE_TOKEN=d9d69bd5...                    # Tushare API 令牌
LLM_PROVIDER=deepseek                        # deepseek / zhipu / openai
DEEPSEEK_API_KEY=sk-dc614...                 # DeepSeek API Key
DEEPSEEK_MODEL=deepseek-chat
ZAI_API_KEY=4fadfa45...                      # 智谱 API Key
ZHIPU_MODEL=glm-5
```

### 配置层级

```
.env  →  core/config.py (SystemConfig)    系统核心配置（LLM/Embedding/Tushare）
     →  app/config.py   (Settings)        应用层配置（数据库/端口）
     →  news_collect_config.json          采集标的/间隔（持久化）
     →  scheduler_config.json             定时任务配置（持久化）
```

---

## 9. 全链路执行序列

以 `POST /api/v2/analysis/quick {"symbol":"600000.SH","name":"浦发银行"}` 为例：

```
1. API层 → UserRequest → OrchestratorAgent.execute()
   │
2. ├─ 构建 FullLinkState (task_id=随机8位)
   │
3. ├─ graph.invoke(initial_state)
   │   │
   │   ├─ [NewsRetrieval]         读本地JSON          18ms    0次LLM
   │   ├─ [Compliance]            合规校验              1ms
   │   │
   │   ├─ [EventClassification]   规则粗筛+LLM Top20   96s    2次LLM
   │   ├─ [Compliance]            合规校验              1ms
   │   │
   │   ├─ [SentimentAnalysis]     批量情绪(30条)       91s    1次LLM
   │   ├─ [Compliance]            合规校验              1ms
   │   │
   │   ├─ [FundamentalImpact]     综合推演+回测        127s    2次LLM
   │   ├─ [IndustryChain]         产业链传导           53s    1次LLM
   │   ├─ [Compliance]            合规校验              1ms
   │   │
   │   ├─ [StrategyGeneration]    策略生成             12s    1次LLM
   │   ├─ [Compliance]            合规校验              1ms
   │   │
   │   ├─ [RiskControl]           风控校验             15s    1次LLM
   │   ├─ [Compliance]            合规校验              1ms
   │   │
   │   └─ [GenerateReport]        聚合报告              1ms
   │
4. └─ 返回 FinalResearchReport
       含: news_summary, event_classification_result,
           sentiment_analysis_result, fundamental_impact_report,
           industry_chain_analysis_result, strategy_suggestion,
           risk_control_rules, compliance_disclaimer, full_link_log
```

**总计**: ~425s, 8次LLM调用, 7次合规校验

---

## 10. 性能优化策略

### 10.1 采集与分析解耦

| | 旧架构 | 新架构 |
|---|---|---|
| 数据获取 | 分析时实时采集 Tushare | 后台定时采集 → JSON |
| 舆情读取 | 300s+（网络超时） | **18ms**（本地文件） |
| 依赖 | Tushare+Embedding API | 零外部依赖 |

### 10.2 两阶段漏斗 LLM 策略

| | 旧策略 | 新策略 |
|---|---|---|
| EventClassification | 60次逐条LLM | 规则全量 + LLM仅Top20 = **2次** |
| SentimentAnalysis | 30次逐条LLM | 批量聚合30条 = **1次** |
| FundamentalImpact | 6次逐事件LLM | 合并为综合推演 = **2次** |
| **总LLM调用** | **~96次** | **~8次** |

### 10.3 LLM 批量调用基础设施

```python
# chat_json_list 兼容两种 LLM 返回格式:
# 格式1: 标准 JSON 数组 [{...}, {...}]
# 格式2: 逗号分隔对象 {...}, {...}  (自动包装为数组)
```

---

## 11. 依赖清单

```
fastapi==0.109.2         # Web 框架
uvicorn==0.27.1          # ASGI 服务器
tushare==1.2.89          # 金融数据 API
pydantic                 # 数据验证
pydantic-settings        # 配置管理
httpx                    # HTTP 客户端
apscheduler              # 定时任务
jinja2                   # 模板引擎
pandas                   # 数据处理
langgraph                # 多智能体编排
lancedb                  # 向量数据库
pyarrow                  # 列式存储
typing-extensions        # 类型扩展
```

---

## 12. 部署与启动

### 首次部署

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填写 TUSHARE_TOKEN, DEEPSEEK_API_KEY 等

# 3. 启动服务
cd news-api-service
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 使用流程

```bash
# 步骤1: 添加采集标的
curl -X POST http://localhost:8000/api/v2/news-collect/add-symbol \
  -H "Content-Type: application/json" \
  -d '{"symbol":"600000.SH","name":"浦发银行"}'

# 步骤2: 执行首次采集（同步，约2-3分钟）
curl -X POST http://localhost:8000/api/v2/news-collect/run-symbol \
  -H "Content-Type: application/json" \
  -d '{"symbol":"600000.SH","name":"浦发银行","hours":72}'

# 步骤3: 查看采集状态
curl http://localhost:8000/api/v2/news-collect/status

# 步骤4: 运行全链路分析（约7分钟）
curl -X POST http://localhost:8000/api/v2/analysis/quick \
  -H "Content-Type: application/json" \
  -d '{"symbol":"600000.SH","name":"浦发银行"}'
```

### 后台定时采集

服务启动后自动按配置间隔（默认30分钟）执行采集。可通过以下接口管理：

```bash
# 修改采集间隔为60分钟
curl -X PUT http://localhost:8000/api/v2/news-collect/settings \
  -H "Content-Type: application/json" \
  -d '{"interval_minutes":60}'

# 立即触发全量采集（异步）
curl -X POST http://localhost:8000/api/v2/news-collect/run-now
```
