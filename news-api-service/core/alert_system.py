# -*- coding: utf-8 -*-
"""舆情风险预警与机会识别模块 (3.4)

核心能力：
  1. 自定义阈值预警（负面影响力突破阈值、情绪指数暴跌、黑天鹅触发等）
  2. 异常舆情识别（热度/情绪突变、未被市场定价的事件）
  3. 四级风险等级划分（低/中/高/重大）+ 风险缓释建议
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger("alert_system")


class RiskLevel:
    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    CRITICAL = "重大风险"


# ── 默认预警阈值 ──
DEFAULT_THRESHOLDS = {
    "negative_influence_min": 60.0,
    "emotion_drop_pct": 20.0,
    "black_swan_labels": ["黑天鹅事件", "高管失联", "财务造假", "供应链断裂"],
    "critical_event_labels": ["监管处罚", "诉讼仲裁", "产品质量问题"],
    "anomaly_zscore": 2.0,
    "min_influence_for_alert": 30.0,
}


class AlertSystem:
    """舆情风险预警系统"""

    def __init__(
        self,
        thresholds: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    def evaluate(
        self,
        events: List[Dict[str, Any]],
        emotion_index: Dict[str, Any],
        historical_indices: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """综合评估所有事件，生成预警结果

        Returns:
            alerts: 预警事件列表
            risk_level: 整体风险等级
            opportunities: 潜在机会列表
            summary: 预警摘要
        """
        alerts: List[Dict[str, Any]] = []
        opportunities: List[Dict[str, Any]] = []

        for ev in events:
            ev_alerts = self._check_event_alerts(ev)
            alerts.extend(ev_alerts)

        idx_alerts = self._check_emotion_alerts(emotion_index, historical_indices)
        alerts.extend(idx_alerts)

        opps = self._identify_opportunities(events, emotion_index)
        opportunities.extend(opps)

        risk_level = self._compute_overall_risk(alerts)

        mitigation = []
        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            mitigation = self._generate_mitigation(alerts, risk_level)

        return {
            "alerts": alerts,
            "alert_count": len(alerts),
            "risk_level": risk_level,
            "opportunities": opportunities,
            "opportunity_count": len(opportunities),
            "mitigation_suggestions": mitigation,
            "evaluation_time": datetime.now().isoformat(timespec="seconds"),
        }

    def _check_event_alerts(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """逐事件检查是否触发预警"""
        alerts = []
        sub_label = event.get("sub_label", "")
        influence = event.get("influence_score", 0)
        polarity = event.get("polarity", "中性")
        score = event.get("score", 50)

        if sub_label in self.thresholds["black_swan_labels"]:
            alerts.append({
                "type": "黑天鹅事件",
                "risk_level": RiskLevel.CRITICAL,
                "event_id": event.get("event_id", ""),
                "description": f"检测到黑天鹅级事件：{sub_label}",
                "detail": event.get("core_summary", ""),
                "influence_score": influence,
                "action": "立即关注，评估仓位风险",
                "priority": 1,
            })

        if sub_label in self.thresholds["critical_event_labels"] and influence >= 40:
            alerts.append({
                "type": "重大负面事件",
                "risk_level": RiskLevel.HIGH,
                "event_id": event.get("event_id", ""),
                "description": f"重大负面事件：{sub_label}（影响力 {influence}分）",
                "detail": event.get("core_summary", ""),
                "influence_score": influence,
                "action": "密切关注事态进展，考虑风险对冲",
                "priority": 2,
            })

        neg_threshold = self.thresholds["negative_influence_min"]
        if polarity in ("强负向", "弱负向") and influence >= neg_threshold:
            alerts.append({
                "type": "负面舆情影响力突破阈值",
                "risk_level": RiskLevel.MEDIUM if influence < 80 else RiskLevel.HIGH,
                "event_id": event.get("event_id", ""),
                "description": (
                    f"负面舆情影响力 {influence}分 超过阈值 {neg_threshold}分"
                ),
                "detail": event.get("core_summary", ""),
                "influence_score": influence,
                "action": "关注舆情发酵情况",
                "priority": 3,
            })

        return alerts

    def _check_emotion_alerts(
        self,
        emotion_index: Dict[str, Any],
        historical: Optional[List[float]],
    ) -> List[Dict[str, Any]]:
        """基于情绪指数检查预警"""
        alerts = []
        idx = emotion_index.get("index", 50.0)
        trend = emotion_index.get("trend", "平稳")
        std = emotion_index.get("std_dev", 0)

        if idx < 30:
            alerts.append({
                "type": "情绪指数极低",
                "risk_level": RiskLevel.HIGH,
                "description": f"情绪指数 {idx} 处于极低水平（趋势：{trend}）",
                "action": "警惕恐慌性抛售风险",
                "priority": 2,
            })
        elif idx > 85:
            alerts.append({
                "type": "情绪指数过热",
                "risk_level": RiskLevel.MEDIUM,
                "description": f"情绪指数 {idx} 过热（趋势：{trend}），警惕情绪反转",
                "action": "注意过度乐观风险，关注获利回吐压力",
                "priority": 3,
            })

        if historical and len(historical) >= 3:
            import statistics
            mean = statistics.mean(historical)
            hist_std = statistics.stdev(historical) if len(historical) > 1 else 10
            zscore = abs(idx - mean) / hist_std if hist_std > 0 else 0
            if zscore > self.thresholds["anomaly_zscore"]:
                direction = "异常偏高" if idx > mean else "异常偏低"
                alerts.append({
                    "type": "情绪异常偏离",
                    "risk_level": RiskLevel.MEDIUM,
                    "description": (
                        f"情绪指数 {idx} {direction}（历史均值 {mean:.1f}，"
                        f"Z-score={zscore:.1f}）"
                    ),
                    "action": "关注是否有未被市场充分消化的事件",
                    "priority": 3,
                })

        return alerts

    def _identify_opportunities(
        self,
        events: List[Dict[str, Any]],
        emotion_index: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """识别潜在投资机会"""
        opportunities = []

        positive_events = [
            e for e in events
            if e.get("polarity") in ("强正向", "弱正向")
            and e.get("influence_score", 0) >= 50
        ]

        idx = emotion_index.get("index", 50)
        if positive_events and idx < 55:
            opportunities.append({
                "type": "利好未充分定价",
                "description": (
                    f"存在 {len(positive_events)} 条高影响力正面舆情，"
                    f"但情绪指数仅 {idx}，市场可能尚未充分反应"
                ),
                "events": [e.get("event_id", "") for e in positive_events[:3]],
                "confidence": 0.6,
            })

        strong_pos = [e for e in events if e.get("polarity") == "强正向"]
        if strong_pos:
            for e in strong_pos:
                if e.get("sub_label") in ("业绩超预期", "重大订单落地", "政策扶持", "技术突破"):
                    opportunities.append({
                        "type": f"事件驱动机会-{e.get('sub_label')}",
                        "description": e.get("core_summary", ""),
                        "event_id": e.get("event_id", ""),
                        "confidence": e.get("confidence", 0.5),
                    })

        return opportunities

    @staticmethod
    def _compute_overall_risk(alerts: List[Dict[str, Any]]) -> str:
        """计算整体风险等级"""
        if not alerts:
            return RiskLevel.LOW

        levels = [a.get("risk_level", RiskLevel.LOW) for a in alerts]
        if RiskLevel.CRITICAL in levels:
            return RiskLevel.CRITICAL
        if levels.count(RiskLevel.HIGH) >= 2:
            return RiskLevel.CRITICAL
        if RiskLevel.HIGH in levels:
            return RiskLevel.HIGH
        if RiskLevel.MEDIUM in levels:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def _generate_mitigation(
        alerts: List[Dict[str, Any]], risk_level: str
    ) -> List[str]:
        """为高风险事件生成缓释建议"""
        suggestions = []

        if risk_level == RiskLevel.CRITICAL:
            suggestions.append("立即审视持仓，评估是否需要减仓或清仓")
            suggestions.append("关注大股东、管理层动态，防范内幕风险")
            suggestions.append("考虑使用期权或其他衍生品进行风险对冲")

        if risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
            suggestions.append("设置严格止损位，控制最大回撤")
            suggestions.append("持续跟踪事件进展，关注官方正式公告")
            suggestions.append("对比同行业标的，评估风险传导范围")

        alert_types = {a.get("type", "") for a in alerts}
        if "黑天鹅事件" in alert_types:
            suggestions.append("启动应急响应，优先保护本金")
        if "情绪指数极低" in alert_types:
            suggestions.append("关注市场恐慌是否过度，可能存在超跌机会")
        if "情绪指数过热" in alert_types:
            suggestions.append("适当止盈，不追高")

        key_metrics = [
            "标的财务数据（现金流、负债率、商誉）",
            "大股东质押比例与减持计划",
            "同行业政策与竞争格局变化",
        ]
        suggestions.append(f"重点关注指标：{'、'.join(key_metrics)}")

        return suggestions

    def grade_event_risk(self, event: Dict[str, Any]) -> str:
        """对单个事件进行风险等级划分"""
        sub_label = event.get("sub_label", "")
        influence = event.get("influence_score", 0)
        polarity = event.get("polarity", "中性")

        if sub_label in self.thresholds["black_swan_labels"]:
            return RiskLevel.CRITICAL
        if sub_label in self.thresholds["critical_event_labels"] and influence > 50:
            return RiskLevel.HIGH
        if polarity in ("强负向",) and influence > 40:
            return RiskLevel.HIGH
        if polarity in ("弱负向",) and influence > 30:
            return RiskLevel.MEDIUM
        if polarity in ("弱负向",) or sub_label in ("行业传闻", "政策草案"):
            return RiskLevel.LOW
        return RiskLevel.LOW
