# 德州扑克学习系统：软件工程实践蓝图 v1 alpha - 2

> 本页承接 v1 alpha 主文档，继续输出“对局（Session）层 & 建议（Suggest）”最小增量的**可复制实现**。保持“教学透明 + 最小改动 + 随时回滚”。

---

## 0. 目标与范围（MVP 补全）

- **对局层（Session）外壳**：
  - `GET  /api/v1/session/{session_id}/state`：按钮位、当前手数、两侧筹码、当前 hand\_id。
  - `POST /api/v1/session/next`：上一手结束后开下一手（按钮轮转、堆栈延续）。
  - **Session JSON 入库**（最小字段）。
- **建议（Suggest）雏形**：
  - `POST /api/v1/suggest`：基于当前 `hand_id, actor` 返回一个**合法**且**可执行**的最小建议 + 简短理由。
- **UI 可视化**：Stacks 药丸、按钮位、Next Hand 按钮；（动作面板/时间线留到下一小步）

> 仍仅支持 **2 人局、无边池、No‑limit 简化**；维持我们现有的“状态机在 `poker_core`、Django 只做编排”的分层原则。

---

## 1. 领域层增量（poker\_core）

### 1.1 `snapshot_session(gs)`

把**当前手**的领域状态，折叠为“对局视角”的最小只读视图（按钮位、两侧筹码、当前 hand\_id）。

```python
# packages/poker_core/session_view.py
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from typing import Any, Dict

def snapshot_session(gs: Any) -> Dict:
    """从当前 GameState 生成对局视图（最小字段）。"""
    def to_dict(x):
        if is_dataclass(x): return asdict(x)
        if hasattr(x, "__dict__"): return dict(x.__dict__)
        return x
    s = to_dict(gs)
    players = s.get("players", [])
    stacks = []
    for p in players:
        if is_dataclass(p): p = asdict(p)
        stacks.append(p.get("stack", 0))
    return {
        "session_id": s.get("session_id"),
        "button": s.get("button"),
        "stacks": stacks,
        "hand_counter": s.get("hand_counter", 1),
        "current_hand_id": s.get("hand_id"),
    }
```

### 1.2 `next_hand(session_cfg, last_gs, seed=None)`

基于上一手结算后的 `GameState` 推出下一手：按钮轮转、堆栈延续、手数+1。保持**纯函数**。

```python
# packages/poker_core/session_flow.py
from __future__ import annotations
from typing import Any, Optional
from dataclasses import replace
from poker_core.state_hu import start_hand

def next_hand(cfg: Any, last_gs: Any, seed: Optional[int] = None):
    """基于上一手（已 complete）的 gs 推导下一手：按钮轮转、堆栈延续、手数+1。"""
    assert getattr(last_gs, "street", None) == "complete", "last hand not complete"
    # 轮转按钮
    next_button = 1 - getattr(last_gs, "button")
    # 继承筹码（堆栈已在 settle 中变更到位）
    stacks = [last_gs.players[0].stack, last_gs.players[1].stack]
    # hand_counter + 1（如果 cfg/gs 里维护该字段，按你的结构替换即可）
    next_counter = getattr(last_gs, "hand_counter", 1) + 1
    # 开新手（hand_id 由上层生成；这里只返回组装好的新 gs）
    # 注意：start_hand 需要 session_id/hand_id/button/seed；hand_id 交给视图层生成
    return {
        "button": next_button,
        "stacks": stacks,
        "hand_counter": next_counter,
        "seed": seed,
    }
```

> 为什么：**跨手编排留在领域层**，保证“按钮轮转/堆栈延续/手数+1”的规则可测试、可复用；视图层只负责 hand\_id 生成与持久化。

---

## 2. 数据层（Django 最小 Session 表）

> 先用 JSONField 保持灵活（教学期优先速度），后续需要范式化再迁移。

```python
# apps/web-django/api/models.py （在现有 Replay 模型旁边新增）
from django.db import models

class Session(models.Model):
    session_id = models.CharField(max_length=64, unique=True)
    config = models.JSONField(default=dict)       # SB/BB/init_stack 等
    stacks = models.JSONField(default=list)       # [p0, p1]
    button = models.IntegerField(default=0)       # 0 or 1
    hand_counter = models.IntegerField(default=1)
    status = models.CharField(max_length=16, default="running")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Session({self.session_id})"
```

迁移：

```bash
cd apps/web-django

# 基本：重新生成并执行迁移
python manage.py makemigrations api
python manage.py migrate

# 若你把 migrations/ 删了，但数据库里的表还在：
# 1) 重新生成“初始迁移”（会根据 models.py 自动生成）
python manage.py makemigrations api
# 2) 用 --fake-initial 标记已存在的表为已迁移（不重复建表）
python manage.py migrate --fake-initial

# 若是开发环境想“从零重来”（会清空数据，谨慎）：
# rm -rf api/migrations
# python manage.py makemigrations api
# python manage.py migrate

# 使用 Postgres 时别忘了加载环境变量（或设置 DATABASE_URL）：
# export $(cat ../../.env | xargs)
```

