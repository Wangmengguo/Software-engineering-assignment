from __future__ import annotations

from functools import lru_cache
from typing import Any

from .config_loader import load_json_cached


def _config_path_for_strategy(strategy: str) -> str:
    s = (strategy or "medium").lower()
    if s not in ("loose", "medium", "tight"):
        s = "medium"
    return f"postflop/flop_rules_HU_{s}.json"


@lru_cache(maxsize=8)
def load_flop_rules(strategy: str) -> tuple[dict[str, Any], int]:
    rel = _config_path_for_strategy(strategy)
    data, ver = load_json_cached(rel)
    return (data or {}), int(ver or 0)


def get_flop_rules() -> tuple[dict[str, Any], int]:
    import os

    s = os.getenv("SUGGEST_STRATEGY", "medium").lower()
    return load_flop_rules(s)


__all__ = ["get_flop_rules", "load_flop_rules"]
