# Poker Teaching System — v0.4+

一个“教学优先”的两人德扑（HU NLHE）系统：纯函数领域引擎 + Django/DRF API + 教学视图。

— 做什么（What） —

- 领域引擎：`packages/poker_core/state_hu.py`（SB/BB 可配置；发盲→轮次→结算；筹码守恒）。
- 评牌：优先 PokerKit，不可用时回退简化评估。
- 会话流：多手对局（按钮轮转、承接筹码）；统一回放结构持久化至 DB。
- 建议：`POST /api/v1/suggest`（preflop v0；仅从合法动作集合内选取，带钳制与理由）。
- 前端最小 UI（MVP）：HTMX + Tailwind，无轮询、事件驱动；一次响应用 OOB 同步更新 HUD/牌面/行动条/金额/Coach/错误/座位与日志；Coach 显式触发；前端零推导（动作与金额范围完全由后端提供）。
- 会话结束（MVP，仅两条规则）：
  - Bust：承接到下一手不足以贴盲（引擎 `start_hand_with_carry` 抛错）→ 结束。
  - Max Hands：达到 `max_hands`（如 20/50）→ 结束。
  - REST 返回 `409 + summary`；UI 返回 200 + OOB 结束卡片；仅在成功开出下一手时才 Push-Url。
 - 牌局回放（UI）：`GET /api/v1/ui/replay/<hand_id>` 轻量回放页（玩家/公共牌时间轴/结果居中；控制：Reset/Prev/Next/Play/Start New Session；内置 UI 锁防止播放中多次点击）。


— 怎么跑（Run） —

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[dev]'
cd apps/web-django
python manage.py makemigrations api
python manage.py migrate
python manage.py runserver
```

打开：

- API Docs: http://127.0.0.1:8000/api/docs
- Metrics:   http://127.0.0.1:8000/api/v1/metrics/prometheus
- 最小 UI 入口（浏览器）：http://127.0.0.1:8000/api/v1/ui/start

最小 UI 对局页（事件驱动 + OOB，无轮询）：

1) 直接从入口页一键开始（推荐）

浏览器打开 `http://127.0.0.1:8000/api/v1/ui/start`，点击 Start the session 即会创建会话与第一手并跳转到游戏页。

或使用 API 手动流程：

1*) 创建会话（记下 `session_id`）
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/session/start -H 'Content-Type: application/json' -d '{}'
```
2) 开一手（记下 `hand_id`）
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/hand/start -H 'Content-Type: application/json' \
     -d '{"session_id":"<session_id>", "seed": 42}'
```
3) 打开 UI 页面（浏览器）
```
http://127.0.0.1:8000/api/v1/ui/game/<session_id>/<hand_id>
```

交互节奏：仅在“执行动作 / 获取建议 / 开始下一手”时发起请求；其余时间零请求；每次响应用 OOB 片段统一更新多个区域。

— 怎么用（API 快查） —

- `POST /api/v1/session/start` 创建会话（可传 `sb/bb/max_hands`）
- `GET  /api/v1/session/<sid>/state` 会话视图
  - `stacks`: 承接栈（下一手扣盲前）
  - `stacks_after_blinds`: 当前手已扣盲后的实时栈（无手牌则为 null）
- `POST /api/v1/hand/start` 在会话内开一手（可传 `seed`）
- `GET  /api/v1/hand/<hid>/state` 查询状态与 `legal_actions`
- `POST /api/v1/hand/<hid>/act` 执行动作（`check/call/bet/raise/fold/allin`）
- `GET  /api/v1/hand/<hid>/replay` 回放（兼容 `/api/v1/replay/<hid>`）
- `GET  /api/v1/ui/replay/<hid>` 回放页面（SSR，一页内控件：Reset/Prev/Next/Play）
- `POST /api/v1/suggest` 最小建议 `{hand_id, actor}`
  - 响应：`{hand_id, actor, suggested{action,amount?}, rationale[], policy}`
  - 错误：`404` 不存在，`409` 非行动者/已结束，`422` 无法给出合法建议

会话推进/结束：

- `POST /api/v1/session/next`：成功→`200 {session_id, hand_id, state}`；若结束→`409 {session_id, ended_reason, hands_played, final_stacks:[p0,p1], pnl:[d0,d1], pnl_fmt:["+N","-N"], last_hand_id}`
  - `ended_reason ∈ {bust, max_hands}`；`last_hand_id` 便于“查看上一手”。

UI 粘合端点（HTML 片段，返回 200 + OOB；仅转译/组合，不改变底层 REST 语义）

