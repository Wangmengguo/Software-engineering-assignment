# 任务单 · A1（API 契约扩展：R/W/D/T + nudge）

> 目标：在不改变现有行为的前提下，向 Suggest API 增加 R/W/D/T 四块字段与“方向性提示 nudge”，保持完全向后兼容；严格 TDD 推进。

---

## 0. 范围与非目标

- 范围（A1 仅做）：
  - 在响应中新增可选字段（R/W/D/T）：
    - `range`: `{ node, bucket, size_options, target_freq_band }`
    - `why`: `[{ code, msg, data }]`（可直接复用 `rationale` 的子集与数学量摘要）
    - `do`: `{ action, amount|size_tag, nudge }`（nudge 固定方向性尾缀）
    - `train_tags`: `[string]`（A1 阶段返回空数组，占位）
  - 保持现有字段与行为：`suggested`、`rationale`、`policy` 等不变。
  - 更新 OpenAPI 标注与示例；Prometheus 指标可延后到 A6。
- 非目标（A1 不做）：
  - Turn/River 新规则（A2/A5）；
  - 标签引擎与持久化（A3/A4）；
  - KPI 聚合与仪表（A5）；
  - 剥削/灰度治理（B/C）。

---

## 1. 用户故事（简）

- 作为学习者，我从 Suggest 面板直接看到区间/理由/动作/标签位（即使标签为空），并获得“方向性提示”。
- 作为前端/调用方，旧客户端不必修改即可继续使用（新增字段可选）。

---

## 2. 契约草案（示例）

```
{
  "hand_id": "h_123",
  "actor": 0,
  "suggested": { "action": "bet", "amount": 125 },
  "rationale": [{ "code": "N101", "msg": "未入池：2.5bb 开局（bet）。" }],
  "policy": "preflop_v0",
  "range": { "node": "preflop_open", "bucket": "HU", "size_options": ["2.0x","2.5x"], "target_freq_band": [0.8,0.9] },
  "why": [{ "code": "M_POT_ODDS", "msg": "基于位置与赔率…", "data": {"need_equity": 0.37, "mdf_needed": 0.5 }}],
  "do": { "action": "bet", "amount": 125, "nudge": "优先使用 0.33P 小注获取更高弃牌率。本提示为方向性教学建议。" },
  "train_tags": []
}
```

---

## 3. 可执行任务清单（严格顺序）

- T1 契约测试（失败红）：新增测试文件 `tests/test_api_suggest_rwd.py`，断言 200 响应包含新增可选字段与类型；旧字段仍在。
- T2 OpenAPI 更新：`apps/web-django/api/views_suggest.py` 增加 schema/示例；文档快照测试通过。
- T3 最小实现：在 `views_suggest.py` 组装 R/W/D/T 字段（占位策略）：
  - range：从现有上下文推导节点与尺寸候选（无则给最小占位与目标频率区间为空或基线）；
  - why：沿用 `rationale`；附带数学量摘要（若有）；
  - do：镜像 `suggested` 并拼接统一 nudge 尾缀；
  - train_tags：空数组。
- T4 回归测试：`tests/test_api_suggest.py` 不回归；新增测试通过。
- T5 文档与变更清单：在 `docs/plan_milestone_A.md` 标记 A1 完成项；生成 API 变更摘要。

说明：任何一个步骤未绿前，不进入下一步实现；先写测试（红）→ 实现（绿）→ 重构（可选）。

---

## 3.1 再拆解为 6 个子任务（Contract-First，不增复杂度）

- A1-1｜契约与枚举清单（Contract）
  - 产出：OpenAPI 增量、字段说明与成功/降级/空值三类示例。
  - 字段口径（统一）：
    - `range`: `{ node, bucket, size_options, target_freq_band }`
      - `node`：如 "preflop/rfi"|"flop/cbet"|"turn/barrel"|"river/barrel"；
      - `bucket`：如 "srp"|"3bp"|"ip"|"oop"|"dry_high"|"wet_mid"（允许多值）；
      - `size_options`：如 ["0.25-0.33","0.50-0.66","0.75-1.00"]；
      - `target_freq_band`：[min,max]（0–1，教学基线目标带）。
    - `why`: `[{ code, msg, data }]`，`data` 限定三项：`need_equity`/`mdf_needed`/`fe_req`；
    - `do`: `{ action, size_tag?, amount_bb?, nudge? }`（以 `size_tag` 为主，`amount_bb` 为辅）；
    - `train_tags`: `string[]`（A1 仅基础/数学类键）。

- A1-2｜编码与 i18n 词典（Lexicon）
  - 产出：自然语言文档中的迷你词典清单（rationale codes、train_tags、action 枚举——键、中文短文案、英文短文案、含义）。
  - 目的：字段键稳定，文案可替换，避免后续 churn。

