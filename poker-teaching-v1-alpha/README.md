# Poker Teaching System — v1+

一个“教学优先”的两人德扑（HU NLHE）系统：纯函数领域引擎 + Django/DRF API + 教学视图。

— 做什么（What） —

- 领域引擎：`packages/poker_core/state_hu.py`（SB/BB 可配置；发盲→轮次→结算；筹码守恒）。
- 评牌：优先 PokerKit，不可用时回退简化评估。
- 会话流：多手对局（按钮轮转、承接筹码）；统一回放结构持久化至 DB。
- 建议（Suggest）：`POST /api/v1/suggest`（纯函数策略 + 合法性钳制 + 理由与教学 plan）。
  - Preflop v1（HU）：RFI/BB 防守，支持 3bet to-bb 计算（`meta.reraise_to_bb/bucket`）。
  - Flop v1（HU）：role+MDF 对齐；已覆盖 single_raised；limped 骨架；threebet（medium 骨架）。
  - 价值加注 JSON 化：在规则中以 `facing{third,half,two_third_plus}` 指定 two_pair+ 的 value-raise（策略透传 size_tag/plan）。
  - 统一 to-amount 口径：postflop `raise_to_amount` + `min‑reopen → cap → clamp`。
- 前端最小 UI（MVP）：HTMX + Tailwind，无轮询、事件驱动；一次响应用 OOB 同步更新 HUD/牌面/行动条/金额/Coach/错误/座位与日志；Coach 显式触发；前端零推导（动作与金额范围完全由后端提供）。
  - Coach 卡片（100% 开启）：一句话计划 + 尺寸标签 + pot_odds/MDF；Preflop/Flop 一致化展示（读 `meta/*`）。
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

可选环境变量（与建议/教学相关）

```bash
# 策略与灰度
export SUGGEST_POLICY_VERSION=v1           # v0|v1|v1_preflop|auto
export SUGGEST_STRATEGY=medium            # loose|medium|tight
export SUGGEST_V1_ROLLOUT_PCT=0           # auto 时生效
export SUGGEST_FLOP_VALUE_RAISE=1         # 价值加注 JSON 化开关（默认 1）

# 教学 Coach 开关
export COACH_CARD_V1=1                    # 开启 Coach 卡片 MVP（Preflop/Flop）

# 调试与观测
export SUGGEST_DEBUG=1                    # 返回 debug.meta（含 pot_odds/pot_type/size_tag 等）
```

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
  - 响应：`{hand_id, actor, suggested{action,amount?}, rationale[], policy, meta?}`
    - Preflop v1 关键 `meta`：`open_bb`｜`reraise_to_bb`｜`bucket`｜`pot_odds`
    - Flop v1 关键 `meta`：`plan`｜`size_tag`｜`mdf`｜`facing_size_tag`｜`spr_bucket`｜`texture`｜`pot_type`
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

- 配置测试环节
	- source .env.test

```
# 测试环境配置 - 始终使用 v1 策略
export SUGGEST_POLICY_VERSION=v1_preflop
export SUGGEST_CONFIG_DIR=packages/poker_core/suggest
export SUGGEST_DEBUG=1
export SUGGEST_TABLE_MODE=HU
```

- Suggest 调试脚本（本地，无需起服务）：
  - 单次输出（包含 debug.meta；preflop 不含 size_tag）：
    ```bash
    python scripts/suggest_debug_tool.py single \
      --policy auto --pct 10 --debug 1 --seed 42 --button 0
    ```
  - 灰度分布粗检（稳定哈希，不调用引擎）：
    ```bash
    python scripts/suggest_debug_tool.py dist --policy auto --pct 10 --debug 1 --count 2000 --show-sample 8
    ```
  - 说明：
    - 通过 `--policy/--pct/--debug/--table-mode` 设置 `SUGGEST_*` 环境变量；`--policy v0` 为默认回退。
    - `single` 会真实构造一手牌并调用 `build_suggestion`，必要时返回完整 JSON（含 `debug.meta`）。
    - `dist` 使用稳定散列（sha1）计算 `rolled_to_v1` 命中，不触发引擎与策略。

环境变量（常用）
- `SUGGEST_POLICY_VERSION`：策略大版本选择
  - `v0`（默认）：兼容老策略
  - `v1` / `v1_preflop`：启用 v1（v1_preflop 为兼容别名）
- `SUGGEST_STRATEGY`：三档策略切换
  - `loose`｜`medium`（默认）｜`tight`
- `SUGGEST_PREFLOP_ENABLE_4BET`：是否启用 SB vs 3bet 的 4-bet 分支
  - `0`（默认关闭）｜`1`（开启；尺寸/上限读取 `table_modes_{strategy}.json`）
- `SUGGEST_CONFIG_DIR`：外置配置根目录（可覆盖内置 `config/`）
  - 该目录下需包含：`table_modes_{strategy}.json` 与 `ranges/preflop_{open,vs_raise}_HU_{strategy}.json`
