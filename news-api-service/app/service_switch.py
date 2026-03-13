# -*- coding: utf-8 -*-
"""服务开启/关闭开关：内存状态 + 持久化到本地文件"""
import json
from pathlib import Path

# 默认开启；持久化文件相对项目根目录
_SWITCH_FILE = Path(__file__).resolve().parent.parent / "service_switch.json"
_enabled: bool = True


def _load() -> bool:
    global _enabled
    if _SWITCH_FILE.exists():
        try:
            with open(_SWITCH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _enabled = data.get("enabled", True)
                return _enabled
        except Exception:
            pass
    _enabled = True
    return _enabled


def _save(enabled: bool) -> None:
    _SWITCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_SWITCH_FILE, "w", encoding="utf-8") as f:
        json.dump({"enabled": enabled}, f, ensure_ascii=False, indent=2)


def is_enabled() -> bool:
    """当前服务是否开启"""
    return _enabled


def set_enabled(enabled: bool) -> bool:
    """设置开关并持久化，返回设置后的状态"""
    global _enabled
    _enabled = bool(enabled)
    _save(_enabled)
    return _enabled


# 启动时从文件恢复
_load()
