from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass(frozen=True)
class CodeDef:
    code: str
    severity: str  # info/warn/error（rationale 默认不输出 severity，仅供 note 使用）
    default_msg: str = ""
    legacy: List[str] = field(default_factory=list)


def mk_rationale(c: CodeDef, msg: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构造策略 rationale item（code/msg/data）。不包含 severity 字段。"""
    return {"code": c.code, "msg": (msg or c.default_msg), **({"data": data} if data else {})}


def mk_note(c: CodeDef, msg: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构造教学 note（含 severity）。供 analysis 使用。"""
    item = {"code": c.code, "severity": c.severity, "msg": (msg or c.default_msg)}
    if data is not None:
        item["data"] = data
    return item


class SCodes:
    # --- Analysis（保持现有对外 code 以兼容测试/UI） ---
    AN_WEAK = CodeDef("E001", "warn", "Weak hand: consider folding in many preflop spots.")
    AN_VERY_WEAK = CodeDef("E002", "warn", "Very weak offsuit/unconnected. Often a fold preflop.")
    AN_SUITED_BROADWAY = CodeDef("N101", "info", "Suited broadway: good equity/realization potential.")
    AN_SUITED_CONNECTED = CodeDef("N101", "info", "Suited & relatively connected. Potential for draws.")
    AN_PREMIUM_PAIR = CodeDef("N102", "info", "Premium pair: raise or 3-bet in many spots.")

    # --- Preflop 策略 ---
    PF_OPEN_BET = CodeDef("PF_OPEN_BET", "info", "未入池：{bb_mult}bb 开局（bet）。")
    PF_OPEN_RAISE = CodeDef("PF_OPEN_RAISE", "info", "未入池：{bb_mult}bb 开局（raise）。")
    PF_CHECK_NOT_IN_RANGE = CodeDef("PF_CHECK", "info", "不在开局白名单，选择过牌。")
    PF_FOLD_NO_BET = CodeDef("PF_FOLD", "info", "无更优可行动作，保底弃牌。")
    PF_CALL_THRESHOLD = CodeDef("PF_CALL", "info", "面对下注：范围内且代价不高（<=阈值），选择跟注。")
    PF_FOLD_EXPENSIVE = CodeDef("PF_FOLD_EXPENSIVE", "info", "面对下注：范围外或代价过高，弃牌。")

    # --- Postflop 策略 ---
    PL_HEADER = CodeDef("PL_HEADER", "info", "Postflop v0.3：hand tags + 赔率阈值 + 最小下注。")
    PL_PROBE_BET = CodeDef("PL_PROBE_BET", "info", "{street} 无人下注线：以最小尺寸试探性下注。")
    PL_CHECK = CodeDef("PL_CHECK", "info", "无法或不宜下注，选择过牌。")
    PL_CALL_POTODDS = CodeDef("PL_CALL", "info", "赔率可接受，选择跟注。")
    PL_FOLD_POTODDS = CodeDef("PL_FOLD", "info", "赔率不利，弃牌。")
    PL_ALLIN_ONLY = CodeDef("PL_ALLIN_ONLY", "info", "仅剩全下可选。")

    # --- 安全/告警 ---
    SAFE_CHECK = CodeDef("SAFE_CHECK", "info", "异常局面：回退为过牌。")
    WARN_CLAMPED = CodeDef("W_CLAMPED", "warn", "策略金额越界，已钳制至合法区间。")
    WARN_ANALYSIS_MISSING = CodeDef("W_ANALYSIS", "warn", "无法分析手牌，使用保守策略。")


__all__ = [
    "CodeDef",
    "mk_rationale",
    "mk_note",
    "SCodes",
]
