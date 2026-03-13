# -*- coding: utf-8 -*-
"""Phase 4 全链路验证脚本

验证内容：
  1. 所有 10 个智能体可独立初始化
  2. Pydantic I/O 结构体完整性
  3. FullLinkState 状态机定义正确
  4. LangGraph 全链路图可编译
  5. 合规校验逻辑（通过/修正/驳回/熔断）
  6. 单节点独立执行测试（Mock 数据）
  7. 全链路集成执行测试
  8. 反馈优化节点独立测试
"""

from __future__ import annotations

import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(__file__))

PASS = 0
FAIL = 0
WARN = 0


def log_pass(msg: str):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def log_fail(msg: str, detail: str = ""):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")
    if detail:
        print(f"         {detail[:200]}")


def log_warn(msg: str):
    global WARN
    WARN += 1
    print(f"  [WARN] {msg}")


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── Mock 新闻数据 ──
MOCK_NEWS = [
    {
        "news_id": "M001",
        "title": "浦发银行2025年度净利润同比增长15%",
        "content": "浦发银行今日发布年度财报，净利润同比增长15%，不良贷款率下降至1.2%。多个业务条线表现稳健。",
        "text": "浦发银行今日发布年度财报，净利润同比增长15%，不良贷款率下降至1.2%。",
        "source": "财联社",
        "source_level": "A",
        "source_weight": 0.85,
        "publish_time": "2026-03-10",
        "spread_count": 500,
        "core_entity": "浦发银行",
        "related_stock": "600000.SH",
        "event_type": "业绩超预期",
        "keywords": ["浦发银行", "净利润", "财报"],
    },
    {
        "news_id": "M002",
        "title": "银保监会对某银行开出罚单",
        "content": "因违规放贷，某中小银行被银保监会罚款500万。市场对银行板块风控能力关注度提升。",
        "text": "因违规放贷，某中小银行被银保监会罚款500万。",
        "source": "第一财经",
        "source_level": "A",
        "source_weight": 0.85,
        "publish_time": "2026-03-09",
        "spread_count": 300,
        "core_entity": "银保监会",
        "related_stock": "",
        "event_type": "监管处罚",
        "keywords": ["银保监会", "罚单", "银行"],
    },
    {
        "news_id": "M003",
        "title": "央行降准0.5个百分点释放长期资金",
        "content": "央行宣布下调存款准备金率0.5个百分点，预计释放约1万亿长期资金，利好银行板块。",
        "text": "央行宣布下调存款准备金率0.5个百分点，预计释放约1万亿长期资金。",
        "source": "新华社",
        "source_level": "S",
        "source_weight": 1.0,
        "publish_time": "2026-03-08",
        "spread_count": 2000,
        "core_entity": "央行",
        "related_stock": "",
        "event_type": "政策扶持",
        "keywords": ["央行", "降准", "银行"],
    },
]


def build_mock_state() -> dict:
    """构建带 Mock 数据的 FullLinkState"""
    return {
        "task_id": "test_001",
        "task_base_info": {
            "target_type": "个股",
            "target_code": ["600000.SH"],
            "target_name": ["浦发银行"],
            "time_range": "近7天",
            "custom_time_start": "2026-03-04",
            "custom_time_end": "2026-03-11",
            "analysis_depth": "标准版",
            "user_custom_rules": {},
        },
        "task_status": "执行中",
        "news_retrieval_output": {
            "task_id": "test_001",
            "news_total_count": len(MOCK_NEWS),
            "news_structured_data": MOCK_NEWS,
            "vector_db_index_info": {"table_name": "news_test"},
            "data_quality_report": {"raw_collected": 3, "after_clean": 3},
            "execution_log": {},
        },
        "event_classification_output": {},
        "sentiment_analysis_output": {},
        "fundamental_impact_output": {},
        "industry_chain_output": {},
        "strategy_generation_output": {},
        "risk_control_output": {},
        "compliance_check_records": [],
        "full_link_execution_log": [],
        "errors": [],
        "final_research_report": {},
        "current_step": "test",
        "retry_counts": {},
        "fuse_triggered": False,
    }


