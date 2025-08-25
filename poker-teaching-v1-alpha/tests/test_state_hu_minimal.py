# tests/test_state_hu_minimal.py
from poker_core.state_hu import start_session, start_hand, legal_actions, apply_action, settle_if_needed

def test_one_hand_checkdown_showdown():
    cfg = start_session(init_stack=200)
    gs = start_hand(cfg, session_id="s1", hand_id="h1", button=0, seed=42)
    # preflop：SB 补齐到 BB，BB check 结束本街
    gs = apply_action(gs, "call")    # SB 补齐
    gs = apply_action(gs, "check")   # BB 关街
    # flop 循环两次 check
    gs = apply_action(gs, "check")
    gs = apply_action(gs, "check")
    # turn 同
    gs = apply_action(gs, "check")
    gs = apply_action(gs, "check")
    # river 同 → 进入 showdown
    gs = apply_action(gs, "check")
    gs = apply_action(gs, "check")
    gs = settle_if_needed(gs)
    assert gs.street == "complete"
    assert gs.players[0].stack + gs.players[1].stack == 400  # 筹码守恒
