# packages/poker_core/suggest/policy.py
# 策略：preflop_v0

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from ..domain.actions import LegalAction, legal_actions_struct
from poker_core.analysis import annotate_player_hand

def _clamp(target: int, lo: int, hi: int) -> int:
    return max(lo, min(target, hi))

def _find_action(acts: List[LegalAction], name: str) -> Optional[LegalAction]:
    for a in acts:
        if a.action == name:
            return a
    return None

def _to_call(acts: List[LegalAction]) -> int:
    a = _find_action(acts, "call")
    return int(a.to_call) if a and a.to_call is not None else 0

def policy_preflop_v0(gs, actor: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    """
    返回 (suggested, rationale[], policy_name)
    - suggested: {"action": "...", "amount"?: int}
    - rationale: [{"code": "...", "msg": "...", "data"?: {...}}]
    """
    acts = legal_actions_struct(gs)
    rationale: List[Dict[str, Any]] = []
    bb = getattr(gs, "bb", 50)

    if not acts:
        raise ValueError("No legal actions")

    to_call = _to_call(acts)
    # 仅使用可见信息做手牌分类（不偷看对手）
    playable_unopened = False
    try:
        hole = list(getattr(gs.players[actor], "hole", []) or [])
        if len(hole) == 2:
            ann = annotate_player_hand(hole)
            info = ann.get("info", {})
            pair = bool(info.get("pair"))
            suited = bool(info.get("suited"))
            high = int(info.get("high", 0))
            low = int(info.get("low", 0))
            is_broadway = (high >= 13 and low >= 10)
            is_suited_broadway = suited and is_broadway
            is_broadway_offsuit = (not suited) and is_broadway
            is_ax_suited = suited and (high == 14 or low == 14)
            playable_unopened = pair or is_suited_broadway or is_ax_suited or is_broadway_offsuit
            # 写入注释理由（非强制）
            if pair:
                rationale.append({"code": "N102", "msg": "口袋对子：纳入开局范围。"})
            elif is_suited_broadway:
                rationale.append({"code": "N102", "msg": "同花大牌：纳入开局范围。"})
            elif is_ax_suited:
                rationale.append({"code": "N102", "msg": "同花 Axs：纳入开局范围。"})
            elif is_broadway_offsuit:
                rationale.append({"code": "N102", "msg": "大牌非同花：纳入开局范围。"})
    except Exception:
        # 分类失败不影响建议计算
        playable_unopened = False

    # 1) 未面对下注（to_call == 0）
    if to_call == 0:
        bet = _find_action(acts, "bet")
        raise_ = _find_action(acts, "raise")
        target = int(round(2.5 * bb))
        # 未入池：仅在手牌“可开局”的情况下建议下注/加注；否则尽量选择过牌
        if playable_unopened and bet and bet.min is not None and bet.max is not None and bet.min <= bet.max:
            amt = _clamp(target, bet.min, bet.max)
            rationale.append({"code": "N101", "msg": "未入池（首攻），采用 2.5bb 开局尺寸。", "data": {"bb": bb, "target": target, "chosen": amt}})
            return ({"action": "bet", "amount": amt}, rationale, "preflop_v0")
        if playable_unopened and raise_ and raise_.min is not None and raise_.max is not None and raise_.min <= raise_.max:
            amt = _clamp(target, raise_.min, raise_.max)
            rationale.append({"code": "N101", "msg": "未入池（首攻），采用 2.5bb 开局尺寸。", "data": {"bb": bb, "target": target, "chosen": amt}})
            return ({"action": "raise", "amount": amt}, rationale, "preflop_v0")
        if _find_action(acts, "check"):
            rationale.append({"code": "N103", "msg": "无法下注，选择过牌以保持底池控制。"})
            return ({"action": "check"}, rationale, "preflop_v0")
        if _find_action(acts, "fold"):
            rationale.append({"code": "N104", "msg": "无更优可行动作，保底弃牌。"})
            return ({"action": "fold"}, rationale, "preflop_v0")

    # 2) 面对下注（to_call > 0）
    threshold = 3 * bb
    # 面对下注：对子或同花大牌 → 跟注；否则弃牌
    if _find_action(acts, "call"):
        # 若已分类可用则更严格过滤：仅对子/同花大牌
        strong_ok = False
        try:
            hole = list(getattr(gs.players[actor], "hole", []) or [])
            if len(hole) == 2:
                ann = annotate_player_hand(hole)
                info = ann.get("info", {})
                pair = bool(info.get("pair"))
                suited = bool(info.get("suited"))
                high = int(info.get("high", 0))
                low = int(info.get("low", 0))
                strong_ok = pair or (suited and high >= 13 and low >= 10)
        except Exception:
            strong_ok = False
        if strong_ok and to_call <= threshold:
            rationale.append({"code": "N201", "msg": "面对下注，牌力充足且代价不高（<=3bb），选择跟注。", "data": {"to_call": to_call, "threshold": threshold}})
            return ({"action": "call"}, rationale, "preflop_v0")

    if _find_action(acts, "fold"):
        rationale.append({"code": "N202", "msg": "面对下注且代价偏大，选择弃牌以保留筹码。", "data": {"to_call": to_call, "threshold": threshold}})
        return ({"action": "fold"}, rationale, "preflop_v0")

    if _find_action(acts, "check"):
        rationale.append({"code": "E001", "msg": "异常局面：回退为过牌。"})
        return ({"action": "check"}, rationale, "preflop_v0")

    raise ValueError("No safe suggestion")