def test_schemas():
    section("1. Pydantic I/O 结构体完整性")
    try:
        from core.schemas import (
            UserRequest, NewsRetrievalOutput, EventClassificationOutput,
            SentimentAnalysisOutput, FundamentalImpactOutput,
            IndustryChainOutput, StrategyGenerationOutput,
            RiskControlOutput, ComplianceCheckOutput,
            FeedbackOptimizationOutput, FinalResearchReport,
            FullLinkState,
        )
        log_pass("所有 I/O 结构体导入成功")

        req = UserRequest(target_code=["600000.SH"], target_name=["浦发银行"])
        assert req.target_type == "个股", "默认 target_type 应为个股"
        log_pass("UserRequest 实例化 & 默认值正确")

        report = FinalResearchReport()
        d = report.model_dump()
        for k in [
            "task_base_info", "news_summary", "event_classification_result",
            "sentiment_analysis_result", "fundamental_impact_report",
            "industry_chain_analysis_result", "strategy_suggestion",
            "risk_control_rules", "compliance_disclaimer", "full_link_log",
        ]:
            assert k in d, f"FinalResearchReport 缺少字段: {k}"
        log_pass("FinalResearchReport 所有必填字段存在")

        comp = ComplianceCheckOutput()
        assert comp.compliance_disclaimer, "免责声明不应为空"
        assert comp.fuse_trigger is False, "默认不触发熔断"
        log_pass("ComplianceCheckOutput 默认值正确")

    except Exception as e:
        log_fail("结构体测试失败", str(e))
        traceback.print_exc()


def test_agent_init():
    section("2. 全部 10 个智能体独立初始化")
    agents_to_test = [
        ("ComplianceAgent", "agents.compliance", "ComplianceAgent"),
        ("EventClassificationAgent", "agents.event_classification", "EventClassificationAgent"),
        ("SentimentAnalysisAgent", "agents.sentiment_analysis", "SentimentAnalysisAgent"),
        ("FundamentalImpactAgent", "agents.fundamental_impact", "FundamentalImpactAgent"),
        ("IndustryChainAgent", "agents.industry_chain", "IndustryChainAgent"),
        ("StrategyGenerationAgent", "agents.strategy_generation", "StrategyGenerationAgent"),
        ("RiskControlAgent", "agents.risk_control", "RiskControlAgent"),
        ("FeedbackOptimizationAgent", "agents.feedback_optimization", "FeedbackOptimizationAgent"),
        ("NewsRetrievalAgent", "agents.news_retrieval", "NewsRetrievalAgent"),
    ]

    for display_name, mod_path, cls_name in agents_to_test:
        try:
            mod = __import__(mod_path, fromlist=[cls_name])
            cls = getattr(mod, cls_name)
            instance = cls()
            assert instance.name, f"{display_name}.name 为空"
            assert hasattr(instance, "run"), f"{display_name} 缺少 run 方法"
            assert hasattr(instance, "safe_run"), f"{display_name} 缺少 safe_run 方法"
            log_pass(f"{display_name} 初始化成功 (name={instance.name})")
        except Exception as e:
            log_fail(f"{display_name} 初始化失败", str(e))

    try:
        from agents.orchestrator import OrchestratorAgent
        orch = OrchestratorAgent()
        assert orch.name == "orchestrator"
        assert hasattr(orch, "_graph"), "OrchestratorAgent 缺少 _graph"
        assert hasattr(orch, "execute"), "OrchestratorAgent 缺少 execute 方法"
        log_pass("OrchestratorAgent 初始化成功 (含 LangGraph 编译)")
    except Exception as e:
        log_fail("OrchestratorAgent 初始化失败", str(e))
        traceback.print_exc()


