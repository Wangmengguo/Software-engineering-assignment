"""
packages/poker_core/suggest/policy.py

策略：preflop_v0, postflop_v0_3（纯函数版本）
签名改造：只接收 Observation/PolicyConfig；不直接依赖 GameState/analysis/metrics。
返回值保持原契约： (suggested: dict, rationale: list[dict], policy_name: str)
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple

from .types import Observation, PolicyConfig
from .utils import pick_betlike_action, find_action, to_call_from_acts
from .codes import SCodes, mk_rationale as R


# 与 analysis 中口径保持一致的范围判定（避免耦合：基于 tags/hand_class）
OPEN_RANGE_TAGS = {"pair", "suited_broadway", "Ax_suited", "broadway_offsuit"}
CALL_RANGE_TAGS = {"pair", "suited_broadway", "Ax_suited", "broadway_offsuit"}


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(int(v), hi))


def _in_open_range(tags: List[str], hand_class: str) -> bool:
    s = set(tags or [])
    return bool(s & OPEN_RANGE_TAGS) or hand_class in ("Ax_suited", "suited_broadway", "broadway_offsuit", "pair")


def _in_call_range(tags: List[str], hand_class: str) -> bool:
    s = set(tags or [])
    return bool(s & CALL_RANGE_TAGS) or hand_class in ("Ax_suited", "suited_broadway", "broadway_offsuit", "pair")


def policy_preflop_v0(obs: Observation, cfg: PolicyConfig) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    """Preflop 策略 v0（纯函数）。

    规则：
    - 未面对下注：范围内以 open_size_bb*bb 开局（bet/raise），否则优先 check。
    - 面对下注：范围内且 to_call <= call_threshold_bb*bb → call，否则 fold。
    """
    acts = list(obs.acts or [])
    if not acts:
        raise ValueError("No legal actions")

    rationale: List[Dict[str, Any]] = []
    bb = int(obs.bb)
    to_call = int(obs.to_call if obs.to_call is not None else to_call_from_acts(acts))

    # 1) 未面对下注
    if to_call == 0:
        if _in_open_range(obs.tags, obs.hand_class):
            betlike = pick_betlike_action(acts)
            if betlike and betlike.min is not None and betlike.max is not None and betlike.min <= betlike.max:
                target = int(round(cfg.open_size_bb * bb))
                amt = _clamp(target, betlike.min, betlike.max)
                code_def = SCodes.PF_OPEN_BET if betlike.action == "bet" else SCodes.PF_OPEN_RAISE
                rationale.append(R(code_def, msg=f"未入池：{cfg.open_size_bb}bb 开局（{betlike.action}）。", data={"bb": bb, "chosen": amt, "bb_mult": cfg.open_size_bb}))
                return ({"action": betlike.action, "amount": amt}, rationale, "preflop_v0")
        # 不在范围：优先过牌
        if find_action(acts, "check"):
            rationale.append(R(SCodes.PF_CHECK_NOT_IN_RANGE))
            return ({"action": "check"}, rationale, "preflop_v0")
        if find_action(acts, "fold"):
            rationale.append(R(SCodes.PF_FOLD_NO_BET))
            return ({"action": "fold"}, rationale, "preflop_v0")

    # 2) 面对下注
    threshold = int(cfg.call_threshold_bb * bb)
    if _in_call_range(obs.tags, obs.hand_class) and find_action(acts, "call") and to_call <= threshold:
        rationale.append(R(SCodes.PF_CALL_THRESHOLD, data={"to_call": to_call, "threshold": threshold}))
        return ({"action": "call"}, rationale, "preflop_v0")

    if find_action(acts, "fold"):
        rationale.append(R(SCodes.PF_FOLD_EXPENSIVE, data={"to_call": to_call, "threshold": threshold}))
        return ({"action": "fold"}, rationale, "preflop_v0")

    if find_action(acts, "check"):
        rationale.append(R(SCodes.SAFE_CHECK))
        return ({"action": "check"}, rationale, "preflop_v0")

    raise ValueError("No safe suggestion")


def policy_postflop_v0_3(obs: Observation, cfg: PolicyConfig) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    """Postflop 策略 v0.3（纯函数）。

    - 无人下注线：flop 用最小试探注；turn/river 仅在具备一定摊牌价值（pair/Ax_suited）下注。
    - 面对下注线：按 pot-odds 与阈值决定 call 或 fold；范围内手牌使用更宽松阈值。
    """
    acts = list(obs.acts or [])
    if not acts:
        raise ValueError("No legal actions")

    rationale: List[Dict[str, Any]] = [
        R(SCodes.PL_HEADER, data={"street": obs.street, "tags": list(obs.tags or [])}),
    ]

    to_call = int(obs.to_call if obs.to_call is not None else to_call_from_acts(acts))
    pot = int(obs.pot)

    # 无人下注线
    if to_call == 0:
        betlike = pick_betlike_action(acts)
        if betlike and betlike.min is not None and betlike.max is not None and betlike.min <= betlike.max:
            allow_bet = (obs.street == "flop") or (obs.street in {"turn", "river"} and ("pair" in (obs.tags or []) or obs.hand_class == "Ax_suited"))
            if allow_bet:
                amt = int(betlike.min)
                rationale.append(R(SCodes.PL_PROBE_BET, msg=f"{obs.street} 无人下注线：以最小尺寸试探性下注。", data={"chosen": amt}))
                return ({"action": betlike.action, "amount": amt}, rationale, "postflop_v0_3")
        if find_action(acts, "check"):
            rationale.append(R(SCodes.PL_CHECK))
            return ({"action": "check"}, rationale, "postflop_v0_3")

    # 面对下注线：赔率判断
    denom = pot + to_call
    pot_odds = (to_call / denom) if denom > 0 else 1.0
    threshold = cfg.pot_odds_threshold_callrange if _in_call_range(obs.tags, obs.hand_class) else cfg.pot_odds_threshold

    if find_action(acts, "call") and pot_odds <= threshold:
        rationale.append(R(SCodes.PL_CALL_POTODDS, data={"to_call": to_call, "pot": pot, "pot_odds": round(pot_odds, 4), "threshold": threshold}))
        return ({"action": "call"}, rationale, "postflop_v0_3")

    if find_action(acts, "fold"):
        rationale.append(R(SCodes.PL_FOLD_POTODDS, data={"to_call": to_call, "pot": pot, "pot_odds": round(pot_odds, 4), "threshold": threshold}))
        return ({"action": "fold"}, rationale, "postflop_v0_3")

    # 兜底
    allin = find_action(acts, "allin")
    if allin:
        rationale.append(R(SCodes.PL_ALLIN_ONLY))
        return ({"action": "allin", "amount": allin.max or allin.min}, rationale, "postflop_v0_3")

    if find_action(acts, "check"):
        rationale.append(R(SCodes.SAFE_CHECK))
        return ({"action": "check"}, rationale, "postflop_v0_3")

    raise ValueError("No safe postflop suggestion")


__all__ = [
    "policy_preflop_v0",
    "policy_postflop_v0_3",
]
