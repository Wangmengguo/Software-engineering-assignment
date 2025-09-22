Fix Preflop & Flop v1 — Executable Task List

Goal
- Remove clear exploit spots in preflop and flop v1 while keeping the “teaching-first” contract stable (Decision + SizeSpec, rationale, meta fields).
- Implement in small, testable steps. Do not advance phases until acceptance criteria are met.

Conventions
- Code references use repo‑relative path with line anchors for orientation.
- Each task has: scope, changes, acceptance, tests. Keep changes minimal and focused.

Phase 0 — Alignment (spec only; no code)
0.1 Confirm constants and inputs
- Scope: Verify HC_VALUE, HC_OP_TPTK, HC_STRONG_DRAW are available in policy.py flows and hand_class mapping is correct in observations pipeline.
- Acceptance: We can create unit fixtures with those hand_class values and see policy_flop_v1 route conditions without KeyError.
- Tests: Basic import + a dry run of policy_flop_v1 on mocked Observation with each class.

Phase 1 — Preflop: SB vs 3bet path and pricing
1.1 SB facing 3bet (4bet disabled) — add call-only helper
- Scope: Add a helper that handles SB vs BB 3bet when 4bet feature is disabled, using the correct vs table and threebet bucketing.
- Changes:
  - Add decide_sb_vs_threebet_callonly(obs, ctx, cfg) in poker-teaching-v1-alpha/packages/poker_core/suggest/policy_preflop.py (next to decide_sb_vs_threebet). Use:
    - Guard: preflop, to_call>0, not first_to_act, not last_to_act, and ctx.flags.enable_preflop_4bet is false.
    - threebet_to_bb = _threebet_to_bb(obs); bucket = _bucket_threebet_to(threebet_to_bb, ctx) [policy_preflop.py:202–238]
    - Table: ctx.vs_table["SB_vs_BB_3bet"][bucket].call for allowed continue set, no raise path.
    - Pricing: pot_odds = obs.to_call/(obs.pot_now+obs.to_call). Threshold: use modes.HU.defend_threshold_ip (default 0.42) as starting point for IP call gate in 3bet pots; expose meta {bucket, threebet_to_bb, pot_odds}.
    - Plan: mirror _plan_sb_rfi() wording without 4bet lines: “≤small 跟注；≤mid 跟注；更大 弃牌”。
- Acceptance:
  - When 4bet disabled and SB is facing 3bet, code path uses SB_vs_BB_3bet table, never BB_vs_SB.
  - If combo in call set and pot_odds≤thr → call; else fold.
- Tests:
  - Unit: SB opens, BB 3bets to small/mid/large buckets with two combos (one in call, one out). Assert decision action and meta.bucket.
  - Snapshot: one golden case per bucket.

1.2 Wire call-only helper in policy_preflop_v1 fallback
- Scope: In poker-teaching-v1-alpha/packages/poker_core/suggest/policy.py, after decide_sb_vs_threebet(...), add a fallback call to decide_sb_vs_threebet_callonly(...). Replace incorrect BB_vs_SB fallback use for SB facing 3bet.
- Changes:
  - policy.py:298–420 — insert branch just after existing decide_sb_vs_threebet return path. Ensure it triggers only for SB facing 3bet (to_call>0, not first_to_act, not last_to_act).
- Acceptance:
  - In SB vs 3bet (4bet disabled), policy_preflop_v1 returns the call-only helper’s decision.
  - No regression for BB vs SB open defend path.
- Tests:
  - Unit: the same fixtures as 1.1 but entrypoint through policy_preflop_v1; assert suggestions identical to helper.

1.3 Fix odd fallback price condition in decide_sb_vs_threebet
- Scope: The current fallback uses pot_odds>0.4 or threebet_to_bb<2.2 to allow calls, which is counterintuitive.
- Changes:
  - policy_preflop.py:251–272 — change to: allow call only when pot_odds≤thr (thr from modes.HU.defend_threshold_ip, default 0.42) OR threebet_to_bb is extremely small (<2.2) for protection.
  - Explain threshold in rationale data.
- Acceptance:
  - Calls are not taken at poor price.
  - Existing tests adapted to thresholds.
- Tests:
  - Unit: cases above/under threshold flip from prior behavior accordingly.

