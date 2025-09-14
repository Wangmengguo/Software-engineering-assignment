# packages/poker_core/suggest/service.py
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from ..analysis import annotate_player_hand_from_gs
from ..domain.actions import LegalAction, legal_actions_struct, to_act_index
from .codes import SCodes
from .codes import mk_rationale as R
from .policy import (
    policy_flop_v1,
    policy_postflop_v0_3,
    policy_preflop_v0,
    policy_preflop_v1,
)
from .preflop_tables import (
    combo_from_hole,
    config_profile_name,
    config_strategy_name,
    get_modes,
    get_open_table,
    get_vs_table,
)
from .types import Observation, PolicyConfig
from .utils import (
    calc_spr,
    classify_flop,
    derive_facing_size_tag,
    drop_nones,
    infer_pfr,
    nut_advantage,
    range_advantage,
    size_to_amount,
    stable_roll,
    to_call_from_acts,
)
from .utils import is_ip as _is_ip
from .utils import spr_bucket as _spr_bucket


def _clamp_amount_if_needed(
    suggested: dict[str, Any], acts: list[LegalAction]
) -> tuple[dict[str, Any], bool, dict[str, int | None]]:
    """将建议金额钳制到合法区间，并返回是否发生钳制及边界信息。"""
    name = suggested.get("action")
    if name not in {"bet", "raise", "allin"}:
        return (
            suggested,
            False,
            {"min": None, "max": None, "given": None, "chosen": None},
        )
    amt = suggested.get("amount")
    if amt is None:
        return (
            suggested,
            False,
            {"min": None, "max": None, "given": None, "chosen": None},
        )
    spec = next((a for a in acts if a.action == name), None)
    if not spec:
        return (
            suggested,
            False,
            {"min": None, "max": None, "given": int(amt), "chosen": int(amt)},
        )
    lo = spec.min if spec.min is not None else int(amt)
    hi = spec.max if spec.max is not None else int(amt)
    if lo is None or hi is None:
        return (
            suggested,
            False,
            {"min": None, "max": None, "given": int(amt), "chosen": int(amt)},
        )
    # 处理异常窗口：min > max（例如上游引擎的边界不一致）。
    # 为了确保打出服务层钳制信号，这里强制将金额压到 hi，并视为 clamped。
    if int(lo) > int(hi):
        clamped_val = int(hi)
        s2 = dict(suggested)
        s2["amount"] = clamped_val
        return (
            s2,
            True,
            {
                "min": int(lo),
                "max": int(hi),
                "given": int(amt),
                "chosen": int(clamped_val),
            },
        )
    clamped_val = max(int(lo), min(int(amt), int(hi)))
    if clamped_val != amt:
        s2 = dict(suggested)
        s2["amount"] = clamped_val
        return (
            s2,
            True,
            {
                "min": int(lo),
                "max": int(hi),
                "given": int(amt),
                "chosen": int(clamped_val),
            },
        )
    return (
        suggested,
        False,
        {"min": int(lo), "max": int(hi), "given": int(amt), "chosen": int(amt)},
    )


# 策略注册表（按版本/街选择）。PR-0：v1 映射到 v0 占位，保证行为不变。
PolicyFn = Callable[
    [Observation, PolicyConfig], tuple[dict[str, Any], list[dict[str, Any]], str]
]
POLICY_REGISTRY_V0: dict[str, PolicyFn] = {
    "preflop": policy_preflop_v0,
    "flop": policy_postflop_v0_3,
    "turn": policy_postflop_v0_3,
    "river": policy_postflop_v0_3,
}
POLICY_REGISTRY_V1: dict[str, PolicyFn] = {
    "preflop": policy_preflop_v1,
    "flop": policy_flop_v1,
    "turn": policy_postflop_v0_3,
    "river": policy_postflop_v0_3,
}

# Backward-compat alias for tests/importers
POLICY_REGISTRY: dict[str, PolicyFn] = POLICY_REGISTRY_V0


