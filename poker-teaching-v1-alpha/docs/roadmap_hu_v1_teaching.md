# HU v1 Suggestion – Teaching Roadmap (Aligned, HU‑Focused)

本路线图以 HU（双人）为唯一范围，目标是构建“适配教学/解释”的 Preflop+Flop+Turn/River 最小闭环；保持 API 向后兼容，可灰度切换与增量演进。

## 目标与范围
- 范围：仅 HU；不扩展多人池/6‑max；优先完成四街闭环（Preflop/Flop/Turn/River）。
- 兼容：不破坏现有 API；仅新增可选字段（如 explanations）与 v1 策略分支；配置沿用 `config_loader`。
- 依赖：不引入三方库；新增的仅为轻量模块与 JSON 规则。

## 全局公理（不变口径）
- 合法性与最小重开：建议先合法后最优；postflop 的 raise 是“to‑amount”语义，若低于最小重开统一抬高并追加 `FL_MIN_REOPEN_ADJUSTED`，越界金额统一 `W_CLAMPED`。
- 锅赔率/MDF 统一：`pot_odds = to_call/(pot_now+to_call)`，`mdf = 1 - pot_odds`，策略与文档口径一致。
- 尺寸统一：翻后统一 `third|half|two_third|pot` 标签；bet 用锅份额，raise 用 to‑amount，并受 `postflop_cap_ratio` 控制。
- 阈值与策略档：三档策略（loose/medium/tight）与阈值来自 `table_modes_{strategy}.json`，代码不硬编码。
- 角色/位置：HU 仅 SB(IP)/BB(OOP) 两角色；preflop 不用 IP；翻后按钮为 IP。
- 策略/呈现解耦：策略返回 Decision+meta（size_tag/rule_path/mdf/pot_odds/plan…），服务层统一金额换算与 clamp/告警。
- 元信息即教学：各街尽可能返回 `size_tag/pot_odds/mdf/facing_size_tag/rule_path/plan`，便于 Coach 卡复用。
- 灰度稳定：`SUGGEST_POLICY_VERSION` 与 `SUGGEST_V1_ROLLOUT_PCT` 保证同一 hand 的确定性（除版本切换）。
- 保守回退：规则缺失/未命中走保守路径并给出 `CFG_FALLBACK_USED`。

## 交付物（Deliverables）
- explanations：将 rationale+meta 渲染为中文可读句子；前端零拼接可直接展示。
- Preflop：所有路径附简短 `meta.plan`（RFI/BB 防守/SB vs 3bet）。
- Turn/River v1 极简：沿用 Flop 框架（角色/纹理/SPR→{check|size_tag}+面对下注线），带 `mdf/pot_odds/plan/rule_path`。
- 单测/快照：保留 v0 默认；v1/auto 受开关控制，零回归。

## 目录与文件结构（新增/修改）
- 代码
  - 新增 `packages/poker_core/suggest/explanations.py`（D1）：模板加载与渲染。
  - 新增 `packages/poker_core/suggest/turn_river_rules.py`（D3）：Turn/River 规则加载。
  - 修改 `packages/poker_core/suggest/policy.py`：新增 `policy_turn_v1`/`policy_river_v1` 骨架（D3），`policy_preflop_v1` 补 `meta.plan`（D2）。
  - 修改 `packages/poker_core/suggest/service.py`：v1 注册 Turn/River；注入 `explanations`（D1）。
- 配置
  - 新增 `packages/poker_core/suggest/config/explanations_zh.json`（D1）。
  - 新增 `packages/poker_core/suggest/config/postflop/turn_rules_HU_{loose,medium,tight}.json`（D3）。
  - 新增 `packages/poker_core/suggest/config/postflop/river_rules_HU_{loose,medium,tight}.json`（D3）。
  - 更新 `packages/poker_core/suggest/config/README.md`（D2–D3）。