---

## 3. 视图层（DRF 端点）

> 延续 `views_play.py`。我们只新增“会话状态”“下一手”和“建议”三类端点，**不改动已有**。

### 3.1 GET /api/v1/session/{session\_id}/state

```python
# apps/web-django/api/views_play.py (追加)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, inline_serializer
from django.shortcuts import get_object_or_404

from .models import Session
from .state import HANDS

SessionStateResp = inline_serializer(
    name="SessionStateResp",
    fields={
        "session_id": serializers.CharField(),
        "button": serializers.IntegerField(),
        "stacks": serializers.ListField(child=serializers.IntegerField()),
        "hand_counter": serializers.IntegerField(),
        "current_hand_id": serializers.CharField(required=False, allow_null=True),
    }
)

@extend_schema(responses={200: SessionStateResp})
@api_view(["GET"])
def session_state_api(request, session_id: str):
    s = get_object_or_404(Session, session_id=session_id)
    # 尝试从内存映射取当前手（教学期：最后一次启动的 hand）
    current_hand_id = None
    for hid, v in HANDS.items():
        if v.get("session_id") == session_id:
            current_hand_id = hid
            break
    return Response({
        "session_id": s.session_id,
        "button": s.button,
        "stacks": s.stacks,
        "hand_counter": s.hand_counter,
        "current_hand_id": current_hand_id,
    })
```

### 3.2 POST /api/v1/session/next

```python
# apps/web-django/api/views_play.py (追加)
import uuid
from rest_framework import status
from poker_core.session_flow import next_hand
from poker_core.state_hu import start_hand, settle_if_needed

NextHandResp = inline_serializer(
    name="NextHandResp",
    fields={
        "session_id": serializers.CharField(),
        "hand_id": serializers.CharField(),
        "state": serializers.JSONField(),
    }
)

@extend_schema(
    request=inline_serializer(name="NextHandReq", fields={
        "session_id": serializers.CharField(),
        "seed": serializers.IntegerField(required=False, allow_null=True),
    }),
    responses={200: NextHandResp}
)
@api_view(["POST"])
def session_next_api(request):
    session_id = request.data.get("session_id")
    seed = request.data.get("seed")
    s = get_object_or_404(Session, session_id=session_id)

    # 找到该会话最近一手（教学期：在内存 HANDS 中找一个）
    latest_hid = None
    latest_gs = None
    for hid, v in list(HANDS.items())[::-1]:  # 反向扫
        if v.get("session_id") == session_id:
            latest_hid = hid
            latest_gs = v.get("gs")
            break
    if latest_gs is None or getattr(latest_gs, "street", None) != "complete":
        return Response({"detail": "last hand not complete"}, status=status.HTTP_409_CONFLICT)

    # 由领域层计算下一手的基本参数（按钮、堆栈、手数+1）
    nh = next_hand(cfg=v.get("cfg", None) or {}, last_gs=latest_gs, seed=seed)

    # 更新 Session（按钮/手数/堆栈）
    s.button = nh["button"]
    s.stacks = nh["stacks"]
    s.hand_counter = nh["hand_counter"]
    s.save(update_fields=["button", "stacks", "hand_counter", "updated_at"])

    # 启动新手
    new_hid = str(uuid.uuid4())
    gs_new = start_hand(v.get("cfg"), session_id=session_id, hand_id=new_hid, button=s.button, seed=seed)
    HANDS[new_hid] = {"gs": gs_new, "session_id": session_id, "cfg": v.get("cfg")}

    from .state import snapshot_state
    return Response({
        "session_id": session_id,
        "hand_id": new_hid,
        "state": snapshot_state(gs_new),
    })
```

> 为什么：**“跨手规则在领域，hand\_id 生成与持久化在视图”**，分工清晰；409 让未结束强启 next 的情况**早失败**。

### 3.3 POST /api/v1/suggest（最小可玩版）

- 先支持 **Preflop**：用我们已有的起手牌分类 + 位置简单规则；
- 仅返回**当前 ****\`\`**** 的子集**；

```python
# apps/web-django/api/views_suggest.py （新建）
from __future__ import annotations
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, inline_serializer
from django.shortcuts import get_object_or_404

from .state import HANDS
from poker_core.state_hu import legal_actions, to_act_index  # 你若有帮助函数可复用
from poker_core.analysis import annotate_player_hand

SuggestResp = inline_serializer(
    name="SuggestResp",
    fields={
        "hand_id": serializers.CharField(),
        "actor": serializers.IntegerField(),
        "suggested": serializers.JSONField(),
        "rationale": serializers.ListField(child=serializers.JSONField()),
    }
)

