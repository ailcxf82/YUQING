# -*- coding: utf-8 -*-
"""标准化预处理流水线

三阶段流水线：
  1. 数据清洗：过滤垃圾/广告、文本归一化、完整性校验
  2. 结构化信息提取：通过 LLM 提取 core_entity、related_stock、event_type、keywords
  3. 文本分块：对长文本按语义边界分块，为向量化做准备
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

from core.logger import get_logger
from core.prompts import get_prompt

logger = get_logger("preprocessor")

# ── 清洗规则 ──

_AD_PATTERNS = [
    r"点击.*关注",
    r"扫码.*领取",
    r"加微信",
    r"免费.*领取",
    r"广告",
    r"推广",
    r"https?://t\.cn/\S+",
    r"点击.*了解更多",
]
_AD_RE = re.compile("|".join(_AD_PATTERNS), re.IGNORECASE)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
MIN_CONTENT_LENGTH = 15
MAX_CHUNK_LENGTH = 500
CHUNK_OVERLAP = 50


class TextCleaner:
    """文本清洗模块"""

    @staticmethod
    def clean(text: str) -> str:
        if not text:
            return ""
        text = _HTML_TAG_RE.sub("", text)
        text = TextCleaner._normalize_unicode(text)
        text = TextCleaner._fullwidth_to_halfwidth(text)
        text = _MULTI_SPACE_RE.sub(" ", text)
        text = _MULTI_NEWLINE_RE.sub("\n\n", text)
        return text.strip()

    @staticmethod
    def is_valid(text: str) -> bool:
        """检查内容完整性：非空、非纯空白、达到最小长度、非纯广告"""
        if not text or len(text.strip()) < MIN_CONTENT_LENGTH:
            return False
        if _AD_RE.search(text) and len(text) < 80:
            return False
        return True

    @staticmethod
    def _normalize_unicode(text: str) -> str:
        return unicodedata.normalize("NFKC", text)

    @staticmethod
    def _fullwidth_to_halfwidth(text: str) -> str:
        result = []
        for ch in text:
            code = ord(ch)
            if 0xFF01 <= code <= 0xFF5E:
                result.append(chr(code - 0xFEE0))
            elif code == 0x3000:
                result.append(" ")
            else:
                result.append(ch)
        return "".join(result)


class TextChunker:
    """语义分块模块——对长文本按段落/句子边界切分"""

    @staticmethod
    def chunk(
        text: str,
        max_length: int = MAX_CHUNK_LENGTH,
        overlap: int = CHUNK_OVERLAP,
    ) -> List[str]:
        if not text or len(text) <= max_length:
            return [text] if text else []

        paragraphs = re.split(r"\n{2,}", text)
        if len(paragraphs) > 1:
            return TextChunker._chunk_paragraphs(paragraphs, max_length, overlap)

        sentences = re.split(r"(?<=[。！？；\.\!\?;])", text)
        return TextChunker._merge_sentences(sentences, max_length, overlap)

    @staticmethod
    def _chunk_paragraphs(
        paragraphs: List[str], max_len: int, overlap: int
    ) -> List[str]:
        chunks: List[str] = []
        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current) + len(para) + 1 <= max_len:
                current = (current + "\n" + para).strip()
            else:
                if current:
                    chunks.append(current)
                if len(para) > max_len:
                    sub = TextChunker._merge_sentences(
                        re.split(r"(?<=[。！？；\.\!\?;])", para), max_len, overlap
                    )
                    chunks.extend(sub)
                    current = ""
                else:
                    current = para
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _merge_sentences(
        sentences: List[str], max_len: int, overlap: int
    ) -> List[str]:
        chunks: List[str] = []
        current = ""
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(current) + len(sent) <= max_len:
                current += sent
            else:
                if current:
                    chunks.append(current)
                    tail = current[-overlap:] if overlap > 0 else ""
                    current = tail + sent
                else:
                    current = sent
        if current:
            chunks.append(current)
        return chunks


class StructuredExtractor:
    """基于 LLM 的结构化信息提取"""

    SYSTEM_PROMPT = get_prompt("preprocessor", "structured_extract")

    def __init__(self, llm_client: Any) -> None:
        self.llm = llm_client

    def extract(self, title: str, content: str) -> Dict[str, Any]:
        """对单条新闻提取结构化字段"""
        text = f"标题：{title}\n正文：{content[:1500]}"
        try:
            result = self.llm.chat_json(
                system_prompt=self.SYSTEM_PROMPT,
                user_prompt=text,
                temperature=0.1,
            )
            return {
                "core_entity": str(result.get("core_entity", "")),
                "related_stock": str(result.get("related_stock", "")),
                "event_type": str(result.get("event_type", "其他")),
                "keywords": result.get("keywords", []),
            }
        except Exception as e:
            logger.warning("LLM 结构化提取失败: %s", e)
            return {
                "core_entity": "",
                "related_stock": "",
                "event_type": "其他",
                "keywords": [],
            }

    def extract_batch(
        self, items: List[Dict[str, Any]], max_llm_calls: int = 50
    ) -> List[Dict[str, Any]]:
        """批量提取。超过 max_llm_calls 的部分跳过 LLM，仅做基础提取。"""
        for i, item in enumerate(items):
            if i < max_llm_calls:
                extracted = self.extract(
                    item.get("title", ""), item.get("content", "")
                )
            else:
                extracted = self._rule_based_extract(
                    item.get("title", ""), item.get("content", "")
                )
            item.update(extracted)
        return items

    @staticmethod
    def _rule_based_extract(title: str, content: str) -> Dict[str, Any]:
        """规则兜底：LLM 配额用尽时的简单规则提取"""
        text = title + content
        event_keywords = {
            "业绩": "业绩发布", "财报": "业绩发布", "年报": "业绩发布",
            "并购": "并购重组", "重组": "并购重组", "收购": "并购重组",
            "政策": "政策变动", "监管": "政策变动", "央行": "政策变动",
            "辞职": "人事变动", "任命": "人事变动", "董事": "人事变动",
            "新品": "产品发布", "发布会": "产品发布", "上市": "产品发布",
            "北向资金": "资金流向", "融资": "资金流向", "增持": "资金流向",
            "风险": "风险预警", "违规": "风险预警", "处罚": "风险预警",
        }
        event_type = "其他"
        for kw, etype in event_keywords.items():
            if kw in text:
                event_type = etype
                break
        return {
            "core_entity": "",
            "related_stock": "",
            "event_type": event_type,
            "keywords": [],
        }


class PreprocessPipeline:
    """预处理流水线：清洗 → 结构化提取 → 分块"""

    def __init__(self, llm_client: Optional[Any] = None, max_llm_calls: int = 50) -> None:
        self.cleaner = TextCleaner()
        self.chunker = TextChunker()
        self.extractor = StructuredExtractor(llm_client) if llm_client else None
        self.max_llm_calls = max_llm_calls

    def process(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """执行完整预处理流水线"""
        logger.info("预处理流水线启动 | 输入 %d 条", len(items))

        # 阶段 1: 清洗
        cleaned = []
        for item in items:
            item["title"] = self.cleaner.clean(item.get("title", ""))
            item["content"] = self.cleaner.clean(item.get("content", ""))
            text = item["title"] + item["content"]
            if self.cleaner.is_valid(text):
                cleaned.append(item)
        removed = len(items) - len(cleaned)
        if removed > 0:
            logger.info("清洗过滤 %d 条无效内容", removed)

        # 阶段 2: 结构化提取
        if self.extractor:
            cleaned = self.extractor.extract_batch(cleaned, self.max_llm_calls)
            logger.info("结构化提取完成 | %d 条", len(cleaned))

        # 阶段 3: 文本分块
        for item in cleaned:
            full_text = f"{item.get('title', '')}\n{item.get('content', '')}"
            item["chunk_texts"] = self.chunker.chunk(full_text)

        logger.info(
            "预处理流水线完成 | 输入=%d 输出=%d",
            len(items), len(cleaned),
        )
        return cleaned
