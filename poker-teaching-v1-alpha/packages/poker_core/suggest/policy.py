"""
packages/poker_core/suggest/policy.py
preflop_v0, postflop_v0_3, preflop_v1
签名改造：只接收 Observation/PolicyConfig；不直接依赖 GameState/analysis/metrics。
返回值保持原契约： (suggested: dict, rationale: list[dict], policy_name: str)
"""

from __future__ import annotations

import os
from typing import Any

from .codes import SCodes
from .codes import mk_rationale as R
from .flop_rules import get_flop_rules
from .preflop_tables import bucket_facing_size, get_modes, get_open_table, get_vs_table
from .types import Observation, PolicyConfig
from .utils import (
    HC_MID_OR_THIRD_MINUS,
    HC_OP_TPTK,
    HC_STRONG_DRAW,
    HC_VALUE,
    HC_WEAK_OR_AIR,
    find_action,
    pick_betlike_action,
    to_call_from_acts,
)

# 与 analysis 中口径保持一致的范围判定（避免耦合：基于 tags/hand_class）
OPEN_RANGE_TAGS = {"pair", "suited_broadway", "Ax_suited", "broadway_offsuit"}
CALL_RANGE_TAGS = {"pair", "suited_broadway", "Ax_suited", "broadway_offsuit"}


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(int(v), hi))


def _in_open_range(tags: list[str], hand_class: str) -> bool:
    s = set(tags or [])
    return bool(s & OPEN_RANGE_TAGS) or hand_class in (
        "Ax_suited",
        "suited_broadway",
        "broadway_offsuit",
        "pair",
    )


def _in_call_range(tags: list[str], hand_class: str) -> bool:
    s = set(tags or [])
    return bool(s & CALL_RANGE_TAGS) or hand_class in (
        "Ax_suited",
        "suited_broadway",
        "broadway_offsuit",
        "pair",
    )


