# 任务单 · A2（Turn/River 基线最小集：尺寸桶 + 主干 + MDF 提示）

> 目标：以“尺寸桶 + 主干决策 + MDF/配比/阻断提示”的教学基线，克制完成 Turn 最小集并定义 River 的口径（实现留到 A5），缺口一律走安全兜底与自然语言降级。坚持“契约优先 + 表驱动 + TDD”，不落实现细节。

---

## 结论（TL;DR）

- 方向正确：用尺寸桶+频率区间+MDF/配比/阻断替代全树，易教易验收；
- 拆解为“10 子任务”与“三助手+两张表+一套快照”，降低后续迭代成本；
- 明确三大模糊点口径与两处耦合风险的切断方式；
- 最小验收以命中率/降级率/延迟与快照稳定为准，设置红黄灯停表信号。

---

## 0. 范围与非目标

- 范围（A2 定义 Turn+River 口径，实施仅 Turn）：
  - 覆盖 SRP 与 3BP 两类底池；IP/OOP 两类位置；PFR/Caller 两类角色；
  - 无下注路径（nobet）：是否二枪（second barrel）与尺寸桶选择；
  - 面对下注路径（facing bet）：MDF/需要权益提示下的 call/fold/（少量）value-raise 最小集；
  - 延迟 C-bet 的方向性基线（flop 过牌→turn 打）；
  - 一致的“方向性提示”与兜底文案；
  - 与 A1 的 R/W/D 契约对齐：range/why/do/train_tags 均可填充 Turn 语义（仍保持可选）。
- 非目标（本阶段不做）：
  - River 的落地实现（移至 A5，本阶段仅对齐口径与表结构）；
  - 剥削/对手画像（移至里程碑 C）；
  - 细粒度 bluff 构造与节点锁定（后续版本）。

---

## 1. 合理性点评（Why 这条线是对的）

- 教学优先：Turn/River 用“尺寸桶（0.33/0.5/1.0/2.0P）+ 目标配比 + MDF 提示”替代复杂解算，学习者易吸收；
- 可度量：每个节点都能产出“是否合规/是否欠配/是否超配”的区间信号，便于 KPI 与标签；
- 可演进：后续 B/C 在不改接口的前提下逐步细化延迟/接力/极化 raise 线与对手触发偏移。

---

## 1. 用户故事（简）

- 作为学习者：到 Turn 我能看到稳定的 R/W/D 输出，知道该不该二枪/用多大，面对不同下注知道“至少防守到 MDF”的底线；遇到规则盲区也有明确的“安全兜底”。
- 作为产品/运营：典型路径覆盖充分（SRP/3BP × IP/OOP × PFR/Caller），建议稳定、不摇摆，有数据与降级标识可观测。

---

## 2. Turn/River 基线口径（自然语言）

- 尺寸桶（统一）：`0.25–0.33P / 0.50–0.66P / 0.75–1.00P / 1.50–2.00P`。
- SRP nobet：
  - IP 作为 PFR：优势转牌优先小注续攻（0.25–0.33P）；中性/湿转牌收缩频率与增大尺寸；
  - OOP 作为 PFR：在优势面保留小注续攻，劣势面更多过牌控制。
- 3BP nobet（SPR≈3）：
  - 优先小注续攻于好牌面；在承诺型牌力（TPTK/超对/强听牌）上避免 -EV 放弃（提示“承诺”方向性）。
- facing bet：
  - 提示 `mdf_needed` 与 `need_equity`，给出“合规防守”底线（call 或最小 raise/弃牌）；
  - 仅最小化 value-raise 触发（例如两对+/强听牌转强），不过度扩展 bluff；
  - 极端/不确定时走兜底（见 §4）。
- 延迟 C-bet：
  - flop 过牌后于利好转牌给方向性提示（“可以用小注覆盖更广”），不承诺具体频率。

- River（本阶段仅定义口径，A5 实现）：
  - barrel：按 0.5/1.0/2.0P 给出“价值:诈唬配比”基线提示（1:2 / 1:1 / 2:1），不输出数值 EV；
  - facing：对 0.5/1.0/2.0P 给出 call/raise/fold 的 MDF 提示与 thin-value 的方向性定义；
  - 阻断：列出坏阻断清单（避免阻断对手弃牌区的 bluff），作为方向性文案。

---

## 3. 可执行任务清单（严格顺序，TDD）

- T1 契约补充测试（红）：`tests/test_turn_rulepath_contract.py`
  - 断言：Turn 响应 `policy=turn_v1`；`meta`/`why` 含 `mdf_needed`/`need_equity` 字段；尺寸标签属于桶集合；字段缺省时仍 200。
- T2 典型路径测试（红）：`tests/test_turn_mainlines.py`
  - SRP×IP/PFR；SRP×OOP/PFR；3BP×OOP/PFR：nobet 能得到稳定 `bet(size_tag)` 或 `check`；
  - 延迟 C-bet 场景能返回 `bet` 或方向性 `nudge`。
- T3 面对下注与 MDF 测试（红）：`tests/test_turn_facing_mdf.py`
  - 面对 0.5P/1.0P，`why.data.mdf_needed` 与 `do.action` 合理（call/fold/少量 raise），并出现“方向性提示”。
- T4 兜底与降级测试（红）：`tests/test_turn_fallbacks.py`
  - 强制制造“不在规则内”的路径：响应包含兜底动作（如 `check/call`）与降级文案、`W_FALLBACK_USED` 码；
  - `rwd_status="degraded"` 可选出现。
