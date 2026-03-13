# -*- coding: utf-8 -*-
"""舆情数据定时采集 Job

将舆情数据采集从分析链路中解耦，作为独立的后台定时任务运行。
采集 → 预处理 → JSON 本地存储（主存储，零 API 依赖）
可选：→ 向量化 → LanceDB（供语义搜索）

数据存储在 data/news_store/ 目录下，按标的分文件。
采集配置持久化在 news_collect_config.json 中。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.collector import NewsCollector
from core.config import get_config
from core.datasources.tushare_source import TushareNewsSource
from core.llm import LLMClient
from core.logger import get_logger
from core.preprocessor import PreprocessPipeline

logger = get_logger("news_collect_job")

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "news_collect_config.json"
_STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "news_store"
_STORE_DIR.mkdir(parents=True, exist_ok=True)

_collect_status: Dict[str, Any] = {
    "last_run_at": None,
    "last_run_duration_ms": 0,
    "last_run_results": {},
    "total_runs": 0,
}


def _load_config() -> Dict[str, Any]:
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "enabled": True,
        "interval_minutes": 30,
        "symbols": [],
        "fetch_hours": 24,
    }


def _save_config(cfg: Dict[str, Any]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_config_data() -> Dict[str, Any]:
    return _load_config()


def add_symbol(symbol: str, name: str = "") -> Dict[str, Any]:
    """添加一个标的到定时采集列表"""
    cfg = _load_config()
    for s in cfg["symbols"]:
        if s["symbol"] == symbol:
            if name:
                s["name"] = name
            _save_config(cfg)
            return cfg
    cfg["symbols"].append({"symbol": symbol, "name": name})
    _save_config(cfg)
    logger.info("添加采集标的 | symbol=%s name=%s", symbol, name)
    return cfg


def remove_symbol(symbol: str) -> Dict[str, Any]:
    """从采集列表中移除标的"""
    cfg = _load_config()
    cfg["symbols"] = [s for s in cfg["symbols"] if s["symbol"] != symbol]
    _save_config(cfg)
    logger.info("移除采集标的 | symbol=%s", symbol)
    return cfg


def set_interval(minutes: int) -> int:
    """设置采集间隔"""
    minutes = max(5, min(1440, minutes))
    cfg = _load_config()
    cfg["interval_minutes"] = minutes
    _save_config(cfg)
    return minutes


def set_enabled(enabled: bool) -> bool:
    cfg = _load_config()
    cfg["enabled"] = enabled
    _save_config(cfg)
    return enabled


def get_status() -> Dict[str, Any]:
    cfg = _load_config()
    return {
        **cfg,
        "status": _collect_status,
        "local_data": _list_local_data(),
    }


def _list_local_data() -> List[Dict[str, Any]]:
    """列出本地已存储的舆情数据文件"""
    result = []
    try:
        for f in _STORE_DIR.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                items = data.get("items", [])
                count = len(items)
                latest = items[0].get("publish_time", "") if items else ""
                result.append({
                    "file": f.name,
                    "symbol": data.get("symbol", ""),
                    "records": count,
                    "latest_time": latest,
                    "collected_at": data.get("collected_at", ""),
                })
            except Exception:
                result.append({"file": f.name, "records": -1, "latest_time": ""})
    except Exception:
        pass
    return result


def collect_for_symbol(
    symbol: str,
    name: str = "",
    hours: int = 24,
) -> Dict[str, Any]:
    """为单个标的执行一次完整采集流程

    采集 → 预处理 → JSON 本地存储（无 embedding API 依赖）
    """
    start = time.time()
    logger.info("采集开始 | symbol=%s name=%s hours=%d", symbol, name, hours)

    sys_cfg = get_config()
    llm = LLMClient(sys_cfg)

    collector = NewsCollector()
    try:
        tushare_src = TushareNewsSource()
        collector.add_source(tushare_src)
    except Exception as e:
        logger.warning("Tushare 数据源注册失败: %s", e)

    now = datetime.now()
    end_date = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(hours=hours)).strftime("%Y-%m-%d")

    collector.reset_seen()
    raw_items = collector.collect(
        symbol=symbol, name=name,
        start_date=start_date, end_date=end_date,
    )
    logger.info("原始采集 | symbol=%s raw=%d", symbol, len(raw_items))

    if not raw_items:
        return {
            "symbol": symbol, "name": name,
            "raw": 0, "processed": 0, "stored": 0,
            "file": "", "duration_ms": int((time.time() - start) * 1000),
        }

    preprocessor = PreprocessPipeline(llm_client=llm, max_llm_calls=50)
    processed = preprocessor.process(raw_items)
    logger.info("预处理完成 | symbol=%s processed=%d", symbol, len(processed))

    stored = _save_to_json(processed, symbol, name)

    duration = int((time.time() - start) * 1000)
    file_name = _symbol_to_filename(symbol)
    logger.info(
        "采集完成 | symbol=%s raw=%d processed=%d stored=%d file=%s duration=%dms",
        symbol, len(raw_items), len(processed), stored, file_name, duration,
    )
    return {
        "symbol": symbol, "name": name,
        "raw": len(raw_items), "processed": len(processed),
        "stored": stored, "file": file_name,
        "duration_ms": duration,
    }


def _symbol_to_filename(symbol: str) -> str:
    return f"news_{symbol.replace('.', '_').lower()}.json" if symbol else "news_general.json"


def _save_to_json(items: List[Dict[str, Any]], symbol: str, name: str) -> int:
    """将预处理后的数据存储为 JSON 文件（无 API 依赖）"""
    file_name = _symbol_to_filename(symbol)
    file_path = _STORE_DIR / file_name

    clean_items = []
    for item in items:
        kw = item.get("keywords", [])
        if isinstance(kw, str):
            kw = kw.split(",") if kw else []
        clean_items.append({
            "news_id": item.get("news_id", ""),
            "title": item.get("title", ""),
            "content": item.get("content", "")[:3000],
            "publish_time": item.get("publish_time", ""),
            "source": item.get("source", ""),
            "source_level": item.get("source_level", "C"),
            "source_weight": float(item.get("source_weight", 0.5)),
            "url": item.get("url", ""),
            "core_entity": item.get("core_entity", ""),
            "related_stock": item.get("related_stock", ""),
            "event_type": item.get("event_type", ""),
            "keywords": kw,
            "spread_count": int(item.get("spread_count", 0)),
            "symbol": item.get("symbol", symbol),
            "content_hash": item.get("content_hash", ""),
        })

    clean_items.sort(key=lambda x: x.get("publish_time", ""), reverse=True)

    data = {
        "symbol": symbol,
        "name": name,
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(clean_items),
        "items": clean_items,
    }

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("JSON 存储完成 | file=%s count=%d", file_name, len(clean_items))
    return len(clean_items)


def collect_all() -> Dict[str, Any]:
    """对配置中所有标的执行一次采集"""
    cfg = _load_config()
    if not cfg.get("enabled", True):
        return {"skipped": True, "reason": "采集已禁用"}

    symbols = cfg.get("symbols", [])
    hours = cfg.get("fetch_hours", 24)
    if not symbols:
        return {"skipped": True, "reason": "无配置标的"}

    start = time.time()
    results = {}
    for s in symbols:
        sym = s.get("symbol", "")
        nm = s.get("name", "")
        if sym:
            results[sym] = collect_for_symbol(sym, nm, hours)

    duration = int((time.time() - start) * 1000)

    global _collect_status
    _collect_status = {
        "last_run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_run_duration_ms": duration,
        "last_run_results": {
            k: {"raw": v["raw"], "processed": v["processed"], "stored": v["stored"]}
            for k, v in results.items()
        },
        "total_runs": _collect_status.get("total_runs", 0) + 1,
    }

    logger.info("全量采集完成 | symbols=%d duration=%dms", len(results), duration)
    return {"results": results, "duration_ms": duration}


def read_local_news(
    symbol: str = "",
    start_time: str = "",
    end_time: str = "",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """从本地 JSON 文件读取已采集的舆情数据——供分析链路使用

    这是分析链路获取数据的唯一入口，不触发任何网络请求。
    纯文件读取，响应时间 <10ms。
    """
    file_name = _symbol_to_filename(symbol)
    file_path = _STORE_DIR / file_name

    if not file_path.exists():
        logger.info("本地无数据 | file=%s (请先配置定时采集)", file_name)
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data.get("items", [])

        if start_time:
            items = [i for i in items if i.get("publish_time", "") >= start_time]
        if end_time:
            items = [i for i in items if i.get("publish_time", "") <= end_time]

        items = items[:limit]

        logger.info("本地读取 | file=%s records=%d", file_name, len(items))
        return items

    except Exception as e:
        logger.warning("本地数据读取失败: %s", e)
        return []