def policy_preflop_v0(
    obs: Observation, cfg: PolicyConfig
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Preflop 策略 v0（纯函数）。

    规则：
    - 未面对下注：范围内以 open_size_bb*bb 开局（bet/raise），否则优先 check。
    - 面对下注：范围内且 to_call <= call_threshold_bb*bb → call，否则 fold。
    """
    acts = list(obs.acts or [])
    if not acts:
        raise ValueError("No legal actions")

    rationale: list[dict[str, Any]] = []
    bb = int(obs.bb)
    to_call = int(obs.to_call if obs.to_call is not None else to_call_from_acts(acts))

    # 1) 未面对下注
    if to_call == 0:
        if _in_open_range(obs.tags, obs.hand_class):
            betlike = pick_betlike_action(acts)
            if (
                betlike
                and betlike.min is not None
                and betlike.max is not None
                and betlike.min <= betlike.max
            ):
                target = int(round(cfg.open_size_bb * bb))
                amt = _clamp(target, betlike.min, betlike.max)
                code_def = (
                    SCodes.PF_OPEN_BET
                    if betlike.action == "bet"
                    else SCodes.PF_OPEN_RAISE
                )
                rationale.append(
                    R(
                        code_def,
                        msg=f"未入池：{cfg.open_size_bb}bb 开局（{betlike.action}）。",
                        data={"bb": bb, "chosen": amt, "bb_mult": cfg.open_size_bb},
                    )
                )
                return (
                    {"action": betlike.action, "amount": amt},
                    rationale,
                    "preflop_v0",
                )
        # 不在范围：优先过牌
        if find_action(acts, "check"):
            rationale.append(R(SCodes.PF_CHECK_NOT_IN_RANGE))
            return ({"action": "check"}, rationale, "preflop_v0")
        if find_action(acts, "fold"):
            rationale.append(R(SCodes.PF_FOLD_NO_BET))
            return ({"action": "fold"}, rationale, "preflop_v0")

    # 2) 面对下注
    threshold = int(cfg.call_threshold_bb * bb)
    if (
        _in_call_range(obs.tags, obs.hand_class)
        and find_action(acts, "call")
        and to_call <= threshold
    ):
        rationale.append(
            R(
                SCodes.PF_CALL_THRESHOLD,
                data={"to_call": to_call, "threshold": threshold},
            )
        )
        return ({"action": "call"}, rationale, "preflop_v0")

    if find_action(acts, "fold"):
        rationale.append(
            R(
                SCodes.PF_FOLD_EXPENSIVE,
                data={"to_call": to_call, "threshold": threshold},
            )
        )
        return ({"action": "fold"}, rationale, "preflop_v0")

    if find_action(acts, "check"):
        rationale.append(R(SCodes.SAFE_CHECK))
        return ({"action": "check"}, rationale, "preflop_v0")

    raise ValueError("No safe suggestion")


def policy_postflop_v0_3(
    obs: Observation, cfg: PolicyConfig
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Postflop 策略 v0.3（纯函数）。

    - 无人下注线：flop 用最小试探注；turn/river 仅在具备一定摊牌价值（pair/Ax_suited）下注。
    - 面对下注线：按 pot-odds 与阈值决定 call 或 fold；范围内手牌使用更宽松阈值。
    """
    acts = list(obs.acts or [])
    if not acts:
        raise ValueError("No legal actions")

    rationale: list[dict[str, Any]] = [
        R(SCodes.PL_HEADER, data={"street": obs.street, "tags": list(obs.tags or [])}),
    ]

    to_call = int(obs.to_call if obs.to_call is not None else to_call_from_acts(acts))
    pot = int(obs.pot)

    # 无人下注线
    if to_call == 0:
        betlike = pick_betlike_action(acts)
        if (
            betlike
            and betlike.min is not None
            and betlike.max is not None
            and betlike.min <= betlike.max
        ):
            allow_bet = (obs.street == "flop") or (
                obs.street in {"turn", "river"}
                and ("pair" in (obs.tags or []) or obs.hand_class == "Ax_suited")
            )
            if allow_bet:
                amt = int(betlike.min)
                rationale.append(
                    R(
                        SCodes.PL_PROBE_BET,
                        msg=f"{obs.street} 无人下注线：以最小尺寸试探性下注。",
                        data={"chosen": amt},
                    )
                )
                return (
                    {"action": betlike.action, "amount": amt},
                    rationale,
                    "postflop_v0_3",
                )
        if find_action(acts, "check"):
            rationale.append(R(SCodes.PL_CHECK))
            return ({"action": "check"}, rationale, "postflop_v0_3")

    # 面对下注线：赔率判断
    denom = pot + to_call
    pot_odds = (to_call / denom) if denom > 0 else 1.0
    threshold = (
        cfg.pot_odds_threshold_callrange
        if _in_call_range(obs.tags, obs.hand_class)
        else cfg.pot_odds_threshold
    )

    if find_action(acts, "call") and pot_odds <= threshold:
        rationale.append(
            R(
                SCodes.PL_CALL_POTODDS,
                data={
                    "to_call": to_call,
                    "pot": pot,
                    "pot_odds": round(pot_odds, 4),
                    "threshold": threshold,
                },
            )
        )
        return ({"action": "call"}, rationale, "postflop_v0_3")

    if find_action(acts, "fold"):
        rationale.append(
            R(
                SCodes.PL_FOLD_POTODDS,
                data={
                    "to_call": to_call,
                    "pot": pot,
                    "pot_odds": round(pot_odds, 4),
                    "threshold": threshold,
                },
            )
        )
        return ({"action": "fold"}, rationale, "postflop_v0_3")

    # 兜底
    allin = find_action(acts, "allin")
    if allin:
        rationale.append(R(SCodes.PL_ALLIN_ONLY))
        return (
            {"action": "allin", "amount": allin.max or allin.min},
            rationale,
            "postflop_v0_3",
        )

    if find_action(acts, "check"):
        rationale.append(R(SCodes.SAFE_CHECK))
        return ({"action": "check"}, rationale, "postflop_v0_3")

    raise ValueError("No safe postflop suggestion")


__all__ = [
    "policy_preflop_v0",
    "policy_postflop_v0_3",
]


# --------- Preflop v1 (HU) ---------


def _conf_score(
    hit_range: bool = False,
    price_ok: bool = False,
    size_ok: bool = False,
    clamped: bool = False,
    fallback: bool = False,
    min_reopen_adjusted: bool = False,
) -> float:
    s = 0.5
    if hit_range:
        s += 0.3
    if price_ok or size_ok:
        s += 0.2
    if clamped:
        s -= 0.1
    if fallback:
        s -= 0.1
    if min_reopen_adjusted:
        # informational nudge, not a penalty
        s += 0.0
    return max(0.5, min(0.9, s))


def _bb_mult(v: float) -> int:
    return int(round(v))


def _pot_odds(to_call: int, pot_now: int) -> float:
    denom = pot_now + max(0, int(to_call))
    return (float(to_call) / float(denom)) if denom > 0 else 1.0


def _effective_stack_bb(obs: Observation) -> int:
    # 简化：使用 obs.bb 与 spr_bucket/pot_now 不足以精确栈深，近似返回较大值，依赖后续 clamp
    # 为 PR-1：我们只需要 cap 的保守界，避免溢出。
    # 近似：eff = max(10, round(spr*pot_now/bb))，spr_bucket 粗略映射
    if obs.spr_bucket == "low":
        return 10
    if obs.spr_bucket == "mid":
        return 20
    if obs.spr_bucket == "high":
        return 40
    # unknown → 20bb 近似
    return 20


def policy_preflop_v1(
    obs: Observation, cfg: PolicyConfig
) -> tuple[dict[str, Any], list[dict[str, Any]], str, dict[str, Any]]:
    """Preflop v1 (HU only in PR-1).

    Scope (PR-1):
    - SB RFI (open) and BB defend vs SB open.
    - SB vs BB 3bet (i.e., 4-bet sizing) is NOT handled in PR-1; related configs are placeholders for future work.
    - Pot odds use invariant: pot_odds = to_call / (pot_now + to_call), where pot_now excludes hero's pending call.

    Priority when ranges overlap: reraise (3bet) > call. If a combo exists in both reraise[bucket] and call[bucket], choose 3bet.
    """
    acts = list(obs.acts or [])
    if not acts:
        raise ValueError("No legal actions")

    rationale: list[dict[str, Any]] = []

    # Load tables + versions
    open_tab, ver_open = get_open_table()
    vs_tab, ver_vs = get_vs_table()
    modes, ver_modes = get_modes()

    # thresholds from modes (with defaults)
    m = modes.get("HU", {}) if isinstance(modes, dict) else {}
    open_bb = float(m.get("open_bb", 2.5))
    defend_ip = float(m.get("defend_threshold_ip", 0.42))
    defend_oop = float(m.get("defend_threshold_oop", 0.38))
    # v1: read 3bet sizing params from modes when available
    reraise_ip_mult = float(m.get("reraise_ip_mult", 3.0))
    reraise_oop_mult = float(m.get("reraise_oop_mult", 3.5))
    reraise_oop_offset = float(m.get("reraise_oop_offset", 0.5))
    cap_ratio = float(m.get("cap_ratio", 0.9))
    # 4bet params (SB vs BB 3bet)
    fourbet_ip_mult = float(m.get("fourbet_ip_mult", 2.2))
    cap_ratio_4b = float(m.get("cap_ratio_4b", cap_ratio))
    enable_4bet = (os.getenv("SUGGEST_PREFLOP_ENABLE_4BET") or "0").strip() == "1"

    # Validate configs; missing critical keys → fallback
    cfg_bad_open = ver_open == 0 or not (open_tab.get("SB") or set())
    # cfg_bad_vs 将按“当前桶”做局部校验，默认 False，稍后在 BB 防守分支计算
    cfg_bad_vs = False

    # Build combo
    combo: str | None = obs.combo or None
    if combo is None:
        rationale.append(R(SCodes.CFG_FALLBACK_USED))

    # Determine position in HU: preflop SB is OOP (ip=False)
    is_sb = not obs.ip

    to_call = int(obs.to_call or 0)
    bb = int(obs.bb or 50)

    # Pot odds (preflop): pot_now 包含盲注与已投入（服务层构建时已给出），否则近似使用 to_call 保护（降频）
    pot_now = int(getattr(obs, "pot_now", 0))
    pot_odds = _pot_odds(to_call, pot_now)

    # Helper: invested split from pot_now & to_call
    def _invested_split(to_call_amt: int, pot_now_amt: int) -> tuple[float, float]:
        # Solve: I_opp - I_me = to_call; I_opp + I_me = pot_now
        try:
            tc = float(max(0, int(to_call_amt or 0)))
            pn = float(max(0, int(pot_now_amt or 0)))
            i_opp = max(0.0, (pn + tc) / 2.0)
            i_me = max(0.0, (pn - tc) / 2.0)
            return i_me, i_opp
        except Exception:
            return 0.0, 0.0

    def _bucket_threebet_to(threebet_to_bb: float) -> str:
        # Configurable thresholds (defaults preserve old behavior)
        small_le = float(m.get("threebet_bucket_small_le", 9.0))
        mid_le = float(m.get("threebet_bucket_mid_le", 11.0))
        v = float(max(0.0, threebet_to_bb))
        if v <= small_le:
            return "small"
        if v <= mid_le:
            return "mid"
        return "large"

    # SB vs BB 3bet (4-bet path) — only when enabled and clearly facing a raise (非首轮)
    # 条件：SB 行动、preflop、to_call>0、无 bet（非 first-in）。不要求外层必须存在 raise，
    # 以便在无合法再加注时仍能命中 call vs 3bet 的回退。
    if (
        is_sb
        and enable_4bet
        and obs.street == "preflop"
        and to_call > 0
        and not find_action(acts, "bet")
    ):
        vs_sb = vs_tab.get("SB_vs_BB_3bet", {})
        # Derive threebet_to from invested split
        i_me, i_opp = _invested_split(to_call, int(getattr(obs, "pot_now", 0)))
        threebet_to_bb = (i_opp / float(bb)) if bb > 0 else 0.0
        bkt_3b = _bucket_threebet_to(threebet_to_bb)
        node = vs_sb.get(bkt_3b, {}) or {}
        # tolerate legacy 'reraise' as alias of 'fourbet'
        fourbet_set = set(
            node.get("fourbet", set()) or node.get("reraise", set()) or set()
        )
        call4b_set = set(node.get("call", set()) or set())

        # Try 4-bet first if in range
        if combo is not None and combo in fourbet_set and find_action(acts, "raise"):
            eff_bb = _effective_stack_bb(obs)
            cap_bb_4b = int(eff_bb * max(0.0, float(cap_ratio_4b)))
            target_to_bb = round(
                max(0.0, float(threebet_to_bb)) * float(fourbet_ip_mult)
            )
            fourbet_to_bb = max(0, min(cap_bb_4b, int(target_to_bb)))
            amt = int(round(fourbet_to_bb * bb))

            # Minimal re-open enforcement
            raise_act = find_action(acts, "raise")
            if raise_act and raise_act.min is not None and amt < int(raise_act.min):
                amt = int(raise_act.min)
                rationale.append(R(SCodes.PF_ATTACK_4BET_MIN_RAISE_ADJUSTED))

            rationale.append(
                R(
                    SCodes.PF_ATTACK_4BET,
                    data={"bucket": bkt_3b, "threebet_to_bb": round(threebet_to_bb, 2)},
                )
            )
            suggested = {"action": "raise", "amount": amt}
            meta = {
                "fourbet_to_bb": int(fourbet_to_bb),
                "bucket": bkt_3b,
                "combo": combo,
                "threebet_to_bb": round(threebet_to_bb, 2),
                "cap_bb": int(cap_bb_4b),
            }
            return suggested, rationale, "preflop_v1", meta

        # Else consider call set (flat vs 3bet) if provided
        if combo is not None and combo in call4b_set and find_action(acts, "call"):
            # Keep rationale simple; advanced pot-odds gating can be added later
            rationale.append(R(SCodes.PF_DEFEND_PRICE_OK, data={"bucket": bkt_3b}))
            meta = {"bucket": bkt_3b, "combo": combo}
            return {"action": "call"}, rationale, "preflop_v1", meta

        # No hit in 4-bet node: fall through to conservative fallback
        # 4bet 配置缺失或未命中时，若存在合法跟注，优先保守选择 call（不再强制“便宜补盲”门槛）。
        if find_action(acts, "call"):
            return {"action": "call"}, rationale, "preflop_v1", {}
        if find_action(acts, "fold"):
            rationale.append(R(SCodes.PF_FOLD_EXPENSIVE, data={"bucket": bkt_3b}))
            return {"action": "fold"}, rationale, "preflop_v1", {}
        if find_action(acts, "check"):
            return {"action": "check"}, rationale, "preflop_v1", {}

    # RFI in HU（仅 first-in）：需要 to_call==0 或存在 bet 动作
    if is_sb and (to_call == 0 or find_action(acts, "bet")):
        if cfg_bad_open:
            rationale.append(R(SCodes.CFG_FALLBACK_USED))
            # conservative fallback: limp if cheap, else check/fold
            if find_action(acts, "call") and to_call <= int(round(1.0 * bb)):
                rationale.append(R(SCodes.PF_LIMP_COMPLETE_BLIND))
                return {"action": "call"}, rationale, "preflop_v1", {}
            if find_action(acts, "check"):
                return {"action": "check"}, rationale, "preflop_v1", {}
            if find_action(acts, "fold"):
                return {"action": "fold"}, rationale, "preflop_v1", {}
        hit = False
        # Only SB has RFI in HU
        if combo is not None and combo in (open_tab.get("SB") or set()):
            hit = True
        betlike = pick_betlike_action(acts)
        if hit and betlike:
            amt = _bb_mult(open_bb * bb)
            rationale.append(R(SCodes.PF_OPEN_RANGE_HIT, data={"open_bb": open_bb}))
            suggested = {"action": betlike.action, "amount": amt}
            meta = {"open_bb": open_bb}
            return suggested, rationale + [], "preflop_v1", meta
        if hit and not betlike:
            # desired to raise but no legal bet/raise
            rationale.append(R(SCodes.PF_NO_LEGAL_RAISE))
        # fallback: prefer call to complete blind if cheap, else check/fold
        if find_action(acts, "call") and to_call <= int(round(1.0 * bb)):
            rationale.append(R(SCodes.PF_LIMP_COMPLETE_BLIND))
            return {"action": "call"}, rationale, "preflop_v1", {}
        if find_action(acts, "check"):
            return {"action": "check"}, rationale, "preflop_v1", {}
        if find_action(acts, "fold"):
            return {"action": "fold"}, rationale, "preflop_v1", {}
        raise ValueError("No safe suggestion")

    # Facing raise（BB vs SB open）: actor is BB
    bucket = bucket_facing_size(max(0.0, to_call / float(bb)))
    ip = bool(obs.ip)
    defend_thr = defend_ip if ip else defend_oop
    # Tables path key
    key = "BB_vs_SB"
    vs = vs_tab.get(key, {})
    node_vs = vs.get(bucket, {}) or {}
    # 局部校验：版本无效/缺 key/缺 bucket 或当前桶缺失关键集合时，视为坏配置
    cfg_bad_vs = (
        ver_vs == 0
        or not isinstance(vs, dict)
        or (bucket not in vs)
        or not isinstance(node_vs.get("call"), set)
        or not isinstance(node_vs.get("reraise"), set)
    )
    if cfg_bad_vs:
        rationale.append(R(SCodes.CFG_FALLBACK_USED))
        if find_action(acts, "fold"):
            return {"action": "fold"}, rationale, "preflop_v1", {}
        if find_action(acts, "check"):
            return {"action": "check"}, rationale, "preflop_v1", {}
        raise ValueError("No safe preflop v1 suggestion (vs table missing)")
    call_set = set(node_vs.get("call", set()))
    reraise_set = set(node_vs.get("reraise", set()))

    # Default meta
    # meta.bucket only for vs-raise
    # meta.reraise_to_bb only when 3bet chosen

    # Prefer 3bet if in range
    if combo is not None and combo in reraise_set and find_action(acts, "raise"):
        # Compute 3bet size
        to_call_bb = to_call / float(bb)
        open_to_bb = to_call_bb + 1.0
        eff_bb = _effective_stack_bb(obs)
        cap_bb = int(eff_bb * cap_ratio)
        target_to_bb = round(
            open_to_bb * (reraise_ip_mult if ip else reraise_oop_mult)
            + (0.0 if ip else reraise_oop_offset)
        )
        reraise_to_bb = min(cap_bb, target_to_bb)
        amt = int(round(reraise_to_bb * bb))

        # Minimal re-open: ensure meets raise.min (to-amount semantics)
        # Many engines define raise.min as the total amount to raise to.
        # If computed target is below this to-amount, lift to raise.min.
        raise_act = find_action(acts, "raise")
        if raise_act and raise_act.min is not None and amt < int(raise_act.min):
            amt = int(raise_act.min)
            rationale.append(R(SCodes.PF_DEFEND_3BET_MIN_RAISE_ADJUSTED))

        rationale.append(R(SCodes.PF_DEFEND_3BET, data={"bucket": bucket}))
        suggested = {"action": "raise", "amount": amt}
        meta = {
            "reraise_to_bb": reraise_to_bb,
            "bucket": bucket,
            "pot_odds": round(pot_odds, 4),
            "cap_bb": int(cap_bb),
        }
        return suggested, rationale, "preflop_v1", meta

    # Else consider call (price + range)
    if combo is not None and combo in call_set and find_action(acts, "call"):
        if pot_odds <= defend_thr:
            rationale.append(
                R(
                    SCodes.PF_DEFEND_PRICE_OK,
                    data={
                        "pot_odds": round(pot_odds, 4),
                        "thr": defend_thr,
                        "bucket": bucket,
                    },
                )
            )
            # Only include bucket meta when facing a raise (to_call > 0), not in limped pots
            meta = (
                {"bucket": bucket, "pot_odds": round(pot_odds, 4)}
                if to_call > 0
                else {}
            )
            return {"action": "call"}, rationale, "preflop_v1", meta
        else:
            rationale.append(
                R(
                    SCodes.PF_DEFEND_PRICE_BAD,
                    data={
                        "pot_odds": round(pot_odds, 4),
                        "thr": defend_thr,
                        "bucket": bucket,
                    },
                )
            )
            # price bad: consider fold if available
            # Only include bucket meta when facing a raise (to_call > 0), not in limped pots
            meta = (
                {"bucket": bucket, "pot_odds": round(pot_odds, 4)}
                if to_call > 0
                else {}
            )
            if find_action(acts, "fold"):
                return {"action": "fold"}, rationale, "preflop_v1", meta
            if find_action(acts, "check"):
                return {"action": "check"}, rationale, "preflop_v1", meta

    # Out of defend range: fold/check with BAD rationale to mark unprofitable defend
    if combo is not None and (combo not in call_set) and (combo not in reraise_set):
        rationale.append(
            R(
                SCodes.PF_DEFEND_PRICE_BAD,
                data={
                    "pot_odds": round(pot_odds, 4),
                    "thr": defend_thr,
                    "bucket": bucket,
                    "reason": "out_of_range",
                },
            )
        )
        # Only include bucket meta when facing a raise (to_call > 0), not in limped pots
        meta = {"bucket": bucket} if to_call > 0 else {}
        if find_action(acts, "fold"):
            return {"action": "fold"}, rationale, "preflop_v1", meta
        if find_action(acts, "check"):
            return {"action": "check"}, rationale, "preflop_v1", meta

    # Fallbacks
    if find_action(acts, "fold"):
        return {"action": "fold"}, rationale, "preflop_v1", {}
    if find_action(acts, "check"):
        return {"action": "check"}, rationale, "preflop_v1", {}
    raise ValueError("No safe preflop v1 suggestion")


__all__.append("policy_preflop_v1")


# --------- Flop v1 (HU, single-raised only; role+MDF aligned) ---------


def _match_rule(node: dict[str, Any], keys: list[str]) -> dict[str, Any] | None:
    """Depth-first lookup with 'defaults' fallback at each level.
    keys: [pot_type, 'role', role, 'ip'|'oop', texture, spr_bucket, hand_class]
    Returns a dict leaf like {action:'bet', size_tag:'third'} or None.
    """
    cur: Any = node
    try:
        for k in keys:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            elif isinstance(cur, dict) and "defaults" in cur:
                cur = cur["defaults"]
            else:
                return None
        if isinstance(cur, dict) and ("action" in cur or "size_tag" in cur):
            return cur
    except Exception:
        return None
    return None


def policy_flop_v1(
    obs: Observation, cfg: PolicyConfig
) -> tuple[dict[str, Any], list[dict[str, Any]], str, dict[str, Any]]:
    acts = list(obs.acts or [])
    if not acts:
        raise ValueError("No legal actions")

    rationale: list[dict[str, Any]] = []

    # Load rules (strategy-aware)
    rules, ver = get_flop_rules()

    # Pot type: support single_raised; limped added in v1.1; threebet TBD
    pot_type = getattr(obs, "pot_type", "single_raised") or "single_raised"
    if pot_type not in (rules or {}):
        rationale.append(R(SCodes.CFG_FALLBACK_USED))

    # Derived inputs
    ip_key = "ip" if bool(obs.ip) else "oop"
    texture = obs.board_texture or "na"
    spr = obs.spr_bucket or "na"
    role = obs.role or "na"
    if pot_type == "limped":
        role = "na"

    # Facing a bet?
    to_call = int(obs.to_call or 0)
    pot_now = int(obs.pot_now or 0)
    denom = pot_now + max(0, to_call)
    pot_odds = (to_call / denom) if denom > 0 else 1.0
    mdf = 1.0 - pot_odds

    # Meta to return (teaching fields)
    meta: dict[str, Any] = {
        "size_tag": None,
        "role": role,
        "texture": texture,
        "spr_bucket": spr,
        "mdf": round(mdf, 4),
        "pot_odds": round(pot_odds, 4),
        "facing_size_tag": getattr(obs, "facing_size_tag", "na"),
        "range_adv": bool(getattr(obs, "range_adv", False)),
        "nut_adv": bool(getattr(obs, "nut_adv", False)),
        "rules_ver": ver,
    }

    # 1) No bet yet: prefer c-bet on dry boards when PFR
    if to_call == 0:
        node = None
        if pot_type == "limped":
            node = _match_rule(
                rules,
                [
                    pot_type,
                    "role",
                    "na",
                    ip_key,
                    texture,
                    spr,
                    str(obs.hand_class or "unknown"),
                ],
            ) or _match_rule(rules, [pot_type, "role", "na", ip_key, texture])
        else:
            node = _match_rule(
                rules,
                [
                    pot_type,
                    "role",
                    role,
                    ip_key,
                    texture,
                    spr,
                    str(obs.hand_class or "unknown"),
                ],
            ) or _match_rule(rules, [pot_type, "role", role, ip_key, texture])

        if node:
            action = str(node.get("action") or "bet")
            size_tag = str(node.get("size_tag") or "third")
            meta["size_tag"] = size_tag
            plan_str = node.get("plan")
            if isinstance(plan_str, str) and plan_str:
                meta["plan"] = plan_str
            if action in {"bet", "raise"}:
                # amount will be filled by service via size_tag if omitted
                suggested = {"action": action}
                # rationale by role/advantage
                if bool(meta["range_adv"]) and size_tag == "third":
                    rationale.append(R(SCodes.FL_RANGE_ADV_SMALL_BET))
                elif bool(meta["nut_adv"]) and size_tag in {"two_third", "pot"}:
                    rationale.append(R(SCodes.FL_NUT_ADV_POLAR))
                else:
                    rationale.append(R(SCodes.FL_DRY_CBET_THIRD))
                # SPR notes
                if (
                    obs.spr_bucket == "le3"
                    and size_tag in {"two_third", "pot"}
                    and (obs.hand_class in {HC_VALUE, HC_OP_TPTK})
                ):
                    rationale.append(R(SCodes.FL_LOW_SPR_VALUE_UP))
                if (
                    obs.spr_bucket == "ge6"
                    and action == "check"
                    and (obs.hand_class in {HC_MID_OR_THIRD_MINUS, HC_WEAK_OR_AIR})
                ):
                    rationale.append(R(SCodes.FL_HIGH_SPR_CTRL))
                return suggested, rationale, "flop_v1", meta
            if action == "check" and find_action(acts, "check"):
                rationale.append(R(SCodes.FL_DELAYED_CBET_PLAN))
                return {"action": "check"}, rationale, "flop_v1", meta

        # Fallback defaults by texture
        if role == "pfr" and texture == "dry" and pick_betlike_action(acts):
            meta["size_tag"] = "third"
            rationale.append(R(SCodes.FL_RANGE_ADV_SMALL_BET))
            return {"action": "bet"}, rationale, "flop_v1", meta
        if find_action(acts, "check"):
            rationale.append(R(SCodes.FL_CHECK_RANGE))
            return {"action": "check"}, rationale, "flop_v1", meta

    # 2) Facing a bet: first check JSON-driven value-raise; otherwise show MDF/pot_odds and choose simple line
    fst = getattr(obs, "facing_size_tag", "na")
    allow_value_raise = (os.getenv("SUGGEST_FLOP_VALUE_RAISE") or "1").strip() != "0"

    # JSON-driven value raise: lookup facing rules under current class node
    try:
        if (
            allow_value_raise
            and str(obs.hand_class) == HC_VALUE
            and fst in {"third", "half", "two_third+"}
        ):
            # resolve role path (limped uses role='na')
            _role = role if pot_type != "limped" else "na"
            # traverse dicts without defaults for precision
            pot_node = (rules or {}).get(pot_type, {})
            role_node = (pot_node.get("role", {}) or {}).get(_role, {})
            pos_node = (role_node.get(ip_key, {}) or {}).get(texture, {})
            spr_node = pos_node.get(spr, {}) or {}
            cls_node = spr_node.get("value_two_pair_plus", {}) or {}
            facing = cls_node.get("facing") if isinstance(cls_node, dict) else None
            if isinstance(facing, dict):
                key = "two_third_plus" if fst == "two_third+" else fst
                fr = facing.get(key)
                if isinstance(fr, dict) and fr.get("action") in {
                    "raise",
                    "call",
                    "fold",
                }:
                    action = str(fr.get("action"))
                    plan = fr.get("plan")
                    if plan:
                        meta["plan"] = plan
                    if action == "raise" and find_action(acts, "raise"):
                        st = str(fr.get("size_tag") or "half")
                        meta["size_tag"] = st
                        rationale.append(R(SCodes.FL_RAISE_VALUE))
                        return {"action": "raise"}, rationale, "flop_v1", meta
                    if action == "call" and find_action(acts, "call"):
                        return {"action": "call"}, rationale, "flop_v1", meta
                    if action == "fold" and find_action(acts, "fold"):
                        return {"action": "fold"}, rationale, "flop_v1", meta
    except Exception:
        pass

    # Default MDF 展示
    rationale.append(
        R(
            SCodes.FL_MDF_DEFEND,
            data={"mdf": meta["mdf"], "pot_odds": meta["pot_odds"], "facing": fst},
        )
    )
    # threebet: add light value-raise and semi-bluff raise stubs
    if getattr(obs, "pot_type", "single_raised") == "threebet":
        # value raise vs small/half when we hold two_pair+ (OOP/IP)
        if (
            fst in {"third", "half"}
            and getattr(obs, "hand_class", "") in {HC_VALUE}
            and find_action(acts, "raise")
        ):
            meta["size_tag"] = "two_third"
            rationale.append(R(SCodes.FL_RAISE_VALUE))
            return {"action": "raise"}, rationale, "flop_v1", meta
        # semi-bluff raise vs small when we have strong_draw (IP preferred but allow both)
        if (
            fst == "third"
            and getattr(obs, "hand_class", "") in {HC_STRONG_DRAW}
            and find_action(acts, "raise")
        ):
            meta["size_tag"] = "half"
            rationale.append(R(SCodes.FL_RAISE_SEMI_BLUFF))
            return {"action": "raise"}, rationale, "flop_v1", meta
    if fst in {"third", "half"} and find_action(acts, "call"):
        return {"action": "call"}, rationale, "flop_v1", meta
    # vs large sizes: if we have any raise path and nut_adv, allow raise stub (service will clamp)
    if fst == "two_third+" and bool(meta["nut_adv"]) and find_action(acts, "raise"):
        meta["size_tag"] = "two_third"
        meta.setdefault("plan", "vs small/half → call; vs two_third+ → raise")
        rationale.append(R(SCodes.FL_RAISE_SEMI_BLUFF))
        return {"action": "raise"}, rationale, "flop_v1", meta
    if find_action(acts, "call"):
        return {"action": "call"}, rationale, "flop_v1", meta
    if find_action(acts, "fold"):
        return {"action": "fold"}, rationale, "flop_v1", meta

    # Last resort
    if find_action(acts, "check"):
        return {"action": "check"}, rationale, "flop_v1", meta
    raise ValueError("No safe flop v1 suggestion")


__all__.append("policy_flop_v1")
