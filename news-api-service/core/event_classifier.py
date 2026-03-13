# -*- coding: utf-8 -*-
"""金融事件分类与标签体系 (3.1.2)

四大事件类别 × 18+ 细分标签，基于 Few-Shot Prompt 实现高准确率分类。
规则兜底防止 LLM 误判。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger("event_classifier")

# ── 标准化金融事件标签体系 ──

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

# ── 规则兜底关键词映射 ──

_KEYWORD_MAP = {
    "业绩超预期": ["业绩超", "超预期", "大幅增长", "净利润翻"],
    "重大订单落地": ["中标", "签约", "订单", "合同"],
    "政策扶持": ["补贴", "扶持", "减税", "优惠政策"],
    "技术突破": ["技术突破", "专利", "自主研发", "创新"],
    "并购重组利好": ["并购", "重组", "收购", "资产注入"],
    "分红超预期": ["分红", "派息", "送转"],
    "业绩暴雷": ["业绩暴雷", "亏损", "大幅下滑", "下降"],
    "监管处罚": ["处罚", "罚款", "违规", "立案"],
    "诉讼仲裁": ["诉讼", "仲裁", "起诉", "判决"],
    "高管失联": ["失联", "留置", "被查", "被抓"],
    "供应链断裂": ["断供", "供应链", "停产"],
    "产品质量问题": ["召回", "质量问题", "安全事故"],
    "黑天鹅事件": ["暴跌", "黑天鹅", "突发"],
    "政策草案": ["征求意见", "草案", "拟出台"],
    "业绩预告": ["业绩预告", "业绩快报", "预增", "预减"],
    "行业传闻": ["传闻", "据悉", "有消息称", "市场传言"],
    "重大事项停牌": ["停牌", "重大事项"],
}


class EventClassifier:
    """金融事件分类器——Few-Shot Prompt + 规则兜底"""

    SYSTEM_PROMPT = (
        "你是金融事件分类专家。对给定新闻判定事件类别与细分标签。\n\n"
        "## 分类体系\n"
        "正向事件: 业绩超预期/重大订单落地/政策扶持/技术突破/并购重组利好/"
        "分红超预期/获得融资/产能扩张/市场份额提升/评级上调\n"
        "负向事件: 业绩暴雷/监管处罚/诉讼仲裁/高管失联/供应链断裂/"
        "产品质量问题/黑天鹅事件/评级下调/大股东减持/财务造假/经营亏损\n"
        "中性事件: 常规公告/例行信息披露/普通人事变动/无实质影响/市场常规波动/行业一般动态\n"
        "不确定性事件: 政策草案/业绩预告/行业传闻/重大事项停牌/战略调整/管理层变更\n\n"
        "## Few-Shot 示例\n"
        "输入: 贵州茅台2025年年报发布，营收增长15%，净利润增长20%，超市场一致预期\n"
        '输出: {"category":"正向事件","sub_label":"业绩超预期","confidence":0.95,'
        '"impact_level":"公司级","reason":"营收和净利润增速超出市场一致预期"}\n\n'
        "输入: 某上市公司因信息披露违规被证监会罚款500万元\n"
        '输出: {"category":"负向事件","sub_label":"监管处罚","confidence":0.92,'
        '"impact_level":"公司级","reason":"证监会行政处罚，涉及信息披露违规"}\n\n'
        "输入: 国务院发布新能源汽车产业发展规划征求意见稿\n"
        '输出: {"category":"不确定性事件","sub_label":"政策草案","confidence":0.88,'
        '"impact_level":"行业级","reason":"政策处于征求意见阶段，最终落地存在不确定性"}\n\n'
        "输入: 公司发布例行季度报告，各项指标平稳\n"
        '输出: {"category":"中性事件","sub_label":"例行信息披露","confidence":0.90,'
        '"impact_level":"公司级","reason":"常规信息披露，无超预期信息"}\n\n'
        "## 输出要求\n"
        "返回严格 JSON：\n"
        "{\n"
        '  "category": "正向事件/负向事件/中性事件/不确定性事件",\n'
        '  "sub_label": "细分标签",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "impact_level": "公司级/行业级/大盘级",\n'
        '  "reason": "分类依据一句话"\n'
        "}\n"
        "仅输出JSON，不要解释。"
    )

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

    BATCH_SYSTEM_PROMPT = (
        "你是金融事件分类专家。对以下多条新闻逐一判定事件类别与细分标签。\n\n"
        "## 分类体系\n"
        "正向事件: 业绩超预期/重大订单落地/政策扶持/技术突破/并购重组利好/"
        "分红超预期/获得融资/产能扩张/市场份额提升/评级上调\n"
        "负向事件: 业绩暴雷/监管处罚/诉讼仲裁/高管失联/供应链断裂/"
        "产品质量问题/黑天鹅事件/评级下调/大股东减持/财务造假/经营亏损\n"
        "中性事件: 常规公告/例行信息披露/普通人事变动/无实质影响/市场常规波动/行业一般动态\n"
        "不确定性事件: 政策草案/业绩预告/行业传闻/重大事项停牌/战略调整/管理层变更\n\n"
        "## 输出格式（严格JSON数组，每条对应一个news_id）\n"
        "[\n"
        '  {"news_id": "N1", "category": "正向事件", "sub_label": "业绩超预期", '
        '"confidence": 0.95, "impact_level": "公司级", "reason": "一句话依据"},\n'
        '  {"news_id": "N2", "category": "中性事件", "sub_label": "无实质影响", '
        '"confidence": 0.8, "impact_level": "公司级", "reason": "一句话依据"}\n'
        "]\n"
        "仅输出JSON数组，不要解释。必须为每条新闻都输出一条结果。"
    )

    def classify_aggregate(
        self, items: List[Dict[str, Any]], batch_size: int = 50
    ) -> List[Dict[str, Any]]:
        """聚合批量分类：将多条新闻组合为一次 LLM 调用

        200 条新闻 → 4 次 LLM 调用（每批 50 条），而非 200 次。
        """
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
