# poker_core/suggest/utils.py
from __future__ import annotations
from typing import Optional, List, Tuple
from poker_core.domain.actions import LegalAction

def pick_betlike_action(acts: List[LegalAction]) -> Optional[LegalAction]:
    # 先 bet，再退而求其次 raise
    for name in ("bet", "raise"):
        a = next((x for x in acts if x.action == name), None)
        if a and a.min is not None and a.max is not None and a.min <= a.max:
            return a
    return None

def find_action(acts: List[LegalAction], name: str) -> Optional[LegalAction]:
    return next((a for a in acts if a.action == name), None)

def to_call_from_acts(acts: List[LegalAction]) -> int:
    a = find_action(acts, "call")
    return int(a.to_call) if a and a.to_call is not None else 0