@extend_schema(
    request=inline_serializer(name="SuggestReq", fields={
        "hand_id": serializers.CharField(),
        "actor": serializers.IntegerField(min_value=0, max_value=1),
    }),
    responses={200: SuggestResp}
)
@api_view(["POST"])
def suggest_api(request):
    hand_id = request.data.get("hand_id")
    actor = int(request.data.get("actor"))
    v = HANDS.get(hand_id)
    if not v:
        return Response({"detail": "hand not found"}, status=404)
    gs = v["gs"]

    la = set(legal_actions(gs))
    # 起手建议（最小版）：弱牌且位置不利 → fold；同花相连 → raise 小额；其他 → call/check
    hole = gs.players[actor].hole
    info = annotate_player_hand(hole)
    notes = info.get("notes", [])

    def pick():
        if any(n.get("code") == "E002" for n in notes) and ("fold" in la):
            return {"action": "fold"}
        if info["info"].get("suited") and info["info"].get("gap", 9) <= 1 and ("raise" in la or "bet" in la):
            # 简化：最小加注或半池下注
            return {"action": "raise" if "raise" in la else "bet", "amount": max(getattr(gs, "bb", 2), 2)}
        # 默认兜底：优先 check / 其次 call
        if "check" in la: return {"action": "check"}
        if "call" in la: return {"action": "call"}
        # 再不行就 allin（极少触发）
        return {"action": "allin"}

    suggested = pick()
    return Response({
        "hand_id": hand_id,
        "actor": actor,
        "suggested": suggested,
        "rationale": notes,
    })
```

> 为什么：**建议只给“合法且可执行”的动作**，并保留“解释列表”（rationale）以符合教学目标；复杂策略以后再迭代。

---

## 4. URL 绑定

```python
# apps/web-django/api/urls.py （追加）
from django.urls import path
from .views_play import session_state_api, session_next_api
from .views_suggest import suggest_api

urlpatterns += [
    path("v1/session/<str:session_id>/state", session_state_api),
    path("v1/session/next", session_next_api),
    path("v1/suggest", suggest_api),
]
```

---

## 5. UI 最小改动（KPI 药丸 + Next Hand 按钮）

在 `api/templates/demo.html` 的 KPI 区追加三颗：

```html
<div class="kpi">
  <div>Stacks P0: <span id="s0">-</span></div>
  <div>Stacks P1: <span id="s1">-</span></div>
  <div>Button: <span id="btn">-</span></div>
  <button id="nextBtn">Next hand</button>
</div>
<script>
async function refreshSession() {
  if (!window.__SID || !window.__HID) return;
  const r = await fetch(`/api/v1/session/${window.__SID}/state`).then(r=>r.json());
  document.getElementById('s0').textContent = r.stacks?.[0] ?? '-';
  document.getElementById('s1').textContent = r.stacks?.[1] ?? '-';
  document.getElementById('btn').textContent = r.button === 0 ? 'P0' : 'P1';
}
async function nextHand(){
  if (!window.__SID) return;
  const r = await fetch('/api/v1/session/next', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id: window.__SID})}).then(r=>r.json());
  if (r.hand_id){ window.__HID = r.hand_id; await refreshSession(); }
}
setInterval(refreshSession, 2000);
(document.getElementById('nextBtn')).onclick = nextHand;
</script>
```

---

## 6. 测试与验收（最小 E2E）

```python
# tests/test_session_flow.py
import json
from django.test import Client

def _post(c, url, payload):
    return c.post(url, data=json.dumps(payload), content_type="application/json")

def test_next_hand_rotates_button_and_carries_stacks(db):
    c = Client()
    sid = _post(c, "/api/v1/session/start", {}).json()["session_id"]
    hid = _post(c, "/api/v1/hand/start", {"session_id": sid, "seed": 42}).json()["hand_id"]
    # 快速把一手打完（这里示意：循环直到 hand_over）
    for _ in range(30):
        s = c.get(f"/api/v1/hand/{hid}/state").json()
        la = s.get("legal_actions", []) or ["check"]
        r = _post(c, f"/api/v1/hand/{hid}/act", {"action": la[0]}).json()
        if r.get("hand_over"): break
    # 开下一手
    r = _post(c, "/api/v1/session/next", {"session_id": sid}).json()
    assert r.get("hand_id")
    st = r.get("state", {})
    assert st.get("street") == "preflop"
    # 查询对局状态
    ss = c.get(f"/api/v1/session/{sid}/state").json()
    assert ss.get("hand_counter") >= 2
