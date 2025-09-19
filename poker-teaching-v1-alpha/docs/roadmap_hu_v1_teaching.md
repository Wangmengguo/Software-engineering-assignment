# HU v1 Suggestion – Teaching Roadmap (TL;DR for Dev Team)

本路线图聚焦于“能用于教学/指导的 HU（双人）Preflop+Flop+Turn/River 最小闭环”，保持 API 兼容，依赖清晰，可增量发布与灰度控制。

## 目标与范围
- 范围：HU 模式；不扩展到 6‑max/多人池；先完成三街（Preflop/Flop/Turn/River）的教学闭环。
- 兼容：不破坏现有 API；仅新增可选字段与 v1 策略分支；配置沿用 `config_loader` 与已有结构。
- 依赖：不新增三方依赖；仅新增少量模块与 JSON 规则文件。

## 交付物（Deliverables）
- rationale → 自然语言解释（中文，带数值），可直接用于前端文案展示。
- Preflop 每条建议附带“下一步计划”（被 3bet/加注时怎么走）。
- Turn/River v1 极简策略与规则 JSON：沿用 flop 框架（角色/纹理/SPR→{check|size_tag} + 面对下注逻辑 + MDF 提示 + plan）。
- 基本单元测试与简要文档说明；默认仍是 v0 行为，设置 `SUGGEST_POLICY_VERSION=v1` 时启用新策略。

## 目录与文件结构（新增/修改）
- 代码
  - 新增 `packages/poker_core/suggest/explanations.py`：rationale 渲染为自然语言；加载模板、数值填充、取整/保留位。
  - 新增 `packages/poker_core/suggest/turn_river_rules.py`：Turn/River 规则加载（与 flop_rules 同模式）。
  - 修改 `packages/poker_core/suggest/policy.py`：
    - 新增 `policy_turn_v1`、`policy_river_v1`（拷贝 flop v1 的轻量骨架）。
    - 给 `policy_preflop_v1` 补 `meta.plan`（SB RFI、BB 3bet/Call 分支）。
  - 修改 `packages/poker_core/suggest/service.py`：
    - v1 注册表接入 turn/river v1。
    - 可选注入 `explanations: list[str]`（从 rationale + meta 渲染）。
- 配置
  - 新增 `packages/poker_core/suggest/config/explanations_zh.json`：code → 模板字符串。
  - 新增 `packages/poker_core/suggest/config/postflop/turn_rules_HU_{loose,medium,tight}.json`。
  - 新增 `packages/poker_core/suggest/config/postflop/river_rules_HU_{loose,medium,tight}.json`。
  - 更新 `packages/poker_core/suggest/config/README.md`：说明新文件与开关变量。
- 测试
  - 新增 `tests/test_explanations_render.py`。
  - 新增 `tests/test_pfv1_preflop_plan.py`。
  - 新增 `tests/test_turn_v1_policy.py`、`tests/test_river_v1_policy.py`。

## 实施细节

### 1) rationale → 自然语言解释（带数值）
- 配置模板（示例，键为 rationale code）：`packages/poker_core/suggest/config/explanations_zh.json`
  - `PF_DEFEND_PRICE_OK`: "锅赔率 {pot_odds:.2f} ≤ 阈值 {thr:.2f}（{bucket}）→ 跟注。"
  - `PF_OPEN_RANGE_HIT`: "首入范围命中：按 {open_bb:.1f}bb 开局。"
  - `PF_DEFEND_3BET_MIN_RAISE_ADJUSTED`: "已提升到最小合法再加注金额 {min}。"
  - `PF_ATTACK_4BET`: "面对 3-bet（{bucket}）：执行 4-bet（目标至 {fourbet_to_bb}bb）。"
  - `FL_MDF_DEFEND`: "MDF {mdf:.2f}；锅赔率 {pot_odds:.2f}；对手下注 {facing}。"
  - `W_CLAMPED`: "建议金额 {given} 超出合法区间 [{min},{max}]，已调整为 {chosen}。"
- 渲染模块：`explanations.py`
  - `load_explanations(locale='zh') -> dict`：经 `config_loader` 带 TTL；locale 缺失回退到默认。
  - `render_explanations(rationale, meta, extras) -> list[str]`：对每条 rationale，用 `rationale.data ∪ meta ∪ extras` 作为上下文填充模板；保留默认 `default_msg` 兜底。
  - 环境变量：`SUGGEST_LOCALE`（默认 `zh`）。
- service 钩子：在 `build_suggestion()` 聚合完成后，调用渲染并注入 `resp["explanations"]`（可选字段，不影响旧消费者）。