- 测试
  - 新增 `tests/test_explanations_render.py`（D1）。
  - 新增 `tests/test_service_explanations_injection.py`（D1）。
  - 新增 `tests/test_pfv1_preflop_plan.py`（D2）。
  - 新增 `tests/test_turn_v1_policy.py`、`tests/test_river_v1_policy.py`（D3）。

## 实施细节（按阶段）

### D1：explanations + service 钩子（TDD 先行）
- 配置模板（键为 rationale code）：
  - `PF_DEFEND_PRICE_OK`: "锅赔率 {pot_odds:.2f} ≤ 阈值 {thr:.2f}（{bucket}）→ 跟注。"
  - `PF_OPEN_RANGE_HIT`: "首入范围命中：按 {open_bb:.1f}bb 开局。"
  - `PF_ATTACK_4BET`: "面对 3-bet（{bucket}）：执行 4-bet（目标至 {fourbet_to_bb}bb）。"
  - `FL_MDF_DEFEND`: "MDF {mdf:.2f}；锅赔率 {pot_odds:.2f}；对手下注 {facing}。"
  - `FL_RANGE_ADV_SMALL_BET`: "范围优势：偏小尺度持续下注（1/3 彩池）。"
  - `FL_RAISE_VALUE`: "价值加注（对手下注较小）。"
  - `FL_MIN_REOPEN_ADJUSTED`: "已提升到最小合法再加注金额。"
  - `W_CLAMPED`: "建议金额 {given} 超出合法区间 [{min},{max}]，已调整为 {chosen}。"
- 渲染模块：`load_explanations(locale='zh')`（TTL 缓存，缺失回退）；`render_explanations(rationale, meta, extras)` 使用 `rationale.data ∪ meta ∪ extras` 作为上下文安全插值；`SUGGEST_LOCALE` 控制语言。
- service 钩子：在 `build_suggestion()` 聚合完成后注入 `resp["explanations"]`（可选字段，不影响旧消费者）。
- 命名一致性：文档与实现统一使用 `FL_MIN_REOPEN_ADJUSTED`（不改动现有常量与测试）。

### D2：Preflop 计划（meta.plan）
- `policy_preflop_v1` 在 SB RFI/BB 防守/SB vs 3bet 三路径补 `meta.plan`；阈值来自 modes（如 `threebet_bucket_small_le/mid_le`）。

### D3：Turn/River v1 极简
- 规则 JSON 与加载器；策略沿用 Flop v1 的 rule_path 匹配与 meta 字段；覆盖无人下注与面对下注两条主线。

### D4：文档清理与快照
- HU 化中文文档（移除 6‑max 位次口径）；补充“公理与口径”章节到中文策略文档；新增回归快照用例集。

## 测试计划（关键用例）
- `tests/test_explanations_render.py`：模板存在/缺失的渲染与取整；默认文案兜底。
- `tests/test_service_explanations_injection.py`：构造最小策略输出，断言 `explanations` 存在且包含关键数值/字段。
- `tests/test_pfv1_preflop_plan.py`：SB RFI 与 BB 防守路径均包含 plan；SB vs 3bet 含 bucket→fourbet_to_bb。
- `tests/test_turn_v1_policy.py` / `tests/test_river_v1_policy.py`：无人下注/面对下注主干与 defaults 路径稳定返回。

## 发布与开关
- `SUGGEST_POLICY_VERSION=v1|v0|auto`、`SUGGEST_V1_ROLLOUT_PCT`（灰度）；`SUGGEST_LOCALE=zh`（可选）；`SUGGEST_PREFLOP_ENABLE_4BET`（默认关闭）。
- 默认保持 v0；仅在 v1/auto 命中时启用新策略与 explanations。

## 节点与验收
- D1 完成标准：
  - 存在 `resp.explanations: list[str]`；
  - 渲染正确（含 `pot_odds/mdf/open_bb/bucket` 等数值/字段）；
  - 不影响既有测试（v0 默认路径零回归）。
- D2–D4 按阶段目标达成并补测试/快照。

备注：若需要并行推进 Turn/River 表格填充，可先合入 D1/D2 骨架，规则 JSON 与策略可逐步完善。