def _choose_policy_version(hand_id: str) -> str:
    """返回 'v0' 或 'v1'（PR-0 中 v1 与 v0 行为一致，仅用于灰度管控与调试展示）。"""
    mode = (os.getenv("SUGGEST_POLICY_VERSION") or "v0").strip().lower()
    if mode in {"v0", "v1", "v1_preflop"}:  # v1_preflop 在 PR-0 等同 v1
        return "v1" if mode != "v0" else "v0"
    if mode == "auto":
        pct = int(os.getenv("SUGGEST_V1_ROLLOUT_PCT") or 0)
        return "v1" if stable_roll(hand_id or "", pct) else "v0"
    return "v0"


def _build_observation(
    gs, actor: int, acts: list[LegalAction]
) -> tuple[Observation, list[dict[str, Any]]]:
    # 从 analysis 取 tags/hand_class（失败时降级 unknown）
    pre_rationale: list[dict[str, Any]] = []
    try:
        ann = annotate_player_hand_from_gs(gs, actor)
        info = ann.get("info", {})
        tags = list(info.get("tags", []) or [])
        hand_class = info.get("hand_class", "unknown")
    except Exception:
        tags, hand_class = ["unknown"], "unknown"
        pre_rationale.append(R(SCodes.WARN_ANALYSIS_MISSING))

    hand_id = str(getattr(gs, "hand_id", ""))
    street = str(getattr(gs, "street", "preflop"))
    bb = int(getattr(gs, "bb", 50))
    pot = int(getattr(gs, "pot", 0))
    to_call = int(to_call_from_acts(acts))

    # v1 扩展：table_mode/ip/texture/spr
    table_mode = (os.getenv("SUGGEST_TABLE_MODE") or "HU").upper()
    try:
        button = int(getattr(gs, "button", 0))
    except Exception:
        button = 0
    texture = classify_flop(getattr(gs, "board", []) or [])
    # 决策点 SPR：pot_now = pot + invested_street_sum
    try:
        p0 = getattr(gs, "players")[0]
        p1 = getattr(gs, "players")[1]
        invested = int(getattr(p0, "invested_street", 0)) + int(
            getattr(p1, "invested_street", 0)
        )
        # Invariant: pot_now is the current pot excluding hero's pending to_call
        # (includes blinds and opponent's invested chips, but not the hero's next call amount).
        # Pot odds must be computed as: to_call / (pot_now + to_call).
        pot_now = pot + invested
        eff_stack = min(
            (
                int(getattr(p0, "stack", 0))
                if actor == 0
                else int(getattr(p1, "stack", 0))
            ),
            (
                int(getattr(p1, "stack", 0))
                if actor == 0
                else int(getattr(p0, "stack", 0))
            ),
        )
        spr_val = calc_spr(pot_now, eff_stack)
        spr_bkt = _spr_bucket(spr_val)
    except Exception:
        spr_bkt = "na"

    # role / advantages
    try:
        pfr_seat = infer_pfr(gs)
    except Exception:
        pfr_seat = None
    role = "na"
    try:
        if pfr_seat is not None:
            role = "pfr" if int(pfr_seat) == int(actor) else "caller"
    except Exception:
        role = "na"
    range_adv = range_advantage(str(texture.get("texture", "na")), role)
    nut_adv = nut_advantage(str(texture.get("texture", "na")), role)

    # facing size tag (only meaningful when to_call>0)
    fst = derive_facing_size_tag(to_call, int(locals().get("pot_now", pot)))
    # pot type inference (preflop raises count)
    try:
        from .utils import infer_pot_type

        pot_type_val = infer_pot_type(gs)
    except Exception:
        pot_type_val = "single_raised"

    # hand_class on flop: use 6-bucket inference; otherwise keep analysis hand_class
    try:
        hc = str(hand_class)
        if street == "flop":
            from .utils import (
                infer_flop_hand_class_from_gs,
            )

            hc = infer_flop_hand_class_from_gs(gs, actor)
    except Exception:
        hc = str(hand_class)

    obs = Observation(
        hand_id=hand_id,
        actor=int(actor),
        street=street,
        bb=bb,
        pot=pot,
        to_call=to_call,
        acts=acts,
        tags=tags,
        hand_class=hc,
        table_mode=table_mode,
        spr_bucket=spr_bkt,
        board_texture=str(texture.get("texture", "na")),
        ip=_is_ip(actor, table_mode, button, street),
        pot_now=int(locals().get("pot_now", pot)),
        combo=(
            combo_from_hole(
                getattr(getattr(gs, "players", [None, None])[actor], "hole", []) or []
            )
            or ""
        ),
        role=role,
        range_adv=bool(range_adv),
        nut_adv=bool(nut_adv),
        facing_size_tag=fst,
        pot_type=str(pot_type_val),
    )
    return obs, pre_rationale