### 2) Preflop 计划（meta.plan）
- 生成位置：`policy_preflop_v1`
  - SB RFI：读取 `vs_tab['SB_vs_BB_3bet']` 及 `modes` 中 `threebet_bucket_small_le/mid_le` 阈值；对当前 combo 生成三档应对：
    - 命中 `fourbet`："若对手 3bet ≤9bb 四bet；≤11bb 四bet/跟注（按配置）；更大 保守处理"；并写入 `fourbet_ip_mult` 目标 to‑bb 值。
    - 命中 `call`："≤9bb 跟注；≤11bb 跟注；更大 弃牌"（保守）。
    - 都未命中："保守：小中档可考虑跟注；更大弃牌"。
  - BB 防守：
    - 若我们 3bet："被四bet 默认弃牌；仅 QQ+/AK 继续"（不引入新配置）。
    - 若我们 call："进入翻牌：按 Flop v1（纹理+MDF）继续"。
- 要求：所有 preflop 返回路径都包含简短 `meta.plan` 字符串。

### 3) Turn/River v1 极简表与策略
- JSON 结构（与 flop 相同的层级，动作集合更小）：
  - `<pot_type> → role(pfr|caller|na) → ip|oop → texture(dry|semi|wet) → spr(le3|3to6|ge6) → {hand_class|defaults} → {action,size_tag?,facing?,plan?}`
- 策略实现：`policy_turn_v1`、`policy_river_v1`
  - 无人下注：按表输出 `bet/check` 与 `size_tag`；在 meta 附 `size_tag` 与可选 `plan`。
  - 面对下注：计算 `pot_odds`、`mdf`；价值对小尺度 `raise two_third` 占位；否则回到 `call/fold`，并在 meta 带上 `mdf/pot_odds/facing_size_tag`。
- 加载器：`turn_river_rules.py` 提供 `get_turn_rules()`、`get_river_rules()`（复用 `config_loader`）。
- 接入：
  - `service.POLICY_REGISTRY_V1['turn'] = policy_turn_v1`
  - `service.POLICY_REGISTRY_V1['river'] = policy_river_v1`
  - 仍保持 `POLICY_REGISTRY` 指向 V0，只有 `SUGGEST_POLICY_VERSION=v1|auto(命中)` 时启用新策略。

## 测试计划（关键用例）
- `tests/test_explanations_render.py`
  - 给定典型 rationale + meta，渲染出含数值的中文句子；模板缺失时使用默认文案。
- `tests/test_pfv1_preflop_plan.py`
  - SB RFI 命中：`meta.plan` 包含 "≤9bb/≤11bb" 等阈值字样；BB 3bet/Call 分支均返回 plan。
- `tests/test_turn_v1_policy.py` / `tests/test_river_v1_policy.py`
  - 无人下注：PFR+value → `bet` 且 `meta.size_tag` 合法（third/half/two_third/pot）。
  - 面对半池：`meta.mdf/pot_odds` 数值正确；动作在 `call/fold/raise` 的合理集合内；limped/threebet 走 defaults 不抛错。
- 回归：旧测试不依赖新增字段；默认策略仍为 v0，零回归。

## 发布与开关
- 环境变量：
  - `SUGGEST_POLICY_VERSION=v1|v0|auto`（已有）。
  - `SUGGEST_V1_ROLLOUT_PCT`（已有，用于 auto 灰度）。
  - `SUGGEST_LOCALE=zh`（新增，但可选）。
  - `SUGGEST_PREFLOP_ENABLE_4BET`（已有，默认关闭）。
- 默认不变更生产行为；仅当设置为 v1 或命中 auto 才启用新 Turn/River 与 explanations。

## 时间与顺序（建议）
- D1：explanations 模块 + JSON + service 钩子 + tests（0.5–1 天）。
- D2：preflop plan 生成（RFI/3bet/Call 三分支）+ tests（0.5 天）。
- D3–D4：Turn/River v1（medium 首版 JSON + loaders + policies + tests）（1–1.5 天）。
- D5：文档完善、命名与清理（0.5 天）。

## 验收标准
- `SUGGEST_POLICY_VERSION=v1`：
  - preflop 返回均含 `meta.plan`；
  - flop/turn/river 返回（视情况）含 `meta.size_tag/mdf/pot_odds/facing_size_tag`；
  - `resp.explanations` 存在且为中文可读句子（包含关键数值、范围/阈值）。
  - Turn/River 策略在无人下注与面对下注两条主线均能稳定给出动作（无异常）；
  - v0 默认路径不受影响，旧测试全部通过。

---

如需我方先提交骨架 PR（新增文件、策略注册与一个最小规则样例）以便团队并行补齐表与文案，请在该文档对应章节标注负责人与预计完成时间。

