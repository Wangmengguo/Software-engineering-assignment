# poker_core/suggest/types.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List
from poker_core.domain.actions import LegalAction

@dataclass(frozen=True)
class Observation:
    hand_id: str
    actor: int
    street: str          # preflop / flop / turn / river
    bb: int
    pot: int
    to_call: int
    acts: List[LegalAction]
    tags: List[str]
    hand_class: str

@dataclass(frozen=True)
class PolicyConfig:
    open_size_bb: float = 2.5
    call_threshold_bb: int = 3
    pot_odds_threshold: float = 0.33
    pot_odds_threshold_callrange: float = 0.40