```

---

## 7. 为什么这样做（工程视角）

- **契约先行**：每个端点在实现前写好 OpenAPI，`/api/docs` 可交互 → 降低前后端沟通成本。
- **分层清晰**：跨手规则在领域层（可测可复用），hand\_id 生成与持久化在视图层（低耦合）。
- **最小持久化**：Session 先 JSON 化，保证速度与弹性；将来需要范式化再做迁移。
- **早失败**：`session/next` 对未完成的手返回 409，避免隐性状态错乱。
- **合法性约束**：Suggest 只从 `legal_actions` 里挑动作，确保任何时候“建议都可执行”。
- **可视化驱动学习**：每加一个能力，首页 KPI 与 /api/docs 都能立刻“看见变化”。

---

## 8. 落地 checklist（按序执行）

1. 新增 `session_view.py` 与 `session_flow.py` 并写最小测试；
2. 新增 `Session` 模型并迁移；
3. 在 DRF 增 `session_state_api`、`session_next_api`、`suggest_api` 并挂路由；
4. 页面加三颗 KPI 药丸 + Next Hand 按钮；
5. 跑最小 E2E 测试，确认能连打两手且按钮轮转；
6. 文档站勾掉对应条目，进入下一个小迭代（动作面板/时间线/Bot）。



---

## 附录：实现补丁 v1‑alpha‑2.1（新增/修改文件清单 + 粘贴块）

> 目的：修复“堆栈延续未落地、hand\_no 归属不清、返回值契约松散”等问题；以**最小改动**打通“按钮轮转 + 延续筹码 + 稳定契约”。

### 变更总览

- ✅ **新增** `packages/poker_core/session_types.py`：稳定数据模型（`SessionView`、`NextHandPlan`）。
- ✅ **新增** `start_hand_with_carry(...)`：在不改动现有 `start_hand` 的前提下，支持**带入上一手筹码**开新手。
- ✅ **重写** `packages/poker_core/session_flow.py::next_hand`：以 `SessionView` 为输入，返回 `NextHandPlan`（包含 `session_id/next_button/stacks/next_hand_no/seed`）。
- ✅ **拆分** `packages/poker_core/session_view.py`：提供 `snapshot_session_from_gs`（过渡）与 `snapshot_session_from_model`（目标）。
- ✅ **调整** `apps/web-django/api/views_play.py::session_next_api`：按计划对象启动新手（调用 `start_hand_with_carry`），并同步会话表。
- ✅ **测试**：补充跨手 E2E 与不变量断言。

---

### 1) `packages/poker_core/session_types.py`（新增）

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, Optional

@dataclass(frozen=True)
class SessionView:
    session_id: str
    button: int                 # 0 or 1
    stacks: Tuple[int, int]     # (p0, p1)
    hand_no: int                # 第几手（从 1 开始）
    current_hand_id: Optional[str] = None

@dataclass(frozen=True)
class NextHandPlan:
    session_id: str
    next_button: int
    stacks: Tuple[int, int]
    next_hand_no: int
    seed: Optional[int] = None
```

---

### 2) `packages/poker_core/state_hu.py`（追加 helper：带入筹码开新手）

```python
# 追加到文件尾部或合适位置
from dataclasses import replace
from typing import Tuple

def start_hand_with_carry(cfg, session_id: str, hand_id: str, button: int,
                          stacks: Tuple[int, int], seed: int | None = None):
    """在沿用上一手 stacks 的前提下开新手。
    - 不修改原 start_hand 的签名/行为，避免破坏现有调用点。
    """
    gs = start_hand(cfg, session_id=session_id, hand_id=hand_id, button=button, seed=seed)
    p0 = replace(gs.players[0], stack=stacks[0], invested_street=0)
    p1 = replace(gs.players[1], stack=stacks[1], invested_street=0)
    gs = replace(gs, players=(p0, p1))
    return gs
```

---

### 3) `packages/poker_core/session_flow.py`（重写 next\_hand：面向 Session）

```python
from __future__ import annotations
from typing import Optional
from poker_core.session_types import SessionView, NextHandPlan


def next_hand(session: SessionView, last_gs, seed: Optional[int] = None) -> NextHandPlan:
    """基于会话视图 + 上一手（已 complete）的 gs 规划下一手。
    - 轮转按钮
    - 沿用上一手后的 stacks
    - hand_no + 1
    - 透传 seed
    """
    assert getattr(last_gs, "street", None) == "complete", "last hand not complete"
    next_button = 1 - session.button
    stacks = (last_gs.players[0].stack, last_gs.players[1].stack)
    return NextHandPlan(
        session_id=session.session_id,
        next_button=next_button,
        stacks=stacks,
        next_hand_no=session.hand_no + 1,
        seed=seed,
    )
```

---

### 4) `packages/poker_core/session_view.py`（过渡版 & 目标版）

```python
from __future__ import annotations
from poker_core.session_types import SessionView

# 过渡：从 gs 折叠最小会话视图（没有真正的 hand_no）

def snapshot_session_from_gs(gs) -> SessionView:
    return SessionView(
        session_id=getattr(gs, "session_id"),
        button=int(getattr(gs, "button")),
        stacks=(gs.players[0].stack, gs.players[1].stack),
        hand_no=1,
        current_hand_id=getattr(gs, "hand_id", None),
    )

# 目标：从 Session 模型折叠

def snapshot_session_from_model(session_model) -> SessionView:
    return SessionView(
        session_id=session_model.session_id,
        button=int(session_model.button),
        stacks=tuple(session_model.stacks),
        hand_no=int(session_model.hand_counter),
        current_hand_id=None,
    )
```

---

### 5) `apps/web-django/api/views_play.py`（替换 session\_next\_api 的关键逻辑）

