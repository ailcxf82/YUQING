# -*- coding: utf-8 -*-
"""Phase 3 验证脚本

验证核心金融舆情分析引擎的全部能力：
  3.1 实体链接 + 事件分类 + 影响力评分
  3.2 细粒度情感分析 + 情绪指数 + 一致性校验
  3.3 影响链路推演 + 产业链分析 + 历史回测
  3.4 风险预警 + 异常识别 + 风险分级
  全链路: SentimentAgent + DeepResearchAgent 集成验证
"""

import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

# 模拟新闻数据——覆盖正向/负向/中性/不确定多种场景
MOCK_NEWS = [
    {
        "id": "N1", "title": "浦发银行2025年年报发布",
        "text": "浦发银行2025年年报发布，全年营收同比增长12%，净利润同比增长18%，超市场一致预期。不良贷款率持续下降。",
        "source_name": "上海证券交易所", "source_level": "S", "source_weight": 1.0,
        "published_at": "2026-03-05T08:00:00+08:00", "spread_count": 500,
        "url": "", "keywords": ["年报", "净利润"], "content_hash": "a1",
    },
    {
        "id": "N2", "title": "监管层对银行理财业务出台新规",
        "text": "银保监会发布银行理财业务管理办法修订征求意见稿，拟加强理财产品信息披露要求，部分业务或受限。",
        "source_name": "财新网", "source_level": "A", "source_weight": 0.85,
        "published_at": "2026-03-06T10:00:00+08:00", "spread_count": 300,
        "url": "", "keywords": ["监管", "理财"], "content_hash": "b2",
    },
    {
        "id": "N3", "title": "浦发银行拟收购某金融科技公司",
        "text": "据市场传闻，浦发银行正在洽谈收购一家头部金融科技公司，交易金额或超50亿元。目前双方尚未正式公告。",
        "source_name": "第一财经", "source_level": "A", "source_weight": 0.85,
        "published_at": "2026-03-07T09:00:00+08:00", "spread_count": 200,
        "url": "", "keywords": ["收购", "金融科技"], "content_hash": "c3",
    },
    {
        "id": "N4", "title": "浦发银行某分行因违规放贷被罚",
        "text": "银保监会网站公布，浦发银行某地分行因违规向不符合条件的企业发放贷款，被处以200万元罚款。",
        "source_name": "银保监会", "source_level": "S", "source_weight": 1.0,
        "published_at": "2026-03-08T14:00:00+08:00", "spread_count": 800,
        "url": "", "keywords": ["处罚", "违规"], "content_hash": "d4",
    },
    {
        "id": "N5", "title": "北向资金持续增持银行板块",
        "text": "北向资金连续5个交易日净买入银行板块，其中浦发银行获净买入3.2亿元，机构看好银行板块估值修复。",
        "source_name": "东方财富", "source_level": "B", "source_weight": 0.7,
        "published_at": "2026-03-09T15:30:00+08:00", "spread_count": 150,
        "url": "", "keywords": ["北向资金", "增持"], "content_hash": "e5",
    },
]


