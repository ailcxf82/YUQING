# -*- coding: utf-8 -*-
"""全链路合规校验智能体（ComplianceAgent）

角色定位：全链路唯一合规守门人。
每一个业务智能体的输出结果，必须先经过本智能体的合规校验，
才能进入下一环节。

核心职责：
  1. 全节点合规校验（违规投资建议/保本承诺/虚假宣传/误导性表述拦截）
  2. 轻微违规内容修正
  3. 强制免责声明植入
  4. 严重违规触发合规熔断
  5. 全链路合规日志记录
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from agents.base import BaseAgent
from core.schemas import ComplianceCheckOutput, FullLinkState, AgentStatus


# ── 违规关键词库 ──
FORBIDDEN_PHRASES = [
    "保本", "无风险", "必赚", "稳赚", "保证收益", "零风险",
    "必涨", "必跌", "绝对安全", "包赚", "躺赚",
    "承诺收益", "保底收益", "刚性兑付",
]

WARNING_PHRASES = [
    "建议买入", "建议卖出", "强烈推荐", "应该满仓",
    "全仓买入", "立即清仓", "必须持有",
]

COMPLIANCE_DISCLAIMER = (
    "【免责声明】本分析报告由AI系统自动生成，仅供投资研究参考，"
    "不构成任何投资建议或投资承诺。市场有风险，投资需谨慎。"
    "过往分析不代表未来表现，本工具不对任何投资损益承担法律责任。"
    "投资者应独立判断并自行承担投资风险。"
)


class ComplianceAgent(BaseAgent):
    """全链路合规校验智能体——每个业务节点输出的必经守门人"""

    name = "compliance"
    description = "全链路合规校验、违规拦截、免责声明植入、合规熔断"

    SYSTEM_PROMPT = (
        "你是金融合规校验专家。你的唯一职责是审查金融分析内容的合规性。\n"
        "你不做任何分析、判断、策略生成，仅做合规审查。\n\n"
        "## 审查规则\n"
        "1. 拦截任何包含保本承诺、保证收益、无风险等违规表述\n"
        "2. 拦截绝对化投资建议（如\"必须买入\"\"立即清仓\"）\n"
        "3. 确保所有分析结论带有不确定性说明\n"
        "4. 确保不存在虚假数据、伪造信息\n"
        "5. 对轻微违规做合规话术修正\n\n"
        "## 输出格式\n"
        '{"compliant": true/false, "violations": ["违规1"], '
        '"corrections": {"原文片段": "修正后片段"}, '
        '"severity": "无/轻微/中度/严重"}\n'
        "仅输出JSON。"
    )

    def run(self, state: FullLinkState) -> Dict[str, Any]:
        """合规校验不通过常规 run 调用，而是通过 check 方法。

        此 run 方法保留以满足 BaseAgent 接口要求。
        """
        return {
            "compliance_check_records": [],
            "current_step": "compliance_standby",
        }

    def check(
        self,
        agent_name: str,
        agent_output: Dict[str, Any],
        task_id: str = "",
    ) -> ComplianceCheckOutput:
        """对指定智能体的输出做合规校验

        Returns:
            ComplianceCheckOutput: 校验结果
        """
        start = time.time()
        violations: List[str] = []
        corrections: Dict[str, str] = {}
        severity = "无"

        text_content = self._extract_text(agent_output)

        for phrase in FORBIDDEN_PHRASES:
            if phrase in text_content:
                violations.append(f"严重违规：包含禁止表述「{phrase}」")
                severity = "严重"

        for phrase in WARNING_PHRASES:
            if phrase in text_content:
                violations.append(f"中度违规：包含绝对化建议「{phrase}」")
                corrected = phrase + "（仅供参考，不构成投资建议）"
                corrections[phrase] = corrected
                if severity != "严重":
                    severity = "中度"

        if self._has_absolute_prediction(text_content):
            violations.append("轻微违规：包含绝对化预测表述")
            if severity == "无":
                severity = "轻微"

        fuse = severity == "严重"

        if violations and not fuse:
            corrected_output = self._apply_corrections(agent_output, corrections)
            check_result = "修正后通过"
        elif fuse:
            corrected_output = agent_output
            check_result = "驳回"
        else:
            corrected_output = agent_output
            check_result = "通过"

        duration = int((time.time() - start) * 1000)

        result = ComplianceCheckOutput(
            task_id=task_id,
            agent_name=agent_name,
            check_result=check_result,
            corrected_content=corrected_output,
            violation_details=violations,
            fuse_trigger=fuse,
            compliance_disclaimer=COMPLIANCE_DISCLAIMER,
            execution_log={
                "duration_ms": duration,
                "severity": severity,
                "corrections_count": len(corrections),
            },
        )

        self.logger.info(
            "合规校验 | agent=%s result=%s severity=%s violations=%d",
            agent_name, check_result, severity, len(violations),
        )
        return result

    # ── 内部方法 ──

    @staticmethod
    def _extract_text(data: Any, depth: int = 0) -> str:
        """递归提取所有文本内容用于合规扫描"""
        if depth > 5:
            return ""
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            parts = []
            for v in data.values():
                parts.append(ComplianceAgent._extract_text(v, depth + 1))
            return " ".join(parts)
        if isinstance(data, (list, tuple)):
            parts = []
            for item in data:
                parts.append(ComplianceAgent._extract_text(item, depth + 1))
            return " ".join(parts)
        return str(data) if data is not None else ""

    @staticmethod
    def _has_absolute_prediction(text: str) -> bool:
        """检测绝对化预测表述"""
        patterns = [
            r"一定会[涨跌]",
            r"必然[上涨下跌]",
            r"肯定能赚",
            r"100%.*概率",
            r"零风险",
        ]
        for pat in patterns:
            if re.search(pat, text):
                return True
        return False

    @staticmethod
    def _apply_corrections(
        data: Dict[str, Any], corrections: Dict[str, str]
    ) -> Dict[str, Any]:
        """将违规表述替换为合规表述"""
        import json
        text = json.dumps(data, ensure_ascii=False)
        for old, new in corrections.items():
            text = text.replace(old, new)
        try:
            return json.loads(text)
        except Exception:
            return data