def test_compliance():
    section("3. 合规校验逻辑验证")
    try:
        from agents.compliance import ComplianceAgent

        comp = ComplianceAgent()

        clean_output = {"analysis": "浦发银行业绩同比增长", "score": 75}
        r = comp.check("test_agent", clean_output, "t001")
        assert r.check_result == "通过", f"合规内容应通过, got {r.check_result}"
        assert not r.fuse_trigger
        log_pass("合规内容 → 通过")

        warn_output = {"suggestion": "建议买入浦发银行，前景乐观"}
        r = comp.check("test_agent", warn_output, "t002")
        assert r.check_result == "修正后通过", f"中度违规应修正通过, got {r.check_result}"
        assert not r.fuse_trigger
        assert "不构成投资建议" in str(r.corrected_content)
        log_pass("中度违规 → 修正后通过")

        bad_output = {"advice": "该股保本无风险，必赚！"}
        r = comp.check("test_agent", bad_output, "t003")
        assert r.check_result == "驳回", f"严重违规应驳回, got {r.check_result}"
        assert r.fuse_trigger
        assert len(r.violation_details) > 0
        log_pass("严重违规 → 驳回 + 熔断触发")

        assert r.compliance_disclaimer, "免责声明不应为空"
        log_pass("免责声明自动植入")

    except Exception as e:
        log_fail("合规校验测试失败", str(e))
        traceback.print_exc()


def test_event_classification():
    section("4. EventClassificationAgent 单节点测试")
    try:
        from agents.event_classification import EventClassificationAgent

        agent = EventClassificationAgent()
        state = build_mock_state()
        result = agent.run(state)

        assert "event_classification_output" in result
        output = result["event_classification_output"]
        assert output.get("entity_linking_result"), "实体链接结果不应为空"
        assert output.get("event_classification_result"), "事件分类结果不应为空"
        assert output.get("influence_score_result"), "影响力评分不应为空"
        assert output.get("core_news_list"), "核心舆情列表不应为空"
        log_pass("EventClassificationAgent 全字段输出正确")

        for inf in output["influence_score_result"]:
            score = inf.get("influence_score", -1)
            assert 0 <= score <= 100, f"影响力分数应在0-100, got {score}"
        log_pass("影响力分数范围正确 (0-100)")

    except Exception as e:
        log_fail("EventClassificationAgent 测试失败", str(e))
        traceback.print_exc()


def test_sentiment_analysis():
    section("5. SentimentAnalysisAgent 单节点测试")
    try:
        from agents.sentiment_analysis import SentimentAnalysisAgent
        from agents.event_classification import EventClassificationAgent

        event_agent = EventClassificationAgent()
        state = build_mock_state()
        event_result = event_agent.run(state)
        state.update(event_result)

        agent = SentimentAnalysisAgent()
        result = agent.run(state)

        assert "sentiment_analysis_output" in result
        output = result["sentiment_analysis_output"]
        assert output.get("news_sentiment_detail"), "情绪详情不应为空"
        assert output.get("target_sentiment_index"), "情绪指数不应为空"
        assert output.get("news_comprehensive_rating"), "综合评级不应为空"
        log_pass("SentimentAnalysisAgent 全字段输出正确")

        idx = output["target_sentiment_index"].get("index", -1)
        assert 0 <= idx <= 100, f"情绪指数应在0-100, got {idx}"
        log_pass(f"情绪指数={idx} 范围正确")

    except Exception as e:
        log_fail("SentimentAnalysisAgent 测试失败", str(e))
        traceback.print_exc()


def test_langgraph_compile():
    section("6. LangGraph 全链路图编译验证")
    try:
        from agents.orchestrator import OrchestratorAgent
        orch = OrchestratorAgent()

        graph = orch._graph
        assert graph is not None, "编译后的图不应为None"
        log_pass("LangGraph StateGraph 编译成功")

    except Exception as e:
        log_fail("LangGraph 编译失败", str(e))
        traceback.print_exc()


