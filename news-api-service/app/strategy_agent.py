# -*- coding: utf-8 -*-
"""交易策略生成与参数精细化模块（Strategy Agent）

对应 ValueCell 的 Strategy Agent：基于有效信号生成结构化交易策略、
仓位管理、止盈止损、入场出场条件、极端行情应对方案、盈亏比测算。
数据来源：统一使用 Tushare。
依赖：pip install tushare pandas
输入：阶段3 的有效信号分级清单 + 标的信息 + 用户风险偏好 + 投资周期 + 仓位上限。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import tushare as ts

from app.config import get_settings

RISK_DISCLAIMER = (
    "本模块输出为基于量化信号的策略建议，不构成任何投资建议或收益承诺；"
    "策略参数基于历史数据与模型假设，不保证未来表现；"
    "所有策略须配合人工判断，最终决策责任由用户自行承担。"
)

# ------------------------------------------------------------------ #
#  风险偏好 → 仓位 / 止损 参数映射
# ------------------------------------------------------------------ #

RISK_PROFILES = {
    "保守": {
        "total_position_pct": 30,
        "first_build_ratio": 0.50,
        "add_ratios": [0.30, 0.20],
        "stop_loss_pct": 3.0,
        "max_drawdown_pct": 5.0,
        "take_profit_tiers": [5, 8, 12],
        "tp_reduce_ratios": [0.40, 0.30, 0.30],
    },
    "稳健": {
        "total_position_pct": 50,
        "first_build_ratio": 0.50,
        "add_ratios": [0.30, 0.20],
        "stop_loss_pct": 5.0,
        "max_drawdown_pct": 8.0,
        "take_profit_tiers": [8, 15, 25],
        "tp_reduce_ratios": [0.30, 0.40, 0.30],
    },
    "进取": {
        "total_position_pct": 80,
        "first_build_ratio": 0.50,
        "add_ratios": [0.30, 0.20],
        "stop_loss_pct": 8.0,
        "max_drawdown_pct": 12.0,
        "take_profit_tiers": [10, 20, 35],
        "tp_reduce_ratios": [0.25, 0.35, 0.40],
    },
}

HORIZON_MAP = {
    "短线": {"hold_days": (1, 10), "label": "1-10个交易日", "ma_ref": 5},
    "中线": {"hold_days": (10, 60), "label": "10-60个交易日", "ma_ref": 20},
    "长线": {"hold_days": (60, 250), "label": "60-250个交易日", "ma_ref": 60},
}


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


@dataclass
class StrategyResult:
    report_md: str
    result_json: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StrategyAgent:
    """量化交易策略设计专家。"""

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
    #  市场数据获取
    # ------------------------------------------------------------------ #

    def _fetch_price_context(self, ts_code: str) -> Dict[str, Any]:
        """获取最近60个交易日行情，用于计算关键价位。"""
        out: Dict[str, Any] = {
            "current_close": None,
            "prev_close": None,
            "ma5": None,
            "ma10": None,
            "ma20": None,
            "ma60": None,
            "recent_high_20d": None,
            "recent_low_20d": None,
            "recent_high_60d": None,
            "recent_low_60d": None,
            "avg_vol_20d": None,
            "atr_20d": None,
            "error": None,
        }
        try:
            pro = self._get_pro()
            end_d = datetime.now().strftime("%Y%m%d")
            start_d = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
            df = pro.daily(ts_code=ts_code, start_date=start_d, end_date=end_d)
            if df is None or df.empty:
                out["error"] = "无法获取行情数据"
                return out

            df = df.sort_values("trade_date").reset_index(drop=True)
            close = df["close"].astype(float)
            high = df["high"].astype(float)
            low = df["low"].astype(float)
            vol = df["vol"].astype(float)

            out["current_close"] = round(float(close.iloc[-1]), 2)
            if len(close) >= 2:
                out["prev_close"] = round(float(close.iloc[-2]), 2)
            if len(close) >= 5:
                out["ma5"] = round(float(close.tail(5).mean()), 2)
            if len(close) >= 10:
                out["ma10"] = round(float(close.tail(10).mean()), 2)
            if len(close) >= 20:
                out["ma20"] = round(float(close.tail(20).mean()), 2)
                out["recent_high_20d"] = round(float(high.tail(20).max()), 2)
                out["recent_low_20d"] = round(float(low.tail(20).min()), 2)
                out["avg_vol_20d"] = round(float(vol.tail(20).mean()), 2)
                tr_series = high.tail(21) - low.tail(21)
                out["atr_20d"] = round(float(tr_series.tail(20).mean()), 2)
            if len(close) >= 60:
                out["ma60"] = round(float(close.tail(60).mean()), 2)
                out["recent_high_60d"] = round(float(high.tail(60).max()), 2)
                out["recent_low_60d"] = round(float(low.tail(60).min()), 2)

        except Exception as e:
            out["error"] = str(e)
        return out

    # ------------------------------------------------------------------ #
    #  Step 1: 策略核心逻辑锚定
    # ------------------------------------------------------------------ #

    def _anchor_strategy(
        self,
        signal: Dict[str, Any],
        horizon: str,
    ) -> Dict[str, Any]:
        """根据信号属性锚定策略类型与核心逻辑。"""
        grade_code = signal.get("grade", {}).get("grade_code", 0)
        sentiment = signal.get("dim_sentiment", {}).get("sentiment", "中性")
        impact_level = signal.get("dim_fundamental", {}).get("impact_level", "待观察")
        pricing = signal.get("pricing_adequacy", {})
        adequacy = pricing.get("adequacy", "")

        if sentiment == "利空":
            strategy_type = "风险规避"
            direction = "做空" if horizon != "长线" else "观望"
            core_logic = (
                f"利空信号确认，基本面影响级别「{impact_level}」，"
                f"定价状态「{adequacy}」。策略以风险规避为核心，"
                "优先减仓/对冲，控制下行风险。"
            )
            revenue_source = "空头头寸收益或对冲保护避免损失"
            core_risk = "利空信号被市场消化后的空头回补风险"
        elif grade_code >= 3:
            strategy_type = "基本面价值"
            direction = "做多"
            core_logic = (
                f"高确定性信号，基本面影响级别「{impact_level}」，"
                f"定价状态「{adequacy}」。策略锚定基本面价值，"
                "匹配中长线投资周期，以基本面改善为核心收益来源。"
            )
            revenue_source = "基本面改善驱动的估值修复与盈利增长"
            core_risk = "基本面预期落空或宏观环境恶化导致估值回调"
        else:
            strategy_type = "事件驱动"
            direction = "做多"
            core_logic = (
                f"中确定性信号，以事件情绪催化为主要驱动，"
                f"定价状态「{adequacy}」。策略锚定事件驱动，"
                "匹配短线投资周期，快进快出捕捉情绪溢价。"
            )
            revenue_source = "事件催化驱动的短期情绪溢价"
            core_risk = "事件情绪消退后的回调风险，以及事件解读偏差"

        if "已充分定价" in adequacy and direction == "做多":
            direction = "观望"
            core_logic += "但当前市场定价可能已充分反映，建议观望等待回调后再入场。"
            core_risk += "；追高入场的高位套牢风险"

        return {
            "strategy_type": strategy_type,
            "direction": direction,
            "core_logic": core_logic,
            "revenue_source": revenue_source,
            "core_risk": core_risk,
            "signal_id": signal.get("signal_id", ""),
            "grade": signal.get("grade", {}).get("grade", ""),
            "grade_code": grade_code,
            "sentiment": sentiment,
        }

    # ------------------------------------------------------------------ #
    #  Step 2: 策略核心参数精细化
    # ------------------------------------------------------------------ #

    def _build_position_plan(
        self,
        risk_pref: str,
        max_pos_pct: float,
        strategy_type: str,
        direction: str,
    ) -> Dict[str, Any]:
        """仓位管理方案。"""
        profile = RISK_PROFILES.get(risk_pref, RISK_PROFILES["稳健"])
        raw_total = profile["total_position_pct"]
        total = min(raw_total, max_pos_pct)
        first_pct = round(total * profile["first_build_ratio"], 1)
        add_pcts = [round(total * r, 1) for r in profile["add_ratios"]]

        if direction == "观望":
            return {
                "total_position_pct": 0,
                "first_build_pct": 0,
                "add_positions": [],
                "note": "当前建议观望，不建仓。等待入场条件满足后按以下方案执行。",
                "standby_plan": {
                    "total_position_pct": total,
                    "first_build_pct": first_pct,
                    "add_positions": [
                        {"seq": i + 1, "pct": p, "condition": f"第{i + 1}次加仓"}
                        for i, p in enumerate(add_pcts)
                    ],
                },
            }

        if strategy_type == "风险规避":
            return {
                "total_position_pct": total,
                "first_build_pct": first_pct,
                "add_positions": [],
                "note": f"风险规避策略：首次减仓 {first_pct}%，"
                        f"后续根据利空兑现程度逐步减仓至清仓。",
            }

        add_conditions = []
        if strategy_type == "基本面价值":
            add_conditions = [
                "股价回调至MA20附近且成交量缩至20日均量0.7倍以下",
                "核心催化剂落地（如财报超预期、政策落地）确认基本面改善",
            ]
        else:
            add_conditions = [
                "事件发酵期股价回调3%以内企稳且量能配合",
                "后续关联事件正面验证（如监管批复、业绩预告）",
            ]

        return {
            "total_position_pct": total,
            "first_build_pct": first_pct,
            "add_positions": [
                {"seq": i + 1, "pct": p, "condition": c}
                for i, (p, c) in enumerate(zip(add_pcts, add_conditions))
            ],
            "note": f"单票仓位上限 {max_pos_pct}%，总仓位严格不超过 {total}%。",
        }

    def _build_entry_conditions(
        self,
        price: Dict[str, Any],
        anchor: Dict[str, Any],
        horizon: str,
    ) -> Dict[str, Any]:
        """入场条件：具体价格点位 + 触发条件 + 时间窗口。"""
        cur = price.get("current_close") or 0
        if cur <= 0:
            return {"error": "无法获取当前价格，入场条件待补充"}

        direction = anchor["direction"]
        strategy_type = anchor["strategy_type"]
        h_cfg = HORIZON_MAP.get(horizon, HORIZON_MAP["中线"])

        if direction == "观望":
            ma_ref = price.get(f"ma{h_cfg['ma_ref']}") or cur
            entry_price = round(min(cur * 0.95, ma_ref), 2)
            return {
                "direction": "观望",
                "entry_trigger": f"股价回落至 {entry_price} 元以下（当前价 {cur} 元的约5%折价或MA{h_cfg['ma_ref']}线附近），同时成交量放大至20日均量1.2倍以上",
                "entry_price_range": {"low": round(entry_price * 0.98, 2), "high": entry_price},
                "time_window": f"策略有效期内，自发布起 {h_cfg['hold_days'][1]} 个交易日内",
                "confirmation_signal": "价格触及入场区间后需连续2根K线站稳，确认支撑有效",
            }

        if strategy_type == "风险规避":
            exit_price = round(cur * 1.02, 2)
            return {
                "direction": "做空/减仓",
                "entry_trigger": f"利空确认后立即执行首次减仓，当前价 {cur} 元",
                "entry_price_range": {"low": cur, "high": exit_price},
                "time_window": "利空确认后1-3个交易日内完成首次减仓",
                "confirmation_signal": "利空消息被主流媒体二次确认，或股价跌破MA5线",
            }

        low_20 = price.get("recent_low_20d") or cur
        ma_ref_val = price.get(f"ma{h_cfg['ma_ref']}") or cur

        if strategy_type == "基本面价值":
            support = round(max(low_20, ma_ref_val * 0.98), 2)
            entry_low = round(support * 0.99, 2)
            entry_high = round(min(support * 1.02, cur), 2)
            return {
                "direction": "做多",
                "entry_trigger": (
                    f"股价回调至 {entry_low}-{entry_high} 元区间（20日低点 {low_20} 与 "
                    f"MA{h_cfg['ma_ref']} 线 {ma_ref_val} 附近），"
                    f"且日成交量不低于20日均量0.8倍"
                ),
                "entry_price_range": {"low": entry_low, "high": entry_high},
                "time_window": f"自发布起 {h_cfg['hold_days'][0]}-{h_cfg['hold_days'][1]} 个交易日内",
                "confirmation_signal": (
                    f"股价在 {entry_low} 元附近企稳，"
                    "连续2个交易日收盘价站稳入场区间上沿，且MACD日线未出现死叉"
                ),
            }
        else:
            entry_high = round(cur * 1.01, 2)
            entry_low = round(cur * 0.98, 2)
            return {
                "direction": "做多",
                "entry_trigger": (
                    f"事件发酵窗口期内，股价在 {entry_low}-{entry_high} 元区间（当前价 {cur} 元附近），"
                    f"日成交量放大至20日均量1.3倍以上"
                ),
                "entry_price_range": {"low": entry_low, "high": entry_high},
                "time_window": "事件公布后1-5个交易日内为最佳入场窗口",
                "confirmation_signal": "事件后首个放量阳线出现，且收盘价站上MA5线",
            }

    def _build_take_profit(
        self,
        entry_price: float,
        risk_pref: str,
        strategy_type: str,
    ) -> List[Dict[str, Any]]:
        """分档位止盈方案。"""
        if entry_price <= 0:
            return []
        profile = RISK_PROFILES.get(risk_pref, RISK_PROFILES["稳健"])
        tiers_pct = profile["take_profit_tiers"]
        reduce_ratios = profile["tp_reduce_ratios"]

        result = []
        for i, (tp_pct, reduce) in enumerate(zip(tiers_pct, reduce_ratios)):
            tp_price = round(entry_price * (1 + tp_pct / 100), 2)
            if strategy_type == "风险规避":
                tp_price = round(entry_price * (1 - tp_pct / 100), 2)

            tier_label = ["一档", "二档", "三档"][i] if i < 3 else f"{i + 1}档"
            if strategy_type == "基本面价值":
                trigger = (
                    f"股价达到 {tp_price} 元（入场价+{tp_pct}%），"
                    f"减仓 {int(reduce * 100)}% 持仓"
                )
            elif strategy_type == "风险规避":
                trigger = (
                    f"股价跌至 {tp_price} 元（入场价-{tp_pct}%），"
                    f"空头减仓 {int(reduce * 100)}% 持仓"
                )
            else:
                trigger = (
                    f"股价达到 {tp_price} 元（入场价+{tp_pct}%），"
                    f"减仓 {int(reduce * 100)}% 持仓"
                )

            result.append({
                "tier": tier_label,
                "target_price": tp_price,
                "target_pct": tp_pct,
                "reduce_ratio": reduce,
                "reduce_pct": int(reduce * 100),
                "trigger_condition": trigger,
            })
        return result

    def _build_stop_loss(
        self,
        entry_price: float,
        risk_pref: str,
        strategy_type: str,
        price: Dict[str, Any],
    ) -> Dict[str, Any]:
        """止损方案。"""
        if entry_price <= 0:
            return {"error": "入场价格无效"}
        profile = RISK_PROFILES.get(risk_pref, RISK_PROFILES["稳健"])
        sl_pct = profile["stop_loss_pct"]
        max_dd = profile["max_drawdown_pct"]

        if strategy_type == "风险规避":
            sl_price = round(entry_price * (1 + sl_pct / 100), 2)
            return {
                "stop_loss_price": sl_price,
                "stop_loss_pct": sl_pct,
                "max_drawdown_pct": max_dd,
                "trigger_condition": (
                    f"空头止损：股价反弹至 {sl_price} 元（入场价+{sl_pct}%）立即平仓止损"
                ),
                "execution": "触发止损价后下一个交易日开盘前15分钟集合竞价挂单平仓",
                "note": f"最大承受回撤 {max_dd}%，超过此限强制全部平仓。",
            }

        sl_price = round(entry_price * (1 - sl_pct / 100), 2)
        low_20 = price.get("recent_low_20d") or sl_price
        hard_stop = round(min(sl_price, low_20 * 0.98), 2)

        return {
            "stop_loss_price": sl_price,
            "hard_stop_price": hard_stop,
            "stop_loss_pct": sl_pct,
            "max_drawdown_pct": max_dd,
            "trigger_condition": (
                f"股价跌破 {sl_price} 元（入场价-{sl_pct}%）触发止损；"
                f"若跌破 {hard_stop} 元（20日低点下方2%硬止损）无条件清仓"
            ),
            "execution": "触发止损价后下一个交易日开盘前15分钟集合竞价挂单卖出",
            "note": (
                f"单笔最大损失控制在 {sl_pct}%，"
                f"组合最大回撤不超过 {max_dd}%。"
                "若遇一字跌停无法卖出，在可交易首日立即执行。"
            ),
        }

    def _build_validity(
        self,
        strategy_type: str,
        horizon: str,
    ) -> Dict[str, Any]:
        """策略有效期与失效条件。"""
        h_cfg = HORIZON_MAP.get(horizon, HORIZON_MAP["中线"])
        hold_min, hold_max = h_cfg["hold_days"]

        invalidation_conditions = [
            f"持仓超过 {hold_max} 个交易日未触发止盈或止损",
            "标的出现重大负面事件导致投资逻辑根本改变",
            "大盘系统性风险升级（如连续3日跌幅超5%）",
        ]

        if strategy_type == "事件驱动":
            invalidation_conditions.append("事件热度消退（舆情提及量降至事件日的20%以下）")
        elif strategy_type == "基本面价值":
            invalidation_conditions.append("最新财报数据显著低于预期，基本面逻辑被证伪")

        return {
            "hold_period": h_cfg["label"],
            "hold_days_range": {"min": hold_min, "max": hold_max},
            "exit_deadline": f"最迟在第 {hold_max} 个交易日收盘前全部清仓",
            "invalidation_conditions": invalidation_conditions,
        }

    # ------------------------------------------------------------------ #
    #  Step 3: 极端行情应对方案
    # ------------------------------------------------------------------ #

    def _build_contingency_plans(
        self,
        entry_price: float,
        direction: str,
        strategy_type: str,
    ) -> List[Dict[str, Any]]:
        """极端行情应对方案。"""
        if entry_price <= 0:
            return []

        plans = []

        plans.append({
            "scenario": "黑天鹅事件（突发系统性利空）",
            "trigger": "持仓标的当日跌幅超7%或大盘单日跌幅超3%",
            "action": "立即减仓50%，剩余持仓设置紧急止损（入场价-3%）",
            "execution": "触发后第一时间市价卖出，不等反弹",
            "priority": "最高",
        })

        plans.append({
            "scenario": "大盘连续暴跌（系统性风险）",
            "trigger": "沪指连续3个交易日累计跌幅超5%",
            "action": "全部持仓降至半仓以下，暂停所有新建仓操作",
            "execution": "在第3个跌停日收盘前完成减仓",
            "priority": "最高",
        })

        plans.append({
            "scenario": "舆情反转（利好变利空/利空变利好）",
            "trigger": "S/A级信源发布与原信号方向相反的重大消息",
            "action": (
                "立即暂停加仓计划，评估反转信息可信度；"
                "若确认反转，72小时内清仓并重新评估"
            ),
            "execution": "发现反转信息后立即启动人工复核，确认后执行清仓",
            "priority": "高",
        })

        if direction == "做多":
            plans.append({
                "scenario": "一字跌停（无法卖出）",
                "trigger": "持仓标的出现一字跌停",
                "action": (
                    "在跌停价挂卖单排队；"
                    "同时评估是否有对冲工具（如对应ETF期权）可用；"
                    "若连续2日跌停仍无法卖出，在可交易首日开盘即卖出"
                ),
                "execution": "跌停日立即挂卖单，次日集合竞价继续挂卖",
                "priority": "高",
            })
            plans.append({
                "scenario": "一字涨停（是否追涨）",
                "trigger": "标的出现一字涨停且与信号方向一致",
                "action": (
                    "已持仓者持有不动，不追加仓位；"
                    "未建仓者不追涨停，等待开板后回调再评估入场"
                ),
                "execution": "涨停日不操作，开板后视回调幅度决策",
                "priority": "中",
            })

        if strategy_type == "风险规避" or direction == "做空":
            plans.append({
                "scenario": "利空信号对冲方案",
                "trigger": "利空信号确认且持有多头仓位",
                "action": (
                    "方案A：买入对应标的的认沽期权（如有）进行保护；"
                    "方案B：做空对应行业ETF进行行业对冲；"
                    "方案C：直接减仓至用户风险偏好允许的最低仓位"
                ),
                "execution": "利空确认后2个交易日内完成对冲头寸建立",
                "priority": "高",
            })

        return plans

    # ------------------------------------------------------------------ #
    #  Step 4: 盈亏比与胜率测算
    # ------------------------------------------------------------------ #

    def _estimate_pnl(
        self,
        entry_price: float,
        take_profit: List[Dict[str, Any]],
        stop_loss: Dict[str, Any],
        backtest: Dict[str, Any],
        direction: str,
    ) -> Dict[str, Any]:
        """盈亏比与胜率测算。"""
        if entry_price <= 0 or not take_profit:
            return {"error": "参数不足，无法测算"}

        sl_pct = stop_loss.get("stop_loss_pct", 5.0)
        tp_weighted = sum(
            t["target_pct"] * t["reduce_ratio"] for t in take_profit
        )

        risk_reward_ratio = round(tp_weighted / sl_pct, 2) if sl_pct > 0 else 0

        bt = backtest.get("backtest", {})
        t5 = bt.get("t5", {})
        t10 = bt.get("t10", {})
        t30 = bt.get("t30", {})
        hist_win_rate_t5 = t5.get("win_rate")
        hist_win_rate_t10 = t10.get("win_rate")
        hist_avg_ret_t5 = t5.get("avg_return")
        hist_max_dd = t5.get("max_drawdown") or t10.get("max_drawdown")

        assumptions = [
            "盈亏比基于当前止盈/止损参数计算，假设所有止盈档位均被触发",
            "历史胜率来自阶段3回测（成交量异动代理法），非精确事件匹配",
            "未考虑交易成本（佣金+印花税约0.15%）和滑点（约0.1-0.3%）",
            "实际执行可能因流动性、涨跌停等因素偏离预期",
        ]

        uncertainties = [
            "宏观政策突变可能导致市场整体风险偏好变化",
            "标的个股可能出现未预期的基本面变化",
            "市场流动性不足时，止损/止盈可能无法按预设价格执行",
        ]

        max_potential_gain = max((t["target_pct"] for t in take_profit), default=0)

        return {
            "risk_reward_ratio": risk_reward_ratio,
            "risk_reward_label": (
                f"{risk_reward_ratio}:1（"
                + ("优秀" if risk_reward_ratio >= 3 else
                   "良好" if risk_reward_ratio >= 2 else
                   "一般" if risk_reward_ratio >= 1 else "偏低")
                + "）"
            ),
            "expected_gain_weighted_pct": round(tp_weighted, 2),
            "max_potential_gain_pct": max_potential_gain,
            "max_potential_loss_pct": sl_pct,
            "historical_win_rate_t5": hist_win_rate_t5,
            "historical_win_rate_t10": hist_win_rate_t10,
            "historical_avg_return_t5": hist_avg_ret_t5,
            "historical_max_drawdown": hist_max_dd,
            "assumptions": assumptions,
            "uncertainties": uncertainties,
        }

    # ------------------------------------------------------------------ #
    #  主入口
    # ------------------------------------------------------------------ #

    def generate(
        self,
        symbol: str,
        name: str,
        signal_result: Dict[str, Any],
        risk_preference: str,
        investment_horizon: str,
        max_position_pct: float,
    ) -> StrategyResult:
        """策略生成主入口。"""
        if not symbol or not name:
            raise ValueError("需要提供标的代码和名称。")
        if not signal_result:
            raise ValueError("需要提供阶段3（signal_result）的完整输出。")
        if risk_preference not in RISK_PROFILES:
            raise ValueError(f"风险偏好须为：保守/稳健/进取，收到「{risk_preference}」。")
        if investment_horizon not in HORIZON_MAP:
            raise ValueError(f"投资周期须为：短线/中线/长线，收到「{investment_horizon}」。")
        if max_position_pct <= 0 or max_position_pct > 100:
            raise ValueError("单票最大仓位上限须在 (0, 100] 之间。")

        ts_code = _normalize_ts_code(symbol)
        if not ts_code:
            raise ValueError("无法解析标的代码，请使用 600000.SH / 000001.SZ 等格式。")

        graded_signals: List[Dict] = signal_result.get("graded_signals") or []
        eligible = [
            s for s in graded_signals
            if s.get("grade", {}).get("strategy_eligible") is True
        ]

        if not eligible:
            raise ValueError(
                "阶段3无可用于策略生成的有效信号（需中/高确定性信号），"
                "请确认阶段3输出中存在 strategy_eligible=true 的信号。"
            )

        price = self._fetch_price_context(ts_code)

        strategies: List[Dict[str, Any]] = []
        for sig in eligible:
            anchor = self._anchor_strategy(sig, investment_horizon)

            position = self._build_position_plan(
                risk_preference, max_position_pct,
                anchor["strategy_type"], anchor["direction"],
            )

            entry = self._build_entry_conditions(price, anchor, investment_horizon)

            ep = entry.get("entry_price_range", {})
            mid_entry = round(
                (ep.get("low", 0) + ep.get("high", 0)) / 2, 2
            ) if ep.get("low") and ep.get("high") else (price.get("current_close") or 0)

            take_profit = self._build_take_profit(
                mid_entry, risk_preference, anchor["strategy_type"],
            )

            stop_loss = self._build_stop_loss(
                mid_entry, risk_preference, anchor["strategy_type"], price,
            )

            validity = self._build_validity(anchor["strategy_type"], investment_horizon)

            contingency = self._build_contingency_plans(
                mid_entry, anchor["direction"], anchor["strategy_type"],
            )

            backtest = sig.get("backtest", {})
            pnl = self._estimate_pnl(
                mid_entry, take_profit, stop_loss, backtest, anchor["direction"],
            )

            strategies.append({
                "signal_id": anchor["signal_id"],
                "anchor": anchor,
                "target": {
                    "ts_code": ts_code,
                    "name": name,
                    "market": "SH" if ".SH" in ts_code else "SZ",
                    "contract_type": "现货（A股）",
                },
                "position_plan": position,
                "entry_conditions": entry,
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "validity": validity,
                "contingency_plans": contingency,
                "pnl_estimation": pnl,
                "price_context": price,
            })

        run_ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        result_json: Dict[str, Any] = {
            "meta": {
                "module_name": "strategy_agent",
                "version": "0.1.0",
                "run_timestamp": run_ts,
                "data_sources": ["tushare"],
            },
            "inputs": {
                "symbol": symbol,
                "name": name,
                "risk_preference": risk_preference,
                "investment_horizon": investment_horizon,
                "max_position_pct": max_position_pct,
                "eligible_signal_count": len(eligible),
            },
            "strategies": strategies,
            "constraints_and_risks": {
                "not_investment_advice": True,
                "capital_guarantee": False,
                "disclaimers": [RISK_DISCLAIMER],
            },
        }

        report_md = self._build_markdown_report(
            symbol=symbol,
            name=name,
            risk_preference=risk_preference,
            investment_horizon=investment_horizon,
            max_position_pct=max_position_pct,
            strategies=strategies,
        )

        return StrategyResult(report_md=report_md, result_json=result_json)

    # ------------------------------------------------------------------ #
    #  报告生成
    # ------------------------------------------------------------------ #

    def _build_markdown_report(
        self,
        symbol: str,
        name: str,
        risk_preference: str,
        investment_horizon: str,
        max_position_pct: float,
        strategies: List[Dict[str, Any]],
    ) -> str:
        lines: List[str] = []

        # ── 第一部分：策略总览 ──
        lines.append("## 一、策略总览")
        lines.append("")
        lines.append(f"- **标的**：{name}（{symbol}）")
        lines.append(f"- **风险偏好**：{risk_preference} | **投资周期**：{investment_horizon} | **单票仓位上限**：{max_position_pct}%")
        lines.append(f"- **生成策略数量**：{len(strategies)} 个")
        lines.append("")
        for idx, st in enumerate(strategies):
            a = st["anchor"]
            pnl = st["pnl_estimation"]
            rr = pnl.get("risk_reward_label", "-")
            lines.append(
                f"> **策略{idx + 1}**（信号 {a['signal_id']}）：{a['direction']}｜{a['strategy_type']}策略"
                f"｜预期盈亏比 {rr}｜核心风险：{a['core_risk'][:60]}"
            )
        lines.append("")
        lines.append(f"**风险提示**：{RISK_DISCLAIMER}")
        lines.append("")

        for idx, st in enumerate(strategies):
            a = st["anchor"]
            lines.append(f"---")
            lines.append(f"## 策略 {idx + 1}：{a['strategy_type']}策略（信号 {a['signal_id']}）")
            lines.append("")
            lines.append(f"**核心逻辑**：{a['core_logic']}")
            lines.append(f"- **收益来源**：{a['revenue_source']}")
            lines.append(f"- **核心风险**：{a['core_risk']}")
            lines.append("")

            # ── 第二部分：标准化策略参数表 ──
            lines.append("### 二、标准化策略参数表")
            lines.append("")
            tgt = st["target"]
            entry = st["entry_conditions"]
            pos = st["position_plan"]
            sl = st["stop_loss"]
            val = st["validity"]

            lines.append("| 参数项 | 值 |")
            lines.append("|--------|-----|")
            lines.append(f"| 策略方向 | **{a['direction']}** |")
            lines.append(f"| 标的代码 | {tgt['ts_code']} |")
            lines.append(f"| 交易市场 | {tgt['market']} |")
            lines.append(f"| 合约类型 | {tgt['contract_type']} |")
            lines.append(f"| 总仓位上限 | {pos['total_position_pct']}% |")
            lines.append(f"| 首次建仓比例 | {pos['first_build_pct']}% |")

            ep = entry.get("entry_price_range", {})
            if ep.get("low") and ep.get("high"):
                lines.append(f"| 入场价格区间 | {ep['low']}-{ep['high']} 元 |")
            lines.append(f"| 入场触发条件 | {entry.get('entry_trigger', '-')} |")
            lines.append(f"| 入场时间窗口 | {entry.get('time_window', '-')} |")
            lines.append(f"| 确认信号 | {entry.get('confirmation_signal', '-')} |")

            if not isinstance(sl, dict) or sl.get("error"):
                lines.append(f"| 止损价 | 待确认 |")
            else:
                lines.append(f"| 止损价 | {sl.get('stop_loss_price', '-')} 元（-{sl.get('stop_loss_pct', '-')}%） |")
                if sl.get("hard_stop_price"):
                    lines.append(f"| 硬止损价 | {sl['hard_stop_price']} 元 |")
                lines.append(f"| 最大回撤限制 | {sl.get('max_drawdown_pct', '-')}% |")

            lines.append(f"| 持仓周期 | {val['hold_period']} |")
            lines.append(f"| 最迟退出 | {val['exit_deadline']} |")
            lines.append("")

            # 止盈分档
            tp = st["take_profit"]
            if tp:
                lines.append("**止盈分档方案：**")
                lines.append("")
                lines.append("| 档位 | 目标价 | 涨幅 | 减仓比例 | 触发条件 |")
                lines.append("|------|--------|------|----------|----------|")
                for t in tp:
                    lines.append(
                        f"| {t['tier']} | {t['target_price']}元 | "
                        f"{t['target_pct']}% | {t['reduce_pct']}% | "
                        f"{t['trigger_condition'][:50]} |"
                    )
                lines.append("")

            # 加仓计划
            add_pos = pos.get("add_positions", [])
            if add_pos:
                lines.append("**分批加仓计划：**")
                lines.append("")
                lines.append("| 序号 | 加仓比例 | 触发条件 |")
                lines.append("|------|----------|----------|")
                for ap in add_pos:
                    lines.append(f"| {ap['seq']} | {ap['pct']}% | {ap['condition'][:60]} |")
                lines.append("")

            # ── 第三部分：策略执行节奏表 ──
            lines.append("### 三、策略执行节奏表")
            lines.append("")
            lines.append("| 阶段 | 触发条件 | 执行动作 | 优先级 |")
            lines.append("|------|----------|----------|--------|")

            lines.append(
                f"| 建仓 | {entry.get('entry_trigger', '-')[:40]} | "
                f"首次建仓 {pos['first_build_pct']}% | 核心 |"
            )
            for ap in add_pos:
                lines.append(
                    f"| 加仓{ap['seq']} | {ap['condition'][:40]} | "
                    f"加仓 {ap['pct']}% | 条件触发 |"
                )
            for t in tp:
                lines.append(
                    f"| 止盈{t['tier']} | 股价达 {t['target_price']}元 | "
                    f"减仓 {t['reduce_pct']}% | 条件触发 |"
                )
            if isinstance(sl, dict) and not sl.get("error"):
                lines.append(
                    f"| 止损 | {sl.get('trigger_condition', '-')[:40]} | "
                    f"全部清仓 | 强制执行 |"
                )
            lines.append(
                f"| 到期退出 | {val['exit_deadline'][:40]} | "
                f"清仓所有剩余持仓 | 强制执行 |"
            )
            lines.append("")

            # 失效条件
            lines.append("**策略失效条件：**")
            for cond in val.get("invalidation_conditions", []):
                lines.append(f"- {cond}")
            lines.append("")

            # ── 第四部分：极端行情应对方案 ──
            lines.append("### 四、极端行情应对方案与风险提示")
            lines.append("")
            ctg = st["contingency_plans"]
            if ctg:
                lines.append("| 场景 | 触发条件 | 执行动作 | 优先级 |")
                lines.append("|------|----------|----------|--------|")
                for c in ctg:
                    lines.append(
                        f"| {c['scenario']} | {c['trigger'][:30]} | "
                        f"{c['action'][:40]} | {c['priority']} |"
                    )
                lines.append("")

            if isinstance(sl, dict) and sl.get("note"):
                lines.append(f"**止损执行说明**：{sl['note']}")
                lines.append("")

            # ── 盈亏比测算 ──
            pnl = st["pnl_estimation"]
            if not pnl.get("error"):
                lines.append("### 盈亏比与胜率测算")
                lines.append("")
                lines.append("| 指标 | 值 |")
                lines.append("|------|-----|")
                lines.append(f"| 盈亏比 | {pnl.get('risk_reward_label', '-')} |")
                lines.append(f"| 加权预期收益 | {pnl.get('expected_gain_weighted_pct', '-')}% |")
                lines.append(f"| 最大潜在收益 | {pnl.get('max_potential_gain_pct', '-')}% |")
                lines.append(f"| 最大潜在损失 | {pnl.get('max_potential_loss_pct', '-')}% |")
                if pnl.get("historical_win_rate_t5") is not None:
                    lines.append(f"| 历史胜率(T+5) | {pnl['historical_win_rate_t5']}% |")
                if pnl.get("historical_win_rate_t10") is not None:
                    lines.append(f"| 历史胜率(T+10) | {pnl['historical_win_rate_t10']}% |")
                if pnl.get("historical_avg_return_t5") is not None:
                    lines.append(f"| 历史平均收益(T+5) | {pnl['historical_avg_return_t5']}% |")
                if pnl.get("historical_max_drawdown") is not None:
                    lines.append(f"| 历史最大回撤 | {pnl['historical_max_drawdown']}% |")
                lines.append("")

                lines.append("**核心假设：**")
                for a in pnl.get("assumptions", []):
                    lines.append(f"- {a}")
                lines.append("")
                lines.append("**不确定性风险：**")
                for u in pnl.get("uncertainties", []):
                    lines.append(f"- {u}")
                lines.append("")

        # ── 第五部分：JSON 说明 ──
        lines.append("## 五、机器可读 JSON 说明")
        lines.append("")
        lines.append(
            "完整 JSON 通过接口返回值中的 `result` 字段获取，含 "
            "`meta`、`inputs`、`strategies`（每个策略含 `anchor`、`target`、"
            "`position_plan`、`entry_conditions`、`take_profit`、`stop_loss`、"
            "`validity`、`contingency_plans`、`pnl_estimation`、`price_context`）、"
            "`constraints_and_risks`。"
        )

        return "\n".join(lines)