- `SUGGEST_DEBUG`：调试开关
  - `1` 时返回 `debug.meta` 并输出结构化日志；`0` 默认关闭

示例（本地运行带调试）：
```bash
export SUGGEST_POLICY_VERSION=v1_preflop
export SUGGEST_STRATEGY=medium
export SUGGEST_PREFLOP_ENABLE_4BET=1   # 可选
export SUGGEST_DEBUG=1
python scripts/suggest_debug_tool.py single --policy v1_preflop --debug 1 --seed 42 --button 0
```

策略说明（关键口径与边界）
- 赔率口径：`pot_odds = to_call / (pot_now + to_call)`；其中 `pot_now = pot + sum(invested_street)`（不含本次待跟注）。
- 最小重开（to-amount 语义）：若目标金额低于 `raise.min`，提升到 `raise.min` 再参与合法性钳制（可能触发 `W_CLAMPED`）。
- 三桶口径：`small ≤2.5x`、`mid ≤4x`、`large >4x`（3bet 的“to-amount”阈值可在 `table_modes_{strategy}.json` 用 `threebet_bucket_small_le/mid_le` 配置）。
- 集合重叠优先级：若同一组合同时属于 `reraise[bucket]` 与 `call[bucket]`，优先 `3bet`。
- 4-bet 行为：需设置 `SUGGEST_PREFLOP_ENABLE_4BET=1`，才会读取 `SB_vs_BB_3bet` 的 `fourbet` 集合并计算 4-bet 尺寸。

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
    - `_coach.html`（建议/理由/Coach 卡片：一句话计划 + pot_odds/MDF + 尺寸）
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

— 测试与观测（Test/Observe） —

- 运行测试：`pytest -q`
- 规则 Gate（Flop）：`python scripts/check_flop_rules.py`（medium 硬 Gate）；`python scripts/check_flop_rules.py --all`（三档 smoke + 单调检查）
- 结构化日志建议：`suggest_v1` 事件包含 `size_tag/plan/hand_class6/pot_type` 等；可按 `street/texture/role/spr_bucket/size_tag/hand_class6/plan` 聚合。
- Prom 指标：
  - `suggest_*`（延迟/动作/钳制/错误）
  - `coach_card_*`（view/action/plan_missing）
  - `flop_value_raise_total{street,texture,spr,role,facing_size_tag,pot_type,strategy}`（价值加注覆盖率与分布）

— 调试与日志（Fix/Debug） —
- `debug.meta`（当 `SUGGEST_DEBUG=1`）主要字段：
  - `to_call_bb` / `open_to_bb` / `pot_odds`：校验赔率口径是否一致
  - `reraise_to_bb` / `fourbet_to_bb` / `cap_bb`：尺寸与封顶检查（若经常触发 `PF_*_MIN_RAISE_ADJUSTED` 或 `W_CLAMPED`，考虑增大 mult 或调整 cap）
  - `bucket` / `strategy` / `config_versions`：归因与追踪
- 结构化日志：包含 `size_tag/plan/hand_class6/pot_type/threebet_to_bb/fourbet_to_bb/pot_odds/bucket` 等；灰度期用来定位金额异常。
- 调参入口：`packages/poker_core/suggest/config/table_modes_{strategy}.json`
  - `reraise_ip_mult` / `reraise_oop_mult` / `reraise_oop_offset` / `cap_ratio`
  - `postflop_cap_ratio`（Flop raise to‑amount 封顶比例）
  - `fourbet_ip_mult` / `cap_ratio_4b`
  - `threebet_bucket_small_le` / `threebet_bucket_mid_le`
- 范围入口：`packages/poker_core/suggest/config/ranges/*.json`
  - `preflop_open_HU_{strategy}.json`（RFI）
  - `preflop_vs_raise_HU_{strategy}.json`（BB_vs_SB 的 `call/reraise`，以及 `SB_vs_BB_3bet` 的 `fourbet/call`）
  - Flop：`postflop/flop_rules_HU_{strategy}.json`（pot_type×role×ip/oop×texture×spr×hand_class6；支持 `facing` 的 value‑raise JSON 化）

CI Ranges Gate（零依赖）
- 工作流会运行 `node scripts/check_preflop_ranges.js --dir packages/poker_core/suggest/config`，校验：
  - RFI 覆盖（grid/combos）、defend 覆盖（small/mid/large）、3bet 占比
  - 桶内单调：small ⊇ mid ⊇ large（call/raise 各自）
  - 跨档单调：loose ⊇ medium ⊇ tight（open/call/raise 各自）
  - overlap 提示（≥8% 提示、≥15% 警告，不阻断）
  - 边界回归（打印型）：SB 4x KQo｜SB 4.5x ATs
  - 单位回归（打印型）：4.0bb/4.5bb → pot_odds
  - （可选）样本统计：设置 `SUGGEST_DEBUG_SAMPLES=/path/to.jsonl` 统计 `W_CLAMPED` 与最小重开占比
  - 结果会作为 Job Summary 与 PR 评论输出简报（RFI/defend/3bet/overlap 摘要）

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
