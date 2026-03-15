# -*- coding: utf-8 -*-
"""金融事件分类与标签体系 (3.1.2)

四大事件类别 × 18+ 细分标签，基于 Few-Shot Prompt 实现高准确率分类。
规则兜底防止 LLM 误判。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.logger import get_logger
from core.prompts import get_prompt

logger = get_logger("event_classifier")

EVENT_TAXONOMY = {
    "正向事件": [
        "业绩超预期", "重大订单落地", "政策扶持", "技术突破",
        "并购重组利好", "分红超预期", "获得融资", "产能扩张",
        "市场份额提升", "评级上调",
    ],
    "负向事件": [
        "业绩暴雷", "监管处罚", "诉讼仲裁", "高管失联",
        "供应链断裂", "产品质量问题", "黑天鹅事件", "评级下调",
        "大股东减持", "财务造假", "经营亏损",
    ],
    "中性事件": [
        "常规公告", "例行信息披露", "普通人事变动", "无实质影响",
        "市场常规波动", "行业一般动态",
    ],
    "不确定性事件": [
        "政策草案", "业绩预告", "行业传闻", "重大事项停牌",
        "战略调整", "管理层变更",
    ],
}

ALL_LABELS = []
for cat, labels in EVENT_TAXONOMY.items():
    for lb in labels:
        ALL_LABELS.append(f"{cat}/{lb}")

_KEYWORD_MAP = {
    "业绩超预期": ["业绩超", "超预期", "大幅增长", "净利润翻"],
    "重大订单落地": ["中标", "签约", "订单", "合同"],
    "政策扶持": ["补贴", "扶持", "减税", "优惠政策"],
    "技术突破": ["技术突破", "专利", "自主研发"],
    "并购重组利好": ["并购", "重组", "收购"],
    "分红超预期": ["分红", "派息", "高送转"],
    "获得融资": ["融资", "定增", "配股"],
    "产能扩张": ["扩产", "新建", "投产"],
    "市场份额提升": ["市场份额", "市占率"],
    "评级上调": ["评级上调", "买入评级", "增持"],
    "业绩暴雷": ["业绩暴雷", "亏损", "大幅下滑"],
    "监管处罚": ["处罚", "立案", "监管"],
    "诉讼仲裁": ["诉讼", "仲裁", "起诉"],
    "高管失联": ["高管失联", "高管被查"],
    "供应链断裂": ["供应链", "断供"],
    "产品质量问题": ["质量问题", "召回", "缺陷"],
    "黑天鹅事件": ["黑天鹅", "突发"],
    "评级下调": ["评级下调", "卖出评级"],
    "大股东减持": ["减持", "套现"],
    "财务造假": ["造假", "虚增"],
    "经营亏损": ["经营亏损", "持续亏损"],
}


class EventClassifier:
    """金融事件分类器——Few-Shot Prompt + 规则兜底"""

    SYSTEM_PROMPT = get_prompt("event_classification", "single_classify")
    BATCH_SYSTEM_PROMPT = get_prompt("event_classification", "batch_classify")

    def __init__(self, llm_client: Any) -> None:
        self.llm = llm_client

    def classify(self, title: str, content: str) -> Dict[str, Any]:
        """对单条新闻进行事件分类"""
        text = f"标题：{title}\n正文：{content[:2000]}"
        try:
            result = self.llm.chat_json(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=text,
                temperature=0.1,
            )
            category = result.get("category", "中性事件")
            sub_label = result.get("sub_label", "无实质影响")
            if not self._validate_label(category, sub_label):
                fallback = self._rule_classify(title + content)
                category = fallback["category"]
                sub_label = fallback["sub_label"]
                result["confidence"] = max(
                    result.get("confidence", 0) * 0.7,
                    fallback.get("confidence", 0.5),
                )
            result["category"] = category
            result["sub_label"] = sub_label
            return result
        except Exception as e:
            logger.warning("LLM 事件分类失败，使用规则兜底: %s", e)
            return self._rule_classify(title + content)

    def classify_aggregate(
        self, items: List[Dict[str, Any]], batch_size: int = 50
    ) -> List[Dict[str, Any]]:
        """聚合批量分类：将多条新闻组合为一次 LLM 调用"""
        all_results: List[Dict[str, Any]] = []
        id_map: Dict[str, int] = {}

        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start:batch_start + batch_size]
            lines = []
            for i, item in enumerate(batch):
                idx = batch_start + i
                nid = item.get("news_id", f"N{idx}")
                id_map[nid] = idx
                title = item.get("title", "")
                content = item.get("content", item.get("text", ""))[:150]
                lines.append(f"[{nid}] {title} | {content}")

            prompt = "\n".join(lines)
            try:
                result_list = self.llm.chat_json_list(
                    system_prompt=self.BATCH_SYSTEM_PROMPT,
                    user_prompt=prompt,
                    temperature=0.1,
                )
                for r in result_list:
                    cat = r.get("category", "中性事件")
                    sub = r.get("sub_label", "无实质影响")
                    if not self._validate_label(cat, sub):
                        r["category"] = "中性事件"
                        r["sub_label"] = "无实质影响"
                        r["confidence"] = r.get("confidence", 0.5) * 0.7
                    all_results.append(r)
            except Exception as e:
                logger.warning("批量分类LLM失败，规则兜底: %s", e)
                for item in batch:
                    text = item.get("title", "") + item.get("content", "")
                    all_results.append(self._rule_classify(text))

        while len(all_results) < len(items):
            text = items[len(all_results)].get("title", "")
            all_results.append(self._rule_classify(text))

        return all_results

    def classify_batch(
        self, items: List[Dict[str, Any]], max_llm: int = 50
    ) -> List[Dict[str, Any]]:
        """批量分类（保留向后兼容）"""
        return self.classify_aggregate(items, batch_size=max_llm)

    @staticmethod
    def _validate_label(category: str, sub_label: str) -> bool:
        """验证分类结果是否在标签体系内"""
        labels = EVENT_TAXONOMY.get(category, [])
        return sub_label in labels

    @staticmethod
    def _rule_classify(text: str) -> Dict[str, Any]:
        """规则兜底分类"""
        for label, keywords in _KEYWORD_MAP.items():
            for kw in keywords:
                if kw in text:
                    for cat, labels in EVENT_TAXONOMY.items():
                        if label in labels:
                            return {
                                "category": cat,
                                "sub_label": label,
                                "confidence": 0.6,
                                "impact_level": "公司级",
                                "reason": f"关键词匹配: {kw}",
                            }
        return {
            "category": "中性事件",
            "sub_label": "无实质影响",
            "confidence": 0.4,
            "impact_level": "公司级",
            "reason": "无明显事件特征",
        }

    @staticmethod
    def get_taxonomy() -> Dict[str, List[str]]:
        return EVENT_TAXONOMY.copy()
