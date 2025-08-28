# packages/poker_core/suggest/policy.py
# 策略：preflop_v0, postflop_v0_3


from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from ..domain.actions import LegalAction, legal_actions_struct
from ..analysis import annotate_player_hand_from_gs, in_open_range, in_call_range

def _clamp(target: int, lo: int, hi: int) -> int:
    return max(lo, min(target, hi))

def _find_action(acts: List[LegalAction], name: str) -> Optional[LegalAction]:
    return next((a for a in acts if a.action == name), None)

def _to_call(acts: List[LegalAction]) -> int:
    a = _find_action(acts, "call")
    return int(a.to_call) if a and a.to_call is not None else 0

def policy_preflop_v0(gs, actor: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    """
    Preflop策略v0：基于手牌强度做基础决策
    - 未面对下注时：范围内的手牌采用2.5bb开局，否则过牌
    - 面对下注时：范围内的手牌且代价不高则跟注，否则弃牌

    返回 (suggested, rationale[], policy_name)
    - suggested: {"action": "...", "amount"?: int}
    - rationale: [{"code": "...", "msg": "...", "data"?: {...}}]
    """
    acts = legal_actions_struct(gs)
    if not acts: raise ValueError("No legal actions")
    rationale: List[Dict[str, Any]] = []
    bb = int(getattr(gs, "bb", 50))
    to_call = _to_call(acts)

    # 单次分类（避免重复计算）
    try:
        ann = annotate_player_hand_from_gs(gs, actor)
        info = ann.get("info", {})
        notes = ann.get("notes", [])
        rationale.extend([n for n in notes if n.get("severity") == "info"])
    except Exception:
        # 分析失败时，使用保守策略
        info = {"tags": ["unknown"], "hand_class": "unknown"}
        rationale.append({"code": "W001", "severity": "warn", "msg": "无法分析手牌，使用保守策略。"})

    # 1) 未面对下注（to_call == 0）
    if to_call == 0:
        if in_open_range(info):
            target = int(round(2.5 * bb))
            bet = _find_action(acts, "bet")
            raise_ = _find_action(acts, "raise")
            if bet and bet.min is not None and bet.max is not None and bet.min <= bet.max:
                amt = _clamp(target, bet.min, bet.max)
                rationale.append({"code": "N101", "msg": "未入池：2.5bb 开局（bet）。", "data": {"bb": bb, "chosen": amt}})
                return ({"action": "bet", "amount": amt}, rationale, "preflop_v0")
            if raise_ and raise_.min is not None and raise_.max is not None and raise_.min <= raise_.max:
                amt = _clamp(target, raise_.min, raise_.max)
                rationale.append({"code": "N102", "msg": "未入池：2.5bb 开局（raise）。", "data": {"bb": bb, "chosen": amt}})
                return ({"action": "raise", "amount": amt}, rationale, "preflop_v0")
        # 不在范围：优先过牌
        if _find_action(acts, "check"):
            rationale.append({"code": "N103", "msg": "不在开局白名单，选择过牌。"})
            return ({"action": "check"}, rationale, "preflop_v0")
        if _find_action(acts, "fold"):
            rationale.append({"code": "N104", "msg": "无更优可行动作，保底弃牌。"})
            return ({"action": "fold"}, rationale, "preflop_v0")

    # 2) 面对下注（to_call > 0）
    threshold = 3 * bb
    if in_call_range(info) and _find_action(acts, "call") and to_call <= threshold:
        rationale.append({"code": "N201", "msg": "面对下注：范围内且代价不高（<=3bb），选择跟注。", "data": {"to_call": to_call, "threshold": threshold}})
        return ({"action": "call"}, rationale, "preflop_v0")

    if _find_action(acts, "fold"):
        rationale.append({"code": "N202", "msg": "面对下注：范围外或代价过高，弃牌。", "data": {"to_call": to_call, "threshold": threshold}})
        return ({"action": "fold"}, rationale, "preflop_v0")

    if _find_action(acts, "check"):
        rationale.append({"code": "E001", "msg": "异常局面：回退为过牌。"})
        return ({"action": "check"}, rationale, "preflop_v0")

    raise ValueError("No safe suggestion")

# --- postflop_v0_3 ---

def policy_postflop_v0_3(gs, actor: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    acts = legal_actions_struct(gs)
    if not acts:
        raise ValueError("No legal actions")

    street = getattr(gs, "street", "flop")
    bb = int(getattr(gs, "bb", 50))
    pot = int(getattr(gs, "pot", 0))

    ann = annotate_player_hand_from_gs(gs, actor)
    info = ann.get("info", {})

    rationale: List[Dict[str, Any]] = [
        {"code": "P300", "msg": "Postflop v0.3：hand tags + 赔率阈值 + 最小下注。", "data": {"street": street, "tags": info.get("tags")}}
    ]

    to_call = _to_call(acts)

    # 无人下注线：在 flop 优先用最小下注做试探（若有 bet/raise），turn/river 仍保守
    if to_call == 0:
        bet = _find_action(acts, "bet") or _find_action(acts, "raise")
        if bet and bet.min is not None and bet.max is not None and bet.min <= bet.max:
            # 简规则：flop 上直接用最小下注；turn/river 仅当有一定摊牌价值（pair 或 Ax_suited）再下注
            if street == "flop" or (street in {"turn", "river"} and ("pair" in info.get("tags", []) or info.get("hand_class") == "Ax_suited")):
                amt = int(bet.min)
                rationale.append({"code": "P301", "msg": f"{street} 无人下注线：以最小尺寸试探性下注。", "data": {"chosen": amt}})
                return ({"action": bet.action, "amount": amt}, rationale, "postflop_v0_3")
        if _find_action(acts, "check"):
            rationale.append({"code": "P302", "msg": "无法或不宜下注，选择过牌。"})
            return ({"action": "check"}, rationale, "postflop_v0_3")

    # 面对下注：按赔率阈值决定跟注或弃牌；范围内手牌放宽阈值
    # pot_odds = to_call / (pot + to_call)
    denom = pot + to_call
    pot_odds = (to_call / denom) if denom > 0 else 1.0
    base_threshold = 0.33
    if in_call_range(info):
        threshold = 0.40  # 范围内更愿意跟注
    else:
        threshold = base_threshold

    call = _find_action(acts, "call")
    if call and pot_odds <= threshold:
        rationale.append({"code": "P311", "msg": "赔率可接受，选择跟注。", "data": {"to_call": to_call, "pot": pot, "pot_odds": round(pot_odds, 4), "threshold": threshold}})
        return ({"action": "call"}, rationale, "postflop_v0_3")

    if _find_action(acts, "fold"):
        rationale.append({"code": "P312", "msg": "赔率不利，弃牌。", "data": {"to_call": to_call, "pot": pot, "pot_odds": round(pot_odds, 4), "threshold": threshold}})
        return ({"action": "fold"}, rationale, "postflop_v0_3")

    # 兜底：仅当只剩 allin
    allin = _find_action(acts, "allin")
    if allin:
        rationale.append({"code": "P399", "msg": "仅剩全下可选。"})
        return ({"action": "allin", "amount": allin.max or allin.min}, rationale, "postflop_v0_3")

    if _find_action(acts, "check"):
        rationale.append({"code": "E002", "msg": "异常局面：回退为过牌。"})
        return ({"action": "check"}, rationale, "postflop_v0_3")

    raise ValueError("No safe postflop suggestion")