- A1-3｜生成职责边界（Separation）
  - 约定：接口只产结构化键值（codes、bands、size_tags、numbers），不硬编码长文案；呈现层模板把键值→人话（沿四句式）。

- A1-4｜兼容与降级（Compatibility）
  - 约定：所有新增字段可选；无法推导时返回空对象/空数组并标注 `rwd_status:"degraded"`；
  - 旗标：`SUGGEST_SCHEMA_VER="rwd_v1"`、开关 `FEATURE_RWD_V1` 支持灰度/回滚。

- A1-5｜观测与快照（Observability）
  - 计数（轻量，可后续接 Prom）：`rwd_generated_total`、`rwd_empty_fallback_total`、`why_items_total`、`train_tags_total`；
  - 快照：固定三套样例（SRP 干燥面、低 SPR 3BP、河牌配比）生成响应并保存 JSON 作为评审/回归素材。

- A1-6｜验收清单（Acceptance）
  - 同一输入 → R/W/D 稳定一致；字段全缺省 → 老客户端正常；
  - i18n 切换仅影响文案，不影响 codes；
  - `size_tag` 与 `amount_bb` 同时存在时以 `size_tag` 为主；
  - 错误路径返回空结构，不返回 `null/undefined`；三套样例快照一致。

---

## 4. TDD 细化（测试用例草案）

- 文件：`tests/test_api_suggest_rwd.py`
  - 用例 A：`test_suggest_contains_rwd_fields_optional()`
    - 步骤：开局→请求 `/api/v1/suggest`；
    - 断言：响应包含 keys：`range|why|do|train_tags`；类型分别为 `dict|list|dict|list`；
      `do.nudge` 为 `str` 且以“本提示为方向性教学建议。”结尾；`suggested`、`rationale` 仍存在；状态 200。
  - 用例 B：`test_suggest_rwd_backward_compatible()`
    - 步骤：同上；
    - 断言：不依赖新增字段也能完成旧断言（回归 `tests/test_api_suggest.py` 的检查逻辑）。
  - 用例 C：`test_suggest_why_aliases_rationale()`
    - 断言：`why` 至少包含一项且字段与 `rationale` 对齐（code/msg）。
  - 用例 D：`test_suggest_range_is_structured()`
    - 断言：`range` 含 `node` 与 `size_options` 字段（允许为空列表）。

---

## 5. 实施要点（A1 占位组装策略）

- range：基于 `gs.street` 给出 `node`（如 preflop_open / flop_cbet / turn_barrel / river_barrel）；`size_options` 优先从现有配置档位推断（若取不到，则返回空列表）；`target_freq_band` 可在 A1 置空或仅在 preflop_open 给出 [0.8,0.9]。
- why：复制 `rationale` 列表；若有 `need_equity/mdf_needed/fe_req` 相关数据则放入 `data`。
- do：等同 `suggested` 的动作/金额，新增 `nudge` 固定尾缀：“本提示为方向性教学建议。”
- train_tags：返回空数组（A3 接管）。
- 保证 100% 可选：任一组装失败都不应导致 5xx，必要时返回占位空结构。

---

## 5.1 模糊点口径对齐（Clarify）

- `range.target_freq_band`：定义为“教学基线目标带”，与对手/池子偏移解耦（偏移放到里程碑 C）。
- `why.data`：A1 固定三项（`need_equity`/`mdf_needed`/`fe_req`），其余暂不暴露。
- `do.size_tag` vs `do.amount_bb`：以 `size_tag` 为主，`amount_bb` 为辅；如两者并存，以 `size_tag` 呈现为准。
- `train_tags`：A1 仅输出平铺标签，不承诺 Top-3 排序与聚合（留到 A4/A5）。

---

## 6. 非功能与守护线

- 性能：A1 不引入新 I/O；仅在视图层组装字典；P95 API 仍应 ≤150ms（本地）。
- 兼容：新增字段均为可选；旧客户端不受影响。
- 可观测：暂不新增指标；若易实现，可加 `SUGGEST_RWD_EMITTED` 计数（非必须）。

---

## 7. 验收标准（A1）

- 新增测试全部通过；既有 API 测试不回归；
- `/api/v1/suggest` 返回包含 R/W/D/T（可选）；`do.nudge` 带统一尾缀；
- OpenAPI 文档生成包含新字段示例；
- 变更清单与使用说明可查。

---

## 8. 风险与回退

- 风险：某些牌面无法推断 `range.size_options` → 占位空列表 + 不影响 200 响应；
- 回退：通过开关 `FEATURE_RWD_V1` 关闭新字段组装，仅返回旧结构（默认 Off→On 灰度）。
