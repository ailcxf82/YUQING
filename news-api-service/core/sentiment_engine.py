# -*- coding: utf-8 -*-
"""细粒度金融情绪量化引擎 (3.2)

核心能力：
  1. 6级情感极性（强正向/弱正向/中性/弱负向/强负向/不确定性）+ 0-100评分
  2. 金融专属 Prompt 处理反讽、隐喻、双重否定等复杂语义
  3. 动态情绪指数构建（单标的 + 行业/主题）
  4. 情绪偏离度计算
  5. 舆情一致性校验（共识 vs 分歧）
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

from core.logger import get_logger
from core.prompts import get_prompt

logger = get_logger("sentiment_engine")

POLARITY_MAP = {
    "强正向": {"min_score": 80, "max_score": 100},
    "弱正向": {"min_score": 60, "max_score": 79},
    "中性":   {"min_score": 40, "max_score": 59},
    "弱负向": {"min_score": 20, "max_score": 39},
    "强负向": {"min_score": 0, "max_score": 19},
    "不确定性": {"min_score": 40, "max_score": 60},
}


def score_to_polarity(score: float) -> str:
    """将 0-100 分数映射为 6 级极性"""
    if score >= 80:
        return "强正向"
    elif score >= 60:
        return "弱正向"
    elif score >= 40:
        return "中性"
    elif score >= 20:
        return "弱负向"
    else:
        return "强负向"


class SentimentEngine:
    """金融细粒度情感分析引擎"""

    SYSTEM_PROMPT = get_prompt("sentiment", "single_analyze")
    BATCH_SYSTEM_PROMPT = get_prompt("sentiment", "batch_analyze")

    def __init__(self, llm_client: Any) -> None:
        self.llm = llm_client

    def analyze(self, title: str, content: str) -> Dict[str, Any]:
        """单条新闻细粒度情感分析"""
        text = f"标题：{title}\n正文：{content[:2000]}"
        try:
            result = self.llm.chat_json(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=text,
                temperature=0.1,
            )
            score = float(result.get("score", 50))
            score = max(0, min(100, score))
            polarity = result.get("polarity", score_to_polarity(score))

            if polarity not in POLARITY_MAP:
                polarity = score_to_polarity(score)

            return {
                "polarity": polarity,
                "score": score,
                "driver": result.get("driver", ""),
                "reasoning": result.get("reasoning", ""),
                "complexity": result.get("complexity", "simple"),
                "key_phrases": result.get("key_phrases", []),
            }
        except Exception as e:
            logger.warning("情感分析失败: %s", e)
            return {
                "polarity": "中性",
                "score": 50.0,
                "driver": "分析异常",
                "reasoning": str(e),
                "complexity": "simple",
                "key_phrases": [],
            }

    def analyze_aggregate(
        self, items: List[Dict[str, Any]], batch_size: int = 30
    ) -> List[Dict[str, Any]]:
        """聚合批量情感分析：将多条新闻组合为一次 LLM 调用"""
        all_results: List[Dict[str, Any]] = []

        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start:batch_start + batch_size]
            lines = []
            for i, item in enumerate(batch):
                idx = batch_start + i
                nid = item.get("news_id", f"N{idx}")
                title = item.get("title", "")
                content = item.get("content", item.get("text", ""))[:200]
                lines.append(f"[{nid}] {title} | {content}")

            prompt = "\n".join(lines)
            try:
                result_list = self.llm.chat_json_list(
                    system_prompt=self.BATCH_SYSTEM_PROMPT,
                    user_prompt=prompt,
                    temperature=0.1,
                )
                for r in result_list:
                    score = float(r.get("score", 50))
                    score = max(0, min(100, score))
                    polarity = r.get("polarity", score_to_polarity(score))
                    if polarity not in POLARITY_MAP:
                        polarity = score_to_polarity(score)
                    all_results.append({
                        "news_id": r.get("news_id", ""),
                        "polarity": polarity,
                        "score": score,
                        "driver": r.get("driver", ""),
                        "reasoning": r.get("reasoning", ""),
                        "complexity": "moderate",
                        "key_phrases": [],
                    })
            except Exception as e:
                logger.warning("批量情感LLM失败，规则兜底: %s", e)
                for item in batch:
                    text = item.get("title", "") + item.get("content", "")
                    all_results.append(self._rule_sentiment(text))

        while len(all_results) < len(items):
            text = items[len(all_results)].get("title", "")
            all_results.append(self._rule_sentiment(text))

        return all_results

    def analyze_batch(
        self, items: List[Dict[str, Any]], max_llm: int = 50
    ) -> List[Dict[str, Any]]:
        """批量情感分析（保留向后兼容）"""
        return self.analyze_aggregate(items, batch_size=max_llm)

    @staticmethod
    def build_emotion_index(
        sentiments: List[Dict[str, Any]],
        source_weights: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """构建情绪指数

        加权平均计算，权重来源：信源权重 × 影响力分数
        """
        if not sentiments:
            return {"index": 50.0, "trend": "平稳", "count": 0}

        scores = [s.get("score", 50.0) for s in sentiments]
        weights = source_weights or [1.0] * len(scores)

        if len(weights) != len(scores):
            weights = [1.0] * len(scores)

        total_w = sum(weights) or 1.0
        weighted_avg = sum(s * w for s, w in zip(scores, weights)) / total_w
        weighted_avg = round(weighted_avg, 1)

        std_dev = statistics.stdev(scores) if len(scores) > 1 else 0.0

        if weighted_avg >= 65:
            trend = "升温"
        elif weighted_avg <= 35:
            trend = "降温"
        elif std_dev > 20:
            trend = "震荡"
        else:
            trend = "平稳"

        polarity_dist = {}
        for s in sentiments:
            p = s.get("polarity", "中性")
            polarity_dist[p] = polarity_dist.get(p, 0) + 1

        return {
            "index": weighted_avg,
            "trend": trend,
            "std_dev": round(std_dev, 1),
            "count": len(scores),
            "polarity_distribution": polarity_dist,
            "max_score": max(scores),
            "min_score": min(scores),
        }

    @staticmethod
    def compute_deviation(
        current_index: float,
        historical_indices: List[float],
    ) -> Dict[str, Any]:
        """情绪偏离度计算——对比历史同期"""
        if not historical_indices:
            return {"deviation": 0.0, "is_extreme": False, "percentile": 50.0}

        mean = statistics.mean(historical_indices)
        std = statistics.stdev(historical_indices) if len(historical_indices) > 1 else 10.0
        deviation = (current_index - mean) / std if std > 0 else 0.0

        sorted_hist = sorted(historical_indices)
        below = sum(1 for h in sorted_hist if h < current_index)
        percentile = (below / len(sorted_hist)) * 100

        return {
            "deviation": round(deviation, 2),
            "is_extreme": abs(deviation) > 2.0,
            "percentile": round(percentile, 1),
            "historical_mean": round(mean, 1),
            "historical_std": round(std, 1),
            "direction": "超预期乐观" if deviation > 1.5 else "超预期悲观" if deviation < -1.5 else "正常范围",
        }

    @staticmethod
    def check_consistency(
        sentiments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """舆情一致性校验——区分共识与分歧"""
        if not sentiments:
            return {"type": "无数据", "agreement_ratio": 0, "noise_count": 0}

        scores = [s.get("score", 50) for s in sentiments]
        std = statistics.stdev(scores) if len(scores) > 1 else 0.0

        positive = sum(1 for s in scores if s >= 60)
        negative = sum(1 for s in scores if s <= 40)
        neutral = len(scores) - positive - negative

        majority = max(positive, negative, neutral)
        agreement = majority / len(scores) if scores else 0

        noise_items = []
        influence_scores = [s.get("influence_score", 50) for s in sentiments]
        for i, s in enumerate(sentiments):
            score = s.get("score", 50)
            inf = s.get("influence_score", 50)
            if (abs(score - 50) > 30) and (inf < 20):
                noise_items.append(i)

        if std < 10 and agreement > 0.7:
            consensus_type = "强共识"
        elif std < 20:
            consensus_type = "弱共识"
        elif positive > 0 and negative > 0 and abs(positive - negative) <= 2:
            consensus_type = "明显分歧"
        else:
            consensus_type = "温和分歧"

        return {
            "type": consensus_type,
            "agreement_ratio": round(agreement, 2),
            "std_dev": round(std, 1),
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
            "noise_count": len(noise_items),
            "noise_indices": noise_items,
        }

    @staticmethod
    def filter_noise(
        sentiments: List[Dict[str, Any]],
        min_influence: float = 15.0,
    ) -> List[Dict[str, Any]]:
        """剔除噪音舆情：情绪极端但影响力极低的内容"""
        filtered = []
        for s in sentiments:
            score = s.get("score", 50)
            influence = s.get("influence_score", 50)
            if abs(score - 50) > 30 and influence < min_influence:
                s["is_noise"] = True
                logger.debug(
                    "噪音过滤 | score=%.1f influence=%.1f",
                    score, influence,
                )
            else:
                s["is_noise"] = False
            filtered.append(s)
        return filtered

    @staticmethod
    def _rule_sentiment(text: str) -> Dict[str, Any]:
        """规则兜底情感分析"""
        positive_kw = ["增长", "利好", "突破", "超预期", "上调", "利润增", "订单"]
        negative_kw = ["下降", "亏损", "处罚", "违规", "暴跌", "减持", "风险"]

        pos = sum(1 for kw in positive_kw if kw in text)
        neg = sum(1 for kw in negative_kw if kw in text)

        if pos > neg + 1:
            return {"polarity": "弱正向", "score": 65.0, "driver": "正面关键词",
                    "reasoning": "规则兜底", "complexity": "simple", "key_phrases": []}
        elif neg > pos + 1:
            return {"polarity": "弱负向", "score": 35.0, "driver": "负面关键词",
                    "reasoning": "规则兜底", "complexity": "simple", "key_phrases": []}
        else:
            return {"polarity": "中性", "score": 50.0, "driver": "无明显倾向",
                    "reasoning": "规则兜底", "complexity": "simple", "key_phrases": []}
