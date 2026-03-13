# -*- coding: utf-8 -*-
"""多维度金融数据查询与基本面分析模块（Research Agent）

对应 ValueCell 的 Research Agent：标的基本面解析、行业产业链分析、估值测算、数据交叉验证。
数据来源：统一使用 Tushare。依赖：pip install tushare pandas
输入：阶段1结构化舆情事件清单、目标标的代码+名称、分析时间范围。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List

import tushare as ts

from app.config import get_settings

RISK_DISCLAIMER = (
    "本模块输出仅基于公开金融数据与阶段1舆情事件的交叉验证，不构成任何投资建议或收益承诺；"
    "证券投资存在风险，估值测算依赖假设，请独立判断并自行承担决策责任。"
)


def _normalize_ts_code(symbol: str) -> str:
    """将 600000.SH / 600000 / 000001.SZ 转为 Tushare 标准 ts_code。"""
    s = (symbol or "").strip().upper()
    if ".SH" in s:
        code = s.split(".SH")[0].strip()
        return f"{code}.SH"
    if ".SZ" in s:
        code = s.split(".SZ")[0].strip()
        return f"{code}.SZ"
    code = s[:6] if len(s) >= 6 else s
    if not code:
        return ""
    return f"{code}.SH" if code.startswith("6") else f"{code}.SZ"


def _date_yyyymmdd(s: str) -> str:
    """转为 YYYYMMDD。"""
    if not s:
        return ""
    return s.replace("-", "").replace("/", "").strip()[:8]


@dataclass
class ResearchAnalysisResult:
    report_md: str
    result_json: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResearchAgent:
    """上市公司基本面与行业研究专家（Research Agent），数据统一来自 Tushare。"""

    def __init__(self) -> None:
        self._pro: ts.pro_api = None

    def _get_pro(self) -> ts.pro_api:
        if self._pro is None:
            token = get_settings().tushare_token
            if not token:
                raise EnvironmentError("未配置 TUSHARE_TOKEN，请在环境变量或 .env 中设置。")
            self._pro = ts.pro_api(token)
        return self._pro

    def _fetch_financial_tushare(self, ts_code: str) -> Dict[str, Any]:
        """Tushare 利润表、资产负债表、现金流量表，近若干期。"""
        out: Dict[str, Any] = {
            "source": "Tushare-财务报表",
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "profit": [],
            "balance": [],
            "cashflow": [],
            "error": None,
        }
        try:
            pro = self._get_pro()
            end_d = _date_yyyymmdd(datetime.now().strftime("%Y-%m-%d")) or "20301231"
            start_d = "20180101"  # 近多年
            for api_name, key in [
                ("income", "profit"),
                ("balancesheet", "balance"),
                ("cashflow", "cashflow"),
            ]:
                api = getattr(pro, api_name, None)
                if api is None:
                    continue
                try:
                    df = api(ts_code=ts_code, start_date=start_d, end_date=end_d)
                    if df is not None and not df.empty:
                        df = df.head(20)
                        for c in df.columns:
                            df[c] = df[c].astype(str)
                        out[key] = df.to_dict(orient="records")
                except Exception:
                    pass
        except Exception as e:
            out["error"] = str(e)
        return out

    def _fetch_hist_tushare(self, ts_code: str, start: str, end: str) -> Dict[str, Any]:
        """Tushare 日线行情，计算 1月/3月/1年涨跌幅。"""
        out: Dict[str, Any] = {
            "source": "Tushare-日线行情",
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "daily": [],
            "current_price": None,
            "pct_1m": None,
            "pct_3m": None,
            "pct_1y": None,
            "error": None,
        }
        try:
            pro = self._get_pro()
            start_d = _date_yyyymmdd(start) or "20200101"
            end_d = _date_yyyymmdd(end) or "20301231"
            df = pro.daily(ts_code=ts_code, start_date=start_d, end_date=end_d)
            if df is not None and not df.empty:
                df = df.sort_values("trade_date", ascending=False).reset_index(drop=True)
                out["daily"] = df.head(252).to_dict(orient="records")
                if "close" in df.columns and len(df) > 0:
                    out["current_price"] = float(df.iloc[0]["close"])
                if "pct_chg" in df.columns and len(df) >= 1:
                    pct = df["pct_chg"].fillna(0)
                    out["pct_1m"] = round(float(pct.head(22).sum()), 2) if len(df) >= 22 else None
                    out["pct_3m"] = round(float(pct.head(66).sum()), 2) if len(df) >= 66 else None
                    out["pct_1y"] = round(float(pct.head(252).sum()), 2) if len(df) >= 252 else None
        except Exception as e:
            out["error"] = str(e)
        return out

    def _fetch_individual_tushare(self, ts_code: str, end_date: str) -> Dict[str, Any]:
        """Tushare 每日指标（PE/PB/市值）+ 股票基本信息（行业）。"""
        out: Dict[str, Any] = {
            "source": "Tushare-每日指标与股票列表",
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "total_mv": None,
            "circ_mv": None,
            "industry": None,
            "pe": None,
            "pb": None,
            "raw": {},
            "error": None,
        }
        try:
            pro = self._get_pro()
            end_d = _date_yyyymmdd(end_date) or _date_yyyymmdd(datetime.now().strftime("%Y-%m-%d"))
            # 每日指标：取最近一条
            try:
                df_basic = pro.daily_basic(ts_code=ts_code, start_date=end_d, end_date=end_d)
                if df_basic is None or df_basic.empty:
                    df_basic = pro.daily_basic(ts_code=ts_code, start_date="20200101", end_date=end_d)
                if df_basic is not None and not df_basic.empty:
                    df_basic = df_basic.sort_values("trade_date", ascending=False).head(1)
                    row = df_basic.iloc[0]
                    out["pe"] = float(row["pe"]) if row.get("pe") is not None and str(row["pe"]) != "nan" else None
                    out["pb"] = float(row["pb"]) if row.get("pb") is not None and str(row["pb"]) != "nan" else None
                    if row.get("total_mv") is not None:
                        out["total_mv"] = f"{float(row['total_mv']):.0f}万元"
                    if row.get("circ_mv") is not None:
                        out["circ_mv"] = f"{float(row['circ_mv']):.0f}万元"
                    out["raw"]["daily_basic"] = row.to_dict()
            except Exception:
                pass
            # 股票列表：行业、名称
            try:
                df_stock = pro.stock_basic(ts_code=ts_code, list_status="L", fields="ts_code,name,industry")
                if df_stock is not None and not df_stock.empty:
                    row = df_stock.iloc[0]
                    out["industry"] = row.get("industry")
                    out["raw"]["stock_basic"] = row.to_dict()
            except Exception:
                try:
                    df_stock = pro.stock_basic(list_status="L", fields="ts_code,name,industry")
                    if df_stock is not None and not df_stock.empty:
                        sub = df_stock[df_stock["ts_code"] == ts_code]
                        if not sub.empty:
                            out["industry"] = sub.iloc[0].get("industry")
                except Exception:
                    pass
        except Exception as e:
            out["error"] = str(e)
        return out

    def _build_valuation(self, individual: Dict[str, Any], hist: Dict[str, Any]) -> Dict[str, Any]:
        """简单估值：PE/PB 来自 Tushare 每日指标。"""
        v: Dict[str, Any] = {
            "methods_used": ["PE", "PB"],
            "current_pe": individual.get("pe"),
            "current_pb": individual.get("pb"),
            "current_price": hist.get("current_price"),
            "conclusion": "合理估值",
            "assumptions": [
                "PE/PB 来自 Tushare 每日指标，未做行业可比调整。",
                "结论为基于当前数据的相对判断，非目标价预测。",
            ],
            "risk_note": "估值受盈利波动与市场情绪影响，请勿作为唯一决策依据。",
        }
        pe = individual.get("pe")
        if pe is not None:
            try:
                pe_f = float(pe)
                if pe_f > 30:
                    v["conclusion"] = "偏高估值"
                elif 0 < pe_f < 15:
                    v["conclusion"] = "偏低估值"
            except (TypeError, ValueError):
                pass
        return v

    def _cross_validate_events(
        self,
        events: List[Dict[str, Any]],
        financial: Dict[str, Any],
        hist: Dict[str, Any],
        individual: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """舆情事件与基本面交叉验证。"""
        validated = []
        for ev in events:
            if not isinstance(ev, dict):
                validated.append({
                    "event_id": "",
                    "impact_level": "未验证",
                    "logic_changed": None,
                    "priced_in": None,
                    "evidence": "事件格式异常，无法交叉验证。",
                })
                continue
            ev_id = ev.get("event_id", "")
            cat = ev.get("event_category", "")
            evidence_parts = []
            impact = "待观察"
            logic_changed = None
            priced_in = None
            if "业绩" in cat or "财报" in str(cat):
                if financial.get("profit"):
                    evidence_parts.append("已获取 Tushare 利润表数据，可对照业绩变动验证。")
                    impact = "需结合财报明细判断"
                else:
                    evidence_parts.append("当前未获取到利润表数据，无法验证业绩影响。")
            if "市场" in cat or "龙虎榜" in str(cat) or "北向" in str(cat):
                if hist.get("daily"):
                    evidence_parts.append("已有 Tushare 日线数据，可观察事件前后涨跌幅与成交量是否异动。")
                    priced_in = "需对比事件时点与涨跌时点判断"
                else:
                    evidence_parts.append("当前未获取到足够行情数据。")
            if not evidence_parts:
                evidence_parts.append("该事件类型暂无自动匹配的财务/行情指标，建议人工结合公告与研报判断。")
            validated.append({
                "event_id": ev_id,
                "event_category": cat,
                "impact_level": impact,
                "logic_changed": logic_changed,
                "priced_in": priced_in,
                "evidence": " ".join(evidence_parts),
            })
        return validated

    def analyze(
        self,
        symbol: str,
        name: str,
        start_date: str,
        end_date: str,
        events: List[Dict[str, Any]],
    ) -> ResearchAnalysisResult:
        if not symbol or not name:
            raise ValueError("需要提供标的代码和名称。")
        if not start_date or not end_date:
            raise ValueError("需要提供分析时间范围（start_date, end_date）。")
        if not isinstance(events, list):
            raise ValueError("events 必须为列表（阶段1的结构化事件清单）。")

        ts_code = _normalize_ts_code(symbol)
        if not ts_code:
            raise ValueError("无法解析标的代码，请使用 600000.SH / 000001.SZ 等格式。")

        financial = self._fetch_financial_tushare(ts_code)
        hist = self._fetch_hist_tushare(ts_code, start_date, end_date)
        individual = self._fetch_individual_tushare(ts_code, end_date)
        valuation = self._build_valuation(individual, hist)
        cross_validation = self._cross_validate_events(events, financial, hist, individual)

        run_ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        result_json: Dict[str, Any] = {
            "meta": {
                "module_name": "research_agent",
                "version": "0.1.0",
                "run_timestamp": run_ts,
                "data_sources": ["tushare"],
            },
            "inputs": {
                "symbol": symbol,
                "name": name,
                "time_window": {"start": start_date, "end": end_date},
                "events_count": len(events),
            },
            "core_data": {
                "financial": financial,
                "market_hist": hist,
                "individual_info": individual,
            },
            "valuation": valuation,
            "event_cross_validation": cross_validation,
            "constraints_and_risks": {
                "not_investment_advice": True,
                "capital_guarantee": False,
                "disclaimers": [RISK_DISCLAIMER],
            },
        }

        report_md = self._build_markdown_report(
            symbol=symbol,
            name=name,
            start_date=start_date,
            end_date=end_date,
            financial=financial,
            hist=hist,
            individual=individual,
            valuation=valuation,
            cross_validation=cross_validation,
        )
        return ResearchAnalysisResult(report_md=report_md, result_json=result_json)

    def _build_markdown_report(
        self,
        symbol: str,
        name: str,
        start_date: str,
        end_date: str,
        financial: Dict[str, Any],
        hist: Dict[str, Any],
        individual: Dict[str, Any],
        valuation: Dict[str, Any],
        cross_validation: List[Dict[str, Any]],
    ) -> str:
        lines: List[str] = []
        lines.append("## 一、基本面分析总览")
        lines.append("")
        lines.append(f"- **标的**：{name}（{symbol}）")
        lines.append(f"- **分析区间**：{start_date} ~ {end_date}")
        price = hist.get("current_price")
        if price is not None:
            lines.append(f"- **最新价**：{price}")
        mv = individual.get("total_mv")
        if mv:
            lines.append(f"- **总市值**：{mv}")
        concl = valuation.get("conclusion", "合理估值")
        lines.append(f"- **估值合理性判断**：{concl}（详见第四部分）")
        lines.append("")
        lines.append(f"**风险提示**：{RISK_DISCLAIMER}")
        lines.append("")
        lines.append("**数据来源**：本报告财务、行情、市值与估值数据均来自 Tushare，统一可溯源。")
        lines.append("")

        lines.append("## 二、核心财务与行情数据表")
        lines.append("")
        lines.append("### 2.1 数据来源与更新时间")
        lines.append(f"- 财务：{financial.get('source', '')}，更新于 {financial.get('updated_at', '')}")
        lines.append(f"- 行情：{hist.get('source', '')}，更新于 {hist.get('updated_at', '')}")
        lines.append(f"- 个股/指标：{individual.get('source', '')}，更新于 {individual.get('updated_at', '')}")
        if financial.get("error"):
            lines.append(f"- 财务获取异常：{financial['error']}")
        if hist.get("error"):
            lines.append(f"- 行情获取异常：{hist['error']}")
        if individual.get("error"):
            lines.append(f"- 个股信息异常：{individual['error']}")
        lines.append("")
        lines.append("### 2.2 关键指标")
        lines.append("| 指标 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 当前股价 | {hist.get('current_price') or '-'} |")
        lines.append(f"| 总市值 | {individual.get('total_mv') or '-'} |")
        lines.append(f"| 流通市值 | {individual.get('circ_mv') or '-'} |")
        lines.append(f"| 近1月涨跌幅(%) | {hist.get('pct_1m') or '-'} |")
        lines.append(f"| 近3月涨跌幅(%) | {hist.get('pct_3m') or '-'} |")
        lines.append(f"| 近1年涨跌幅(%) | {hist.get('pct_1y') or '-'} |")
        lines.append(f"| 市盈率(PE) | {individual.get('pe') or '-'} |")
        lines.append(f"| 市净率(PB) | {individual.get('pb') or '-'} |")
        lines.append(f"| 所属行业 | {individual.get('industry') or '-'} |")
        lines.append("")

        lines.append("## 三、舆情-基本面交叉验证报告")
        lines.append("")
        if not cross_validation:
            lines.append("> 无阶段1事件输入，未做交叉验证。")
        else:
            lines.append("| 事件ID | 事件分类 | 影响程度 | 逻辑是否变化 | 是否已被定价 | 依据摘要 |")
            lines.append("|--------|----------|----------|--------------|--------------|----------|")
            for cv in cross_validation:
                ev_id = cv.get("event_id", "")
                cat = cv.get("event_category", "")
                impact = cv.get("impact_level", "")
                logic = cv.get("logic_changed") or "-"
                priced = cv.get("priced_in") or "-"
                evidence = (cv.get("evidence") or "")[:80].replace("|", " ")
                lines.append(f"| {ev_id} | {cat} | {impact} | {logic} | {priced} | {evidence} |")
        lines.append("")

        lines.append("## 四、行业与估值分析结论")
        lines.append("")
        lines.append(f"- **估值结论**：{valuation.get('conclusion', '合理估值')}")
        lines.append("- **所用方法**：" + ", ".join(valuation.get("methods_used", [])))
        lines.append("- **核心假设**：")
        for a in valuation.get("assumptions", []):
            lines.append(f"  - {a}")
        lines.append(f"- **风险提示**：{valuation.get('risk_note', '')}")
        lines.append("")
        lines.append("## 五、机器可读 JSON 说明")
        lines.append("")
        lines.append("完整 JSON 通过接口返回值中的 `result` 字段获取，含 `meta`、`inputs`、`core_data`、`valuation`、`event_cross_validation`、`constraints_and_risks`。")
        return "\n".join(lines)
