# poker_core/suggest/utils.py
from __future__ import annotations

from hashlib import sha1
from math import isfinite
from typing import Any

from poker_core.domain.actions import LegalAction


def pick_betlike_action(acts: list[LegalAction]) -> LegalAction | None:
    # 先 bet，再退而求其次 raise
    for name in ("bet", "raise"):
        a = next((x for x in acts if x.action == name), None)
        if a and a.min is not None and a.max is not None and a.min <= a.max:
            return a
    return None


def find_action(acts: list[LegalAction], name: str) -> LegalAction | None:
    return next((a for a in acts if a.action == name), None)


def to_call_from_acts(acts: list[LegalAction]) -> int:
    a = find_action(acts, "call")
    return int(a.to_call) if a and a.to_call is not None else 0


# ----- PR-0: helpers for v1 baseline (kept unused by default) -----


def calc_spr(pot_now: int, eff_stack: int) -> float:
    """SPR 定义（决策点）：
    spr = eff_stack / pot_now；当 pot_now<=0 时返回 float('inf') 并由 bucket 做 'na' 处理。

    说明：街首 SPR 可在进入新街时用 (effective_stack_at_street_start / pot_at_street_start)。
    这里提供通用决策点口径（更常用）。
    """
    try:
        pot = float(pot_now)
        if pot <= 0:
            return float("inf")
        return float(eff_stack) / pot
    except Exception:
        return float("inf")


def spr_bucket(spr: float) -> str:
    """按阈值分桶：≤3 / 3–6 / ≥6；无法计算返回 'na'。"""
    if spr is None or not isfinite(float(spr)):
        return "na"
    try:
        v = float(spr)
        if v <= 3.0:
            return "low"
        if v <= 6.0:
            return "mid"
        return "high"
    except Exception:
        return "na"


def classify_flop(board: list[str]) -> dict[str, Any]:
    """简化的翻面纹理分类。
    返回：{texture:'dry|semi|wet|na', paired:bool, fd:bool, sd:bool}
    规则（近似且稳定）：
      - <3 张公共牌 → na
      - 若有对子或三张同花或三连顺/双连顺 → wet
      - 两张同花或两张相连（含 1-gap） → semi
      - 否则 dry
    """
    if not board or len(board) < 3:
        return {"texture": "na", "paired": False, "fd": False, "sd": False}

    # ranks / suits 提取
    ranks = [c[:-1] for c in board[:3]]
    suits = [c[-1] for c in board[:3]]
    # paired
    paired = len(set(ranks)) < 3
    # 同花倾向
    s_counts: dict[str, int] = {}
    for s in suits:
        s_counts[s] = s_counts.get(s, 0) + 1
    three_suited = any(v == 3 for v in s_counts.values())
    two_suited = any(v == 2 for v in s_counts.values())
    fd = three_suited or two_suited  # 简化：两同花即认为有同花倾向

    # 顺听倾向（粗略，以排序后相邻差值衡量）
    RANK_ORDER = {
        "2": 2,
        "3": 3,
        "4": 4,
        "5": 5,
        "6": 6,
        "7": 7,
        "8": 8,
        "9": 9,
        "T": 10,
        "J": 11,
        "Q": 12,
        "K": 13,
        "A": 14,
    }
    vals = sorted(RANK_ORDER.get(r, 0) for r in ranks)
    gaps = [vals[1] - vals[0], vals[2] - vals[1]]
    connected = (gaps[0] <= 1 and gaps[1] <= 1) or (gaps[0] == 2 or gaps[1] == 2)
    sd = connected

    if paired or three_suited or (connected and two_suited):
        texture = "wet"
    elif two_suited or connected:
        texture = "semi"
    else:
        texture = "dry"

    return {"texture": texture, "paired": paired, "fd": fd, "sd": sd}


def position_of(actor: int, table_mode: str, button: int, street: str) -> str:
    """最小位置映射（PR-0：HU 优先）。
    HU：button 为 SB；另一位为 BB。
    其它桌型占位实现（后续 PR 扩展）。
    """
    try:
        if (table_mode or "HU").upper() == "HU":
            return "SB" if actor == int(button) else "BB"
    except Exception:
        pass
    # 占位：未知/未实现
    return "NA"


def is_ip(actor: int, table_mode: str, button: int, street: str) -> bool:
    """判断 actor 在当前街是否“在位”（最后行动）。
    HU：preflop 按钮先手（OOP），翻后按钮后手（IP）。
    """
    try:
        if (table_mode or "HU").upper() == "HU":
            if street == "preflop":
                return actor != int(button)
            else:
                return actor == int(button)
    except Exception:
        return False
    return False


def active_player_count(gs) -> int:
    """现阶段引擎为 HU，固定返回 2。
    若传入对象含 players，则断言其长度为 2（帮助在测试/开发期尽早发现误用）。
    """
    try:
        players = getattr(gs, "players", None)
        if players is not None:
            assert len(players) == 2, "HU engine expects exactly 2 players"
    except AttributeError:
        # 忽略属性访问错误，继续返回默认值
        pass
    return 2


def size_to_amount(pot: int, last_bet: int, size_tag: str, bb: int) -> int | None:
    """根据 size_tag 计算目标下注量（bet 语义）。
    raise 语义后续可在策略中基于 min-raise 规则转换；
    这里提供统一的锅份额到金额换算。
    """
    if size_tag is None:
        return None
    sizing_map = {
        "third": 1.0 / 3.0,
        "half": 0.5,
        "two_third": 2.0 / 3.0,
        "pot": 1.0,
        "all_in": 10.0,  # 实际会被后续 min(hero_stack, max) 钳制
    }
    mult = sizing_map.get(size_tag)
    if mult is None:
        return None
    base = max(0, int(round(float(pot) * mult)))
    # 下注最小值通常 >= bb；此处先返回裸值，交由 service 钳制
    return max(base, 1)


def stable_roll(hand_id: str, pct: int) -> bool:
    """稳定灰度：使用 sha1(hand_id) 取模决定是否命中 [0, pct)。
    pct 超界会被裁剪到 [0,100]。
    """
    q = max(0, min(int(pct or 0), 100))
    if q <= 0:
        return False
    if q >= 100:
        return True
    h = sha1((hand_id or "").encode("utf-8")).hexdigest()
    # 取前 8 字节作为无符号整数
    bucket = int(h[:8], 16) % 100
    return bucket < q


def drop_nones(d: dict[str, Any]) -> dict[str, Any]:
    """剔除值为 None 的键（浅层）。"""
    return {k: v for k, v in (d or {}).items() if v is not None}
