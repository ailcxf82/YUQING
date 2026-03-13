# -*- coding: utf-8 -*-
"""实体链接与标的精准关联模块 (3.1.1)

功能：
  1. 基于 LLM 的金融命名实体识别（公司、高管、监管机构、产品、产业链节点）
  2. 实体 → 股票代码的唯一映射（借助 Tushare stock_basic 缓存）
  3. 产业链上下游实体关联
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger("entity_linker")

# 缓存的股票名称→代码映射
_STOCK_MAP_CACHE: Dict[str, Dict[str, str]] = {}


class EntityLinker:
    """金融实体链接器"""

    NER_SYSTEM_PROMPT = (
        "你是金融命名实体识别专家。从给定新闻文本中提取所有金融相关实体。\n"
        "返回严格 JSON：\n"
        "{\n"
        '  "entities": [\n'
        '    {"name": "实体名称", "type": "company/person/regulator/product/industry/location", '
        '"role": "该实体在文本中的角色(主体/关联方/监管方)"}\n'
        "  ],\n"
        '  "primary_company": "核心涉及的上市公司名称(如有)",\n'
        '  "related_companies": ["关联公司1", "关联公司2"],\n'
        '  "industry_chain": {"upstream": ["上游公司/行业"], "downstream": ["下游公司/行业"]}\n'
        "}\n"
        "仅输出JSON。"
    )

    CHAIN_SYSTEM_PROMPT = (
        "你是产业链分析专家。给定一个上市公司名称及其所属行业，"
        "分析其产业链上下游核心企业与行业。\n"
        "返回严格 JSON：\n"
        "{\n"
        '  "company": "公司名称",\n'
        '  "industry": "所属行业",\n'
        '  "upstream": [{"name": "上游企业/行业", "relation": "关系描述"}],\n'
        '  "downstream": [{"name": "下游企业/行业", "relation": "关系描述"}],\n'
        '  "competitors": ["竞争对手1", "竞争对手2"]\n'
        "}\n"
        "仅输出JSON。"
    )

    def __init__(self, llm_client: Any, tushare_pro: Optional[Any] = None) -> None:
        self.llm = llm_client
        self._pro = tushare_pro
        self._stock_map: Dict[str, str] = {}
        self._load_stock_map()

    def _load_stock_map(self) -> None:
        """加载 Tushare 股票名称→代码映射（缓存）"""
        global _STOCK_MAP_CACHE
        if _STOCK_MAP_CACHE.get("loaded"):
            self._stock_map = _STOCK_MAP_CACHE.get("data", {})
            return

        if self._pro is None:
            try:
                import tushare as ts
                from core.config import get_config
                token = get_config().tushare_token
                if token:
                    self._pro = ts.pro_api(token)
            except Exception:
                pass

        if self._pro:
            try:
                df = self._pro.stock_basic(
                    exchange="", list_status="L",
                    fields="ts_code,name,industry,area"
                )
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        name = str(row.get("name", "")).strip()
                        code = str(row.get("ts_code", "")).strip()
                        if name and code:
                            self._stock_map[name] = code
                            short = name.replace("股份", "").replace("集团", "")
                            if short != name and len(short) >= 2:
                                self._stock_map[short] = code
                    _STOCK_MAP_CACHE["loaded"] = True
                    _STOCK_MAP_CACHE["data"] = self._stock_map
                    logger.info("股票映射表加载完成 | count=%d", len(self._stock_map))
            except Exception as e:
                logger.warning("股票映射表加载失败: %s", e)

    def extract_entities(self, title: str, content: str) -> Dict[str, Any]:
        """从新闻文本中提取金融实体"""
        text = f"标题：{title}\n正文：{content[:2000]}"
        try:
            result = self.llm.chat_json(
                system_prompt=self.NER_SYSTEM_PROMPT,
                user_prompt=text,
                temperature=0.1,
            )
            entities = result.get("entities", [])
            primary = result.get("primary_company", "")
            related = result.get("related_companies", [])
            chain = result.get("industry_chain", {})

            linked = self._link_entities(entities, primary)

            return {
                "entities": entities,
                "primary_company": primary,
                "primary_stock_code": linked.get("primary_code", ""),
                "related_companies": related,
                "related_stock_codes": linked.get("related_codes", {}),
                "industry_chain": chain,
            }
        except Exception as e:
            logger.warning("实体提取失败: %s", e)
            return {
                "entities": [],
                "primary_company": "",
                "primary_stock_code": "",
                "related_companies": [],
                "related_stock_codes": {},
                "industry_chain": {},
            }

    def link_to_stock(self, company_name: str) -> str:
        """将公司名称映射为股票代码"""
        if not company_name:
            return ""
        if company_name in self._stock_map:
            return self._stock_map[company_name]
        for name, code in self._stock_map.items():
            if company_name in name or name in company_name:
                return code
        return ""

    def get_industry_chain(self, company_name: str, industry: str = "") -> Dict[str, Any]:
        """获取产业链上下游分析"""
        prompt = f"公司名称：{company_name}"
        if industry:
            prompt += f"\n所属行业：{industry}"
        try:
            return self.llm.chat_json(
                system_prompt=self.CHAIN_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.2,
            )
        except Exception as e:
            logger.warning("产业链分析失败: %s", e)
            return {"company": company_name, "upstream": [], "downstream": [], "competitors": []}

    BATCH_NER_PROMPT = (
        "你是金融命名实体识别专家。从以下多条新闻中提取所有金融相关实体。\n"
        "返回严格JSON数组，每条对应一个news_id：\n"
        "[\n"
        '  {"news_id": "N1", "primary_company": "核心公司名", '
        '"related_companies": ["关联公司1"], "entities_count": 3},\n'
        '  {"news_id": "N2", "primary_company": "", '
        '"related_companies": [], "entities_count": 0}\n'
        "]\n"
        "仅输出JSON数组。必须为每条新闻都输出一条结果。"
    )

    def extract_entities_batch(
        self, items: List[Dict[str, Any]], batch_size: int = 50
    ) -> List[Dict[str, Any]]:
        """聚合批量实体提取：多条新闻组合为一次 LLM 调用"""
        all_results: List[Dict[str, Any]] = []

        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start:batch_start + batch_size]
            lines = []
            for i, item in enumerate(batch):
                nid = item.get("news_id", f"N{batch_start + i}")
                title = item.get("title", "")
                content = item.get("content", item.get("text", ""))[:100]
                lines.append(f"[{nid}] {title} | {content}")

            try:
                result_list = self.llm.chat_json_list(
                    system_prompt=self.BATCH_NER_PROMPT,
                    user_prompt="\n".join(lines),
                    temperature=0.1,
                )
                for r in result_list:
                    primary = r.get("primary_company", "")
                    primary_code = self.link_to_stock(primary) if primary else ""
                    related = r.get("related_companies", [])
                    related_codes = {}
                    for comp in related:
                        code = self.link_to_stock(comp)
                        if code:
                            related_codes[comp] = code
                    all_results.append({
                        "news_id": r.get("news_id", ""),
                        "entities": [],
                        "primary_company": primary,
                        "primary_stock_code": primary_code,
                        "related_companies": related,
                        "related_stock_codes": related_codes,
                        "industry_chain": {},
                    })
            except Exception as e:
                logger.warning("批量实体提取失败: %s", e)
                for item in batch:
                    all_results.append(self._empty_entity(item))

        while len(all_results) < len(items):
            all_results.append(self._empty_entity(items[len(all_results)]))

        return all_results

    @staticmethod
    def _empty_entity(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "news_id": item.get("news_id", ""),
            "entities": [],
            "primary_company": "",
            "primary_stock_code": "",
            "related_companies": [],
            "related_stock_codes": {},
            "industry_chain": {},
        }

    def _link_entities(
        self, entities: List[Dict], primary: str
    ) -> Dict[str, Any]:
        """批量链接实体到股票代码"""
        primary_code = self.link_to_stock(primary) if primary else ""
        related_codes: Dict[str, str] = {}
        for ent in entities:
            if ent.get("type") == "company":
                name = ent.get("name", "")
                code = self.link_to_stock(name)
                if code:
                    related_codes[name] = code
        return {"primary_code": primary_code, "related_codes": related_codes}
