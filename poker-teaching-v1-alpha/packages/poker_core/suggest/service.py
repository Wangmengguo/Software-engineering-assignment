# packages/poker_core/suggest/service.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional, Callable

from ..domain.actions import to_act_index, legal_actions_struct, LegalAction
from ..analysis import annotate_player_hand_from_gs
from .policy import policy_preflop_v0, policy_postflop_v0_3
from .types import Observation, PolicyConfig
from .utils import to_call_from_acts
from .codes import SCodes, mk_rationale as R


def _clamp_amount_if_needed(suggested: Dict[str, Any], acts: List[LegalAction]) -> Tuple[Dict[str, Any], bool, Dict[str, Optional[int]]]:
    """将建议金额钳制到合法区间，并返回是否发生钳制及边界信息。"""
    name = suggested.get("action")
    if name not in {"bet", "raise", "allin"}:
        return suggested, False, {"min": None, "max": None, "given": None, "chosen": None}
    amt = suggested.get("amount")
    if amt is None:
        return suggested, False, {"min": None, "max": None, "given": None, "chosen": None}
    spec = next((a for a in acts if a.action == name), None)
    if not spec:
        return suggested, False, {"min": None, "max": None, "given": int(amt), "chosen": int(amt)}
    lo = spec.min if spec.min is not None else int(amt)
    hi = spec.max if spec.max is not None else int(amt)
    if lo is None or hi is None:
        return suggested, False, {"min": None, "max": None, "given": int(amt), "chosen": int(amt)}
    clamped_val = max(lo, min(int(amt), hi))
    if clamped_val != amt:
        s2 = dict(suggested)
        s2["amount"] = clamped_val
        return s2, True, {"min": int(lo), "max": int(hi), "given": int(amt), "chosen": int(clamped_val)}
    return suggested, False, {"min": int(lo), "max": int(hi), "given": int(amt), "chosen": int(amt)}


# 策略注册表：按 street 选择
PolicyFn = Callable[[Observation, PolicyConfig], Tuple[Dict[str, Any], List[Dict[str, Any]], str]]
POLICY_REGISTRY: Dict[str, PolicyFn] = {
    "preflop": policy_preflop_v0,
    "flop": policy_postflop_v0_3,
    "turn": policy_postflop_v0_3,
    "river": policy_postflop_v0_3,
}


def _build_observation(gs, actor: int, acts: List[LegalAction]) -> Observation:
    # 从 analysis 取 tags/hand_class（失败时降级 unknown）
    try:
        ann = annotate_player_hand_from_gs(gs, actor)
        info = ann.get("info", {})
        tags = list(info.get("tags", []) or [])
        hand_class = info.get("hand_class", "unknown")
    except Exception:
        tags, hand_class = ["unknown"], "unknown"

    hand_id = str(getattr(gs, "hand_id", ""))
    street = str(getattr(gs, "street", "preflop"))
    bb = int(getattr(gs, "bb", 50))
    pot = int(getattr(gs, "pot", 0))
    to_call = int(to_call_from_acts(acts))

    return Observation(
        hand_id=hand_id,
        actor=int(actor),
        street=street,
        bb=bb,
        pot=pot,
        to_call=to_call,
        acts=acts,
        tags=tags,
        hand_class=str(hand_class),
    )


def build_suggestion(gs, actor: int, cfg: Optional[PolicyConfig] = None) -> Dict[str, Any]:
    """Suggest 入口（纯函数策略版）。

    契约：
    - 若 actor != gs.to_act → PermissionError（视图层转 409）
    - 若无法产生合法建议 → ValueError（视图层转 422）
    - cfg 可选：缺省使用 PolicyConfig()
    """
    cur = to_act_index(gs)
    if cur != actor:
        raise PermissionError("actor is not to_act")

    # 只计算一次合法动作
    acts = legal_actions_struct(gs)
    if not acts:
        raise ValueError("No legal actions")

    # 组装 Observation
    obs = _build_observation(gs, actor, acts)

    # 选择策略
    policy_fn = POLICY_REGISTRY.get(obs.street)
    if policy_fn is None:
        policy_fn = policy_preflop_v0 if obs.street == "preflop" else policy_postflop_v0_3

    # 执行策略
    cfg = cfg or PolicyConfig()
    suggested, rationale, policy_name = policy_fn(obs, cfg)

    # 名称校验
    names = {a.action for a in acts}
    if suggested.get("action") not in names:
        raise ValueError("Policy produced illegal action")

    # 越界金额钳制 + 告警
    suggested2, clamped, clamp_info = _clamp_amount_if_needed(suggested, acts)
    if clamped:
        rationale.append(R(SCodes.WARN_CLAMPED, data=clamp_info))

    return {
        "hand_id": getattr(gs, "hand_id", None),
        "actor": actor,
        "suggested": suggested2,
        "rationale": rationale,
        "policy": policy_name,
    }
