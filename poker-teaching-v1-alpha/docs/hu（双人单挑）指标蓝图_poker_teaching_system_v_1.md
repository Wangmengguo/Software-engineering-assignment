# HU（双人单挑）指标蓝图 · Poker-Teaching-system\_v1

> 目标：将德扑 **state\_hu（双人单挑）** 的核心打法抽象为可追踪、可回放、可训练的 **KPI 指标体系**，用于你们的 Suggest/Replay/HUD 三件套。默认 **现金局、100BB、BTN 2–2.5x 开局、常规抽水**。

---

## 0. 使用范围与默认假设

- 场景：HU 现金局、有效筹码 100BB。
- 开局：BTN 纯 Raise（2–2.5x），BB 混合跟注/3bet。
- 统计：展示 **长期均值**（≥10k 手）与 **近期窗口**（1k 手）双视图，识别短期漂移。

---

## 1. 8 个维度 → 可量化 KPI（目标带 & 采集方式）

### 1.1 起手与位置（Preflop）

- **BTN RFI**：80–90%；**开局尺寸**：2.0–2.5x。
- **BB vs BTN 防守率**（Call+3bet）：60–70%（= Fold 30–40%）。
- **BB 3bet 总频**：12–18%（对 2.0x 稍高，对 2.5x 稍低）。
- **BTN vs 3bet 继续率**（Call+4bet）：55–65%；**4bet 频**：6–9%；**IP 4bet 尺度**：2.2–2.5× 对手 3bet。
- **BB vs 4bet 继续率**：35–45%；**5bet（全下）**：2–4%。
- **尺寸联动**：BTN 开局越小→BB 防守与3bet 越多；若对手对开局 **Fold >45%** → BTN RFI 提升至 90%+。
- **采集**：按位记录机会分母/分子；拆 2.0x/2.5x 档；输出 1k/10k 手移动平均与偏差告警。

### 1.2 筹码深度与 SPR

- **常见 SPR**：
  - SRP（BTN 2.5x，BB 跟）：Flop **SPR≈9–10**。
  - 3bet 底池（至 9bb 左右）：Flop **SPR≈3**。
  - 4bet 底池（至 20–22bb）：Flop **SPR≈1.6–1.9**。
- **承诺规则**：
  - **SPR≤3**：**TPTK/超对/强听牌** → **承诺率≥70%**（避免 -EV 放弃）。
  - **SPR≈9–10**：单对主控池，减少大额投入（控池率↑）。
- **采集**：逐手记录 `flop_SPR`、`commit_flag`；统计 TPTK 在低 SPR 的“打光覆盖率”。

### 1.3 牌面纹理与范围优势

- **SRP（IP 为进攻方） Flop C-bet**：
  - **干燥高牌面（A/K 高、彩虹）**：**70–80%**，**25–33% pot**。
  - **半湿/湿（两同花、中低连张）**：**45–60%**，**33–50% pot**。
- **3bet 底池 OOP C-bet**（BB 3bet 成功后）：高牌/优势面 **55–65%**，多用 **25–33% pot** 小注。
- **OOP Check-raise（SRP）**：总体 **10–14%**；在两同花/连张面 **12–16%**（强听牌+少量极化诈唬）。
- **Turn 接力（二枪）**：好转牌 **40–55%**；**River 三枪** ≈ 二枪的 **35–45%**。
- **延迟 C-bet（Flop 过牌→Turn 打）**：**33–45%**（好牌+无坏阻断诈唬）。
- **采集**：按牌面分类（干燥/半湿/湿），分别统计 `cbet_f`, `xr_f`, `barrel_t`, `delayed_cbet_t`。

### 1.4 下注体系（尺寸与价值:诈唬配比）

- **尺寸桶**：`25–33% / 50–66% / 75–100% / 150–200%（超池/加注）`。
- **River 价值:诈唬配比（基线）**：
  - **0.5P** → **1:2**；**1.0P** → **1:1**；**2.0P** → **2:1**。
- **阻断选择**：避免“坏阻断”（不要阻断对手弃牌区）；优选无红利牌空气与强听牌错峰混入。
- **3bet/4bet 尺度**：3bet 至 **8–10bb**；4bet 至 **20–22bb**（保持 SPR 可控）。
- **采集**：河牌下注回溯摊牌标注 value/bluff，按尺寸桶计算配比与偏差。

### 1.5 单挑特性基准（HU Bench）

- **WWSF（见翻赢池）**：**47–52%**。
- **WTSD（去摊牌率）**：**32–37%**。
- **W\$SD（摊牌赢率）**：**49–54%**。
- **对 Flop C-bet 的弃牌率**：**40–50%**。
- **采集**：HUD 与复盘报表固定项，>±3pt 偏离高亮。

### 1.6 数学底层（Pot Odds / Equity / MDF）