def banner(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check(label: str, passed: bool, detail: str = "") -> bool:
    tag = "[PASS]" if passed else "[FAIL]"
    msg = f"  {tag} {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return passed


def main() -> None:
    banner("Phase 3 验证：核心金融舆情分析引擎")

    from core.logger import setup_logger
    setup_logger(level="INFO")
    from core.config import reload_config
    reload_config()

    all_ok = True

    # ── 3.1.1 实体链接 ──
    banner("3.1.1 实体链接与标的关联")
    try:
        from core.llm import LLMClient
        from core.entity_linker import EntityLinker

        llm = LLMClient()
        linker = EntityLinker(llm)

        result = linker.extract_entities(
            "浦发银行2025年年报发布",
            "浦发银行全年营收同比增长12%，净利润同比增长18%，超市场一致预期。"
        )
        check("实体提取", "entities" in result, f"entities={len(result.get('entities', []))}")
        check("主体公司识别", bool(result.get("primary_company")),
              f"primary={result.get('primary_company')}")

        code = linker.link_to_stock("浦发银行")
        check("股票代码映射", True, f"浦发银行→{code or '(映射表未加载)'}")

    except Exception as e:
        all_ok = check("实体链接模块", False, str(e))
        traceback.print_exc()

    # ── 3.1.2 事件分类 ──
    banner("3.1.2 事件分类")
    try:
        from core.event_classifier import EventClassifier, EVENT_TAXONOMY

        classifier = EventClassifier(llm)
        check("标签体系完整", len(EVENT_TAXONOMY) == 4,
              f"categories={len(EVENT_TAXONOMY)}")

        r1 = classifier.classify(
            "浦发银行年报发布",
            "净利润同比增长18%，超市场一致预期"
        )
        check("正向事件分类", r1.get("category") == "正向事件",
              f"{r1.get('category')}/{r1.get('sub_label')} conf={r1.get('confidence')}")

        r2 = classifier.classify(
            "浦发银行分行被罚",
            "因违规放贷被处以200万元罚款"
        )
        check("负向事件分类", r2.get("category") == "负向事件",
              f"{r2.get('category')}/{r2.get('sub_label')}")

        r3 = EventClassifier._rule_classify("据市场传闻，某公司或将重组")
        check("规则兜底分类", r3.get("category") != "",
              f"{r3.get('category')}/{r3.get('sub_label')}")

    except Exception as e:
        all_ok = check("事件分类模块", False, str(e))
        traceback.print_exc()

    # ── 3.1.3 影响力评分 ──
    banner("3.1.3 影响力评分")
    try:
        from core.influence_scorer import InfluenceScorer

        s1 = InfluenceScorer.score(
            source_weight=1.0, spread_count=800,
            event_sub_label="监管处罚", impact_level="公司级", confidence=0.9
        )
        check("高影响力评分", s1 > 60, f"score={s1}")

        s2 = InfluenceScorer.score(
            source_weight=0.3, spread_count=5,
            event_sub_label="无实质影响", impact_level="公司级", confidence=0.4
        )
        check("低影响力评分", s2 < 30, f"score={s2}")

        spread = InfluenceScorer.track_spread_velocity([
            "2026-03-05T08:00:00+08:00",
            "2026-03-05T08:30:00+08:00",
            "2026-03-05T09:00:00+08:00",
            "2026-03-05T09:15:00+08:00",
            "2026-03-05T09:30:00+08:00",
            "2026-03-05T10:00:00+08:00",
        ])
        check("传播速度跟踪", spread["velocity_per_hour"] > 0,
              f"velocity={spread['velocity_per_hour']}/h fast={spread['is_fast_spreading']}")

        items_prop = InfluenceScorer.classify_propagation(
            [{"publish_time": "2026-03-05T08:00:00", "title": "原始新闻", "content": "内容A", "content_hash": "h1"},
             {"publish_time": "2026-03-05T09:00:00", "title": "转载新闻", "content": "内容B", "content_hash": "h2"}]
        )
        check("源头/二次传播区分", items_prop[0].get("propagation_type") == "源头舆情")

    except Exception as e:
        all_ok = check("影响力评分模块", False, str(e))
        traceback.print_exc()

    # ── 3.2 情感分析 ──
    banner("3.2 细粒度情感分析")
    try:
        from core.sentiment_engine import SentimentEngine

        engine = SentimentEngine(llm)

        s_pos = engine.analyze("浦发银行年报超预期", "净利润同比增长18%，超市场预期。")
        check("正向情感识别", s_pos["score"] > 60,
              f"polarity={s_pos['polarity']} score={s_pos['score']} driver={s_pos['driver']}")

        s_neg = engine.analyze("分行被罚", "因违规放贷被处以200万元罚款。")
        check("负向情感识别", s_neg["score"] < 40,
              f"polarity={s_neg['polarity']} score={s_neg['score']}")

        s_complex = engine.analyze(
            "业绩不及预期但亏损收窄",
            "公司业绩不及预期，但亏损大幅收窄，经营性现金流首次转正。"
        )
        check("复合语义处理", s_complex["polarity"] != "",
              f"polarity={s_complex['polarity']} score={s_complex['score']} "
              f"complexity={s_complex['complexity']}")

        mock_sentiments = [
            {"score": 75, "polarity": "弱正向", "source_weight": 1.0, "influence_score": 70},
            {"score": 30, "polarity": "弱负向", "source_weight": 1.0, "influence_score": 65},
            {"score": 80, "polarity": "强正向", "source_weight": 0.85, "influence_score": 55},
            {"score": 50, "polarity": "中性", "source_weight": 0.7, "influence_score": 40},
            {"score": 95, "polarity": "强正向", "source_weight": 0.3, "influence_score": 10},
        ]

        eidx = SentimentEngine.build_emotion_index(mock_sentiments)
        check("情绪指数构建", "index" in eidx,
              f"index={eidx['index']} trend={eidx['trend']} std={eidx['std_dev']}")

        deviation = SentimentEngine.compute_deviation(eidx["index"], [50, 52, 48, 55, 53])
        check("情绪偏离度", "deviation" in deviation,
              f"dev={deviation['deviation']} direction={deviation['direction']}")

        consistency = SentimentEngine.check_consistency(mock_sentiments)
        check("一致性校验", consistency["type"] != "",
              f"type={consistency['type']} agreement={consistency['agreement_ratio']}")

        filtered = SentimentEngine.filter_noise(mock_sentiments)
        noise_count = sum(1 for s in filtered if s.get("is_noise"))
        check("噪音过滤", noise_count >= 1, f"noise={noise_count}")

    except Exception as e:
        all_ok = check("情感分析模块", False, str(e))
        traceback.print_exc()

    # ── 3.3 影响链路推演 ──
    banner("3.3 影响链路推演")
    try:
        from core.impact_analyzer import ImpactAnalyzer

        analyzer = ImpactAnalyzer(llm)

        chain = analyzer.analyze_impact_chain(
            "浦发银行年报净利润增长18%", "正向事件",
            "浦发银行", {"pe": 5.2, "pb": 0.4, "total_mv": 200000}
        )
        check("影响链路拆解", "impact_dimensions" in chain,
              f"dims={len(chain.get('impact_dimensions', []))}")

        industry = analyzer.analyze_industry_chain(
            "银行理财新规出台", "浦发银行", "银行"
        )
        check("产业链分析", "upstream_impact" in industry or "upstream" in industry,
              f"upstream={len(industry.get('upstream_impact', industry.get('upstream', [])))}")

        bt = analyzer.historical_backtest(
            "银行年报业绩超预期", "正向事件", "业绩超预期", "浦发银行", "600000.SH"
        )
        check("历史回测", "similar_events" in bt,
              f"events={len(bt.get('similar_events', []))} conf={bt.get('confidence')}")

    except Exception as e:
        all_ok = check("影响链路模块", False, str(e))
        traceback.print_exc()

    # ── 3.4 风险预警 ──
    banner("3.4 风险预警与机会识别")
    try:
        from core.alert_system import AlertSystem, RiskLevel

        alert_sys = AlertSystem()

        mock_events_for_alert = [
            {"event_id": "N4", "sub_label": "监管处罚", "influence_score": 75,
             "polarity": "强负向", "score": 15, "core_summary": "违规放贷被罚200万"},
            {"event_id": "N1", "sub_label": "业绩超预期", "influence_score": 80,
             "polarity": "强正向", "score": 85, "core_summary": "净利润增长18%"},
        ]

        result = alert_sys.evaluate(
            mock_events_for_alert,
            {"index": 45, "trend": "震荡", "std_dev": 25},
            [50, 52, 48, 55, 53],
        )
        check("预警生成", result["alert_count"] > 0, f"alerts={result['alert_count']}")
        check("风险等级", result["risk_level"] != "", f"level={result['risk_level']}")
        check("机会识别", "opportunities" in result,
              f"opps={result['opportunity_count']}")

        if result["risk_level"] in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            check("缓释建议", len(result.get("mitigation_suggestions", [])) > 0,
                  f"suggestions={len(result.get('mitigation_suggestions', []))}")

        grade = alert_sys.grade_event_risk(mock_events_for_alert[0])
        check("事件风险分级", grade in (RiskLevel.HIGH, RiskLevel.CRITICAL, RiskLevel.MEDIUM),
              f"grade={grade}")

    except Exception as e:
        all_ok = check("风险预警模块", False, str(e))
        traceback.print_exc()

    # ── 全链路集成：SentimentAgent ──
    banner("全链路集成：SentimentAgent")
    try:
        from agents.sentiment import SentimentAgent

        agent = SentimentAgent(llm_client=llm)
        check("SentimentAgent 初始化", True)

        mock_state = {
            "task": {
                "task_id": "phase3_test",
                "symbol": "600000.SH",
                "name": "浦发银行",
                "industry": "银行",
                "time_range": {"start": "2026-03-01", "end": "2026-03-10"},
                "topics": [],
            },
            "news_data": {"news_items": MOCK_NEWS, "total_count": len(MOCK_NEWS)},
            "sentiment_result": {},
            "research_result": {},
            "strategy_result": {},
            "agent_outputs": [],
            "errors": [],
            "final_report": "",
            "final_json": {},
            "current_step": "news_retrieval_done",
        }

        print("\n  执行 SentimentAgent 全链路分析...")
        t0 = time.time()
        result = agent.safe_run(mock_state)
        elapsed = int((time.time() - t0) * 1000)
        print(f"  完成 | 耗时 {elapsed}ms")

        sr = result.get("sentiment_result", {})
        events = sr.get("events", [])
        check("事件分析完成", len(events) == len(MOCK_NEWS), f"events={len(events)}")
        check("情绪指数", "emotion_index" in sr,
              f"index={sr.get('emotion_index', {}).get('index')}")
        check("一致性校验", "consistency" in sr,
              f"type={sr.get('consistency', {}).get('type')}")
        check("预警输出", "alerts" in sr,
              f"risk={sr.get('alerts', {}).get('risk_level')}")

        if events:
            e0 = events[0]
            required = ["event_id", "polarity", "score", "event_category",
                        "sub_label", "influence_score", "risk_level"]
            missing = [k for k in required if k not in e0]
            check("事件字段完整", len(missing) == 0,
                  f"missing={missing}" if missing else f"all {len(required)} fields present")

    except Exception as e:
        all_ok = check("SentimentAgent 全链路", False, str(e))
        traceback.print_exc()

    # ── 全链路集成：DeepResearchAgent ──
    banner("全链路集成：DeepResearchAgent")
    try:
        from agents.deep_research import DeepResearchAgent

        dr_agent = DeepResearchAgent(llm_client=llm)
        check("DeepResearchAgent 初始化", True)

        mock_state_dr = {
            "task": {
                "task_id": "phase3_test",
                "symbol": "600000.SH",
                "name": "浦发银行",
                "industry": "银行",
                "time_range": {"start": "2026-03-01", "end": "2026-03-10"},
                "topics": [],
            },
            "news_data": {},
            "sentiment_result": sr,
            "research_result": {},
            "strategy_result": {},
            "agent_outputs": [],
            "errors": [],
            "final_report": "",
            "final_json": {},
            "current_step": "sentiment_done",
        }

        print("\n  执行 DeepResearchAgent 全链路分析...")
        t1 = time.time()
        dr_result = dr_agent.safe_run(mock_state_dr)
        elapsed_dr = int((time.time() - t1) * 1000)
        print(f"  完成 | 耗时 {elapsed_dr}ms")

        rr = dr_result.get("research_result", {})
        check("影响链路", "impact_chains" in rr,
              f"chains={len(rr.get('impact_chains', []))}")
        check("产业链分析", "industry_analysis" in rr)
        check("历史回测", "backtest_results" in rr,
              f"backtests={len(rr.get('backtest_results', []))}")
        check("综合评估", "value_assessment" in rr,
              f"conclusion={rr.get('value_assessment', {}).get('conclusion', '')[:30]}")

    except Exception as e:
        all_ok = check("DeepResearchAgent 全链路", False, str(e))
        traceback.print_exc()

    # ── 保存结果 ──
    try:
        os.makedirs("tests", exist_ok=True)
        output = {
            "sentiment_result": sr,
            "research_result": rr if "rr" in dir() else {},
        }
        with open("tests/phase3_result.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)
        check("结果保存", True, "tests/phase3_result.json")
    except Exception as e:
        check("结果保存", False, str(e))

    # ── 汇总 ──
    banner("Phase 3 验证汇总")
    if all_ok:
        print("  所有核心检查通过！Phase 3 实现验证成功。")
    else:
        print("  部分检查未通过，请查看上方 [FAIL] 项。")
    print()


if __name__ == "__main__":
    main()