```python
# 顶部 import 补充
from poker_core.session_types import SessionView
from poker_core.session_flow import next_hand
from poker_core.state_hu import start_hand_with_carry

# ... 保持其他代码不变，仅替换 session_next_api 内部

@api_view(["POST"])
def session_next_api(request):
    session_id = request.data.get("session_id")
    seed = request.data.get("seed")
    s = get_object_or_404(Session, session_id=session_id)

    # 找到该会话最近一手且 complete 的 gs
    latest_gs, latest_cfg = None, None
    for hid, v in list(HANDS.items())[::-1]:
        if v.get("session_id") == session_id and getattr(v.get("gs"), "street", None) == "complete":
            latest_gs, latest_cfg = v["gs"], v.get("cfg")
            break
    if latest_gs is None:
        return Response({"detail": "last hand not complete"}, status=status.HTTP_409_CONFLICT)

    # 会话视图
    sv = SessionView(
        session_id=s.session_id,
        button=int(s.button),
        stacks=tuple(s.stacks),
        hand_no=int(s.hand_counter),
    )

    # 规划下一手
    plan = next_hand(sv, latest_gs, seed=seed)

    # 更新 Session
    s.button = plan.next_button
    s.stacks = list(plan.stacks)
    s.hand_counter = plan.next_hand_no
    s.save(update_fields=["button", "stacks", "hand_counter", "updated_at"])

    # 启动新手（带入筹码）
    new_hid = str(uuid.uuid4())
    gs_new = start_hand_with_carry(
        latest_cfg, session_id=session_id, hand_id=new_hid,
        button=plan.next_button, stacks=plan.stacks, seed=plan.seed
    )
    HANDS[new_hid] = {"gs": gs_new, "session_id": session_id, "cfg": latest_cfg}

    from .state import snapshot_state
    return Response({
        "session_id": session_id,
        "hand_id": new_hid,
        "state": snapshot_state(gs_new),
    })
```

---

### 6) `tests/test_session_flow.py`（增强断言：延续筹码 + 轮转 + 手数）

```python
import json
from django.test import Client

def _post(c, url, payload):
    return c.post(url, data=json.dumps(payload), content_type="application/json")

def total_of(st):
    p = st.get("players", [])
    stacks = sum(int(x.get("stack", 0)) for x in p)
    return stacks + int(st.get("pot", 0))

def test_next_hand_carries_stacks_and_rotates(db):
    c = Client()
    sid = _post(c, "/api/v1/session/start", {}).json()["session_id"]
    hid = _post(c, "/api/v1/hand/start", {"session_id": sid, "seed": 42}).json()["hand_id"]

    # 打完一手
    base_total = None
    for _ in range(50):
        st = c.get(f"/api/v1/hand/{hid}/state").json()
        if base_total is None:
            base_total = total_of(st)
        la = st.get("legal_actions", []) or ["check"]
        r = _post(c, f"/api/v1/hand/{hid}/act", {"action": la[0]}).json()
        # 不变量：筹码守恒
        st2 = c.get(f"/api/v1/hand/{hid}/state").json()
        assert total_of(st2) == base_total
        if r.get("hand_over"): break

    # 开下一手
    nxt = _post(c, "/api/v1/session/next", {"session_id": sid}).json()
    assert nxt.get("hand_id")
    st_new = nxt.get("state", {})
    assert st_new.get("street") == "preflop"

    # 会话手数 +1
    ss = c.get(f"/api/v1/session/{sid}/state").json()
    assert ss.get("hand_counter", 1) >= 2
```

---

### 7) 验收说明 & 回滚策略

- **验收**：
  1. 连续两手后，`/api/v1/session/{id}/state` 的 `hand_counter` 递增、`button` 轮转；
  2. 第二手开局时，两侧 `stack` == 第一手结算后数值；
  3. 任何时刻满足筹码守恒（端到端测试中断言）。
- **回滚**：
  - 若出现兼容性问题，API 侧可暂时改回旧的 `start_hand` 调用；领域层保留 `start_hand_with_carry` 不影响现有测试；
  - dataclass 仅新增文件，不改动旧函数签名，回滚风险低。



---

## 附录：修正补丁 v1‑alpha‑2.2（盲注一致性 / 会话持久化 / 最新 hand / 迁移）

> 本附录在 v1‑alpha‑2.1 基础上进一步修复：
>
> 1. `start_hand_with_carry` 与盲注事件/字段的一致性；
> 2. 会话持久化与内存镜像割裂；
> 3. 最新 hand 选择的不稳定；
> 4. 迁移文件与路由文档。

### A. 修复：`start_hand_with_carry` 需按本手盲注从承接栈扣减

**替换** v1‑alpha‑2.1 中的 helper：

