# packages/poker_core/suggest/service.py
from __future__ import annotations
from typing import Dict, Any
from ..domain.actions import to_act_index, legal_actions_struct, LegalAction
from .policy import policy_preflop_v0

def _clamp_amount_if_needed(suggested: Dict[str, Any], acts: list[LegalAction]) -> Dict[str, Any]:
    name = suggested.get("action")
    if name not in {"bet", "raise", "allin"}:
        return suggested
    amt = suggested.get("amount")
    if amt is None:
        return suggested
    spec = next((a for a in acts if a.action == name), None)
    if not spec:
        return suggested
    lo = spec.min if spec.min is not None else amt
    hi = spec.max if spec.max is not None else amt
    if lo is None or hi is None:
        return suggested
    clamped = max(lo, min(int(amt), hi))
    if clamped != amt:
        # 保守：若策略给出越界金额，将其钳制到合法区间
        suggested = dict(suggested)
        suggested["amount"] = clamped
    return suggested

def build_suggestion(gs, actor: int) -> Dict[str, Any]:
    """Suggest 入口（v0：仅 preflop_v0）。

    契约：
    - 若 actor != gs.to_act → PermissionError（视图层转 409）
    - 若无法产生合法建议 → ValueError（视图层转 422）
    """
    cur = to_act_index(gs)
    if cur != actor:
        raise PermissionError("actor is not to_act")

    suggested, rationale, policy = policy_preflop_v0(gs, actor)

    # 保险：动作名必须在当前合法集合中
    acts = legal_actions_struct(gs)
    names = {a.action for a in acts}
    if suggested["action"] not in names:
        raise ValueError("Policy produced illegal action")

    # 金额二次校验：若有 amount，钳制到合法 [min,max]
    suggested = _clamp_amount_if_needed(suggested, acts)

    return {
        "hand_id": getattr(gs, "hand_id", None),
        "actor": actor,
        "suggested": suggested,
        "rationale": rationale,
        "policy": policy,
    }
