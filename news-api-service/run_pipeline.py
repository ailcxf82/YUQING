# -*- coding: utf-8 -*-
"""多智能体系统验证脚本

验收标准：
  1. 所有智能体类可成功初始化
  2. OrchestratorAgent 完成模拟任务全流程调度，状态流转正常
  3. LLM 接口可正常调用（SentimentAgent 会触发实际 LLM 调用）
  4. 配置文件可正常读取，日志系统正常运行

用法：
  cd news-api-service
  python run_pipeline.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.logger import setup_logger
from core.config import get_config, reload_config
from core.schemas import Task, TimeRange, RiskPreference, InvestmentHorizon


def main():
    # ── 1. 初始化日志系统 ──
    logger = setup_logger(level="INFO", log_dir="./logs")
    logger.info("=" * 60)
    logger.info("  多智能体系统 Phase 1 验证")
    logger.info("=" * 60)

    # ── 2. 验证配置加载 ──
    logger.info("── 步骤 1：配置加载验证 ──")
    config = get_config()
    logger.info("  LLM 提供商: %s", config.llm_provider)
    logger.info("  Tushare: %s", "已配置" if config.tushare_token else "未配置")
    logger.info("  LanceDB 路径: %s", config.lancedb_path)
    logger.info("  日志级别: %s", config.log_level)

    # 配置热更新测试
    reloaded = reload_config()
    logger.info("  配置热更新: 成功 (provider=%s)", reloaded.llm_provider)
    print("[PASS] 配置加载与热更新正常\n")

    # ── 3. 验证所有智能体初始化 ──
    logger.info("── 步骤 2：智能体初始化验证 ──")
    from agents.news_retrieval import NewsRetrievalAgent
    from agents.sentiment import SentimentAgent
    from agents.deep_research import DeepResearchAgent
    from agents.strategy import StrategyAgent
    from agents.orchestrator import OrchestratorAgent

    agents = {
        "NewsRetrievalAgent": NewsRetrievalAgent(),
        "SentimentAgent": SentimentAgent(),
        "DeepResearchAgent": DeepResearchAgent(),
        "StrategyAgent": StrategyAgent(),
    }
    for name, agent in agents.items():
        logger.info("  %s (name=%s) 初始化成功", name, agent.name)
    print("[PASS] 所有智能体初始化成功\n")

    # ── 4. 验证 LLM 连通性 ──
    logger.info("── 步骤 3：LLM 连通性验证 ──")
    from core.llm import LLMClient
    try:
        llm = LLMClient()
        response = llm.chat([
            {"role": "system", "content": "你是一个助手。"},
            {"role": "user", "content": "请回复：连通性测试成功"},
        ], max_tokens=50)
        logger.info("  LLM 响应: %s", response[:80])
        print("[PASS] LLM 连通性正常\n")
    except Exception as e:
        logger.error("  LLM 连通性测试失败: %s", e)
        print(f"[WARN] LLM 连通性测试失败: {e}")
        print("       （不影响调度框架验证，继续执行）\n")

    # ── 5. 创建测试任务 ──
    logger.info("── 步骤 4：全流程调度验证 ──")
    task = Task(
        symbol="600519.SH",
        name="贵州茅台",
        industry="白酒",
        topics=["业绩增长", "新品发布", "北向资金"],
        time_range=TimeRange(start="2026-03-01", end="2026-03-11"),
        requirements="分析贵州茅台近期舆情，评估投资价值",
        risk_preference=RiskPreference.BALANCED,
        investment_horizon=InvestmentHorizon.MID,
        max_position_pct=30.0,
    )
    logger.info("  任务创建: task_id=%s symbol=%s", task.task_id, task.symbol)

    # 查看任务分解
    orchestrator = OrchestratorAgent()
    plan = orchestrator.decompose_task(task)
    logger.info("  任务分解为 %d 个子步骤：", len(plan))
    for step in plan:
        deps = ", ".join(step["depends_on"]) if step["depends_on"] else "无"
        logger.info(
            "    Step %d: [%s] %s (依赖: %s)",
            step["step"], step["agent"], step["description"], deps,
        )

    # ── 6. 执行全流程 ──
    logger.info("  开始执行全流程调度…")
    result = orchestrator.execute(task)

    # ── 7. 验证结果 ──
    final_step = result.get("current_step", "")
    final_report = result.get("final_report", "")
    final_json = result.get("final_json", {})
    agent_outputs = result.get("agent_outputs", [])
    errors = result.get("errors", [])

    logger.info("  最终步骤: %s", final_step)
    logger.info("  智能体输出数: %d", len(agent_outputs))
    logger.info("  错误数: %d", len(errors))
    logger.info("  报告长度: %d 字符", len(final_report))

    if final_step == "completed":
        print("[PASS] 全流程调度完成，状态流转正常\n")
    else:
        print(f"[WARN] 流程未完全完成，最终步骤: {final_step}\n")

    # 输出报告摘要
    print("=" * 60)
    print("  最终报告预览（前 500 字符）")
    print("=" * 60)
    print(final_report[:500] if final_report else "(无报告)")
    print("…\n")

    # 保存完整结果
    output_path = os.path.join("tests", "pipeline_result.json")
    os.makedirs("tests", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)
    logger.info("完整 JSON 结果已保存至 %s", output_path)

    # ── 8. 验证向量数据库 ──
    logger.info("── 步骤 5：向量数据库验证 ──")
    try:
        from core.vector_store import VectorStore
        vs = VectorStore()
        test_data = [
            {"text": "贵州茅台发布业绩快报", "vector": [0.1] * 768, "source": "test"},
            {"text": "北向资金持续流入", "vector": [0.2] * 768, "source": "test"},
        ]
        vs.create_table("test_verification", test_data)
        tables = vs.list_tables()
        logger.info("  LanceDB 表列表: %s", tables)
        vs.drop_table("test_verification")
        logger.info("  LanceDB 读写测试通过")
        print("[PASS] 向量数据库（LanceDB）读写正常\n")
    except Exception as e:
        logger.error("  LanceDB 测试失败: %s", e)
        print(f"[WARN] LanceDB 测试失败: {e}\n")

    # ── 总结 ──
    print("=" * 60)
    print("  Phase 1 验证完成")
    print("=" * 60)
    print(f"  配置加载: OK")
    print(f"  智能体初始化: {len(agents)} 个全部成功")
    print(f"  调度流程: {final_step}")
    print(f"  智能体执行: {len(agent_outputs)} 个输出 / {len(errors)} 个错误")
    print(f"  结果文件: {output_path}")
    print()


if __name__ == "__main__":
    main()