- `GET  /api/v1/ui/game/<session_id>/<hand_id>` 首屏 SSR（HUD/牌面/座位/日志/行动条为“真数据”）。
- `POST /api/v1/ui/hand/<hand_id>/act` 执行动作（表单编码，含 CSRF；一次 OOB 更新 HUD/牌面/座位/金额/动作/日志）。
- `POST /api/v1/ui/session/<session_id>/next` 开启下一手（成功→OOB + `HX-Push-Url` 到新 hand；若结束→返回 OOB 结束卡片，不 Push）。
- `POST /api/v1/ui/coach/<hand_id>/suggest` 显式触发建议（若含金额则回填默认值；若被钳制显示胶囊提示）。
  回放页（SSR）：
 - `GET  /api/v1/ui/replay/<hand_id>`：服务器组装时间轴与基础数据；前端仅本地播放；播放时按钮带 UI 锁。
 - `POST /api/v1/ui/prefs/teach` 切换教学模式（server truth 存于 `request.session['teach']`，默认开启 Teach）。
  - 行为：返回 OOB 片段刷新 对手手牌区域 与开关按钮本身；不改变 URL。
  - 规则（摊牌展示）：仅当满足以下任一条件时，才展示对手底牌：
    1) Teach=ON；或
    2) 本手以摊牌结束（事件含 `showdown`/`win_showdown`）。
    若以弃牌结束（事件含 `win_fold`），即便 `street == 'complete'`，也不展示对手底牌。

— 怎么测（Test） —

```bash
pytest -q
coverage run -m pytest && coverage report --include "packages/poker_core/*"
```

— 怎么修（Dev/Fix） —

- 引擎：`packages/poker_core/state_hu.py`；评牌在 `packages/poker_core/providers/*`。
- 建议：`packages/poker_core/suggest/*`
  - 策略：`policy.py`；类型/工具：`types.py` / `utils.py`；服务：`service.py`
  - 动作结构化：`packages/poker_core/domain/actions.py`
- REST API：`apps/web-django/api/views_play.py`（会话/手牌/回放/会话结束）、`views_suggest.py`（建议）
  - 会话结束：`finalize_session(session, last_gs, reason)` 幂等 + 事务；返回统一 summary；在 `/session/next` 的 Max Hands 与 Bust 分支调用。
  - 并发与一致性：`/session/next` 与 `finalize_session` 使用 `transaction.atomic() + select_for_update()` 防止并发双写；仅成功开新手时返回 Push-Url（UI 端）。
- UI 粘合：`apps/web-django/api/views_ui.py`（HTMX 事件驱动 + OOB 片段）
  - 片段模板：`apps/web-django/templates/ui/`
    - `_error.html`（统一错误横幅 `#global-error`）
    - `_hud.html`（更新 `#hud-*` 与 `aria-live`）
    - `_board.html`（公共牌/底池）
    - `_seats.html`（座位/按钮位/栈与“本街投入 Bet”）
    - `_log.html`（最近 5 条行动，`You/Opponent + action [+amount]`）
    - `_action_form.html`（整表单 OOB；当 hand 变化时整体替换，确保 hx-post 指向新 hand）
    - `_actions.html`（动作按钮）
    - `_amount.html`（金额输入显示/范围/默认值）
    - `_coach.html`（建议/理由）
    - `_coach_trigger.html`（“Get Suggestion”按钮）
    - `_teach_toggle.html`（对局页头部 Teach/Practice 开关，触发 `POST /api/v1/ui/prefs/teach`）
    - `_session_end.html`（会话结束卡片：Hands / Stacks / PnL / Reason + 按钮）
  - 回放 UI：`apps/web-django/api/views_ui.py::ui_replay_view` + `templates/poker_teaching_replay.html`
    - 数据源优先内存 REPLAYS，其次 DB `Replay`；与 `/hand/<hid>/replay` 保持一致。
    - 仅界面播放，无后续请求；控制条含 Reset/Prev/Next/Play，播放时按钮禁用（UI 锁）。
- 前端骨架：`apps/web-django/templates/poker_teaching_game_ui_skeleton_htmx_tailwind.html`
  - 不轮询；仅“执行动作/获取建议/开始下一手”发请求
  - Coach 显式触发；CSRF 通过 `{% csrf_token %}` 与 `hx-headers` 注入
  - 首屏 SSR 为真数据；OOB 与刷新效果一致（Session 结束时 SSR 直接渲染结束卡片；回放页 SSR 直接可用）。

数据与迁移

- 最小迁移：`apps/web-django/api/migrations/0003_session_end_fields.py`
  - `Session.ended_reason`（null=True）、`ended_at`（null=True）、`stats`（default=dict）。
  - 老数据 `status` 保持原值（running）。

准则（MVP 保持简洁）

- 前端零推导：按钮集合、Call 文案与金额范围由后端给定；页面不做规则推断。
- 结束态优先：先判 `street in {complete, showdown_complete}`，结束态不计算合法动作，直接展示“开始下一手/回放”。
- 单次响应 OOB：一次性更新 ≥5 个区域，避免闪烁与状态错位。
- 统一错误出口：仅 `#global-error` 展示 404/409/422 文案；其它区域不弹错。

— 可选（PostgreSQL） —

```bash
docker compose -f infra/docker-compose.yml up -d
cp .env.example .env && export $(cat .env | xargs)   # Windows: 手动设置
cd apps/web-django && python manage.py migrate
```

Tips

- 自定义盲注：在 `POST /api/v1/session/start` 传 `{sb, bb}`。
- 常见 409：非当前行动者或手牌已结束；先 `GET /hand/state` 查看 `to_act/street` 再操作。
- 教学/实战切换：对局页头部提供 Teach 开关按钮（默认 ON）。切换即发起 `POST /api/v1/ui/prefs/teach`，
  服务端写入会话首选项，随后用 OOB 片段刷新 seats 与开关；SSR 与 HTMX 路径遵循同一规则，无需前端推断。