- **MDF（最小防守频率）**：对 **0.5P/1.0P/2.0P** 分别为 **67%/50%/33%**。
- **BB 跟 BTN 2.5x 的权益阈值**：约 **37–38%**（含抽水略上调）。
- **半诈所需弃牌率**：下注 X 倍池 → **FE ≥ X/(1+X)**。
- **合规跟注率**：当 `need_equity ≤ est_equity` 的跟注，**≥80%** 被执行。
- **采集**：决策面板显示 `need_equity / est_equity / MDF_needed / FE_req`，并记录 `is_compliant`。

### 1.7 GTO 基线 ↔ 剥削（对手建模）

- **基线偏差容忍**：核心节点（RFI/3bet/C-bet/XR/River 尺度）**±5–10%**。
- **剥削触发样例**：
  - 对手 **Fold to Flop C-bet >55%** → 我的 **Flop C-bet 提至 75–85%**（多小注）。
  - 对手 **3bet <6%** → 我的 **BTN RFI→90%**、vs 3bet 继续更宽。
  - 对手 **River 过度跟注** → **减少 Bluff，增厚 Thin Value**。
  - 对手 **River 过度弃牌** → **增加 Bluff，优选大尺寸**。
- **节点锁定 KPI**：`villain_tag → my_adjustment` 是否发生（布尔），并统计触发率。

### 1.8 选局、资金与心态（HU 版）

- **资金管理**：HU 波动大，建议 **75–100 BI**。
- **停损/停赢**：如 **-3 BI / +3 BI**，**执行率≥90%**。
- **复盘纪律**：**每场≥3 手关键标记** + **当日回看**。
- **专注度**：一桌为主，避免多桌拖垮质量。
- **采集**：会后校验停损/停赢与复盘打卡。

---

## 2. 指标配置（`metrics.json` 雏形）

```json
{
  "mode": "state_hu_cash_100bb",
  "preflop": {
    "btn": { "rfi_pct": [0.80, 0.90], "open_size_x": [2.0, 2.5], "vs3bet_continue_pct": [0.55, 0.65], "fourbet_pct": [0.06, 0.09], "fourbet_size_vs_3bet_x": [2.2, 2.5] },
    "bb": { "defend_pct_vs_2p5x": [0.60, 0.70], "threebet_pct": [0.12, 0.18], "vs4bet_continue_pct": [0.35, 0.45], "fivebet_pct": [0.02, 0.04] }
  },
  "spr": { "srp_flop": [9.0, 10.5], "threebet_flop": [2.7, 3.3], "fourbet_flop": [1.6, 1.9], "commit_rate_tptk_spr_le3": [0.70, 1.00] },
  "board": {
    "srp_ip_cbet_dry_high": { "freq": [0.70, 0.80], "size_bucket": "0.25-0.33" },
    "srp_ip_cbet_wet_mid": { "freq": [0.45, 0.60], "size_bucket": "0.33-0.50" },
    "threebet_oop_cbet_high": { "freq": [0.55, 0.65], "size_bucket": "0.25-0.33" },
    "srp_oop_xr_overall": { "freq": [0.10, 0.14] },
    "turn_barrel_good": { "freq": [0.40, 0.55] },
    "river_barrel_of_turn": { "freq": [0.35, 0.45] }
  },
  "sizing": {
    "buckets": ["0.25-0.33", "0.50-0.66", "0.75-1.00", "1.50-2.00"],
    "river_value_to_bluff": { "0.5": "1:2", "1.0": "1:1", "2.0": "2:1" },
    "threebet_to_bb": [8, 10],
    "fourbet_to_bb": [20, 22]
  },
  "hu_bench": { "wwsf": [0.47, 0.52], "wtsd": [0.32, 0.37], "wsd": [0.49, 0.54], "fold_to_flop_cbet": [0.40, 0.50] },
  "math": { "mdf": { "0.5": 0.67, "1.0": 0.50, "2.0": 0.33 }, "bb_call_vs_2p5x_equity_need": [0.37, 0.38], "min_fe_for_size": "X/(1+X)" },
  "exploit_triggers": {
    "villain_fold_to_cbet_gt": 0.55,
    "my_cbet_raise_to": [0.75, 0.85],
    "villain_threebet_lt": 0.06,
    "btn_rfi_raise_to": [0.90, 0.95],
    "calling_station_river": true,
    "bluff_downshift_when_station": true
  },
  "discipline": { "bankroll_bi": [75, 100], "stoploss_bi": 3, "stopwin_bi": 3, "review_marks_min": 3 }
}
```

---

## 3. 数据采集字段（逐手写入）