```python
# packages/poker_core/state_hu.py
from dataclasses import replace
from typing import Tuple

def start_hand_with_carry(cfg, session_id: str, hand_id: str, button: int,
                          stacks: Tuple[int, int], seed: int | None = None):
    """
    使用上一手结算后的栈（扣盲前）开新手。
    契约：`stacks` 为“新手开始前、尚未发盲”的堆栈。
    本函数会基于 start_hand 计算出的 SB/BB 投入额，从 stacks 中扣除；
    保留 players[i].invested_street，以与 events/last_bet/open_bet 保持一致。
    MVP：若承接栈小于应扣盲注，抛错并提示（后续再支持短栈处理）。
    """
    gs = start_hand(cfg, session_id=session_id, hand_id=hand_id, button=button, seed=seed)

    inv0 = gs.players[0].invested_street  # 本手 start_hand 已写入的 SB/BB
    inv1 = gs.players[1].invested_street
    s0, s1 = stacks

    if s0 < inv0 or s1 < inv1:
        raise ValueError("carry stacks smaller than blinds; unsupported in MVP")

    # 仅覆盖 stack，保留 invested_street（与事件/last_bet/open_bet 一致）
    p0 = replace(gs.players[0], stack=s0 - inv0)
    p1 = replace(gs.players[1], stack=s1 - inv1)
    gs = replace(gs, players=(p0, p1))
    return gs
```

### B. 一致化：会话持久化（DB）与内存镜像

1. ``\*\* 必须创建 DB 记录\*\*（并可选同步内存镜像）：

```python
# apps/web-django/api/views_play.py （新增/替换）
import uuid
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Session

@api_view(["POST"])
def session_start_api(request):
    init_stack = int(request.data.get("init_stack", 200))
    sb = int(request.data.get("sb", 1))
    bb = int(request.data.get("bb", 2))

    session_id = str(uuid.uuid4())
    s = Session.objects.create(
        session_id=session_id,
        config={"init_stack": init_stack, "sb": sb, "bb": bb},
        stacks=[init_stack, init_stack],
        button=0,
        hand_counter=1,
        status="running",
    )
    # 可选：若保留内存镜像
    # SESSIONS[session_id] = {"config": s.config}
    return Response({"session_id": session_id, "config": s.config})
```

2. ``（如有）应优先使用 DB 的 `Session.config`，并把 `cfg` 写入 `HANDS[hid]['cfg']`：

```python
# apps/web-django/api/views_play.py 片段
s = get_object_or_404(Session, session_id=session_id)
cfg = s.config
# ... hand 启动后：
HANDS[hand_id] = {"gs": gs, "session_id": session_id, "cfg": cfg}
```

3. `` 获取配置：

```python
latest_cfg = v.get("cfg") or s.config
```

### C. 稳定：选择“最新 hand”

`` 与 `` 一致，按插入顺序取最新：

```python
current_hand_id = None
for hid, v in reversed(list(HANDS.items())):
    if v.get("session_id") == session_id:
        current_hand_id = hid
        break
```

### D. 迁移与 CI 提醒

- 请将 `api/migrations/0002_session.py` 纳入版本库；
- CI/本地在测试前执行：

```bash
python manage.py migrate --noinput
# 可选：检查缺失迁移（某些团队会用）
# python manage.py makemigrations --check --dry-run
```

### E. README / 路由清单（Key API Routes）

在仓库 README 增加：

```
POST /api/v1/session/start
GET  /api/v1/session/{id}/state
POST /api/v1/session/next
POST /api/v1/hand/start
GET  /api/v1/hand/{id}/state
POST /api/v1/hand/{id}/act
POST /api/v1/suggest
GET  /api/v1/replay/{hand_id}
```

### F. 备注与后续

- `snapshot_session_from_gs(..., hand_no=1)` 为**过渡函数**，API 层尽量使用模型 `Session.hand_counter`；
- `start_hand_with_carry` 的 docstring 已明确“承接栈为扣盲前，函数内扣盲”；
- 后续可在 `start_hand_with_carry` 增强“短栈盲注最小化”与 All‑in SB/BB 的边界处理。



---

## 附录：修正补丁 v1‑alpha‑2.3（对齐返回体 / sb‑bb 贯穿 / stacks 语义 / 清理 SESSIONS）

> 目的：收口审核团队的四点建议，做到“文档即合同、返回即事实”。本补丁为**最小可落地**改动，配有可粘贴片段与快速验证。

### A. `/session/start` 返回体与文档对齐

**改动**：补齐 `button`、`stacks`（保留 `config` 亦可）。

```python
# apps/web-django/api/views_play.py
@api_view(["POST"])
def session_start_api(request):
    init_stack = int(request.data.get("init_stack", 200))
    sb = int(request.data.get("sb", 1))
    bb = int(request.data.get("bb", 2))
    s = Session.objects.create(
        session_id=str(uuid.uuid4()),
        config={"init_stack": init_stack, "sb": sb, "bb": bb},
        stacks=[init_stack, init_stack],
        button=0,
        hand_counter=1,
        status="running",
    )
    return Response({
        "session_id": s.session_id,
        "button": s.button,
        "stacks": s.stacks,
        "config": s.config,  # 可选保留
    })
```

**Schema**（若使用 inline\_serializer，加 2 字段）：

