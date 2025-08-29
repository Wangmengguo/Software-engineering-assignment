# Poker Teaching System — v0.4+

一个“教学优先”的两人德扑（HU NLHE）系统：纯函数领域引擎 + Django/DRF API + 教学视图。

— 做什么（What） —

- 领域引擎：`packages/poker_core/state_hu.py`（SB/BB 可配置，发盲→轮次→结算，筹码守恒）。
- 评牌：优先 PokerKit，不可用时回退简化评估。
- 会话流：多手对局（按钮轮转、承接筹码），回放持久化到 DB。
- 建议：`POST /api/v1/suggest`（preflop v0，动作仅从合法集合挑选）。
- 教学视图：`/teaching/hand/<hand_id>` 展示手牌、注释与时间线。

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

- Demo: http://127.0.0.1:8000/
- API Docs: http://127.0.0.1:8000/api/docs
- Teaching: http://127.0.0.1:8000/teaching/hand/<hand_id>
 - Metrics (Prometheus): http://127.0.0.1:8000/api/v1/metrics/prometheus

— 怎么用（API 快查） —

- `POST /api/v1/session/start` 创建会话（可传 `sb/bb`）
- `GET  /api/v1/session/<sid>/state` 会话视图
  - `stacks`: 承接栈（下一手扣盲前）
  - `stacks_after_blinds`: 当前手已扣盲后的实时栈（无手牌则为 null）
- `POST /api/v1/hand/start` 在会话内开一手（可传 `seed`）
- `GET  /api/v1/hand/<hid>/state` 查询状态与 `legal_actions`
- `POST /api/v1/hand/<hid>/act` 执行动作（`check/call/bet/raise/fold/allin`）
- `GET  /api/v1/hand/<hid>/replay` 回放（兼容 `/api/v1/replay/<hid>`）
- `POST /api/v1/suggest` 最小建议 `{hand_id, actor}`
  - 响应：`{hand_id, actor, suggested{action,amount?}, rationale[], policy}`
  - 错误：`404` 不存在，`409` 非行动者/已结束，`422` 无法给出合法建议

— 怎么测（Test） —

```bash
pytest -q
coverage run -m pytest && coverage report --include "packages/poker_core/*"
```

— 怎么修（Dev/Fix） —

- 引擎：`packages/poker_core/state_hu.py`（HU 状态机）；评牌在 `packages/poker_core/providers/*`。
- 建议：`packages/poker_core/suggest/*`
  - 策略：`policy.py`（纯函数，签名：`(Observation, PolicyConfig)`）
  - 类型/工具：`types.py` / `utils.py`
  - 服务：`service.py`（装配 Observation、策略注册表、金额钳制与告警）
  - 动作结构化：`packages/poker_core/domain/actions.py`
- API：`apps/web-django/api/*.py`（会话/手牌/建议/回放路由在 `urls.py`）。
  - 指标：`apps/web-django/api/metrics.py`（Prometheus 封装；抓取 `/api/v1/metrics/prometheus`）。
- 持久化：`apps/web-django/api/models.py`（`Session`、`Replay`），只在“进行中”手牌时用内存 `HANDS`。
- DB 变更：修改模型后运行 `python manage.py makemigrations api && python manage.py migrate`。
- 契约：所有接口在 `/api/docs`，新增/变更接口请同步 serializer/extend_schema。

— 可选（PostgreSQL） —

```bash
docker compose -f infra/docker-compose.yml up -d
cp .env.example .env && export $(cat .env | xargs)   # Windows: 手动设置
cd apps/web-django && python manage.py migrate
```

Tips

- 自定义盲注：在 `POST /api/v1/session/start` 传 `{sb, bb}`。
- 常见 409：非当前行动者或手牌已结束；先 `GET /hand/state` 查看 `to_act/street` 再操作。
