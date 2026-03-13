# -*- coding: utf-8 -*-
"""舆情信息炼化与结构化解析模块（News Agent）

依赖：
    pip install httpx

配置：
    通过 Settings.llm_provider 选择 LLM 提供商（deepseek/zhipu/openai）
    各提供商的 API Key 和模型通过环境变量配置
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings, LLMProvider


RISK_DISCLAIMER = (
    "本模块输出仅基于用户提供的舆情文本及公开信息，由大模型进行结构化提取和归纳，"
    "不构成任何投资建议或收益承诺；证券等投资产品存在较大风险，可能导致本金亏损，"
    "请务必根据自身风险承受能力独立作出决策并自行承担全部后果。"
)


@dataclass
class NewsItem:
    """单条舆情输入结构。"""

    id: str
    source_name: str
    published_at: str
    text: str
    url: Optional[str] = None


@dataclass
class NewsAnalysisResult:
    report_md: str
    result_json: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LLMJsonClient:
    """面向 JSON 输出的 LLM 客户端封装，支持多提供商。"""

    def __init__(self) -> None:
        settings = get_settings()
        llm_config = settings.get_llm_config()
        self.provider = llm_config.provider
        self.api_key = llm_config.api_key
        self.model = llm_config.model
        self.api_url = llm_config.api_url
        self.timeout = llm_config.timeout

    def chat_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """调用 LLM 并从返回内容中解析 JSON。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
        }

        try:
            with httpx.Client(timeout=float(self.timeout)) as client:
                resp = client.post(self.api_url, headers=headers, json=data)
            resp.raise_for_status()
            js = resp.json()
            content = (
                js.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"调用 LLM API 失败: {exc}") from exc

        try:
            first = content.find("{")
            last = content.rfind("}")
            if first == -1 or last == -1:
                raise ValueError("未找到 JSON 对象")
            json_str = content[first : last + 1]
            result = json.loads(json_str)
            if not isinstance(result, dict):
                raise ValueError(f"LLM 返回的 JSON 根节点不是对象，而是 {type(result).__name__}")
            return result
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"解析 LLM 返回 JSON 失败: {exc}; 片段: {content[:200]}"
            ) from exc


DeepseekJsonClient = LLMJsonClient