def build_suggestion(gs, actor: int, cfg: PolicyConfig | None = None) -> dict[str, Any]:
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
    obs, pre_rationale = _build_observation(gs, actor, acts)

    # 选择策略（按版本 + 街）
    version = _choose_policy_version(str(getattr(gs, "hand_id", "")))
    reg = POLICY_REGISTRY_V1 if version == "v1" else POLICY_REGISTRY_V0
    policy_fn = reg.get(obs.street) or (
        policy_preflop_v0 if obs.street == "preflop" else policy_postflop_v0_3
    )

    # 执行策略
    cfg = cfg or PolicyConfig()
    out = policy_fn(obs, cfg)
    if isinstance(out, tuple) and len(out) == 4:
        suggested, rationale, policy_name, meta_from_policy = out  # type: ignore
    else:
        suggested, rationale, policy_name = out  # type: ignore
        meta_from_policy = {}
    # 若策略仅返回 size_tag（无金额），在服务层统一换算
    try:
        if (
            suggested
            and suggested.get("action") in {"bet", "raise"}
            and (suggested.get("amount") is None)
        ):
            size_tag = (meta_from_policy or {}).get("size_tag")
            if size_tag:
                if suggested.get("action") == "raise":
                    # use raise-to semantics for postflop
                    try:
                        from .utils import raise_to_amount

                        modes, _ = get_modes()
                        cap_ratio = (
                            (modes.get("HU", {}) or {}).get("postflop_cap_ratio", 0.85)
                            if isinstance(modes, dict)
                            else 0.85
                        )
                    except Exception:
                        cap_ratio = 0.85
                    eff_stack = None  # conservative; service-level clamp will still enforce bounds
                    amt = raise_to_amount(
                        pot_now=int(getattr(obs, "pot_now", obs.pot) or 0),
                        last_bet=int(getattr(gs, "last_bet", 0) or 0),
                        size_tag=str(size_tag),
                        bb=int(obs.bb or 1),
                        eff_stack=eff_stack,
                        cap_ratio=float(cap_ratio),
                    )
                else:
                    amt = size_to_amount(
                        pot=int(getattr(obs, "pot_now", obs.pot) or 0),
                        last_bet=int(getattr(gs, "last_bet", 0) or 0),
                        size_tag=str(size_tag),
                        bb=int(obs.bb or 1),
                    )
                if amt is not None:
                    suggested["amount"] = int(amt)
        # Min-reopen lift for postflop raise sizing (to-amount semantics)
        if (
            suggested
            and suggested.get("action") == "raise"
            and suggested.get("amount") is not None
        ):
            try:
                raise_spec = next((a for a in acts if a.action == "raise"), None)
                if (
                    raise_spec
                    and raise_spec.min is not None
                    and int(suggested["amount"]) < int(raise_spec.min)
                ):
                    suggested["amount"] = int(raise_spec.min)
                    # append rationale later (after pre_rationale merge)
                    meta_from_policy = dict(meta_from_policy or {})
                    meta_from_policy.setdefault("_min_reopen_adjusted", True)
            except Exception:
                pass
    except Exception:
        pass

    # 注入预先的告警（例如分析缺失）
    if pre_rationale:
        rationale = list(pre_rationale) + list(rationale or [])
    # Inject min-reopen adjusted rationale if flagged
    try:
        if (meta_from_policy or {}).get("_min_reopen_adjusted"):
            rationale = list(rationale or [])
            rationale.append(R(SCodes.FL_MIN_REOPEN_ADJUSTED))
    except Exception:
        pass

    # 名称校验
    names = {a.action for a in acts}
    if suggested.get("action") not in names:
        raise ValueError("Policy produced illegal action")

    # SB 补盲（limp）时确保附带解释码（防止上游遗漏）
    try:
        if (
            obs.street == "preflop"
            and suggested.get("action") == "call"
            and not bool(obs.ip)  # SB preflop 为 OOP
            and int(obs.to_call or 0) <= int(obs.bb or 0)
        ):
            rationale = list(rationale or [])
            codes = {str((r or {}).get("code")) for r in rationale}
            if "PF_LIMP_COMPLETE_BLIND" not in codes:
                rationale.append(R(SCodes.PF_LIMP_COMPLETE_BLIND))
    except Exception:
        pass

    # 越界金额钳制 + 告警
    suggested2, clamped, clamp_info = _clamp_amount_if_needed(suggested, acts)
    if clamped:
        rationale.append(R(SCodes.WARN_CLAMPED, data=clamp_info))

    # 兼容 + 扩展返回
    resp: dict[str, Any] = {
        "hand_id": getattr(gs, "hand_id", None),
        "actor": actor,
        "suggested": suggested2,
        "rationale": rationale,
        "policy": policy_name,
        "confidence": 0.5,
    }

    # meta 仅在有值时返回；由策略层提供
    meta_clean = drop_nones(dict(meta_from_policy or {}))
    if meta_clean:
        resp["meta"] = meta_clean

    # Compute confidence after clamp, based on rationale codes + meta hints (small tweaks)
    try:
        codes = {str((r or {}).get("code")) for r in (rationale or [])}
        hit_range = any(
            c in {"PF_OPEN_RANGE_HIT", "PF_DEFEND_3BET", "PF_DEFEND_PRICE_OK"}
            for c in codes
        )
        price_or_size_ok = any(
            c in {"PF_DEFEND_PRICE_OK", "PF_OPEN_RANGE_HIT", "PF_DEFEND_3BET"}
            for c in codes
        )
        fallback = any(
            c in {"CFG_FALLBACK_USED", "PF_NO_LEGAL_RAISE", "PF_LIMP_COMPLETE_BLIND"}
            for c in codes
        )
        meta_all = resp.get("meta") or {}
        hit_mainline = (
            str(resp.get("policy")) == "flop_v1"
            and (meta_all.get("size_tag") is not None)
            and int(getattr(obs, "to_call", 0) or 0) == 0
        )
        has_plan = (
            isinstance(meta_all.get("plan"), str)
            and len(str(meta_all.get("plan") or "")) > 0
        )
        base = 0.5
        base += 0.3 if hit_range else 0.0
        base += 0.2 if price_or_size_ok else 0.0
        base += 0.05 if hit_mainline else 0.0
        base += 0.05 if has_plan else 0.0
        base -= 0.1 if clamped else 0.0
        base -= 0.1 if fallback else 0.0
        resp["confidence"] = max(0.5, min(0.9, base))
    except Exception:
        pass

    if (os.getenv("SUGGEST_DEBUG") or "0") == "1":
        # config versions for quick diagnosis
        _, ver_open = get_open_table()
        _, ver_vs = get_vs_table()
        _, ver_modes = get_modes()
        cfg_versions = {
            "open": int(ver_open or 0),
            "vs": int(ver_vs or 0),
            "modes": int(ver_modes or 0),
        }
        profile = config_profile_name()
        # debug units/deriveds for preflop v1 troubleshooting
        try:
            to_call_bb_dbg = float(obs.to_call) / float(obs.bb) if obs.bb else 0.0
            open_to_bb_dbg = (
                to_call_bb_dbg + 1.0
                if obs.to_call and obs.street == "preflop"
                else None
            )
            pot_odds_dbg = (
                (float(obs.to_call) / float(obs.pot_now + obs.to_call))
                if (obs.pot_now + obs.to_call) > 0
                else None
            )
            r2bb_dbg = None
            r2amt_dbg = None
            if resp.get("policy") == "preflop_v1":
                r2bb_dbg = (resp.get("meta") or {}).get("reraise_to_bb")
                if (resp.get("suggested") or {}).get("action") == "raise":
                    r2amt_dbg = (resp.get("suggested") or {}).get("amount")
        except Exception:
            to_call_bb_dbg = None
            open_to_bb_dbg = None
            pot_odds_dbg = None
            r2bb_dbg = None
            r2amt_dbg = None
        debug_meta = {
            "policy_version": version,
            "table_mode": obs.table_mode,
            "spr_bucket": obs.spr_bucket,
            "board_texture": obs.board_texture,
            "pot_type": getattr(obs, "pot_type", "single_raised"),
            "rollout_pct": int(os.getenv("SUGGEST_V1_ROLLOUT_PCT") or 0),
            "rolled_to_v1": (version == "v1"),
            "config_versions": cfg_versions,
            "config_profile": profile,
            "strategy": config_strategy_name(),
            # units
            "to_call_bb": to_call_bb_dbg,
            "open_to_bb": open_to_bb_dbg,
            "pot_odds": None if pot_odds_dbg is None else round(pot_odds_dbg, 6),
            "reraise_to_bb": r2bb_dbg,
            "reraise_to_amount": r2amt_dbg,
            "fourbet_to_bb": (resp.get("meta") or {}).get("fourbet_to_bb"),
            "cap_bb": (resp.get("meta") or {}).get("cap_bb"),
            "bucket": (resp.get("meta") or {}).get("bucket"),
            # flop v1 diagnostics
            "role": getattr(obs, "role", "na"),
            "range_adv": getattr(obs, "range_adv", False),
            "nut_adv": getattr(obs, "nut_adv", False),
            "facing_size_tag": getattr(obs, "facing_size_tag", "na"),
        }
        resp["debug"] = {"meta": debug_meta}

    # Structured log for v1 (or when debug enabled), including profile
    try:
        log = logging.getLogger(__name__)
        if version == "v1" or (os.getenv("SUGGEST_DEBUG") or "0") == "1":
            action = str(resp.get("suggested", {}).get("action", ""))
            amount = resp.get("suggested", {}).get("amount")
            log.info(
                "suggest_v1",
                extra={
                    "policy_name": policy_name,
                    "street": obs.street,
                    "action": action,
                    "amount": amount,
                    "size_tag": (resp.get("meta") or {}).get("size_tag"),
                    "plan": (resp.get("meta") or {}).get("plan"),
                    "hand_class6": getattr(obs, "hand_class", None),
                    "config_profile": resp.get("debug", {})
                    .get("meta", {})
                    .get("config_profile"),
                    "strategy": config_strategy_name(),
                    "rolled_to_v1": (version == "v1"),
                    "confidence": resp.get("confidence"),
                    "pot_type": getattr(obs, "pot_type", None),
                    "to_call_bb": (
                        float(obs.to_call) / float(obs.bb) if obs.bb else None
                    ),
                    "pot_odds": (
                        (float(obs.to_call) / float(obs.pot_now + obs.to_call))
                        if (obs.pot_now + obs.to_call) > 0
                        else None
                    ),
                    "threebet_to_bb": (resp.get("meta") or {}).get("reraise_to_bb"),
                    "fourbet_to_bb": (resp.get("meta") or {}).get("fourbet_to_bb"),
                    "bucket": (resp.get("meta") or {}).get("bucket"),
                },
            )
    except Exception:
        pass

    return drop_nones(resp)
