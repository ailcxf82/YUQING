# -*- coding: utf-8 -*-
"""舆情-基本面影响链路推演模块 (3.3)

三层分析能力：
  1. 事件影响逻辑拆解（维度/周期/量级）
  2. 产业链传导分析（上下游受益/受损）
  3. 历史同类事件回测对比
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger("impact_analyzer")


class ImpactAnalyzer:
    """舆情影响链路推演引擎"""

    IMPACT_SYSTEM_PROMPT = (
        "你是机构级投研分析师。请对给定的舆情事件进行深度影响链路拆解。\n\n"
        "## 分析框架\n"
        "1. 核心影响维度：营收/利润/毛利率/市场份额/行业壁垒/政策环境/估值中枢\n"
        "2. 影响周期：短期(1-7天)/中期(1-3个月)/长期(3个月以上)\n"
        "3. 影响量级：对业绩的影响区间测算、对估值的影响逻辑\n"
        "4. 影响传导路径：从事件到各影响维度的逻辑链条\n\n"
        "## 输出格式（严格JSON）\n"
        "{\n"
        '  "event_summary": "事件一句话总结",\n'
        '  "impact_dimensions": [\n'
        '    {"dimension": "影响维度", "direction": "正向/负向/不确定",\n'
        '     "magnitude": "重大/中等/轻微", "logic": "影响逻辑一句话"}\n'
        "  ],\n"
        '  "impact_timeline": {\n'
        '    "short_term": {"description": "1-7天影响", "probability": 0.0-1.0},\n'
        '    "mid_term": {"description": "1-3月影响", "probability": 0.0-1.0},\n'
        '    "long_term": {"description": "3月以上影响", "probability": 0.0-1.0}\n'
        "  },\n"
        '  "earnings_impact": {\n'
        '    "revenue_impact_pct": "预计营收影响百分比区间(如 +2%~+5%)",\n'
        '    "profit_impact_pct": "预计利润影响百分比区间",\n'
        '    "assumptions": "核心假设"\n'
        "  },\n"
        '  "valuation_impact": "对估值中枢的影响逻辑",\n'
        '  "transmission_chain": ["节点1→节点2→...→最终影响"],\n'
        '  "key_risks": ["风险点1", "风险点2"],\n'
        '  "key_opportunities": ["机会点1"]\n'
        "}\n"
        "仅输出JSON。"
    )

    CHAIN_SYSTEM_PROMPT = (
        "你是产业链分析专家。请分析给定事件对产业链上下游的传导影响。\n\n"
        "## 输出格式（严格JSON）\n"
        "{\n"
        '  "event": "事件概述",\n'
        '  "primary_target": "直接影响标的",\n'
        '  "upstream_impact": [\n'
        '    {"company_or_sector": "上游企业/行业", "impact": "正向/负向",\n'
        '     "logic": "传导逻辑", "magnitude": "重大/中等/轻微"}\n'
        "  ],\n"
        '  "downstream_impact": [\n'
        '    {"company_or_sector": "下游企业/行业", "impact": "正向/负向",\n'
        '     "logic": "传导逻辑", "magnitude": "重大/中等/轻微"}\n'
        "  ],\n"
        '  "cross_sector_risk": [\n'
        '    {"sector": "跨行业", "risk_type": "传导风险类型", "description": "描述"}\n'
        "  ],\n"
        '  "beneficiaries": ["受益标的1(代码+名称)", "受益标的2"],\n'
        '  "losers": ["受损标的1(代码+名称)", "受损标的2"]\n'
        "}\n"
        "仅输出JSON。"
    )

    BACKTEST_SYSTEM_PROMPT = (
        "你是金融历史事件分析专家。请根据给定的当前事件类型，"
        "回忆 A 股市场历史上类似事件的影响模式。\n\n"
        "## 输出格式（严格JSON）\n"
        "{\n"
        '  "current_event": "当前事件概述",\n'
        '  "similar_events": [\n'
        '    {"date": "历史事件日期(年月)", "description": "事件描述",\n'
        '     "price_impact": "事后股价走势(如: 5日涨幅+8%)",\n'
        '     "duration": "影响持续时间", "fund_flow": "资金流向变化"}\n'
        "  ],\n"
        '  "pattern_summary": "历史规律总结",\n'
        '  "reference_range": {\n'
        '    "price_impact_min": "最小影响幅度",\n'
        '    "price_impact_max": "最大影响幅度",\n'
        '    "typical_duration": "典型持续时间"\n'
        "  },\n"
        '  "current_differences": ["与历史的不同点1", "不同点2"],\n'
        '  "confidence": 0.0-1.0\n'
        "}\n"
        "仅输出JSON。重要：如无法回忆起类似事件，说明原因并将 confidence 设为 0.3 以下。"
    )

    def __init__(self, llm_client: Any, tushare_pro: Optional[Any] = None) -> None:
        self.llm = llm_client
        self._pro = tushare_pro

    def analyze_impact_chain(
        self,
        event_summary: str,
        event_category: str,
        company_name: str,
        financials: Dict[str, Any],
    ) -> Dict[str, Any]:
        """事件影响逻辑拆解"""
        prompt = (
            f"公司：{company_name}\n"
            f"事件类别：{event_category}\n"
            f"事件摘要：{event_summary}\n"
            f"基本面数据：PE={financials.get('pe','N/A')}, "
            f"PB={financials.get('pb','N/A')}, "
            f"总市值={financials.get('total_mv','N/A')}万元"
        )
        try:
            return self.llm.chat_json(
                system_prompt=self.IMPACT_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.2,
            )
        except Exception as e:
            logger.warning("影响链路分析失败: %s", e)
            return self._fallback_impact(event_summary, event_category)

    def analyze_industry_chain(
        self,
        event_summary: str,
        company_name: str,
        industry: str = "",
    ) -> Dict[str, Any]:
        """产业链传导分析"""
        prompt = (
            f"事件：{event_summary}\n"
            f"直接涉及公司：{company_name}\n"
            f"所属行业：{industry or '未知'}"
        )
        try:
            return self.llm.chat_json(
                system_prompt=self.CHAIN_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.2,
            )
        except Exception as e:
            logger.warning("产业链分析失败: %s", e)
            return {
                "event": event_summary,
                "primary_target": company_name,
                "upstream_impact": [],
                "downstream_impact": [],
                "cross_sector_risk": [],
                "beneficiaries": [],
                "losers": [],
            }

    def historical_backtest(
        self,
        event_summary: str,
        event_category: str,
        sub_label: str,
        company_name: str,
        ts_code: str = "",
    ) -> Dict[str, Any]:
        """历史同类事件回测对比"""
        prompt = (
            f"当前事件：{event_summary}\n"
            f"事件类别：{event_category}/{sub_label}\n"
            f"涉及标的：{company_name}({ts_code})"
        )

        price_data = {}
        if ts_code and self._pro:
            price_data = self._fetch_price_around_event(ts_code)

        if price_data:
            prompt += (
                f"\n当前市场数据：最新价={price_data.get('close','N/A')}, "
                f"近5日涨跌幅={price_data.get('pct_5d','N/A')}%"
            )

        try:
            result = self.llm.chat_json(
                system_prompt=self.BACKTEST_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.3,
            )
            result["market_context"] = price_data
            return result
        except Exception as e:
            logger.warning("历史回测失败: %s", e)
            return {
                "current_event": event_summary,
                "similar_events": [],
                "pattern_summary": "无法获取历史对比数据",
                "reference_range": {},
                "current_differences": [],
                "confidence": 0.1,
                "market_context": price_data,
            }

    BATCH_IMPACT_SYSTEM_PROMPT = (
        "你是机构级投研分析师。请对以下多个舆情事件进行综合影响分析。\n\n"
        "## 分析框架\n"
        "1. 对每个关键事件进行影响维度拆解（营收/利润/估值等）\n"
        "2. 影响周期判断（短期/中期/长期）\n"
        "3. 综合所有事件的叠加效应\n"
        "4. 历史同类事件参考\n\n"
        "## 输出格式（严格JSON）\n"
        "{\n"
        '  "event_impacts": [\n'
        '    {"event_id": "N1", "summary": "事件概述", '
        '"direction": "正向/负向/不确定", "magnitude": "重大/中等/轻微",\n'
        '     "dimensions": ["影响维度1", "影响维度2"],\n'
        '     "timeline": "短期/中期/长期", "logic": "影响逻辑"}\n'
        "  ],\n"
        '  "combined_assessment": {\n'
        '    "overall_direction": "正向/负向/中性/混合",\n'
        '    "confidence": 0.0-1.0,\n'
        '    "short_term": {"description": "1-7天综合影响", "probability": 0.0-1.0},\n'
        '    "mid_term": {"description": "1-3月综合影响", "probability": 0.0-1.0},\n'
        '    "long_term": {"description": "3月+综合影响", "probability": 0.0-1.0}\n'
        "  },\n"
        '  "earnings_impact": {\n'
        '    "revenue_impact_pct": "综合营收影响估计",\n'
        '    "profit_impact_pct": "综合利润影响估计"\n'
        "  },\n"
        '  "key_risks": ["风险1", "风险2"],\n'
        '  "key_opportunities": ["机会1"],\n'
        '  "historical_reference": "历史同类事件参考总结"\n'
        "}\n"
        "仅输出JSON。"
    )

    def analyze_impact_batch(
        self,
        events: List[Dict[str, Any]],
        company_name: str,
        financials: Dict[str, Any],
        ts_code: str = "",
    ) -> Dict[str, Any]:
        """综合批量影响分析：将所有关键事件合并为单次 LLM 调用"""
        lines = []
        for ev in events:
            nid = ev.get("news_id", ev.get("event_id", ""))
            summary = ev.get("core_summary", ev.get("summary", ""))[:200]
            cat = ev.get("event_category", "")
            polarity = ev.get("polarity", "")
            lines.append(f"[{nid}] 类别:{cat} 情绪:{polarity} | {summary}")

        prompt = (
            f"公司：{company_name} ({ts_code})\n"
            f"基本面：PE={financials.get('pe','N/A')}, "
            f"PB={financials.get('pb','N/A')}, "
            f"总市值={financials.get('total_mv','N/A')}万元\n\n"
            f"以下为{len(events)}个关键舆情事件：\n"
            + "\n".join(lines)
        )

        try:
            result = self.llm.chat_json(
                system_prompt=self.BATCH_IMPACT_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.2,
            )
            return result
        except Exception as e:
            logger.warning("批量影响分析失败: %s", e)
            return {
                "event_impacts": [],
                "combined_assessment": {
                    "overall_direction": "不确定",
                    "confidence": 0.2,
                    "short_term": {"description": "分析失败", "probability": 0.5},
                    "mid_term": {"description": "分析失败", "probability": 0.3},
                    "long_term": {"description": "分析失败", "probability": 0.2},
                },
                "earnings_impact": {},
                "key_risks": ["LLM分析不可用"],
                "key_opportunities": [],
                "historical_reference": "",
            }

    def full_analysis(
        self,
        events: List[Dict[str, Any]],
        company_name: str,
        ts_code: str,
        industry: str,
        financials: Dict[str, Any],
    ) -> Dict[str, Any]:
        """完整深度分析——合并全部事件为单次综合分析"""
        batch_result = self.analyze_impact_batch(
            events[:10], company_name, financials, ts_code
        )

        industry_analysis = None
        if events:
            primary = events[0]
            industry_analysis = self.analyze_industry_chain(
                primary.get("core_summary", ""),
                company_name, industry,
            )

        return {
            "batch_impact": batch_result,
            "industry_analysis": industry_analysis or {},
            "analysis_count": len(events[:10]),
        }

    def _fetch_price_around_event(self, ts_code: str) -> Dict[str, Any]:
        """拉取标的近期价格数据用于回测对比"""
        try:
            df = self._pro.daily(
                ts_code=ts_code,
                fields="trade_date,open,high,low,close,pct_chg,vol",
            )
            if df is None or df.empty:
                return {}
            df = df.sort_values("trade_date", ascending=False).head(20)
            latest = df.iloc[0]
            pct_5d = round(df.head(5)["pct_chg"].sum(), 2) if len(df) >= 5 else 0
            return {
                "close": float(latest["close"]),
                "trade_date": str(latest["trade_date"]),
                "pct_chg": float(latest["pct_chg"]),
                "pct_5d": pct_5d,
                "vol": float(latest["vol"]),
            }
        except Exception as e:
            logger.warning("价格数据获取失败: %s", e)
            return {}

    @staticmethod
    def _fallback_impact(event_summary: str, category: str) -> Dict[str, Any]:
        """LLM 不可用时的兜底影响分析"""
        direction = "正向" if "正向" in category or "利好" in category else \
                    "负向" if "负向" in category or "利空" in category else "不确定"
        return {
            "event_summary": event_summary,
            "impact_dimensions": [{
                "dimension": "综合评估",
                "direction": direction,
                "magnitude": "待评估",
                "logic": "LLM 分析不可用，需人工评估",
            }],
            "impact_timeline": {
                "short_term": {"description": "待评估", "probability": 0.5},
                "mid_term": {"description": "待评估", "probability": 0.3},
                "long_term": {"description": "待评估", "probability": 0.2},
            },
            "earnings_impact": {
                "revenue_impact_pct": "待评估",
                "profit_impact_pct": "待评估",
                "assumptions": "LLM 不可用，仅基于事件类别粗判",
            },
            "valuation_impact": "待评估",
            "transmission_chain": [],
            "key_risks": ["分析能力降级"],
            "key_opportunities": [],
        }