class NewsSentimentAgent:
    """舆情信息炼化与结构化解析 Agent。"""

    def __init__(self, llm_client: Optional[LLMJsonClient] = None) -> None:
        self.llm = llm_client or LLMJsonClient()

    @staticmethod
    def _build_system_prompt() -> str:
        return textwrap.dedent(
            """
            你是一名严格合规的金融舆情结构化解析专家（News Agent）。
            必须遵守以下规则：
            1. 不做任何收益承诺或具体买卖建议，只做舆情本身的结构化提取与情绪评估。
            2. 不能自创新的分类或标签，只能在指定的有限选项中选择。
            3. 所有结论必须能在原文片段中找到依据，禁止凭空想象。
            4. 对 D 级信源的内容，必须标记为「高风险噪音」，不纳入核心结论，只做风险提示。

            【信源等级定义（source_level）】
            - S级：交易所官方公告、证监会/监管机构官方文件、上市公司官方发布的财报/公告
            - A级：权威财经媒体（财新、路透、彭博、第一财经等）、持牌机构发布的正式研报
            - B级：行业垂直媒体、知名财经KOL/博主公开发布的深度内容
            - C级：社交媒体、论坛、股吧等UGC内容
            - D级：无明确信源的传闻、小道消息

            【事件分类（event_category & event_subtype）】
            只能在以下大类中选择一种：
            - 「基本面事件」：业绩预告/财报发布、并购重组、股权变动、产能扩张/收缩、技术突破、核心产品变动
            - 「政策事件」：行业监管政策、产业扶持/限制政策、财税政策、货币政策变动
            - 「风险事件」：监管处罚、诉讼仲裁、负面丑闻、业绩暴雷、退市风险、供应链断裂
            - 「市场事件」：大股东增减持、机构调研、龙虎榜异动、北向资金异动、分红送转
            - 「中性事件」：常规经营动态、无实质影响的信息

            event_category 必须是上面的大类之一，
            event_subtype 可以从括号内的小类中选择最接近的一种，如无合适，可使用「其他」。

            【情绪与影响量化要求】
            - sentiment（情绪方向）：仅能为「利好」「利空」「中性」
            - sentiment_score（情绪强度）：0-10 之间的数字，0 极度利空，10 极度利好，5 完全中性
            - impact_scope（影响层级）：仅能为「大盘级」「行业级」「公司级」
            - impact_horizon（影响周期）：仅能为
              「短期（1-5个交易日）」「中期（1-3个月）」「长期（3个月以上）」
            - sentiment_rationale：说明打分依据，必须引用原文要点。

            【舆情传导路径】
            - propagation_path.current_stage：仅可为「起点」「发酵期」「高潮期」「拐点」之一
            - propagation_path.catalysts：可能强化或推动舆情发展的因素
            - propagation_path.decay_factors：可能削弱或终止舆情影响的因素

            【需要返回的 JSON 顶层字段】
            - events: 事件数组，每个事件结构见后续要求
            - aggregated_view: 汇总视角，包含 overall_sentiment, overall_sentiment_score,
              high_value_signals, high_risk_noise_event_ids, watchlist_event_ids

            请严格返回 UTF-8 JSON，不能包含解释性文字，只返回一个 JSON 对象。
            """
        ).strip()

    @staticmethod
    def _build_user_prompt(
        symbol: str,
        name: str,
        news_items: List[NewsItem],
        start_date: str,
        end_date: str,
    ) -> str:
        items_repr: List[Dict[str, Any]] = []
        for item in news_items:
            text_short = item.text or ""
            if len(text_short) > 2000:
                text_short = text_short[:2000] + " ……【截断】"
            items_repr.append(
                {
                    "id": item.id,
                    "source_name": item.source_name,
                    "published_at": item.published_at,
                    "url": item.url,
                    "text": text_short,
                }
            )

        user_instruction = {
            "task_description": "请基于以下舆情，对指定证券进行事件抽取、情绪与影响量化，并输出结构化 JSON。",
            "target": {"symbol": symbol, "name": name},
            "time_window": {"start": start_date, "end": end_date},
            "news_items": items_repr,
        }
        return json.dumps(user_instruction, ensure_ascii=False)

    def analyze(
        self,
        symbol: str,
        name: str,
        news_items: List[NewsItem],
        start_date: str,
        end_date: str,
    ) -> NewsAnalysisResult:
        if not symbol or not name:
            raise ValueError("需要提供标的代码和名称。")
        if not news_items:
            raise ValueError("需要提供至少一条舆情文本。")
        if not start_date or not end_date:
            raise ValueError("需要提供舆情发布时间范围（start_date, end_date）。")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(symbol, name, news_items, start_date, end_date)

        llm_output = self.llm.chat_json(system_prompt, user_prompt)
        if not isinstance(llm_output, dict):
            raise RuntimeError(f"LLM 返回结果类型错误，期望字典，实际为 {type(llm_output).__name__}")
        events = llm_output.get("events", [])
        aggregated_view = llm_output.get("aggregated_view", {})
        if not isinstance(events, list):
            raise RuntimeError("模型返回的 events 字段格式错误，期望为列表。")

        from datetime import datetime, timezone

        run_ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

        result_json: Dict[str, Any] = {
            "meta": {
                "module_name": "news_sentiment_agent",
                "version": "0.1.0",
                "run_timestamp": run_ts,
                "data_sources": ["user_provided_news_texts"],
            },
            "inputs": {
                "symbol": symbol,
                "name": name,
                "time_window": {"start": start_date, "end": end_date},
                "news_items": [asdict(n) for n in news_items],
            },
            "events": events,
            "aggregated_view": aggregated_view,
            "constraints_and_risks": {
                "not_investment_advice": True,
                "capital_guarantee": False,
                "disclaimers": [RISK_DISCLAIMER],
            },
        }

        report_md = self._build_markdown_report(result_json)
        return NewsAnalysisResult(report_md=report_md, result_json=result_json)

    @staticmethod
    def _build_markdown_report(result_json: Dict[str, Any]) -> str:
        symbol = result_json["inputs"]["symbol"]
        name = result_json["inputs"]["name"]
        tw = result_json["inputs"]["time_window"]
        events = result_json.get("events", [])
        if not isinstance(events, list):
            events = []
        agg = result_json.get("aggregated_view", {})
        if not isinstance(agg, dict):
            agg = {}

        overall_sentiment = agg.get("overall_sentiment", "中性/未知")
        overall_score = agg.get("overall_sentiment_score")
        high_value_signals = agg.get("high_value_signals") or []
        high_risk_noise_ids = agg.get("high_risk_noise_event_ids") or []
        watchlist_event_ids = agg.get("watchlist_event_ids") or []

        lines: List[str] = []
        lines.append("## 一、舆情分析总览")
        lines.append("")
        lines.append(f"- **标的**：{name}（{symbol}）")
        lines.append(f"- **分析区间**：{tw['start']} ~ {tw['end']}")
        if overall_score is not None:
            lines.append(f"- **整体情绪**：{overall_sentiment}（情绪得分约 {overall_score} / 10）")
        else:
            lines.append(f"- **整体情绪**：{overall_sentiment}")
        lines.append("")
        lines.append(f"**风险提示（重要）**：{RISK_DISCLAIMER}")
        lines.append("")

        lines.append("## 二、结构化事件清单")
        lines.append("")
        if not events:
            lines.append("> 当前样本内未识别出明确结构化事件。")
        else:
            header = (
                "| 事件ID | 事件分类 | 核心摘要 | 信源等级 | 情绪方向 | 情绪强度(0-10) | 影响层级 | 影响周期 | 原文溯源 |"
            )
            sep = "|--------|----------|----------|----------|----------|----------------|----------|----------|----------|"
            lines.append(header)
            lines.append(sep)
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                ev_id = ev.get("event_id", "")
                cat = ev.get("event_category", "")
                summary = (ev.get("core_summary", "") or "").replace("|", " ")
                src_level = ev.get("source_level", "")
                sent = ev.get("sentiment", "")
                score = ev.get("sentiment_score", "")
                scope = ev.get("impact_scope", "")
                horizon = ev.get("impact_horizon", "")
                src_name = ev.get("source_name", "")
                snippets = ev.get("evidence_snippets") or []
                src_snippet = ""
                if snippets:
                    first_snip = snippets[0]
                    src_snippet = first_snip[:50].replace("|", " ")
                    if len(first_snip) > 50:
                        src_snippet += "…"
                ref_text = f"{src_name}: {src_snippet}"
                row = (
                    f"| {ev_id} | {cat} | {summary} | {src_level} | {sent} | "
                    f"{score} | {scope} | {horizon} | {ref_text} |"
                )
                lines.append(row)
        lines.append("")

        lines.append("## 三、舆情风险与机会提示")
        lines.append("")
        lines.append("### 1. 高价值信号")
        if not high_value_signals:
            lines.append("- 当前未识别出高置信度的高价值舆情信号。")
        else:
            for sig in high_value_signals:
                if not isinstance(sig, dict):
                    continue
                ev_id = sig.get("event_id", "")
                reason = sig.get("reason", "")
                lines.append(f"- **事件 {ev_id}**：{reason}")
        lines.append("")

        lines.append("### 2. 高风险噪音（D级传闻等）")
        if not high_risk_noise_ids:
            lines.append("- 当前未识别出明显的高风险噪音事件。")
        else:
            for ev_id in high_risk_noise_ids:
                lines.append(
                    f"- **事件 {ev_id}**：该事件主要来自 D 级或低可信度信源，只作为潜在风险提示，不应作为核心决策依据。"
                )
        lines.append("")

        lines.append("### 3. 需要重点关注的后续节点")
        if not watchlist_event_ids:
            lines.append("- 暂未识别出需要重点跟踪的关键舆情事件节点。")
        else:
            for ev_id in watchlist_event_ids:
                lines.append(
                    f"- **事件 {ev_id}**：建议持续跟踪后续公告、财报或权威媒体报道，看是否出现新信息对该事件产生实质性验证或修正。"
                )
        lines.append("")

        lines.append("## 四、机器可读 JSON 结果说明")
        lines.append("")
        lines.append(
            "本报告对应的完整机器可读 JSON 结构可通过接口返回值中的 `result` 字段获取，"
            "字段包括 `meta`、`inputs`、`events`、`aggregated_view`、`constraints_and_risks` 等。"
        )

        return "\n".join(lines)