- T5 文档口径与样例（绿前）：补充《Turn 口径小表》：节点枚举、尺寸桶键、最小化 value-raise 触发说明、兜底语料；并生成 3 套样例响应（SRP 干燥、3BP 低 SPR、延迟 C-bet）。
- T6 最小实现（绿）：落地 Turn 主干规则与兜底逻辑，保证 T1–T4 通过（不展开算法细节）。
- T7 回归与快照（绿）：对样例响应做 JSON 快照，纳入 CI；旧测试不回归。

说明：任一测试未绿，禁止推进下一项；严格先红后绿。

---

## 4. 兜底与一致性

- 缺规则或判定模糊 → 统一兜底：
  - nobet：优先 `check` 或最小注试探（小注试探仅在合法窗口与安全范围内）；
  - facing bet：若缺数据，默认按 MDF 提示方向，动作取 `call` 或 `fold` 的安全侧；
  - 统一降级文案：“此牌面接近均衡，优先控池/小注试探。”
- 导出 `W_FALLBACK_USED` 码与可选 `rwd_status:"degraded"`，便于观测。

---

## 5. 契约对齐（与 A1 保持一致）

- `range`：`node`（如 `turn/barrel` or `turn/facing`）、`bucket`（如 `srp|3bp|ip|oop|wet_mid`）、`size_options`（统一桶键）、`target_freq_band`（可为空）。
- `why`：包含 `code/msg`，`data` 仅含 `need_equity`/`mdf_needed`/`fe_req`（其余暂不暴露）。
- `do`：`action` + `size_tag?` + `nudge?`；并遵循“仅方向性，不给数值 EV”的边界。
- `train_tags`：A2 可为空（A3 接管标签生成）。

---

## 6. 子任务再拆解（10 项，Contract-First，不增复杂度）

- A2-1｜节点目录与范围声明：Turn/River 节点覆盖/暂缓/兜底清单（本阶段实现 Turn，River 只对齐口径）。
- A2-2｜牌面分类与 SPR 档位：`{dry_high, mid_wet, two_tone, monotone, paired}` 与 `{low≤3, mid 3–6, high>6}` 的统一小字典。
- A2-3｜尺寸桶与映射规范：`size_tag → 比例`（S/M/L/X）与 3BP 固定 bb 的辅助显示，一节点“1 主 + 1 备”。
- A2-4｜Turn 主干决策表：表驱动（CSV/JSON）维度与输出字段口径落表。
- A2-5｜River 主干配比+动作表：配比基线与 facing MDF/薄价值的方向性提示（定义口径，不实现）。
- A2-6｜数学助手：need_equity/mdf_needed/fe_req 的统一展示口径与 rounding 规则。
- A2-7｜阻断与例外轻规则：坏阻断清单、好/坏转牌方向性提示。
- A2-8｜兜底与降级语料：fallback 触发条件与标准文案，附输出码 `W_FALLBACK_USED`。
- A2-9｜标准样例与快照：≥10 手典型路径快照，用于回归与评审。
- A2-10｜验收仪表：/metrics 增加 node_hit/fallback/math_helper 使用计数与延迟直方图。

---

## 7. 非功能与守护线

- 性能：Turn 规则匹配为 O(1) 查表语义（不落实现），P95 引擎 ≤50ms；
- 一致性：同状态输出稳定；尺寸桶与文案口径与 A1/River 一致；
- 安全：金额合法性与最小重开钳制始终生效；
- 文案：仍使用四句式模板输出 R/W/D；方向性提示尾缀统一；
- 兼容：字段可选，缺省返回空结构，老客户端不受影响。

---

## 8. 模糊点口径对齐（Clarify）

- 牌面分类边界：半湿/湿与 paired two-tone 的归属以小字典为准，每类附 1 句判定 + 正/反例各 1；
- 面对下注尺度的优先级：先 Pot-odds（能赢就跟）→ 再 MDF（别弃过头）→ Exploit 后置到 B/C；
- value-raise vs bluff-raise：A2 仅提供 value-raise（两对+/明显受益强牌），不提供 bluff-raise；
- Turn→River 联动：River 以配比/阻断为主，不做对前街“反向纠偏”；
- thin-value 定义：方向性口径——“能被大量次优单对跟注的顶对/边缘两对”，细化留到 B/C。

---

## 9. 过度耦合风险与切断（Decouple）

- 策略 ↔ 文案：规则只产 codes/size_tag/阈值，文案模板/i18n 生成人话；
- 策略 ↔ 对手画像：A2 禁止读取画像，一律基线输出；
- 牌类/SPR ↔ 决策表：产单一 Helper，所有表查询共用；
- size_tag ↔ amount 映射：集中到一处助手；策略侧只写 size_tag。

---

## 10. 验收标准与“停表”信号（Acceptance Signals）

- 通过即上线：
  - 典型路径命中率 ≥95%（其余走兜底且文案清晰）；
  - 同一输入的 Turn/River 输出稳定无抖动（快照一致）；
  - 所有输出含 `node/size_tag/hint_code` 或 fallback；
  - P95 引擎≤50ms；`fallback_rate ≤10%`（样本足够的房间）。
- 红灯停表：
  - 牌面分类不一致导致同牌面不同建议（快照抖动）；
  - River 给出与前街相悖的配比/动作趋势；
  - `fallback_rate > 25%` 连续 24h。
- 黄灯观察：
  - `math_helper_usage`/失败计数异常；
  - 单一节点（如 `3BP-OOP-midSPR-vs1.0P`）命中率显著低于总体。

