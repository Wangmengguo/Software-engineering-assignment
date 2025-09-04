import json
import pytest
from django.test import Client


def _post(c: Client, url: str, payload: dict):
    return c.post(url, data=json.dumps(payload), content_type="application/json")


@pytest.mark.django_db
def test_ui_game_page_and_act_flow():
    c = Client()
    # 准备：创建会话与手牌
    sid = _post(c, "/api/v1/session/start", {}).json()["session_id"]
    hid = _post(c, "/api/v1/hand/start", {"session_id": sid, "seed": 7}).json()["hand_id"]

    # 访问 UI 页面
    r = c.get(f"/api/v1/ui/game/{sid}/{hid}")
    assert r.status_code == 200
    assert b"action-form" in r.content

    # 获取一次 state，选择一个合法动作
    st = c.get(f"/api/v1/hand/state/{hid}").json()
    legal = st.get("legal_actions") or ["check"]
    action = legal[0]

    # 走 UI 粘合端点
    r2 = c.post(f"/api/v1/ui/hand/{hid}/act", data={"action": action})
    assert r2.status_code == 200
    # OOB 片段中应包含 legal-actions/amount-wrap 的容器
    text = r2.content.decode("utf-8")
    assert "id=\"legal-actions\"" in text
    assert "id=\"amount-wrap\"" in text


@pytest.mark.django_db
def test_ui_coach_suggest_returns_panel():
    c = Client()
    sid = _post(c, "/api/v1/session/start", {}).json()["session_id"]
    hid = _post(c, "/api/v1/hand/start", {"session_id": sid, "seed": 11}).json()["hand_id"]
    # 轮到谁
    st = c.get(f"/api/v1/hand/state/{hid}").json()
    actor = int(st["state"]["to_act"]) if st.get("state") else 0
    r = c.post(f"/api/v1/ui/coach/{hid}/suggest", data={"hand_id": hid, "actor": actor})
    assert r.status_code == 200
    assert b"id=\"coach-panel\"" in r.content

