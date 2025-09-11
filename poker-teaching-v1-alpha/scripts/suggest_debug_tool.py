#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def _ensure_path():
    # Allow running from repo root without installation
    here = Path(__file__).resolve()
    pkg = here.parent.parent / "packages"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))


_ensure_path()

from poker_core.state_hu import start_hand, start_session  # type: ignore  # noqa: E402
from poker_core.suggest.service import build_suggestion  # type: ignore  # noqa: E402
from poker_core.suggest.utils import stable_roll  # type: ignore  # noqa: E402


def _set_env(policy: str, pct: int, table_mode: str, debug: int):
    if policy:
        os.environ["SUGGEST_POLICY_VERSION"] = policy
    os.environ["SUGGEST_V1_ROLLOUT_PCT"] = str(int(pct))
    os.environ["SUGGEST_TABLE_MODE"] = table_mode
    os.environ["SUGGEST_DEBUG"] = "1" if int(debug) == 1 else "0"


def cmd_single(args: argparse.Namespace) -> int:
    _set_env(args.policy, args.pct, args.table_mode, args.debug)

    # Build a minimal real GameState (preflop)
    cfg = start_session(init_stack=args.init_stack, sb=args.sb, bb=args.bb)
    hand_id = args.hand_id or f"h_cli_{int(time.time())}"
    gs = start_hand(
        cfg, session_id=args.session_id, hand_id=hand_id, button=args.button, seed=args.seed
    )
    actor = args.actor
    if actor is None:
        actor = getattr(gs, "to_act", 0)

    resp: dict[str, Any] = build_suggestion(gs, int(actor))
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    return 0


def cmd_dist(args: argparse.Namespace) -> int:
    _set_env(args.policy, args.pct, args.table_mode, args.debug)
    n = int(args.count)
    hits = 0
    samples = []
    for i in range(n):
        hid = f"h_{i}"
        hit = stable_roll(hid, int(args.pct))
        hits += 1 if hit else 0
        if args.show_sample and len(samples) < int(args.show_sample):
            samples.append({"hand_id": hid, "rolled_to_v1": hit})
    ratio = hits / max(1, n)
    out = {"count": n, "hits": hits, "rate": ratio, "pct": int(args.pct), "samples": samples}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Suggest debug tool (local, no server)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_common = argparse.ArgumentParser(add_help=False)
    ap_common.add_argument("--policy", default="v0", help="v0|v1|v1_preflop|auto (default: v0)")
    ap_common.add_argument(
        "--pct", type=int, default=0, help="v1 rollout percent when policy=auto (0-100)"
    )
    ap_common.add_argument("--table-mode", default="HU", help="HU|4max|6max (default: HU)")
    ap_common.add_argument(
        "--debug", type=int, default=1, help="1 to include debug.meta in response (default: 1)"
    )

    sp1 = sub.add_parser("single", parents=[ap_common], help="Produce a single suggestion JSON")
    sp1.add_argument("--session-id", default="s_cli", help="Session id tag")
    sp1.add_argument("--hand-id", default=None, help="Override hand id")
    sp1.add_argument("--seed", type=int, default=42, help="Shuffle seed (default: 42)")
    sp1.add_argument(
        "--button", type=int, choices=[0, 1], default=0, help="Button seat index (default: 0)"
    )
    sp1.add_argument(
        "--actor", type=int, choices=[0, 1], default=None, help="Actor index; default=gs.to_act"
    )
    sp1.add_argument(
        "--init-stack", type=int, default=200, help="Initial stack per player (default: 200)"
    )
    sp1.add_argument("--sb", type=int, default=1, help="Small blind (default: 1)")
    sp1.add_argument("--bb", type=int, default=2, help="Big blind (default: 2)")
    sp1.set_defaults(func=cmd_single)

    sp2 = sub.add_parser(
        "dist", parents=[ap_common], help="Check rollout distribution via stable hash"
    )
    sp2.add_argument("--count", type=int, default=2000, help="Number of samples (default: 2000)")
    sp2.add_argument("--show-sample", type=int, default=0, help="Show first K samples")
    sp2.set_defaults(func=cmd_dist)

    args = ap.parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
