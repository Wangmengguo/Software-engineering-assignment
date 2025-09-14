# poker_core/suggest/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from poker_core.domain.actions import LegalAction


@dataclass(frozen=True)
class Observation:
    hand_id: str
    actor: int
    street: str  # preflop / flop / turn / river
    bb: int
    pot: int
    to_call: int
    acts: list[LegalAction]
    tags: list[str]
    hand_class: str
    # v1 additions (PR-0 baseline; defaults keep compatibility)
    table_mode: str = "HU"  # HU/4max/6max
    spr_bucket: str = "na"  # low/mid/high/na
    board_texture: str = "na"  # dry/semi/wet/na (non-flop: na)
    ip: bool = False
    # PR-1: preflop pot-odds 需要的“当前池”口径（含盲注/已投入）
    pot_now: int = 0
    # PR-1: 169 栅格组合标签（如 'AKs','KQo','TT'；未知为空串）
    combo: str = ""
    # PR-2 (Flop v1): role/MDF helpers and facing size tag
    role: str = "na"  # pfr | caller | na
    range_adv: bool = False  # heuristic range advantage on flop
    nut_adv: bool = False  # heuristic nut advantage on flop
    facing_size_tag: str = "na"  # third | half | two_third+ | na
    # v1.1: pot type classification (single_raised|limped|threebet)
    pot_type: str = "single_raised"


@dataclass(frozen=True)
class PolicyConfig:
    open_size_bb: float = 2.5
    call_threshold_bb: int = 3
    pot_odds_threshold: float = 0.33
    pot_odds_threshold_callrange: float = 0.40


# For postflop sizing annotations (preflop keeps meta.open_bb instead)
SizeTag = Literal["third", "half", "two_third", "pot", "all_in"]

__all__ = [
    "Observation",
    "PolicyConfig",
    "SizeTag",
]