Phase 2 — Flop: add MDF/price fold gating vs large sizes
2.1 Add fold gating vs two_third+ for weak classes
- Scope: When facing size_tag two_third+ and hand is not strong, prefer fold instead of unconditional call.
- Changes:
  - policy_flop_v1 at poker-teaching-v1-alpha/packages/poker_core/suggest/policy.py:729–748
    - Insert before generic “if find_action('call')” fallback: if fst=="two_third+" and hand_class not in {HC_VALUE, HC_STRONG_DRAW, HC_OP_TPTK} and not meta["nut_adv"], then fold if fold is legal. Optionally guard by pot_odds>0.40.
- Acceptance:
  - Weak holdings vs two_third+ default to fold; strong keep their existing paths.
- Tests:
  - Unit: weak class vs two_third+ → fold; strong_draw/value/TPTK vs two_third+ → not auto-fold.

2.2 Semi-bluff raise allowance vs half for strong draws
- Scope: Mirror the existing third-size semi-bluff raise allowance to half-size.
- Changes:
  - policy_flop_v1: add condition fst in {"third","half"} and hand_class==HC_STRONG_DRAW → raise with SizeSpec.tag("half") or configurable size.
- Acceptance:
  - Strong draws vs half now can raise when legal; default stays call for others.
- Tests:
  - Unit: strong_draw vs half has a raise suggestion; vs third unchanged.

2.3 Value raise stub for TPTK/overpair at low SPR vs small/half
- Scope: When spr is low (“le3”) and facing small/half, TPTK/overpair should have a value-raise option.
- Changes:
  - policy_flop_v1: after JSON value-raise miss, add branch if obs.spr_bucket == "le3" and hand_class in {HC_OP_TPTK} and fst in {"third","half"} → raise SizeSpec.tag("two_third").
- Acceptance:
  - TPTK/overpair at low SPR gains raise value line.
- Tests:
  - Unit: le3 + TPTK vs third/half → raise two_third; mid/high SPR → not forced.

Phase 3 — Tests, metrics, toggles
3.1 Unit tests
- Scope: Add targeted tests only for changed branches to avoid broad regressions.
- Changes:
  - tests/:
    - test_preflop_sb_vs_threebet_callonly.py — buckets small/mid/large; combs in/out call set; 4bet disabled.
    - test_preflop_sb_vs_threebet_fallback_threshold.py — verify price threshold behavior.
    - test_flop_facing_large_gating.py — weak vs two_third+ folds; strong not forced.
    - test_flop_strong_draw_raise_half.py — semi-bluff vs half enabled.
    - test_flop_tptk_low_spr_raise.py — value raise for le3 TPTK/overpair.
- Acceptance: All new tests green; existing tests unaffected.

3.2 Metrics/telemetry (optional, non‑blocking)
- Scope: Track counts of “flop large facing → fold” and “sb_vs_3bet_callonly path” for sanity.
- Changes: apps/web-django/api/metrics.py — increment counters in service integrate points.
- Acceptance: New counters visible in /metrics; can be off if not needed now.

Phase 4 — Rollout & docs
4.1 Feature flags and defaults
- Scope: Ensure behavior is gated by existing flags where applicable (SUGGEST_PREFLOP_ENABLE_4BET, SUGGEST_FLOP_VALUE_RAISE) and that new behaviors don’t break defaults.
- Changes: Only wire new helper when 4bet disabled; keep value-raise JSON precedence.
- Acceptance: With all flags default, no breaking changes; improvements active where intended.

4.2 Docs updates
- Scope: Update README “策略关键口径”和 SUGGEST_FILE_INDEX 说明新增 preflop 分流和 flop gating。
- Changes: README.md; docs/SUGGEST_FILE_INDEX.md.
- Acceptance: Brief bullets added; no deep rewrite.

Out-of-scope backlog (later)
- Use real effective stack for cap instead of spr_bucket heuristic in preflop helpers.
- Expand JSON rules to encode TPTK/overpair facing bet raise conditions (so code stubs can be simplified later).

Execution Notes
- Implement Phase 1 first (1.1→1.3), land tests; only then proceed to Phase 2.
- Keep diffs tight; avoid refactors outside listed files/blocks.
- If any test requires fixture helpers, add minimal local helpers under tests/.

