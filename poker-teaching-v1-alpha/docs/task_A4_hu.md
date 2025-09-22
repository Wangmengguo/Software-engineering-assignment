# 任务单 · A4（KPI 仪表口径与 UI 占位：近期/长期 + 红黄绿 + 方向性）

> 目标：以自然语言锁定 KPI 口径与展示契约，在不引入技术爆炸的前提下，按 TDD 方式交付“可度量、可降级、可回放”的仪表最小集与 UI 占位（文本+红黄绿灯+样本状态）。不落实现细节。

---

## 0. 范围与非目标

- 范围（A4 仅做）：
  - KPI 最小集与固定口径：`WWSF 47–52% / WTSD 32–37% / W$SD 49–54% / Fold to Flop C-bet 40–50% / A高干燥面 C-bet 70–80%`；
  - 双窗口：`近期=1k`、`长期=10k`；样本不足 → 展示“方向性”而非结论；
  - 红/黄/绿判色规则（±5pt 阈值）与色弱友好方案（附文字）；
  - UI 占位：仪表卡片（标题/当前值/目标带/样本状态/趋势箭头/说明文案），不做复杂图表；
  - 与 A3 联动约定：KPI 偏离触发 Top-3 标签主题置顶（仅约定，不在本阶段实现排序逻辑）。
- 非目标（本阶段不做）：
  - KPI 广义集合与自定义指标；
  - 多维切片（SRP/3BP/IP/OOP/牌面微类）与对手画像相关统计；
  - 训练任务/主题复盘交互（移至里程碑 B）。

---

## 1. 用户故事（简）

- 学习者：我能看到关键 KPI 的当前值、目标带、样本状态与“方向性提示”，知道该先练哪类手。
- 运营/教练：我能判断近期是否漂移（>±5pt），并将对应标签主题置顶，拉出代表手复盘。

---

## 2. 契约与口径（Contract-First）

- 定义项
  - `window`: `recent|long`；`sample`: 实际样本量；`enough`: boolean（是否≥门槛）；
  - `value`: 当前数值（%, 一位小数）；`target_band`: `[min,max]`；`delta_pt`: 与目标带最近边界的偏差点数（可为负）；
  - `status`: `green|yellow|red|directional`（directional=样本不足，仅给趋势）；
  - `hint`: 自然语言一句话（≤120 字），包含“区间/理由/动作/标签名”；
  - `linkage`: 可选，指向建议置顶的标签键（如 `C_BET_DRY_LOW`）。
- 样例（自然语言，非实现）：
  - `WWSF`（recent=980, long=10234）：`value=46.2%`, `target=47–52%`, `status=yellow`，`hint="近期见翻偏低，建议在 IP 干燥面增加 0.33P 小注持续。"`，`linkage=["C_BET_DRY_LOW"]`。

---

## 3. 可执行任务清单（严格顺序，TDD）

- T1 契约测试（红）：`tests/test_kpi_contract.py`
  - 断言：KPI 汇总接口/模块返回上述字段结构；双窗口均有；字段缺省时走 `status=directional`；
  - 断言：判色规则（±5pt）与门槛（recent=1k/long=10k）被正确反映在 `status/enough`。
- T2 判色与阈值测试（红）：`tests/test_kpi_thresholds.py`
  - 构造边界值用例：刚好在带内、越界 4.9pt/5.1pt；断言 `green/yellow/red` 切换准确；
  - 样本不足（如 recent=120）→ `status=directional`，`hint` 出现“方向性”词条。
- T3 联动约定测试（红）：`tests/test_kpi_linkage_to_tags.py`
  - 当 `WWSF` 低于带且 `recent.enough=true` 时，`linkage` 包含建议置顶的标签键（如 `C_BET_DRY_LOW`）；
  - 当 `A高干燥面 C-bet` 低于带，`linkage` 指向 `C_BET_DRY_LOW`。
- T4 UI 占位快照（红）：`tests/test_kpi_cards_snapshot.py`
  - 渲染“仪表卡片”文本片段（标题/当前值/目标带/样本状态/说明），保存快照；
  - 样本不足时卡片展示“方向性”徽标；颜色文案附文字（色弱友好）。
- I1 最小实现（绿）：
  - 聚合模块按契约返回结构化 KPI 数据；
  - 判色器与提示生成器基于固定目标带与±5pt 规则产出 `status/hint/linkage`；
  - UI 层渲染文本占位与红黄绿灯（附文字）。
- R1 回归与文档：
  - 旧测试不回归；
  - 在 `docs/plan_milestone_A.md` 标记 A4 完成项，并附“口径小表与样例 JSON”。

说明：任一测试未绿，不推进下一项；严格“先红→后绿→必要重构”。

---

## 4. 实施要点（不落实现细节）

- 目标带固定：按指标蓝图，首期不做个性化调参；
- 门槛固定：`recent=1k`、`long=10k`；不足即 `status=directional`；
- 判色规则：与目标带最近边界的偏差点数≥5 → `red`；在 3–5 之间 → `yellow`；≤3 → `green`；（阈值可在评审会确认）
- 方向性提示：严禁给数值化 EV，用“先做什么”表达（如“IP 干燥面增加 0.33P 小注”）；
- i18n 与文案：沿四句式模板输出；
- 与 A3 解耦：A4 只返回 `linkage` 键，不排序、不下发主题列表；
- 降级：任一 KPI 计算异常 → 该项 `status=directional` 且 `hint` 给出“数据不足/计算失败，稍后再试”。

---

## 5. 非功能与守护线

- 性能：KPI 计算为 O(n) 窗口聚合（实现层可缓存，不在本阶段规定）；
- 兼容：新增接口/字段可选；旧客户端不受影响；
- 观测：
  - 计数：`kpi_calc_total`, `kpi_calc_failed_total`, `kpi_directional_total`；
  - 延迟直方图：`kpi_calc_latency_seconds`；
- 可回退：以开关 `FEATURE_KPI_V1` 控制展示，异常可一键关闭。

---

## 6. 验收标准（A4）

- 所有 T1–T4 新增测试通过；旧测试不回归；
- KPI 卡片能同时展示近期/长期、目标带、样本状态与红黄绿文字标识；
- 样本不足时，所有 KPI 显示 `status=directional` 且提示语包含“方向性”；
- `linkage` 键与 A3 标签词典一致，可被前端用于置顶主题；
- 性能/降级/回退口径达标。

---

## 7. 风险与缓解

- 样本不足引发误判 → 强制门槛 + `directional` 状态 + 非数值化提示；
- 指标口径争议 → 在文档固化“口径小表”，评审会签字；
- 颜色不可达（色弱） → 必附文字标识；
- 与 A3 过度绑定 → 只回传 `linkage` 键，不做排序与主题计算。

