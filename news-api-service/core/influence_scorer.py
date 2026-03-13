# -*- coding: utf-8 -*-
"""舆情传播力与影响力量化模块 (3.1.3)

基于渠道权重 + 传播量级 + 事件类型 + 实体级别计算影响力总分（0-100）。
实现传播速度跟踪与源头/二次传播区分。
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger("influence_scorer")

# ── 事件类型影响力权重 ──
EVENT_TYPE_WEIGHTS: Dict[str, float] = {
    "业绩超预期": 0.9, "业绩暴雷": 0.95,
    "监管处罚": 0.9, "黑天鹅事件": 1.0,
    "并购重组利好": 0.85, "政策扶持": 0.85,
    "高管失联": 0.9, "诉讼仲裁": 0.8,
    "重大订单落地": 0.8, "技术突破": 0.75,
    "分红超预期": 0.7, "供应链断裂": 0.85,
    "产品质量问题": 0.85, "大股东减持": 0.8,
    "财务造假": 0.95, "评级上调": 0.7,
    "评级下调": 0.75, "政策草案": 0.65,
    "业绩预告": 0.7, "行业传闻": 0.5,
    "重大事项停牌": 0.75, "战略调整": 0.6,
    "常规公告": 0.3, "例行信息披露": 0.25,
    "普通人事变动": 0.35, "无实质影响": 0.1,
}

# ── 影响级别权重 ──
IMPACT_LEVEL_WEIGHTS: Dict[str, float] = {
    "大盘级": 1.0,
    "行业级": 0.85,
    "公司级": 0.7,
}


class InfluenceScorer:
    """舆情影响力评分器"""

    @staticmethod
    def score(
        source_weight: float = 0.5,
        spread_count: int = 0,
        event_sub_label: str = "",
        impact_level: str = "公司级",
        confidence: float = 0.5,
    ) -> float:
        """计算单条舆情的影响力总分（0-100）

        公式：
          base = source_w * 25 + spread_w * 25 + event_w * 30 + level_w * 20
          final = base * confidence_factor
        """
        source_w = min(source_weight, 1.0)

        if spread_count <= 0:
            spread_w = 0.0
        else:
            spread_w = min(math.log10(spread_count + 1) / 5.0, 1.0)

        event_w = EVENT_TYPE_WEIGHTS.get(event_sub_label, 0.3)
        level_w = IMPACT_LEVEL_WEIGHTS.get(impact_level, 0.7)
        conf_factor = 0.6 + 0.4 * min(confidence, 1.0)

        raw = source_w * 25 + spread_w * 25 + event_w * 30 + level_w * 20
        return round(min(raw * conf_factor, 100.0), 1)

    @staticmethod
    def score_batch(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量计算影响力评分，将结果写入 item['influence_score']"""
        for item in items:
            item["influence_score"] = InfluenceScorer.score(
                source_weight=item.get("source_weight", 0.5),
                spread_count=item.get("spread_count", 0),
                event_sub_label=item.get("sub_label", ""),
                impact_level=item.get("impact_level", "公司级"),
                confidence=item.get("confidence", 0.5),
            )
        return items

    @staticmethod
    def track_spread_velocity(
        timestamps: List[str],
    ) -> Dict[str, Any]:
        """跟踪舆情传播速度

        Args:
            timestamps: 多条相关舆情的发布时间列表

        Returns:
            velocity_per_hour: 每小时传播条数
            peak_hour: 传播高峰时段
            is_fast_spreading: 是否快速发酵（>5条/小时）
        """
        if not timestamps or len(timestamps) < 2:
            return {"velocity_per_hour": 0, "peak_hour": "", "is_fast_spreading": False}

        parsed = []
        for ts in timestamps:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                parsed.append(dt)
            except (ValueError, AttributeError):
                continue

        if len(parsed) < 2:
            return {"velocity_per_hour": 0, "peak_hour": "", "is_fast_spreading": False}

        parsed.sort()
        span_hours = max((parsed[-1] - parsed[0]).total_seconds() / 3600, 0.1)
        velocity = len(parsed) / span_hours

        hour_counts: Dict[int, int] = {}
        for dt in parsed:
            h = dt.hour
            hour_counts[h] = hour_counts.get(h, 0) + 1
        peak_h = max(hour_counts, key=hour_counts.get) if hour_counts else 0

        return {
            "velocity_per_hour": round(velocity, 2),
            "peak_hour": f"{peak_h:02d}:00-{peak_h:02d}:59",
            "is_fast_spreading": velocity > 5,
            "total_count": len(parsed),
            "span_hours": round(span_hours, 1),
        }

    @staticmethod
    def classify_propagation(
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """区分源头舆情和二次传播舆情

        基于发布时间排序，最早发布且内容最完整的为源头，
        后续相似内容标记为二次传播。
        """
        if not items:
            return items

        sorted_items = sorted(
            items, key=lambda x: x.get("publish_time", "")
        )

        if sorted_items:
            sorted_items[0]["propagation_type"] = "源头舆情"
            sorted_items[0]["propagation_order"] = 1

        seen_hashes = {sorted_items[0].get("content_hash", "")} if sorted_items else set()

        for i, item in enumerate(sorted_items[1:], start=2):
            ch = item.get("content_hash", "")
            if ch in seen_hashes:
                item["propagation_type"] = "重复传播"
            else:
                title = item.get("title", "")
                content = item.get("content", "")[:200]
                is_similar = any(
                    _text_similarity(title + content, prev.get("title", "") + prev.get("content", "")[:200]) > 0.6
                    for prev in sorted_items[:i-1]
                )
                item["propagation_type"] = "二次传播" if is_similar else "独立来源"
            item["propagation_order"] = i
            seen_hashes.add(ch)

        return sorted_items


def _text_similarity(a: str, b: str) -> float:
    """简易字符级 Jaccard 相似度"""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union > 0 else 0.0