```ts
HandMetrics = {
  hand_id: string,
  pos: "BTN" | "BB",
  eff_bb: number,
  preflop: { open_to_x?: number, faced_3bet?: boolean, hero_3bet?: boolean, faced_4bet?: boolean, hero_4bet?: boolean },
  flop: { spr: number, board_class: "dry_high" | "wet_mid" | "mono" | "two_tone" | "paired", hero_role: "IP" | "OOP", cbet?: boolean, xr?: boolean, size_bucket?: "0.25-0.33" | "0.50-0.66" | "0.75-1.00" | "1.50-2.00" },
  turn: { barrel?: boolean, delayed_cbet?: boolean, size_bucket?: string },
  river: { barrel?: boolean, size_bucket?: string, is_value?: boolean, is_bluff?: boolean },
  math: { need_equity?: number, est_equity?: number, mdf_needed?: number, fe_req?: number, is_compliant?: boolean },
  players: 2,
  villain_tags?: string[],
  result: { won?: boolean, net_bb: number, showdown?: boolean },
  notes?: string
}
```

---

## 4. 仪表盘与提示文案（红/黄/绿）

**总览层**：

- 8 维雷达 + KPI 红黄绿灯。
- 展示【长期】与【近期】双刻度；近期偏离>5pt 加“⚠️ 漂移”标。

**街层诊断**：

- Flop/Turn/River 频率面板（C-bet/XR/二枪/尺寸桶）。
- 每类牌面举 3 手“反事实建议”（如果换成基线打法将多赚/少亏 X bb）。

**对手与场景层**：

- `villain_fold_to_cbet`、`villain_3bet`、`villain_call_river` 热力图；
- SRP vs 3BP、IP vs OOP、干燥 vs 湿 面的切片统计。

**提示文案模板（示例）**：

- 绿：`BTN RFI 86%（目标 80–90%）👌 保持当前 2.2x 策略。`
- 黄：`BB vs 2.5x 防守 57%（低于 60–70%），建议：扩大同花连接牌与带 A 阻断的轻型跟注。`
- 红：`Flop C-bet@干燥高牌面 61%（低于 70–80%），下轮练习已生成：IP 小注高频持续 40 手。`

---

## 5. 训练卡包（自动生成）

- **BTN vs 3bet 继续范围 扩展**（40 手）：强调 Axs、Kxs 与中等口袋对的 IP 防守。
- **SRP 干燥面 小注高频**（50 手）：范围保护 + 低风险获取弃牌率。
- **低 SPR 承诺判断**（30 手）：TPTK/超对/强听牌的 EV 比较与“打光”触发。
- **River 阻断与配比**（30 手）：按 0.5P/1.0P/2.0P 练习价值:诈唬配比。

---

## 6. 剥削引擎（触发与回写）

- **触发**：当 `villain_fold_to_cbet > 0.55` → `my_cbet_f_dry_high` 目标上调至 0.75–0.85。
- **锁定**：标记 `calling_station_river` → 降低 bluff 档、增加 thin value 线（提示“改打薄价值，减少空气”）。
- **回写**：在回放页侧栏展示“本手使用的偏移策略：{rule\_id}，预估 +EV {x} bb”。

---

## 7. 落地建议（与现有系统对接）

1. **配置文件**：将本页 `metrics.json` 作为全局配置，后端装载为阈值表，前端接入红黄绿灯。
2. **数据埋点**：在 `packages/poker_core` 的建议器流程中，完成 `HandMetrics` 的逐节点写入（含 need\_equity/MDF/FE）。
3. **回放页改造**：增加【反事实建议】与【等价尺寸替代】提示；显示“若改用 0.33P 将提升 FE ≈ y%”。
4. **HUD**：最上方显示对手 4 项关键人口统计（fold\_to\_cbet / 3bet / call\_river / fold\_vs\_steal），并映射到剥削规则。
5. **CI 校验**：加入指标解析单元测试（示例数据 → 正确判色/正确触发卡包）。

---

## 8. 版本与后续

- v1（当前）：HU 现金局 100BB 指标与仪表盘、训练卡包模板。
- v1.1（建议）：加上 **深筹（150BB+）** 与 **前注/高抽水** 的阈值分支。
- v2（建议）：引入 **Turn/River 牌面微类** 与 **节点锁定（node locking）** 的策略曲线导入。

---

## 9. 三道快测（团队讨论热身）

1. **SPR≈3 的 3bet 底池**，你持 **TPTK**，对手持续强攻，默认应否**承诺**？给出理由与例外。
2. **SRP 干燥 A 高面（你 IP）**：你的 **C-bet 频率**与**尺寸**应落在何区间？为什么？
3. **对手 Fold to Flop C-bet=60%**：你的首要调整是什么、幅度多大、优先用哪些牌作 bluff？

> 备注：上述所有阈值为“教学基线”，请按你们数据池微调（±5–10%），并在代码层保留 `POOL_PROFILE` 参数位。