```python
SessionStartResp = inline_serializer(
  name="SessionStartResp",
  fields={
    "session_id": serializers.CharField(),
    "button": serializers.IntegerField(),
    "stacks": serializers.ListField(child=serializers.IntegerField()),
    "config": serializers.JSONField(required=False),
  }
)
```

**验证**：在 `/api/docs` 里调用 `POST /api/v1/session/start`，响应中应含 `button/stacks`。

---

### B. 盲注 `sb/bb` 贯穿到引擎（替换常量 1/2）

> 若暂不打算支持动态盲注，可先隐藏 `sb/bb`；建议直接贯穿，变更极小但收益大。

1. **在开手读取并保存 sb/bb**

```python
# packages/poker_core/state_hu.py
from dataclasses import replace

def start_hand(cfg, session_id: str, hand_id: str, button: int, seed=None):
    sb = int(cfg.get("sb", 1))
    bb = int(cfg.get("bb", 2))
    # ... 原有发牌/初始化
    # 发盲注：按钮位为 SB，另一位为 BB（按你现有实现）
    # p_sb.invested_street = sb; p_bb.invested_street = bb; pot += sb + bb
    # 将 sb/bb 写入 gs（如 GameState 没字段，请为其新增 sb: int = 1, bb: int = 2）
    gs = replace(gs, sb=sb, bb=bb)
    return gs
```

2. \*\*最小下注/加注逻辑改用 \*\*``

```python
# packages/poker_core/state_hu.py::legal_actions 或相关处
min_unit = getattr(gs, "bb", 2)
min_bet = max(min_unit, to_call or min_unit)
min_raise = max(min_unit, last_bet_delta or min_unit)
```

**快速测试**：`POST /api/v1/session/start` 传 `{"sb":5,"bb":10}` → 开手后任意一处最小下注金额应为 `10`。

---

### C. 明确 `stacks` 语义并补 `stacks_after_blinds`

> DB 的 `Session.stacks` 保存**承接栈（扣盲前）**；当前手 `gs.players[*].stack` 为**实时栈（扣盲后）**。API 同时返回两套，杜绝歧义。

```python
# apps/web-django/api/views_play.py
@api_view(["GET"])
def session_state_api(request, session_id: str):
    s = get_object_or_404(Session, session_id=session_id)
    current_hand_id, latest_gs = None, None
    for hid, item in reversed(list(HANDS.items())):
        if item.get("session_id") == session_id:
            current_hand_id, latest_gs = hid, item.get("gs")
            break
    stacks_after_blinds = None
    if latest_gs:
        stacks_after_blinds = [latest_gs.players[0].stack, latest_gs.players[1].stack]
    return Response({
        "session_id": s.session_id,
        "button": s.button,
        "stacks": s.stacks,  # 承接栈（扣盲前）
        "stacks_after_blinds": stacks_after_blinds,  # 实时栈（扣盲后）
        "hand_counter": s.hand_counter,
        "current_hand_id": current_hand_id,
    })
```

**文档提示**：在 README / OpenAPI 描述中注明两者含义；UI KPI 药丸可左/右各显示一套。

---

### D. 清理 `SESSIONS`（DB 为单一事实来源）

- 将所有 `SESSIONS[...]` 读取替换为 `Session.objects.get(...).config`；
- `hand_start_api` 写入 `HANDS[hid]['cfg']` 仍可保留作为**读缓存**；
- 标注 `snapshot_session_from_gs(..., hand_no=1)` 为 deprecated，API 层优先 `from_model`。

**示意**：

```python
# hand_start_api 内
s = get_object_or_404(Session, session_id=session_id)
cfg = s.config
# ... 启动后：
HANDS[hand_id] = {"gs": gs, "session_id": session_id, "cfg": cfg}
```

---

### E. 快速 E2E 验收清单

1. `/session/start` 响应含 `session_id/button/stacks`；
2. `sb/bb` 自定义后，最小下注/加注单位按 `bb` 生效；
3. `/session/state` 同时返回 `stacks` 与 `stacks_after_blinds`，语义正确；
4. 所有读取配置改为从 DB `Session.config` 获取；
5. `/session/next` 能在**上一手 complete**后成功开新手，按钮轮转、堆栈延续；
6. README 与 `/api/docs` 的字段描述与返回**完全一致**。

---

### F. 回滚策略

- 若 `sb/bb` 贯穿引起兼容问题：暂时在 `start_hand` 回退为常量（1/2），同步隐藏 `/session/start` 的 `sb/bb`；
- 保留 `HANDS[*]['cfg']` 作为读缓存，便于快速切换；
- 文档与返回字段务必**同向调整**，保持合同一致性。



---

## 9. E2E：Session 流完整校验（含 409、sb/bb、轮转、守恒）

> 本节记录你已补充并通过的端到端断言，用于回归与代码评审的“合同化清单”。

**覆盖范围**

