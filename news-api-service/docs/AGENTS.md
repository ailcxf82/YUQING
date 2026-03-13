# 十智能体架构审查报告

> 审查日期 2026-03-12 | 审查范围 `agents/` 目录全部 11 个源文件

---

## 目录

- [1. 架构总览与审查结论](#1-架构总览与审查结论)
- [2. 基类 BaseAgent](#2-基类-baseagent)
- [3. 中枢总控 — OrchestratorAgent](#3-中枢总控--orchestratoragent)
- [4. 核心业务智能体 ×7](#4-核心业务智能体-7)
- [5. 支撑保障智能体 ×2](#5-支撑保障智能体-2)
- [6. LangGraph 编排拓扑](#6-langgraph-编排拓扑)
- [7. 数据流转矩阵](#7-数据流转矩阵)
- [8. 合规校验时序](#8-合规校验时序)
- [9. 问题与改进建议](#9-问题与改进建议)

---

## 1. 架构总览与审查结论

### 声称架构

> 1 个中枢总控 + 7 个核心业务 + 2 个支撑保障 = 10 个单一职责智能体

### 审查结论：**✅ 已真实实现，全部 10 个 Agent 均有独立文件、独立类、独立 `run()` 逻辑**

| 分类 | Agent | 文件 | 继承 BaseAgent | 有独立 run() | 有 LLM 调用 | 有 SYSTEM_PROMPT |
|------|-------|------|:-:|:-:|:-:|:-:|
| **中枢总控** | OrchestratorAgent | `orchestrator.py` | ✅ | ✅ | ❌(仅调度) | ✅ |
| **核心业务** | NewsRetrievalAgent | `news_retrieval.py` | ✅ | ✅ | ❌(读本地) | ✅ |
| **核心业务** | EventClassificationAgent | `event_classification.py` | ✅ | ✅ | ✅ 2次 | ✅ |
| **核心业务** | SentimentAnalysisAgent | `sentiment_analysis.py` | ✅ | ✅ | ✅ 1次 | ✅ |
| **核心业务** | FundamentalImpactAgent | `fundamental_impact.py` | ✅ | ✅ | ✅ 2次 | ✅ |
| **核心业务** | IndustryChainAgent | `industry_chain.py` | ✅ | ✅ | ✅ 1次 | ✅ |
| **核心业务** | StrategyGenerationAgent | `strategy_generation.py` | ✅ | ✅ | ✅ 1次 | ✅ |
| **核心业务** | RiskControlAgent | `risk_control.py` | ✅ | ✅ | ✅ 1次 | ✅ |
| **支撑保障** | ComplianceAgent | `compliance.py` | ✅ | ✅(占位) | ❌(规则引擎) | ✅ |
| **支撑保障** | FeedbackOptimizationAgent | `feedback_optimization.py` | ✅ | ✅(standby) | ✅ 1次 | ✅ |

---

## 2. 基类 BaseAgent

**文件**：`agents/base.py`（113 行）

```python
class BaseAgent(ABC):
    name: str = "base_agent"       # 子类必须覆盖
    description: str = ""
    max_retries: int = 2           # safe_run 失败重试次数

    def __init__(self, llm_client=None, config=None):
        self.config = config or get_config()      # core.config.SystemConfig
        self.llm = llm_client or LLMClient(config) # core.llm.LLMClient
        self.logger = get_logger(self.name)

    @abstractmethod
    def run(self, state: Dict) -> Dict: ...        # 子类必须实现

    def safe_run(self, state: Dict) -> Dict: ...   # 异常捕获 + 指数退避重试
    def _make_output(self, status, data, error, duration_ms, retries) -> Dict
```

**基类强制契约**：
- 所有子类必须实现 `run(state) -> Dict`
- 所有子类通过 `safe_run()` 被 LangGraph 调用，确保异常不传播
- 统一日志格式 `agent_system.{name}`
- 统一输出结构 `AgentOutput(agent_name, status, data, error, duration_ms, retries)`

---

## 3. 中枢总控 — OrchestratorAgent

**文件**：`agents/orchestrator.py`（428 行）  
**角色**：全链路唯一大脑，**不执行任何业务分析**，仅做调度、管控、聚合

### 3.1 初始化 — 创建 9 个子 Agent

```python
def __init__(self, llm_client=None, config=None):
    shared_llm = self.llm          # 所有子 Agent 共享同一个 LLMClient 实例
    shared_cfg = self.config

    self.compliance_agent  = ComplianceAgent(llm_client=shared_llm, config=shared_cfg)
    self.news_agent        = NewsRetrievalAgent(...)
    self.event_agent       = EventClassificationAgent(...)
    self.sentiment_agent   = SentimentAnalysisAgent(...)
    self.fundamental_agent = FundamentalImpactAgent(...)
    self.industry_agent    = IndustryChainAgent(...)
    self.strategy_agent    = StrategyGenerationAgent(...)
    self.risk_agent        = RiskControlAgent(...)
    self.feedback_agent    = FeedbackOptimizationAgent(...)

    self._graph = self._build_graph()  # 编译 LangGraph 状态机
```

### 3.2 LangGraph 图构建 — `_build_graph()`

```python
def _build_graph(self):
    builder = StateGraph(FullLinkState)

    # 注册 7 个节点（6个包装节点 + 1个并行节点 + 1个报告节点）
    builder.add_node("news_retrieval",        _wrap_node(news_agent))
    builder.add_node("event_classification",  _wrap_node(event_agent))
    builder.add_node("sentiment_analysis",    _wrap_node(sentiment_agent))
    builder.add_node("parallel_deep_analysis", _node_parallel_analysis)  # fund ‖ industry
    builder.add_node("strategy_generation",   _wrap_node(strategy_agent))
    builder.add_node("risk_control",          _wrap_node(risk_agent))
    builder.add_node("generate_report",       _node_generate_report)

    # 入口
    builder.set_entry_point("news_retrieval")

    # 每个节点后接条件边：fuse_check → next(继续) 或 fuse(跳到报告)
    builder.add_conditional_edges("news_retrieval",       _fuse_check, {"next": "event_classification",  "fuse": "generate_report"})
    builder.add_conditional_edges("event_classification", _fuse_check, {"next": "sentiment_analysis",    "fuse": "generate_report"})
    builder.add_conditional_edges("sentiment_analysis",   _fuse_check, {"next": "parallel_deep_analysis","fuse": "generate_report"})
    builder.add_conditional_edges("parallel_deep_analysis",_fuse_check,{"next": "strategy_generation",   "fuse": "generate_report"})
    builder.add_conditional_edges("strategy_generation",  _fuse_check, {"next": "risk_control",          "fuse": "generate_report"})
    builder.add_conditional_edges("risk_control",         _fuse_check, {"next": "generate_report",       "fuse": "generate_report"})
    builder.add_edge("generate_report", END)

    return builder.compile()
```

### 3.3 节点包装器 — `_wrap_node()`

**每个业务节点统一经过三步**：

```
agent.safe_run(state)  →  compliance_agent.check(output)  →  状态更新
```

```python
def _wrap_node(self, agent, output_key):
    def node_fn(state):
        if state.get("fuse_triggered"):
            return {}                              # 熔断后跳过

        result = agent.safe_run(state)             # 步骤1: 执行业务
        agent_output = result.get(output_key, {})

        comp = self.compliance_agent.check(        # 步骤2: 合规校验
            agent.name, agent_output, state.get("task_id")
        )

        if comp.fuse_trigger:                      # 严重违规 → 熔断
            update["fuse_triggered"] = True
            update["task_status"] = "熔断"
        elif comp.check_result == "修正后通过":      # 轻微违规 → 替换为修正内容
            update[output_key] = comp.corrected_content

        return update                              # 步骤3: 更新状态
    return node_fn
```

### 3.4 并行节点 — `_node_parallel_analysis()`

`FundamentalImpactAgent` 和 `IndustryChainAgent` 在同一节点中**串行执行**（当前未用线程），各自独立合规校验后合并：

```python
def _node_parallel_analysis(self, state):
    fund_result = self.fundamental_agent.safe_run(state)
    fund_comp   = self.compliance_agent.check("fundamental_impact", ...)

    ind_result  = self.industry_agent.safe_run(state)
    ind_comp    = self.compliance_agent.check("industry_chain", ...)

    # 合并两个 Agent 的结果 + 两份合规记录
    return {
        "fundamental_impact_output": ...,
        "industry_chain_output": ...,
        "compliance_check_records": [fund_comp, ind_comp],
    }
```

### 3.5 报告生成 — `_node_generate_report()`

**纯聚合逻辑，0 次 LLM**：从 FullLinkState 中提取各 Agent 输出，组装为 `FinalResearchReport`，附加免责声明。

### 3.6 对外接口

| 方法 | 入参 | 说明 |
|------|------|------|
| `execute(UserRequest)` | 用户请求 | 一键入口：构建初始 State → graph.invoke → 返回报告 |
| `run(state)` | 已有 State | 直接运行图 |
| `run_feedback(history, actual, task_id)` | 历史报告+实际结果 | 触发 FeedbackOptimizationAgent |

---

## 4. 核心业务智能体 ×7

### 4.1 NewsRetrievalAgent — 舆情数据读取

**文件**：`agents/news_retrieval.py`（223 行）  
**职责边界**：读取本地预采集数据，**不做网络请求、不做分析**  
**LLM 调用**：0 次

```
run(state):
  1. 从 state.task_base_info 提取 symbol, name, time_range
  2. read_local_news(symbol, start, end, limit=200)  ← 读本地 JSON 文件
  3. _filter_by_topics() — 可选的关键词过滤
  4. _to_output_items() — 标准化输出格式
  5. → NewsRetrievalOutput (news_structured_data, data_quality_report, ...)
```

**核心逻辑**：
- 数据来自 `core.news_collector_job.read_local_news()`，纯文件读取
- 空数据时检查 `get_collect_status()` 给出提示（标的未配置/未采集）
- 输出每条包含 `news_id, source_level, source_weight, publish_time, title, content, keywords, spread_count`

### 4.2 EventClassificationAgent — 事件分类

**文件**：`agents/event_classification.py`（222 行）  
**职责边界**：实体提取 + 事件分类 + 影响力评分，**不做情绪判断**  
**LLM 调用**：2 次  
**依赖引擎**：`EntityLinker`, `EventClassifier`, `InfluenceScorer`

```
run(state):
  ── 阶段1：全量规则粗分类（0次LLM，<100ms）──
  1. for 200条 → EventClassifier._rule_classify(text) → 关键词匹配
  2. 按 (规则置信度×40 + 信源权重×30 + 传播量×30) 评分排序
  3. 选 Top20 高价值条目

  ── 阶段2：LLM 精分析 Top20（2次LLM）──
  4. EventClassifier.classify_aggregate(top20)       → 1次 chat_json_list
  5. EntityLinker.extract_entities_batch(top20)       → 1次 chat_json_list
  6. 其余 180 条保留规则分类结果

  ── 后处理（纯计算）──
  7. InfluenceScorer.score() × 200条 → 影响力评分
  8. _select_core_news() → 影响力≥25的，最多30条
  9. → EventClassificationOutput (entity, classification, influence, core_news)
```

**事件分类标签体系**（4大类 33 细分）：
- 正向事件(10)：业绩超预期、重大订单、政策扶持、技术突破...
- 负向事件(11)：业绩暴雷、监管处罚、诉讼仲裁、高管失联...
- 中性事件(6)：常规公告、例行披露...
- 不确定性事件(6)：政策草案、业绩预告、行业传闻...

### 4.3 SentimentAnalysisAgent — 情绪量化

**文件**：`agents/sentiment_analysis.py`（162 行）  
**职责边界**：情绪极性判断 + 指数构建 + 一致性校验，**不做基本面推演**  
**LLM 调用**：1 次  
**依赖引擎**：`SentimentEngine`

```
run(state):
  输入: event_classification_output.core_news_list（≤30条）

  1. SentimentEngine.analyze_aggregate(core_news, batch_size=30)   → 1次LLM
     每条返回: polarity(6级), score(0-100), driver, reasoning
  2. SentimentEngine.build_emotion_index(detail, weights)          → 纯计算
     加权情绪指数(0-100) + trend(升温/降温/震荡/平稳)
  3. SentimentEngine.check_consistency(detail)                     → 纯计算
     强共识/弱共识/明显分歧/温和分歧
  4. SentimentEngine.filter_noise(detail)                          → 纯计算
     情绪极端但影响力<15 标记为噪音
  5. _compute_ratings(detail, index)                               → 纯计算
     综合评级: 积极/谨慎乐观/中性/谨慎/负面
  6. → SentimentAnalysisOutput (detail, index, consistency, ratings)
```

**情绪极性体系**（6 级）：
- 强正向(80-100) / 弱正向(60-79) / 中性(40-59)
- 弱负向(20-39) / 强负向(0-19) / 不确定性(40-60)

### 4.4 FundamentalImpactAgent — 基本面推演

**文件**：`agents/fundamental_impact.py`（217 行）  
**职责边界**：舆情对基本面的影响分析，**不做产业链传导、策略生成**  
**LLM 调用**：2 次  
**依赖引擎**：`ImpactAnalyzer`  
**外部数据**：Tushare `daily_basic`（PE/PB/市值）+ `daily`（近期价格）

```
run(state):
  输入: core_news + classifications + sentiments

  1. _build_events()                                              → 纯计算
     合并新闻+分类+情绪为事件列表
  2. _fetch_financials(ts_code) → pro.daily_basic()               → Tushare API
     获取 PE, PB, 总市值
  3. ImpactAnalyzer.analyze_impact_batch(events[:10], ...)        → 1次LLM (chat_json)
     综合推演：对每个事件拆解影响维度、方向、量级、周期
     返回: event_impacts[], combined_assessment, earnings_impact
  4. ImpactAnalyzer.historical_backtest(key_event, ...)           → 1次LLM (chat_json)
     内部先调 _fetch_price_around_event() → Tushare daily
     历史同类事件回测: similar_events[], pattern_summary, reference_range
  5. _rate_certainty(events, sentiment_output)                    → 纯计算
     高确定性/中确定性/不确定性/低确定性
  6. → FundamentalImpactOutput (impact_breakdown, cycle_scale, backtest, certainty)
```

### 4.5 IndustryChainAgent — 产业链传导

**文件**：`agents/industry_chain.py`（126 行）  
**职责边界**：产业链上下游传导分析，**不做单标的基本面推演**  
**LLM 调用**：1 次

```
run(state):
  输入: core_news[0]（最关键事件）+ company + industry

  1. 取 core_news 第一条组装 event_summary
  2. self.llm.chat_json(CHAIN_PROMPT, ...)                        → 1次LLM
     返回: chain_mapping(上中下游), conduction_logic(传导路径),
           beneficiaries(受益标的), losers(受损标的),
           cross_sector(跨行业风险), boom_change(景气度)
  3. 组装 benefit_damage_target_list
  4. → IndustryChainOutput (chain_mapping, conduction, benefit_damage, cross_sector, boom)
```

### 4.6 StrategyGenerationAgent — 策略生成

**文件**：`agents/strategy_generation.py`（160 行）  
**职责边界**：事件驱动策略生成，**不做风控校验**  
**LLM 调用**：1 次

```
run(state):
  输入: 全链路上游全部结果

  1. _build_context()                                             → 纯计算
     聚合：标的名称、核心事件标题Top3、情绪指数、影响确定性、产业链景气度
  2. self.llm.chat_json(STRATEGY_PROMPT, context)                 → 1次LLM
     返回: adaptability(适配判断), core_logic(策略逻辑),
           direction(做多/做空/观望), entry_conditions(入场条件),
           take_profit(止盈), stop_loss(止损),
           position_range(仓位), holding_period(持有周期),
           focus_indicators(跟踪指标)
  3. LLM 失败时 _fallback_strategy() → 基于情绪指数的规则兜底
  4. 所有建议附加"仅供参考"标注
  5. → StrategyGenerationOutput (adaptability, core_logic, entry_exit, position, focus)
```

### 4.7 RiskControlAgent — 策略风控

**文件**：`agents/risk_control.py`（140 行）  
**职责边界**：策略风险校验与风控补充，**不修改策略核心逻辑**  
**LLM 调用**：1 次

```
run(state):
  输入: strategy_generation_output + sentiment + fundamental

  1. 组装上下文：策略方向、逻辑、仓位、入场条件、情绪指数、影响确定性
  2. self.llm.chat_json(RISK_PROMPT, context)                     → 1次LLM
     返回: risk_level(5级), rationality_check(合理性校验),
           enhanced_rules(动态止损/极端行情/仓位调整),
           risk_points(风险点), monitoring(监控频率+指标)
  3. LLM 失败时 _fallback_risk() → 基于情绪偏离度的规则兜底
  4. 强制附加3条固定风险提示
  5. → RiskControlOutput (risk_level, rationality, stop_rules, risk_points, monitoring)
```

---

## 5. 支撑保障智能体 ×2

### 5.1 ComplianceAgent — 合规守门人

**文件**：`agents/compliance.py`（198 行）  
**职责边界**：全链路唯一合规守门人，**不做任何业务分析**  
**LLM 调用**：0 次（纯规则引擎）  
**调用方式**：不走 `safe_run()`，由 Orchestrator 在每个节点后调用 `check()`

```
check(agent_name, agent_output, task_id) -> ComplianceCheckOutput:

  1. _extract_text(agent_output, depth=0)                → 递归提取所有文本（最深5层）
  2. for phrase in FORBIDDEN_PHRASES:                     → 严重违规扫描
     "保本/无风险/必赚/稳赚/保证收益/零风险/必涨/必跌/绝对安全..."
     命中 → severity="严重" → fuse_trigger=True (熔断)
  3. for phrase in WARNING_PHRASES:                       → 中度违规扫描
     "建议买入/建议卖出/强烈推荐/应该满仓/全仓买入/立即清仓..."
     命中 → severity="中度" → 自动添加"仅供参考"后缀
  4. _has_absolute_prediction(text)                       → 轻微违规：正则扫描
     "一定会涨/必然上涨/肯定能赚/100%概率/零风险"
  5. 根据 severity 决定结果：
     严重 → check_result="驳回" + fuse_trigger=True
     中度 → check_result="修正后通过" + _apply_corrections()
     无   → check_result="通过"
  6. 附加 COMPLIANCE_DISCLAIMER
  7. → ComplianceCheckOutput (check_result, corrected_content, violation_details, fuse_trigger)
```

**合规熔断机制**：
- 任何业务 Agent 输出含 FORBIDDEN_PHRASES → 整条链路立即熔断
- 后续所有节点跳过，直接跳到 `generate_report` 输出带熔断标记的报告
- 由 `_fuse_check()` 条件边函数在每个节点间拦截

### 5.2 FeedbackOptimizationAgent — 闭环优化

**文件**：`agents/feedback_optimization.py`（139 行）  
**职责边界**：复盘与模型优化，**不参与实时投研链路**  
**LLM 调用**：1 次（仅在独立触发时）  
**调用方式**：`run()` 为 standby 占位，实际逻辑在 `run_optimization()`

```
run(state):
  → 直接返回 standby，不阻塞实时链路

run_optimization(history_report, actual_result, task_id):
  1. 提取历史分析结论：情绪指数、影响确定性、策略方向
  2. 对比实际结果：股价变动、事件进展、持续时间
  3. self.llm.chat_json(REVIEW_PROMPT, context)           → 1次LLM
     返回: accuracy(4维准确率), deviations(偏差原因),
           optimizations(优化建议), backtest_validation(回测验证)
  4. 输出 priority: 综合评分<0.5 → 高优先级
  5. auto_apply=False, requires_review=True (人工确认)
  6. → FeedbackOptimizationOutput (accuracy, deviations, optimizations, backtest, suggestion)
```

**触发入口**：`OrchestratorAgent.run_feedback()` → `POST /api/v2/analysis/feedback`

---

## 6. LangGraph 编排拓扑

```
           ┌─────────────────────────────────────────────────────────────────┐
           │                    FullLinkState (TypedDict)                    │
           │  task_id, task_base_info, task_status, fuse_triggered,         │
           │  news_retrieval_output, event_classification_output,           │
           │  sentiment_analysis_output, fundamental_impact_output,         │
           │  industry_chain_output, strategy_generation_output,            │
           │  risk_control_output, compliance_check_records[],              │
           │  full_link_execution_log[], errors[], final_research_report    │
           └─────────────────────────────────────────────────────────────────┘

Entry → [news_retrieval] → fuse? → [event_classification] → fuse?
           │                                   │
           ├─ NewsRetrievalAgent.safe_run()     ├─ EventClassificationAgent.safe_run()
           ├─ ComplianceAgent.check()           ├─ ComplianceAgent.check()
           │                                   │
      → [sentiment_analysis] → fuse? → [parallel_deep_analysis] → fuse?
           │                                   │
           ├─ SentimentAnalysisAgent            ├─ FundamentalImpactAgent.safe_run()
           ├─ ComplianceAgent.check()           ├─ ComplianceAgent.check()
           │                                   ├─ IndustryChainAgent.safe_run()
           │                                   ├─ ComplianceAgent.check()
           │                                   │
      → [strategy_generation] → fuse? → [risk_control] → fuse? → [generate_report] → END
           │                                   │
           ├─ StrategyGenerationAgent           ├─ RiskControlAgent
           ├─ ComplianceAgent.check()           ├─ ComplianceAgent.check()

fuse? = _fuse_check(state): 若 fuse_triggered=True → 跳到 generate_report
```

**节点总数**：7 个 LangGraph 节点  
**条件边**：6 条（每个业务节点后都有熔断检查）  
**合规校验**：7 次（6 个包装节点各 1 次 + 并行节点内 2 次 = 8 次，但并行算 1 个节点）

---

## 7. 数据流转矩阵

| Agent | 读取上游字段 | 写入字段 | 向下游传递的关键数据 |
|-------|-------------|---------|-------------------|
| NewsRetrieval | `task_base_info` | `news_retrieval_output` | `news_structured_data` (200条) |
| EventClassification | `news_retrieval_output` → `news_structured_data` | `event_classification_output` | `core_news_list` (≤30条), `event_classification_result`, `influence_score_result` |
| SentimentAnalysis | `event_classification_output` → `core_news_list` | `sentiment_analysis_output` | `news_sentiment_detail`, `target_sentiment_index` |
| FundamentalImpact | `event_classification_output` + `sentiment_analysis_output` + `task_base_info` | `fundamental_impact_output` | `impact_logic_breakdown`, `impact_certainty_rating` |
| IndustryChain | `event_classification_output` + `task_base_info` | `industry_chain_output` | `industry_boom_change_judgment`, `benefit_damage_target_list` |
| StrategyGeneration | 上述全部 + `industry_chain_output` | `strategy_generation_output` | `core_strategy_logic`, `entry_exit_conditions`, `reference_position_range` |
| RiskControl | `strategy_generation_output` + `sentiment` + `fundamental` | `risk_control_output` | `strategy_risk_level`, `stop_loss_stop_profit_rules`, `core_risk_points` |
| Compliance | 各 Agent output | `compliance_check_records` | `check_result`, `fuse_trigger` |
| GenerateReport | 全部 output | `final_research_report` | `FinalResearchReport` |

---

## 8. 合规校验时序

以一次正常（无熔断）的全链路执行为例：

```
时间线 →

NewsRetrieval ──────┐
                    ├─ ComplianceAgent.check("news_retrieval", output)         ✅ 通过
EventClassification ┐
                    ├─ ComplianceAgent.check("event_classification", output)   ✅ 通过
SentimentAnalysis ──┐
                    ├─ ComplianceAgent.check("sentiment_analysis", output)     ✅ 通过
FundamentalImpact ──┐
                    ├─ ComplianceAgent.check("fundamental_impact", output)     ✅ 通过
IndustryChain ──────┐
                    ├─ ComplianceAgent.check("industry_chain", output)         ✅ 通过
StrategyGeneration ─┐
                    ├─ ComplianceAgent.check("strategy_generation", output)    ⚠️ 修正后通过
RiskControl ────────┐
                    ├─ ComplianceAgent.check("risk_control", output)           ✅ 通过
GenerateReport ─────┘ → FinalResearchReport + COMPLIANCE_DISCLAIMER
```

合规校验总计 **7 次**，全部基于规则引擎（FORBIDDEN_PHRASES + WARNING_PHRASES + 正则），**0 次 LLM 调用**。

---

## 9. 问题与改进建议

### ✅ 已验证的优点

| 项 | 说明 |
|---|---|
| 10 Agent 独立实现 | 每个 Agent 有独立文件、独立类、独立 `run()` |
| 单一职责清晰 | 每个 SYSTEM_PROMPT 明确禁止做其他 Agent 的工作 |
| LangGraph 编排 | 真正使用 `StateGraph` + 条件边 + 熔断机制 |
| 合规无缝嵌入 | 每个业务节点后强制合规校验 |
| 统一基类契约 | safe_run + 重试 + 日志 + 输出格式一致 |
| 共享 LLM 实例 | 9 个子 Agent 共用一个 LLMClient，不重复初始化 |

### ⚠️ 待改进项

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| 1 | parallel_deep_analysis 实为串行 | Fund 和 Industry 在同一函数内顺序执行，不是真并行 | 用 `concurrent.futures.ThreadPoolExecutor` 或 `asyncio` 实现真并行 |
| 2 | IndustryChain 仅分析第一条核心新闻 | `core_news[0]` 作为唯一输入，其余核心舆情被忽略 | 考虑聚合 Top3 核心事件摘要 |
| 3 | ComplianceAgent 纯规则无 LLM | 仅靠关键词+正则，无法检测语义层面的隐晦违规 | 可增加轻量 LLM 审查（仅对策略和风控输出） |
| 4 | FeedbackOptimization 未自动触发 | 仅手动 API 触发，无定时复盘 | 可接入 scheduler 定时复盘历史任务 |
| 5 | 无 Agent 间通信机制 | 各 Agent 只通过 FullLinkState 单向传递 | 若需 Agent 间协商，可引入 LangGraph 的 channel 机制 |
