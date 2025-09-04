# 前端最小调用序列（单人牌局 MVP）

目标：最少接口完成一局德州（用户与“电脑方”对战），并可回看回放。

接口前缀：`/api/v1`

步骤

1) 创建会话（可选自定义盲注）

POST `/session/start`
Body: `{ "init_stack": 200, "sb": 1, "bb": 2 }`
Resp: `{ "session_id", "button", "stacks", "config" }`

2) 开启一手

POST `/hand/start`
Body: `{ "session_id": "...", "seed": 123 }`
Resp: `{ "hand_id", "state", "legal_actions" }`

提示：`state.to_act` 为当前行动者（0/1）。`legal_actions` 是字符串集合（用于快速 UI）
；若需结构化限制与金额区间，调用领域层或后端另有 `/hand/state` 提供。

3) 自动步进（让电脑方行动到轮到用户）

POST `/hand/auto-step/{hand_id}`
Body: `{ "user_actor": 0, "max_steps": 10 }`
Resp: `{ "hand_id", "steps": [...], "state", "hand_over", "legal_actions" }`

- 若 `hand_over == true`：一手已结束，转步骤 (6)；
- 若 `hand_over == false` 且 `state.to_act == user_actor`：轮到用户行动，继续步骤 (4)。

4) 获取建议（可选，用于教学/辅助）

POST `/suggest`
Body: `{ "hand_id": "...", "actor": 0 }`
Resp: `{ "suggested": {"action": "bet", "amount": 125}, "rationale": [...], "policy": "..." }`

5) 执行动作

POST `/hand/act/{hand_id}`
Body: `{ "action": "bet", "amount": 125 }`（金额仅在 `bet/raise/allin` 时需要）
Resp: `{ "state", "hand_over", "legal_actions", "outcome?" }`

- 若 `hand_over == false`：回到步骤 (3) 继续由电脑方自动推进；
- 若 `hand_over == true`：进入步骤 (6)。

6) 回看回放

GET `/hand/{hand_id}/replay`（或兼容旧路由 `/replay/{hand_id}`）
Resp: `{ "players", "annotations", "steps", "board", "winner", ... }`

注意

- 错误语义：
  - `404` 未找到手牌；`409` 非当前行动者/手牌已结束；`422` 无法给出建议或非法动作。
- 指标：
  - Prometheus 抓取：`/api/v1/metrics/prometheus`；
  - 常用：`api_latency_seconds{route,method,status}`、`suggest_*`（动作/错误/钳制）。

前端伪代码（fetch 版）

```js
// 1) start session
const s = await (await fetch('/api/v1/session/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({init_stack:200,sb:1,bb:2})})).json();

// 2) start hand
const h = await (await fetch('/api/v1/hand/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id: s.session_id, seed: Date.now()%100000})})).json();
let handId = h.hand_id;

while(true){
  // 3) auto-step to user's turn (user is actor 0)
  let step = await (await fetch(`/api/v1/hand/auto-step/${handId}`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({user_actor:0, max_steps:10})})).json();
  if(step.hand_over){ break; }

  // 4) suggest (optional)
  const sug = await (await fetch('/api/v1/suggest', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({hand_id: handId, actor: 0})})).json();

  // 5) act (use suggestion or user's choice)
  await fetch(`/api/v1/hand/act/${handId}`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(sug.suggested)});
}

// 6) replay
const rep = await (await fetch(`/api/v1/hand/${handId}/replay`)).json();
console.log(rep);

// 7) start next hand in the same session (optional, for full session flow)
const n = await (await fetch('/api/v1/session/next', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id: s.session_id})})).json();
// n.hand_id is the new hand; loop back to auto-step/suggest/act
```