- `GET /api/v1/session/{id}/state`、`POST /api/v1/session/next`
- `sb/bb` 贯穿（自定义盲注生效）
- 延续筹码 + 按钮轮转 + 手数递增
- 筹码守恒：`players[*].stack` 之和 + `pot` 恒等于 `2 * init_stack`

**关键断言**

- **未完成强启 next → 409**：
  - `POST /session/next` 在上一手未 `complete` 时返回 **409**。
- **新手开始 pot == sb+bb**：验证盲注已入锅且贯穿引擎。
- **手数递增**：`session/state.hand_counter == hand_no_before + 1`。
- **按钮轮转**：`button_after == 1 - button_before`。
- **sb/bb 回读一致**：`session/state.sb == sb`；`session/state.bb == bb`。
- **current\_hand\_id 一致**：`session/state.current_hand_id == 新手 hand_id`。
- **双栈语义对齐**：
  - `session/state.stacks_after_blinds == 新手 state.players[*].stack`
  - `session/state.stacks == 第一手结束时 end_stacks`（承接栈=扣盲前）
- **守恒不变量**：任意时刻 `sum(players[*].stack) + pot == 2 * init_stack`，跨手也成立。

> 备注：该 E2E 与“开手→尽量 check/call 的和平路线→/session/next”配合，确保最小路径即可结束一手并覆盖关键状态转移。

---

## 10. 下一步（面向 MVP 的最小增量路线图）

> 坚持“小步安全改动 + 可视化立刻可见 + 文档即合同”。

### P0（现在就能开做的 1–2 个迭代）

1. **动作面板（前端）**
   - 读取 `/hand/{id}/state.legal_actions`，非法按钮自动禁用；
   - 动态最小额：根据 `gs.bb` 计算最小 bet/raise；
   - “Next hand” 按钮仅在 `hand_over=true` 后启用（与 409 形成正交校验）。
2. **Suggest API v0.2（postflop 最小启发）**
   - 规则：
     - `no_bet_line` → `check`/`bet(min)`；
     - `facing_bet` → `call` 若底池赔率可接受，否则 `fold`；
   - 保持“**只从 legal\_actions 里挑**”，并返回解释 `rationale`（沿用 E001/E002/N10x）。
   - 单测：不同 `legal_actions` 与牌型组合下，建议均可执行。
3. **Replay 字段补充与合同更新**
   - 在 `/hand/over` 路径（或回放入库）**存入**：`winner`、`best5`；
   - OpenAPI 增字段；`/api/docs` 可 Try it out。
4. **会话态补充**
   - `Session` 增 `last_hand_id`（或 `current_hand_id`）；
   - `GET /session/{id}/state` 直接返回，减少一次在内存结构中 `reversed(HANDS)` 的查找。

### P1（随手就绪的工程硬化）

5. **时间线（前端）**
   - 使用 `events[]` 渲染：盲注、行动、发牌、摊牌/派彩；
   - 点击事件回放：高亮当街牌面与行动者。
6. **教学 Bot v0.1**
   - 规则驱动 + 少量随机性；保证动作合法；
   - `/suggest` 可传 `policy=bot_v0` 直接下发动作（受控模式）。
7. **可观测性**
   - 前端：`/metrics` 轮询调慢到 2.5–5s；页面隐藏时暂停（`visibilitychange`）。
   - 后端：为 `/metrics` 增速率限制与缓存 1–2s，避免 N+1 压力。
8. **CI 强化**
   - 新增 E2E 作为 gate；
   - `pytest --maxfail=1 -q`；
   - `python manage.py migrate --check`/`--noinput`；
   - 覆盖率门槛：核心 `poker_core/*` ≥ 85%。

### P2（MVP 收官前的“体验与健壮性”）

9. **错误模型与恢复**：非法时序返回 409/422；重复 `act` 幂等；
10. **并发与一致性**：同一 `hand_id` 并发行动排它（乐观锁/版本号）；
11. **DB 优化**：`Replay.hand_id`、`Session.session_id` 索引；事件表分区（可选）。

---

## 11. 本迭代“学中做”知识点映射

- **合同驱动开发（CDD）**：在实现前定义 OpenAPI，`/api/docs` 即合同，避免“口头约定”。
- **状态机建模**：街道推进、行动合法集、摊牌/派彩；以不可变数据（`dataclass`/`replace`）实现可测试的状态转移。
- **单一事实来源（SSOT）**：`Session.config`/`stacks` 落 DB；`GameState` 仅代表“当前手”。
- **适配器/策略模式**：评牌层 `PokerKitEvaluator/FallbackEvaluator` + 选择器，解耦第三方库与领域。
- **不变量测试**：筹码守恒、`pot == sb+bb`（开手）、跨手栈扣盲等，用 E2E 持续验证。
- **前后端协同最小闭环**：动作面板禁用非法按钮；`Next hand` 与 409 互证；KPI 药丸可视化。
- **演进式设计**：先 JSON 模型、最小字段；后续需要再范式化迁移。
- **可观测性与性能**：前端轮询退避/暂停，后端速率限制 + 缓存，日志采样。

---

##
