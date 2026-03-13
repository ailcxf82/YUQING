# -*- coding: utf-8 -*-
"""三维度交叉验证与信号过滤模块（Signal Validator）

对应 ValueCell 交叉验证引擎：基本面-舆情-资金面三维验证、历史相似事件回测、噪音过滤、信号确定性分级。
数据来源：统一使用 Tushare。
依赖：pip install tushare pandas
输入：阶段1（News Agent）完整输出 + 阶段2（Research Agent）完整输出。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import tushare as ts

from app.config import get_settings

RISK_DISCLAIMER = (
    "本模块输出为三维度信号验证的机器辅助结论，不构成任何投资建议或收益承诺；"
    "历史回测数据仅供参考，过去表现不代表未来收益；"
    "所有信号分级结论均须配合人工判断，最终决策责任由用户自行承担。"
)

# 有效信号的舆情强度阈值
SENTIMENT_BULLISH_MIN = 7.0  # 利好信号最低情绪分
SENTIMENT_BEARISH_MAX = 3.0  # 利空信号最高情绪分
SOURCE_VALID_LEVELS = {"S", "A"}  # 满足信源等级

# 历史回测观察窗口（交易日）
BACKTEST_WINDOWS = [1, 5, 10, 30]
# 每次回测最多取近3年同类事件样本数量上限
BACKTEST_MAX_SAMPLES = 20


def _normalize_ts_code(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if ".SH" in s:
        return f"{s.split('.SH')[0].strip()}.SH"
    if ".SZ" in s:
        return f"{s.split('.SZ')[0].strip()}.SZ"
    code = s[:6] if len(s) >= 6 else s
    if not code:
        return ""
    return f"{code}.SH" if code.startswith("6") else f"{code}.SZ"


def _date_yyyymmdd(s: str) -> str:
    if not s:
        return ""
    return s.replace("-", "").replace("/", "").strip()[:8]


def _yyyymmdd_to_date(s: str) -> datetime:
    s = (s or "").replace("-", "").replace("/", "").strip()
    try:
        return datetime.strptime(s[:8], "%Y%m%d")
    except ValueError:
        return datetime.now()


@dataclass
class SignalValidationResult:
    report_md: str
    result_json: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SignalValidator:
    """三维度交叉验证与信号过滤专家。"""

    def __init__(self) -> None:
        self._pro: Optional[ts.pro_api] = None

    def _get_pro(self) -> ts.pro_api:
        if self._pro is None:
            token = get_settings().tushare_token
            if not token:
                raise EnvironmentError("未配置 TUSHARE_TOKEN，请在环境变量或 .env 中设置。")
            self._pro = ts.pro_api(token)
        return self._pro

    # ------------------------------------------------------------------ #
    #  Step 1: 三维度校验矩阵
    # ------------------------------------------------------------------ #

    def _validate_sentiment_dim(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """维度1：舆情验证。"""
        source_level = (event.get("source_level") or "").strip().upper()
        sentiment = (event.get("sentiment") or "").strip()
        try:
            score = float(event.get("sentiment_score") or 5)
        except (TypeError, ValueError):
            score = 5.0

        source_ok = source_level in SOURCE_VALID_LEVELS
        score_ok = (sentiment == "利好" and score >= SENTIMENT_BULLISH_MIN) or (
            sentiment == "利空" and score <= SENTIMENT_BEARISH_MAX
        )
        has_entity = bool(event.get("entity") or event.get("core_summary"))
        has_time = bool(event.get("occur_time") or event.get("published_at"))

        passed = source_ok and score_ok and has_entity and has_time
        reasons = []
        if not source_ok:
            reasons.append(f"信源等级为 {source_level or '未知'}，要求 S/A 级")
        if not score_ok:
            if sentiment == "中性":
                reasons.append("中性情绪不构成有效方向性信号")
            else:
                reasons.append(f"情绪得分 {score:.1f}，利好需≥{SENTIMENT_BULLISH_MIN}，利空需≤{SENTIMENT_BEARISH_MAX}")
        if not has_entity:
            reasons.append("缺少事件主体或摘要")
        if not has_time:
            reasons.append("缺少明确发生时间")

        return {
            "passed": passed,
            "source_level": source_level,
            "sentiment": sentiment,
            "sentiment_score": score,
            "reason": "通过" if passed else "；".join(reasons),
        }

    def _validate_fundamental_dim(self, event: Dict[str, Any], research: Dict[str, Any]) -> Dict[str, Any]:
        """维度2：基本面验证，从阶段2交叉验证结果中查找匹配项。"""
        ev_id = event.get("event_id", "")
        cat = event.get("event_category", "中性事件")
        cross_list: List[Dict] = research.get("event_cross_validation") or []

        matched = None
        for item in cross_list:
            if item.get("event_id") == ev_id:
                matched = item
                break

        # 中性事件默认基本面影响有限
        if cat in ("中性事件",):
            return {
                "passed": False,
                "reason": "中性事件对基本面无实质影响，不纳入有效信号",
                "impact_level": "无",
                "matched_cross_validation": matched,
            }

        if matched is None:
            return {
                "passed": False,
                "reason": "阶段2未能匹配到该事件的交叉验证结论，基本面影响待确认",
                "impact_level": "待确认",
                "matched_cross_validation": None,
            }

        impact = matched.get("impact_level", "待观察")
        # 有财务数据支撑且事件对基本面有明确描述则通过
        evidence = matched.get("evidence", "")
        has_data = "利润表" in evidence or "日线" in evidence or "财报" in evidence
        impact_unclear = impact in ("待观察",)
        passed = has_data and not impact_unclear
        reason = matched.get("evidence", "") or ("基本面影响暂无实质数据支撑" if not passed else "通过")
        return {
            "passed": passed,
            "reason": reason[:200] if reason else "通过",
            "impact_level": impact,
            "matched_cross_validation": matched,
        }

    def _validate_capital_dim(self, ts_code: str, event: Dict[str, Any]) -> Dict[str, Any]:
        """维度3：资金面验证，基于 Tushare 日线 + 每日指标。
        逻辑：事件发生日前后 3 个交易日，成交量或换手率是否有显著放大（>均值 1.5倍）。
        """
        out: Dict[str, Any] = {
            "passed": False,
            "volume_anomaly": False,
            "turnover_anomaly": False,
            "avg_vol_ratio": None,
            "avg_turnover_ratio": None,
            "data_source": "Tushare-日线",
            "reason": "",
            "error": None,
        }
        # 确定事件时间
        occur_time_raw = event.get("occur_time") or event.get("published_at") or ""
        if not occur_time_raw:
            out["reason"] = "事件无发生时间，无法做资金面验证"
            return out

        try:
            event_date = _yyyymmdd_to_date(occur_time_raw[:10])
            window_start = (event_date - timedelta(days=60)).strftime("%Y%m%d")
            window_end = (event_date + timedelta(days=10)).strftime("%Y%m%d")
            event_str = event_date.strftime("%Y%m%d")
        except Exception as e:
            out["reason"] = f"事件时间解析失败：{e}"
            out["error"] = str(e)
            return out

        try:
            pro = self._get_pro()
            df = pro.daily(ts_code=ts_code, start_date=window_start, end_date=window_end)
            if df is None or df.empty:
                out["reason"] = "未获取到对应时间段日线数据"
                return out

            df = df.sort_values("trade_date")
            # 事件日前 30 个交易日基准
            baseline = df[df["trade_date"] < event_str].tail(30)
            event_window = df[df["trade_date"] >= event_str].head(3)

            if baseline.empty or event_window.empty:
                out["reason"] = "基准期或事件窗口数据不足，无法判断资金面"
                return out

            baseline_vol_mean = float(baseline["vol"].mean())
            event_vol_mean = float(event_window["vol"].mean())
            vol_ratio = event_vol_mean / baseline_vol_mean if baseline_vol_mean > 0 else 0.0
            out["avg_vol_ratio"] = round(vol_ratio, 2)
            volume_anomaly = vol_ratio >= 1.5

            # 换手率可选（daily_basic，积分受限时允许 skip）
            turnover_anomaly = False
            try:
                df_basic = pro.daily_basic(ts_code=ts_code, start_date=window_start, end_date=window_end)
                if df_basic is not None and not df_basic.empty:
                    df_basic = df_basic.sort_values("trade_date")
                    base_turn = df_basic[df_basic["trade_date"] < event_str]["turnover_rate"].tail(30)
                    event_turn = df_basic[df_basic["trade_date"] >= event_str]["turnover_rate"].head(3)
                    if not base_turn.empty and not event_turn.empty:
                        base_mean = float(base_turn.mean())
                        ev_mean = float(event_turn.mean())
                        turn_ratio = ev_mean / base_mean if base_mean > 0 else 0.0
                        out["avg_turnover_ratio"] = round(turn_ratio, 2)
                        turnover_anomaly = turn_ratio >= 1.5
            except Exception:
                pass

            out["volume_anomaly"] = volume_anomaly
            out["turnover_anomaly"] = turnover_anomaly
            out["passed"] = volume_anomaly or turnover_anomaly

            if out["passed"]:
                anomaly_desc = []
                if volume_anomaly:
                    anomaly_desc.append(f"成交量放大约 {vol_ratio:.1f} 倍")
                if turnover_anomaly and out["avg_turnover_ratio"]:
                    anomaly_desc.append(f"换手率放大约 {out['avg_turnover_ratio']:.1f} 倍")
                out["reason"] = "资金面有明显异动：" + "，".join(anomaly_desc)
            else:
                out["reason"] = f"资金面无显著异动（成交量倍数 {vol_ratio:.1f}，阈值 1.5）"

        except Exception as e:
            out["reason"] = f"资金面数据获取失败：{e}"
            out["error"] = str(e)

        return out

    def _build_validation_matrix(
        self,
        ts_code: str,
        events: List[Dict[str, Any]],
        research: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """构建三维校验矩阵，返回每个信号的验证结果。"""
        matrix = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            ev_id = ev.get("event_id", "")
            cat = ev.get("event_category", "")
            summary = (ev.get("core_summary") or "")[:100]

            dim_sentiment = self._validate_sentiment_dim(ev)
            dim_fundamental = self._validate_fundamental_dim(ev, research)
            dim_capital = self._validate_capital_dim(ts_code, ev)

            all_passed = (
                dim_sentiment["passed"]
                and dim_fundamental["passed"]
                and dim_capital["passed"]
            )
            signal_type = "有效信号" if all_passed else "噪音信号"
            filter_reason = None
            if not all_passed:
                parts = []
                if not dim_sentiment["passed"]:
                    parts.append(f"舆情维度未通过（{dim_sentiment['reason']}）")
                if not dim_fundamental["passed"]:
                    parts.append(f"基本面维度未通过（{dim_fundamental['reason'][:60]}）")
                if not dim_capital["passed"]:
                    parts.append(f"资金面维度未通过（{dim_capital['reason']}）")
                filter_reason = "；".join(parts)

            matrix.append({
                "signal_id": ev_id,
                "event_category": cat,
                "event_summary": summary,
                "signal_type": signal_type,
                "filter_reason": filter_reason,
                "dim_sentiment": dim_sentiment,
                "dim_fundamental": dim_fundamental,
                "dim_capital": dim_capital,
            })
        return matrix

    # ------------------------------------------------------------------ #
    #  Step 2: 历史相似事件回测
    # ------------------------------------------------------------------ #

    def _backtest_similar_events(
        self,
        ts_code: str,
        event: Dict[str, Any],
        end_date: str,
    ) -> Dict[str, Any]:
        """历史相似事件回测：在近3年该标的自身行情里，按事件分类找历史相似信号点，统计T+N收益。
        说明：由于无综合事件数据库，以「成交量/换手率高于1.5倍均值的交易日」为历史信号发生日代理，
        统计其后 T+1/5/10/30 日涨跌幅，作为同类资金异动背景下的历史经验参考。
        """
        out: Dict[str, Any] = {
            "method": "Tushare-日线历史成交量异动代理法",
            "method_note": (
                "由于无结构化历史事件库，以近3年该标的成交量放大日（>30日均量1.5倍）为相似信号代理点，"
                "统计其后 T+1/T+5/T+10/T+30 日涨跌幅。此方法为统计参考，非精确事件回测。"
            ),
            "sample_count": 0,
            "backtest": {},
            "win_rate_t5": None,
            "avg_return_t5": None,
            "conclusion": "",
            "error": None,
        }
        try:
            pro = self._get_pro()
            end_d = _date_yyyymmdd(end_date) or datetime.now().strftime("%Y%m%d")
            start_d = (datetime.strptime(end_d[:8], "%Y%m%d") - timedelta(days=3 * 365)).strftime("%Y%m%d")

            df = pro.daily(ts_code=ts_code, start_date=start_d, end_date=end_d)
            if df is None or df.empty or len(df) < 40:
                out["conclusion"] = "历史数据不足，无法进行回测统计"
                return out

            df = df.sort_values("trade_date").reset_index(drop=True)
            df["vol"] = df["vol"].fillna(0).astype(float)
            df["pct_chg"] = df["pct_chg"].fillna(0).astype(float)

            # 找高量日（代理信号日）
            roll_mean = df["vol"].rolling(30, min_periods=10).mean()
            signal_mask = df["vol"] > roll_mean * 1.5
            signal_indices = df.index[signal_mask].tolist()

            samples: List[Dict[str, Any]] = []
            for idx in signal_indices:
                record: Dict[str, Any] = {
                    "signal_date": df.at[idx, "trade_date"],
                }
                for w in BACKTEST_WINDOWS:
                    end_idx = idx + w
                    if end_idx < len(df):
                        cum_pct = float(df["pct_chg"].iloc[idx + 1 : end_idx + 1].sum())
                    else:
                        cum_pct = None
                    record[f"t{w}_pct"] = round(cum_pct, 2) if cum_pct is not None else None
                samples.append(record)

            samples = samples[-BACKTEST_MAX_SAMPLES:]  # 取最近样本
            out["sample_count"] = len(samples)

            if not samples:
                out["conclusion"] = "历史相似信号样本不足"
                return out

            # 统计各窗口
            backtest: Dict[str, Any] = {}
            for w in BACKTEST_WINDOWS:
                key = f"t{w}"
                vals = [s[f"t{w}_pct"] for s in samples if s[f"t{w}_pct"] is not None]
                if not vals:
                    backtest[key] = {"win_rate": None, "avg_return": None, "max_drawdown": None, "count": 0}
                    continue
                win_rate = round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1)
                avg_ret = round(sum(vals) / len(vals), 2)
                max_dd = round(min(vals), 2)
                backtest[key] = {
                    "win_rate": win_rate,
                    "avg_return": avg_ret,
                    "max_drawdown": max_dd,
                    "count": len(vals),
                }

            out["backtest"] = backtest
            # 以 T+5 为主要参考
            t5 = backtest.get("t5", {})
            out["win_rate_t5"] = t5.get("win_rate")
            out["avg_return_t5"] = t5.get("avg_return")

            wr5 = t5.get("win_rate") or 0
            ar5 = t5.get("avg_return") or 0
            if wr5 >= 70:
                hist_grade = "历史胜率较高"
            elif wr5 >= 50:
                hist_grade = "历史胜率中等"
            else:
                hist_grade = "历史胜率偏低"
            out["conclusion"] = (
                f"近3年共找到 {len(samples)} 个类似资金异动样本；"
                f"T+5 {hist_grade}（{wr5}%），平均涨跌幅 {ar5}%。"
                f"注：本回测为成交量异动代理，非精确同类事件匹配，结论仅供参考。"
            )
        except Exception as e:
            out["error"] = str(e)
            out["conclusion"] = f"回测执行出错：{e}"

        return out

    # ------------------------------------------------------------------ #
    #  Step 3: 信号确定性分级
    # ------------------------------------------------------------------ #

    def _grade_signal(
        self,
        validation: Dict[str, Any],
        backtest: Dict[str, Any],
    ) -> Dict[str, Any]:
        """严格三级分级：高/中/低确定性信号。"""
        if validation["signal_type"] == "噪音信号":
            return {
                "grade": "噪音信号",
                "grade_code": 0,
                "reason": validation.get("filter_reason", "三维度验证未通过"),
                "strategy_eligible": False,
            }

        win_rate_t5 = backtest.get("win_rate_t5")
        # 三维均通过
        t5_wr = float(win_rate_t5) if win_rate_t5 is not None else 50.0
        sentiment_score = validation["dim_sentiment"]["sentiment_score"]
        impact = validation["dim_fundamental"].get("impact_level", "待观察")
        has_fundamental = validation["dim_fundamental"]["passed"]
        has_capital = validation["dim_capital"]["passed"]

        impact_horizon = validation.get("dim_fundamental", {}).get(
            "matched_cross_validation", {}
        )
        if isinstance(impact_horizon, dict):
            impact_horizon = impact_horizon.get("impact_horizon", "")
        else:
            impact_horizon = ""
        is_mid_long_term = any(
            kw in (impact_horizon or "")
            for kw in ("中期", "长期", "中长期", "3个月", "1-3个月", "3个月以上")
        )

        if (
            has_fundamental
            and has_capital
            and t5_wr >= 70
            and (sentiment_score >= 8 or sentiment_score <= 2)
            and is_mid_long_term
        ):
            grade = "高确定性信号"
            grade_code = 3
            reason = (
                f"三维度完全匹配；T+5历史胜率 {t5_wr}%≥70%；"
                f"情绪强度 {sentiment_score:.1f}；基本面影响 {impact}；"
                f"影响周期 {impact_horizon or '中长期'}。"
            )
        elif t5_wr >= 50:
            grade = "中确定性信号"
            grade_code = 2
            reason = (
                f"三维度基本匹配；T+5历史胜率 {t5_wr}%（50%~70%）；"
                f"以短期情绪影响为主，基本面影响 {impact}。"
            )
        else:
            grade = "低确定性信号"
            grade_code = 1
            reason = (
                f"三维度存在分歧或历史胜率 {t5_wr}%<50%；"
                "仅纳入风险提示，不用于策略生成核心依据。"
            )

        return {
            "grade": grade,
            "grade_code": grade_code,
            "reason": reason,
            "strategy_eligible": grade_code >= 2,  # 中/高确定性才可进入策略
        }

    # ------------------------------------------------------------------ #
    #  Step 4: 市场定价充分性判断
    # ------------------------------------------------------------------ #

    def _price_adequacy(
        self,
        ts_code: str,
        event: Dict[str, Any],
        hist: Dict[str, Any],
    ) -> Dict[str, Any]:
        """分析事件是否已被市场充分定价。
        逻辑：事件发生后至今，标的累计涨跌幅 vs 历史同类回测平均涨幅。
        """
        out: Dict[str, Any] = {
            "adequacy": "无法判断",
            "current_cumulative_pct": None,
            "event_occur_date": None,
            "reason": "",
        }
        occur_raw = event.get("occur_time") or event.get("published_at") or ""
        if not occur_raw:
            out["reason"] = "事件无发生时间，无法评估定价充分性"
            return out

        try:
            event_date = _yyyymmdd_to_date(occur_raw[:10])
            out["event_occur_date"] = event_date.strftime("%Y-%m-%d")
            event_d = event_date.strftime("%Y%m%d")
            today_d = datetime.now().strftime("%Y%m%d")

            daily = hist.get("daily") or []  # 阶段2已获取的日线
            if not daily:
                out["reason"] = "阶段2行情数据为空，无法计算事件后累计涨跌"
                return out

            # 取事件日之后的 pct_chg 累计
            post_rows = [r for r in daily if str(r.get("trade_date", "")) >= event_d]
            post_rows = sorted(post_rows, key=lambda x: x.get("trade_date", ""))[:30]
            if not post_rows:
                out["reason"] = "事件后无可用行情数据（可能为未来事件）"
                return out

            cum_pct = sum(float(r.get("pct_chg") or 0) for r in post_rows)
            out["current_cumulative_pct"] = round(cum_pct, 2)

            # 与情绪方向做对照
            sentiment = event.get("sentiment", "中性")
            if sentiment == "利好":
                if cum_pct >= 10:
                    out["adequacy"] = "可能已充分定价（追高风险）"
                    out["reason"] = f"事件后累计涨幅 {cum_pct:.1f}%，利好可能已兑现，追高风险较高。"
                elif cum_pct <= 0:
                    out["adequacy"] = "存在预期差（未被充分定价）"
                    out["reason"] = f"事件后累计涨幅 {cum_pct:.1f}%，利好尚未被市场充分定价，存在潜在超额空间。"
                else:
                    out["adequacy"] = "定价部分充分（中性）"
                    out["reason"] = f"事件后累计涨幅 {cum_pct:.1f}%，定价部分反映，仍有一定空间但需关注后续催化剂。"
            elif sentiment == "利空":
                if cum_pct <= -10:
                    out["adequacy"] = "可能已充分定价（反弹风险）"
                    out["reason"] = f"事件后累计跌幅 {abs(cum_pct):.1f}%，利空可能已充分释放，需警惕技术性反弹。"
                elif cum_pct >= 0:
                    out["adequacy"] = "存在预期差（利空未被充分定价）"
                    out["reason"] = f"事件后累计涨幅 {cum_pct:.1f}%，市场尚未反映利空，存在下行风险。"
                else:
                    out["adequacy"] = "定价部分充分（中性）"
                    out["reason"] = f"事件后累计跌幅 {abs(cum_pct):.1f}%，利空已部分定价。"
            else:
                out["adequacy"] = "中性事件，定价影响有限"
                out["reason"] = f"事件后累计涨跌幅 {cum_pct:.1f}%，中性事件对定价影响有限。"

        except Exception as e:
            out["reason"] = f"定价充分性计算出错：{e}"

        return out

    # ------------------------------------------------------------------ #
    #  主入口
    # ------------------------------------------------------------------ #

    def validate(
        self,
        symbol: str,
        name: str,
        news_result: Dict[str, Any],
        research_result: Dict[str, Any],
    ) -> SignalValidationResult:
        """三维度交叉验证主入口。"""
        if not symbol or not name:
            raise ValueError("需要提供标的代码和名称。")
        if not news_result or not research_result:
            raise ValueError("需要同时提供阶段1（news_result）和阶段2（research_result）的完整输出。")

        ts_code = _normalize_ts_code(symbol)
        if not ts_code:
            raise ValueError("无法解析标的代码，请使用 600000.SH / 000001.SZ 等格式。")

        # 取事件列表（阶段1 result.events）与时间范围
        events: List[Dict] = news_result.get("events") or []
        inputs_n: Dict = news_result.get("inputs") or {}
        inputs_r: Dict = research_result.get("inputs") or {}
        end_date: str = inputs_n.get("time_window", {}).get("end") or inputs_r.get("time_window", {}).get("end") or ""
        hist: Dict = (research_result.get("core_data") or {}).get("market_hist") or {}

        # 三维校验矩阵
        matrix = self._build_validation_matrix(ts_code, events, research_result)

        valid_signals = [m for m in matrix if m["signal_type"] == "有效信号"]
        noise_signals = [m for m in matrix if m["signal_type"] == "噪音信号"]

        # 回测 + 分级 + 定价充分性（仅对有效信号）
        graded_signals: List[Dict[str, Any]] = []
        noise_list: List[Dict[str, Any]] = []

        for m in matrix:
            ev = next((e for e in events if e.get("event_id") == m["signal_id"]), {})
            if m["signal_type"] == "有效信号":
                backtest = self._backtest_similar_events(ts_code, ev, end_date)
                grade = self._grade_signal(m, backtest)
                pricing = self._price_adequacy(ts_code, ev, hist)
                graded_signals.append({
                    **m,
                    "backtest": backtest,
                    "grade": grade,
                    "pricing_adequacy": pricing,
                })
            else:
                noise_list.append(m)

        # 高确定性信号摘要
        high_grade = [g for g in graded_signals if g["grade"]["grade_code"] == 3]
        mid_grade = [g for g in graded_signals if g["grade"]["grade_code"] == 2]
        low_grade = [g for g in graded_signals if g["grade"]["grade_code"] == 1]

        run_ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        result_json: Dict[str, Any] = {
            "meta": {
                "module_name": "signal_validator",
                "version": "0.1.0",
                "run_timestamp": run_ts,
                "data_sources": ["tushare"],
            },
            "inputs": {
                "symbol": symbol,
                "name": name,
                "total_events": len(events),
            },
            "summary": {
                "valid_signal_count": len(valid_signals),
                "noise_signal_count": len(noise_signals),
                "high_grade_count": len(high_grade),
                "mid_grade_count": len(mid_grade),
                "low_grade_count": len(low_grade),
            },
            "validation_matrix": matrix,
            "graded_signals": graded_signals,
            "noise_signals": noise_list,
            "constraints_and_risks": {
                "not_investment_advice": True,
                "capital_guarantee": False,
                "disclaimers": [RISK_DISCLAIMER],
            },
        }

        report_md = self._build_markdown_report(
            symbol=symbol,
            name=name,
            matrix=matrix,
            graded_signals=graded_signals,
            noise_list=noise_list,
            high_grade=high_grade,
            mid_grade=mid_grade,
            low_grade=low_grade,
        )
        return SignalValidationResult(report_md=report_md, result_json=result_json)

    # ------------------------------------------------------------------ #
    #  报告生成
    # ------------------------------------------------------------------ #

    def _build_markdown_report(
        self,
        symbol: str,
        name: str,
        matrix: List[Dict[str, Any]],
        graded_signals: List[Dict[str, Any]],
        noise_list: List[Dict[str, Any]],
        high_grade: List[Dict[str, Any]],
        mid_grade: List[Dict[str, Any]],
        low_grade: List[Dict[str, Any]],
    ) -> str:
        lines: List[str] = []

        # 一、总览
        valid_cnt = len(graded_signals)
        noise_cnt = len(noise_list)
        high_cnt = len(high_grade)
        lines.append("## 一、交叉验证总览")
        lines.append("")
        lines.append(f"- **标的**：{name}（{symbol}）")
        lines.append(
            f"- **信号概况**：共处理 {valid_cnt + noise_cnt} 个舆情事件，"
            f"有效信号 **{valid_cnt}** 个，噪音信号 **{noise_cnt}** 个。"
        )
        if high_grade:
            top = high_grade[0]
            lines.append(
                f"- **核心高确定性信号**：事件 {top['signal_id']}（{top['event_summary'][:40]}…）"
                f"三维完全匹配，{top['grade']['reason'][:80]}"
            )
        else:
            lines.append("- **高确定性信号**：当前无，请关注中确定性信号或等待更多数据支撑。")

        # 定价充分性一句话
        pricing_parts = [
            g["pricing_adequacy"]["adequacy"]
            for g in graded_signals
            if g.get("pricing_adequacy", {}).get("adequacy") not in ("无法判断", None)
        ]
        if pricing_parts:
            lines.append(f"- **定价充分性判断**：有效信号中，{' / '.join(set(pricing_parts))}。")
        lines.append("")
        lines.append(f"**风险提示**：{RISK_DISCLAIMER}")
        lines.append("")

        # 二、三维校验矩阵
        lines.append("## 二、三维校验矩阵")
        lines.append("")
        lines.append("| 信号ID | 事件摘要 | 舆情维度 | 基本面维度 | 资金面维度 | 信号类型 |")
        lines.append("|--------|----------|----------|------------|------------|----------|")
        for m in matrix:
            s_id = m["signal_id"]
            summary = (m["event_summary"] or "")[:30].replace("|", " ")
            s_dim = "✅通过" if m["dim_sentiment"]["passed"] else f"❌{m['dim_sentiment']['reason'][:20]}"
            f_dim = "✅通过" if m["dim_fundamental"]["passed"] else f"❌{(m['dim_fundamental']['reason'] or '')[:20]}"
            c_dim = "✅通过" if m["dim_capital"]["passed"] else f"❌{(m['dim_capital']['reason'] or '')[:20]}"
            sig_type = m["signal_type"]
            lines.append(f"| {s_id} | {summary} | {s_dim} | {f_dim} | {c_dim} | **{sig_type}** |")
        if noise_list:
            lines.append("")
            lines.append("**噪音信号过滤原因：**")
            for n in noise_list:
                lines.append(f"- {n['signal_id']}：{(n.get('filter_reason') or '')[:120]}")
        lines.append("")

        # 三、历史相似事件回测报告
        lines.append("## 三、历史相似事件回测报告")
        lines.append("")
        if not graded_signals:
            lines.append("> 无有效信号，跳过历史回测。")
        else:
            for g in graded_signals:
                bt = g.get("backtest") or {}
                lines.append(f"### 信号 {g['signal_id']}（{(g['event_summary'] or '')[:40]}）")
                lines.append(f"- **方法**：{bt.get('method', '')}")
                lines.append(f"- **说明**：{bt.get('method_note', '')}")
                lines.append(f"- **样本量**：{bt.get('sample_count', 0)} 个历史相似点")
                btr = bt.get("backtest") or {}
                if btr:
                    lines.append("  | 窗口 | 胜率(%) | 平均涨跌幅(%) | 最大回撤(%) | 样本数 |")
                    lines.append("  |------|---------|--------------|-------------|--------|")
                    for wk in [f"t{w}" for w in BACKTEST_WINDOWS]:
                        b = btr.get(wk, {})
                        wr = b.get("win_rate", "-")
                        ar = b.get("avg_return", "-")
                        dd = b.get("max_drawdown", "-")
                        cnt = b.get("count", 0)
                        lines.append(f"  | {wk.upper()} | {wr} | {ar} | {dd} | {cnt} |")
                lines.append(f"- **回测结论**：{bt.get('conclusion', '')}")
                if bt.get("error"):
                    lines.append(f"- **异常**：{bt['error']}")
                lines.append("")

        # 四、信号分级清单
        lines.append("## 四、信号分级清单")
        lines.append("")
        for grade_label, grade_list in [
            ("🔴 高确定性信号（可用于策略生成）", high_grade),
            ("🟡 中确定性信号（短期参考，需结合人工判断）", mid_grade),
            ("⚪ 低确定性信号（仅做风险提示，不用于策略）", low_grade),
        ]:
            lines.append(f"### {grade_label}")
            if not grade_list:
                lines.append("- 暂无")
            else:
                for g in grade_list:
                    pa = g.get("pricing_adequacy") or {}
                    lines.append(
                        f"- **{g['signal_id']}**：{(g['event_summary'] or '')[:50]}"
                        f"  \n  分级理由：{g['grade']['reason'][:120]}"
                        f"  \n  定价充分性：{pa.get('adequacy', '-')}（{pa.get('reason', '')[:80]}）"
                    )
            lines.append("")

        # 五、JSON 说明
        lines.append("## 五、机器可读 JSON 说明")
        lines.append("")
        lines.append(
            "完整 JSON 通过接口返回值中的 `result` 字段获取，含 "
            "`meta`、`inputs`、`summary`、`validation_matrix`、"
            "`graded_signals`、`noise_signals`、`constraints_and_risks`。"
        )
        return "\n".join(lines)
