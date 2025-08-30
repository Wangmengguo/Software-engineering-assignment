from poker_core.suggest.service import _clamp_amount_if_needed, POLICY_REGISTRY, _build_observation
from poker_core.domain.actions import LegalAction


def test_clamp_amount_if_needed_clamps_and_reports():
    acts = [LegalAction(action="bet", min=100, max=300)]
    suggested = {"action": "bet", "amount": 500}
    out, clamped, info = _clamp_amount_if_needed(suggested, acts)
    assert clamped is True
    assert out["amount"] == 300
    assert info == {"min": 100, "max": 300, "given": 500, "chosen": 300}


def test_policy_registry_contains_all_streets():
    for k in ("preflop", "flop", "turn", "river"):
        assert k in POLICY_REGISTRY


class _DummyGS:
    def __init__(self):
        self.hand_id = "h_x"
        self.street = "flop"
        self.bb = 50
        self.pot = 0


def test_build_observation_injects_warning_on_analysis_failure(monkeypatch):
    # 强制 analysis 抛错
    import poker_core.suggest.service as svc

    def _boom(gs, actor):
        raise RuntimeError("no hole cards")

    monkeypatch.setattr(svc, "annotate_player_hand_from_gs", _boom)

    gs = _DummyGS()
    acts = [LegalAction(action="check")]
    obs, pre = _build_observation(gs, 0, acts)
    assert obs.street == "flop"
    assert pre and any(x.get("code") == "W_ANALYSIS" for x in pre)

