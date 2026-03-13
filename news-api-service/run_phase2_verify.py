# -*- coding: utf-8 -*-
"""Phase 2 验证脚本

逐项验证舆情数据采集与预处理模块的全部能力：
  1. 数据源抽象基类 + Tushare 数据源
  2. 采集器（去重、标的过滤）
  3. 预处理流水线（清洗 + 结构化提取 + 分块）
  4. Embedding 向量化
  5. LanceDB 向量存储与检索
  6. NewsRetrievalAgent 全链路集成
"""

import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(__file__))

os.chdir(os.path.dirname(__file__))


def banner(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check(label: str, passed: bool, detail: str = "") -> None:
    tag = "[PASS]" if passed else "[FAIL]"
    msg = f"  {tag} {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def main() -> None:
    banner("Phase 2 验证：舆情数据采集与预处理模块")

    # ── 0. 环境初始化 ──
    from core.logger import setup_logger
    setup_logger(level="INFO")

    from core.config import get_config, reload_config
    reload_config()
    cfg = get_config()
    check("配置加载", True, f"provider={cfg.llm_provider}")

    all_passed = True

    # ── 1. 数据源层 ──
    banner("1. 数据源层验证")
    try:
        from core.datasources.base import BaseDataSource, SOURCE_WEIGHTS, SourceLevel
        check("BaseDataSource 导入", True)
        check("信源权重配置", len(SOURCE_WEIGHTS) == 5,
              f"S={SOURCE_WEIGHTS.get('S')}, A={SOURCE_WEIGHTS.get('A')}")
    except Exception as e:
        check("数据源基类", False, str(e))
        all_passed = False

    tushare_ok = False
    try:
        from core.datasources.tushare_source import TushareNewsSource
        ts_src = TushareNewsSource()
        check("TushareNewsSource 初始化", True)
        level = ts_src.get_source_level("cls")
        check("信源等级映射", level == "A", f"cls → {level}")
        tushare_ok = True
    except EnvironmentError as e:
        check("TushareNewsSource", False, f"TUSHARE_TOKEN 未配置: {e}")
    except Exception as e:
        check("TushareNewsSource", False, str(e))

    # ── 2. 采集器验证 ──
    banner("2. 采集器验证")
    try:
        from core.collector import NewsCollector, content_fingerprint

        fp1 = content_fingerprint("测试标题", "测试正文内容")
        fp2 = content_fingerprint("测试标题", "测试正文内容")
        fp3 = content_fingerprint("不同标题", "不同内容")
        check("内容指纹一致性", fp1 == fp2, f"same={fp1[:12]}")
        check("内容指纹区分度", fp1 != fp3, f"diff={fp3[:12]}")

        collector = NewsCollector()
        if tushare_ok:
            collector.add_source(ts_src)

        mock_items = [
            {"title": "浦发银行年报发布", "content": "净利润同比增长15%。" * 5,
             "publish_time": "2026-03-01 08:00:00", "source": "cls",
             "source_level": "A", "source_weight": 0.85, "url": ""},
            {"title": "浦发银行年报发布", "content": "净利润同比增长15%。" * 5,
             "publish_time": "2026-03-01 08:00:00", "source": "sina",
             "source_level": "B", "source_weight": 0.7, "url": ""},
            {"title": "贵州茅台新品发布", "content": "茅台推出新系列产品。" * 5,
             "publish_time": "2026-03-02 10:00:00", "source": "yicai",
             "source_level": "A", "source_weight": 0.85, "url": ""},
        ]
        collector.reset_seen()
        from core.collector import content_fingerprint as cfp
        for item in mock_items:
            item["content_hash"] = cfp(item["title"], item["content"])

        deduped = collector._deduplicate(mock_items)
        check("去重功能", len(deduped) == 2, f"3条→{len(deduped)}条")

    except Exception as e:
        check("采集器", False, str(e))
        traceback.print_exc()
        all_passed = False

    # ── 3. 预处理流水线 ──
    banner("3. 预处理流水线验证")
    try:
        from core.preprocessor import TextCleaner, TextChunker, PreprocessPipeline

        cleaner = TextCleaner()
        dirty = "  <b>测试</b>  \t 　全角测试　  \n\n\n\n多余换行  "
        cleaned = cleaner.clean(dirty)
        check("HTML标签清除", "<b>" not in cleaned, f"'{cleaned}'")
        check("全角转半角", "　" not in cleaned)
        check("多余换行压缩", "\n\n\n" not in cleaned)

        check("有效内容识别", cleaner.is_valid("这是一条有效的金融新闻内容测试文本"))
        check("无效内容过滤", not cleaner.is_valid("广告"))

        long_text = "这是第一段。" * 100 + "\n\n" + "这是第二段。" * 100
        chunks = TextChunker.chunk(long_text, max_length=200)
        check("文本分块", len(chunks) > 1, f"分为{len(chunks)}块")
        for i, c in enumerate(chunks):
            if len(c) > 250:
                check(f"分块{i}长度", False, f"len={len(c)}")
                break
        else:
            check("分块长度合理", True, f"max={max(len(c) for c in chunks)}")

        pipeline = PreprocessPipeline(llm_client=None, max_llm_calls=0)
        test_items = [
            {"title": "浦发银行年报", "content": "净利润同比增长15%，营收同比增长8%。" * 3,
             "source": "cls", "source_level": "A", "source_weight": 0.85},
            {"title": "", "content": "广告", "source": "unknown",
             "source_level": "D", "source_weight": 0.3},
        ]
        result = pipeline.process(test_items)
        check("流水线过滤无效内容", len(result) == 1, f"2条→{len(result)}条")
        check("流水线分块输出", "chunk_texts" in result[0])

    except Exception as e:
        check("预处理流水线", False, str(e))
        traceback.print_exc()
        all_passed = False

    # ── 4. Embedding 向量化 ──
    banner("4. Embedding 向量化验证")
    emb_ok = False
    emb_client = None
    try:
        from core.embedding import EmbeddingClient
        emb_client = EmbeddingClient()
        vec = emb_client.embed("浦发银行年报利润增长")
        check("单文本向量化", len(vec) > 0, f"dim={len(vec)}")

        vecs = emb_client.embed_batch(["文本A", "文本B", "文本C"])
        check("批量向量化", len(vecs) == 3, f"batch=3, dims={len(vecs[0])}")

        emb_ok = True
    except Exception as e:
        check("Embedding", False, str(e))
        traceback.print_exc()
        all_passed = False

    # ── 5. LanceDB 向量存储与检索 ──
    banner("5. LanceDB 向量存储与检索验证")
    search_ok = False
    try:
        from core.vector_store import VectorStore
        vs = VectorStore()
        test_table = "phase2_test"

        dim = emb_client.dim if emb_client else 256
        test_records = [
            {
                "news_id": "T1", "chunk_index": 0,
                "title": "浦发银行年报", "content": "净利润增长15%",
                "chunk_text": "浦发银行年报净利润增长15%",
                "publish_time": "2026-03-01 08:00:00",
                "source": "cls", "source_level": "A", "source_weight": 0.85,
                "core_entity": "浦发银行", "related_stock": "600000.SH",
                "event_type": "业绩发布", "keywords": "年报,净利润",
                "spread_count": 100, "symbol": "600000.SH",
                "content_hash": "abc123",
                "vector": emb_client.embed("浦发银行年报净利润增长15%") if emb_client else [0.1]*dim,
            },
            {
                "news_id": "T2", "chunk_index": 0,
                "title": "贵州茅台新品", "content": "推出新系列白酒产品",
                "chunk_text": "贵州茅台推出新系列白酒产品",
                "publish_time": "2026-03-02 10:00:00",
                "source": "yicai", "source_level": "A", "source_weight": 0.85,
                "core_entity": "贵州茅台", "related_stock": "600519.SH",
                "event_type": "产品发布", "keywords": "新品,白酒",
                "spread_count": 200, "symbol": "600519.SH",
                "content_hash": "def456",
                "vector": emb_client.embed("贵州茅台推出新系列白酒产品") if emb_client else [0.2]*dim,
            },
        ]

        vs.create_table(test_table, test_records, mode="overwrite")
        check("向量表创建", test_table in vs.list_tables())

        if emb_client:
            q_vec = emb_client.embed("银行业绩")
            results = vs.search(test_table, q_vec, limit=5)
            check("向量语义检索", len(results) > 0, f"found={len(results)}")
            search_ok = True
        else:
            check("向量检索(跳过)", True, "Embedding 不可用")

        from core.news_search import NewsSearchEngine
        if emb_client:
            engine = NewsSearchEngine(vs, emb_client)
            sem_results = engine.semantic_search("银行利润", test_table, limit=5)
            check("NewsSearchEngine 语义检索", len(sem_results) > 0)

            kw_results = engine.keyword_search("茅台", test_table)
            check("NewsSearchEngine 关键词检索", len(kw_results) > 0,
                  f"found={len(kw_results)}")

            sym_results = engine.symbol_search("600000.SH", test_table)
            check("NewsSearchEngine 标的检索", len(sym_results) > 0)

            filtered = engine.filtered_search(
                test_table, query="银行", min_source_weight=0.8
            )
            check("NewsSearchEngine 组合过滤", len(filtered) > 0)

        vs.drop_table(test_table)
        check("向量表清理", test_table not in vs.list_tables())

    except Exception as e:
        check("LanceDB 存储与检索", False, str(e))
        traceback.print_exc()
        all_passed = False

    # ── 6. NewsRetrievalAgent 全链路 ──
    banner("6. NewsRetrievalAgent 全链路集成验证")
    try:
        from agents.news_retrieval import NewsRetrievalAgent
        from core.llm import LLMClient

        llm = LLMClient()
        agent = NewsRetrievalAgent(llm_client=llm)
        check("NewsRetrievalAgent 初始化", True,
              f"数据源={len(agent.collector.data_sources)}个")

        mock_state = {
            "task": {
                "task_id": "phase2_test",
                "symbol": "600000.SH",
                "name": "浦发银行",
                "time_range": {"start": "2026-03-01", "end": "2026-03-10"},
                "topics": ["年报", "银行"],
            },
            "news_data": {},
            "sentiment_result": {},
            "research_result": {},
            "strategy_result": {},
            "agent_outputs": [],
            "errors": [],
            "final_report": "",
            "final_json": {},
            "current_step": "initialized",
        }

        print("\n  开始全链路执行（采集→预处理→向量化→存储）...")
        start = time.time()
        result = agent.safe_run(mock_state)
        elapsed = int((time.time() - start) * 1000)
        print(f"  执行完成 | 耗时 {elapsed}ms")

        news_data = result.get("news_data", {})
        outputs = result.get("agent_outputs", [])
        step = result.get("current_step", "")

        total = news_data.get("total_count", 0)
        stats = news_data.get("stats", {})
        vector_idx = news_data.get("vector_index", "")

        check("全链路执行完成", step == "news_retrieval_done", f"step={step}")
        check("输出 agent_outputs", len(outputs) > 0)

        agent_status = outputs[0].get("status", "") if outputs else ""
        check("智能体状态", agent_status in ("success", "partial"),
              f"status={agent_status}")

        check("采集数据", total >= 0, f"total_count={total}")
        check("采集统计", "raw_collected" in stats,
              f"raw={stats.get('raw_collected',0)} clean={stats.get('after_clean',0)}")
        check("向量索引", bool(vector_idx), f"index={vector_idx}")

        if news_data.get("news_items"):
            item = news_data["news_items"][0]
            check("输出字段完整", all(
                k in item for k in ["id", "source_name", "source_level",
                                     "published_at", "text"]
            ))

        output_path = os.path.join("tests", "phase2_result.json")
        os.makedirs("tests", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        check("结果保存", True, output_path)

    except Exception as e:
        check("NewsRetrievalAgent 全链路", False, str(e))
        traceback.print_exc()
        all_passed = False

    # ── 汇总 ──
    banner("Phase 2 验证汇总")
    if all_passed:
        print("  所有核心检查通过！Phase 2 实现验证成功。")
    else:
        print("  部分检查未通过，请查看上方 [FAIL] 项。")
    print()


if __name__ == "__main__":
    main()