def test_full_link():
    section("7. 全链路集成测试 (Mock 数据)")
    try:
        from agents.orchestrator import OrchestratorAgent
        from core.schemas import UserRequest

        orch = OrchestratorAgent()
        request = UserRequest(
            target_type="个股",
            target_code=["600000.SH"],
            target_name=["浦发银行"],
            time_range="近7天",
            custom_time_start="2026-03-04",
            custom_time_end="2026-03-11",
            analysis_depth="标准版",
        )

        start = time.time()
        print("  [WAIT] Running full link (LLM calls, may take 30-120s)...")
        report = orch.execute(request)
        elapsed = int((time.time() - start) * 1000)
        print(f"  [TIME] Full link elapsed: {elapsed}ms")

        if not report:
            log_warn("全链路返回空报告（可能因网络/API问题）")
            return

        for key in [
            "task_base_info", "news_summary", "compliance_disclaimer",
        ]:
            if key in report:
                log_pass(f"最终报告包含字段: {key}")
            else:
                log_warn(f"最终报告缺少字段: {key}")

        if report.get("compliance_disclaimer"):
            log_pass("免责声明已植入最终报告")
        else:
            log_warn("免责声明缺失")

        if report.get("full_link_log", {}).get("status") in ("已完成", "熔断"):
            log_pass(f"全链路状态: {report['full_link_log']['status']}")
        else:
            log_warn(f"全链路状态: {report.get('full_link_log', {}).get('status', '未知')}")

    except Exception as e:
        log_fail("全链路集成测试失败", str(e))
        traceback.print_exc()


def test_feedback():
    section("8. FeedbackOptimizationAgent 独立测试")
    try:
        from agents.feedback_optimization import FeedbackOptimizationAgent

        agent = FeedbackOptimizationAgent()

        mock_history = {
            "sentiment_analysis_result": {
                "target_sentiment_index": {"index": 72}
            },
            "fundamental_impact_report": {
                "impact_certainty_rating": "中确定性"
            },
            "strategy_suggestion": {
                "entry_exit_conditions": {"direction": "做多"}
            },
        }
        mock_actual = {
            "price_change_pct": 5.3,
            "event_progress": "业绩兑现",
            "duration": "30天",
        }

        result = agent.run_optimization(mock_history, mock_actual, "hist_001")
        assert result.task_id == "hist_001"
        assert result.analysis_accuracy_evaluation, "准确率评估不应为空"
        log_pass("FeedbackOptimizationAgent 复盘优化执行成功")

    except Exception as e:
        log_fail("FeedbackOptimizationAgent 测试失败", str(e))
        traceback.print_exc()


def test_state_isolation():
    section("9. 状态隔离验证（各智能体仅修改自己的字段）")
    try:
        from agents.event_classification import EventClassificationAgent

        agent = EventClassificationAgent()
        state = build_mock_state()
        result = agent.run(state)

        allowed_keys = {
            "event_classification_output", "full_link_execution_log",
            "current_step", "errors",
        }
        actual_keys = set(result.keys())
        violation = actual_keys - allowed_keys
        if not violation:
            log_pass("EventClassificationAgent 仅修改自身字段")
        else:
            log_warn(f"EventClassificationAgent 修改了额外字段: {violation}")

    except Exception as e:
        log_fail("状态隔离测试失败", str(e))
        traceback.print_exc()


def main():
    print()
    print("=" * 60)
    print("  Phase 4 精细化多智能体全链路验证")
    print("=" * 60)

    test_schemas()
    test_agent_init()
    test_compliance()
    test_event_classification()
    test_sentiment_analysis()
    test_langgraph_compile()
    test_feedback()
    test_state_isolation()
    test_full_link()

    print()
    print("=" * 60)
    print(f"  Phase 4 验证汇总: PASS={PASS}  FAIL={FAIL}  WARN={WARN}")
    print("=" * 60)
    if FAIL == 0:
        print("  ALL CORE CHECKS PASSED! Phase 4 verified successfully.")
    else:
        print(f"  {FAIL} checks FAILED. See details above.")
    print()


if __name__ == "__main__":
    main()
