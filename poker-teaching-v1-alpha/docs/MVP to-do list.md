19) V1（MVP）框架定义：完整一手牌 → 多手对局（教学友好版）

目标：能从发牌一路打到摊牌/弃牌结算，并连续开下一手。强调可学性与可实现性：减少规则边界，先把“完整闭环”跑通。

19.1 规则边界（为教学降复杂）

人数：仅 Heads‑Up（2 人）。

盲注：SB=1，BB=2（固定，不动态调盲）。

筹码：起始 100 BB，允许 All‑in。

下注模型：简化 No‑Limit：

每条街最多 2 次加注（raise cap=2），最小下注/加注额 = max(BB, 当前需跟注额)；

允许超额加注到对手有效筹码上限（以 有效筹码 为界）。

流程：Preflop（发两张）→ Flop（3）→ Turn（1）→ River（1）；各街按顺序下注；

胜负：任一方弃牌或摊牌按牌力判定（引入 PokerKit 的评牌能力）；

分配：只有两人，无边池问题（All‑in 时以较小有效筹码为上限，超出部分自动退回）。

座次轮转：每手切换按钮（SB/BB 互换），下一手继续；

对局终止：达到目标手数或有一方筹码 ≤ 0。

19.2 领域模型（最小可用）

Session（对局）：session_id、配置（SB/BB/起始筹码/上限手数）、玩家（human/bot）、当前按钮位、手数计数、状态；

Hand（一手）：hand_id、session_id、seed、按钮位、起始筹码快照、时间戳、Steps（事件时间线）、结算结果；

State（运行态）：当前街（preflop/flop/turn/river）、行动方、需跟注额、已加注次数、底池、各方剩余筹码、公共牌/手牌；

Action：check/call/bet/raise/fold/allin，可选 amount；

Outcome：赢家/平分、筹码变动、下一手按钮位。

实现策略：packages/poker_core 内实现 纯函数状态机：

start_session(config) -> session；

start_hand(session, seed?) -> (hand, state, events[])；

legal_actions(state) -> set[str]；

apply_action(state, action) -> (state', events[])；

is_hand_over(state) -> bool；

settle(state) -> outcome；

评牌/胜者：优先用 PokerKit 作为 evaluator（保持“库 + 关键自研”的路线），我们专注状态机与筹码账。

19.3 核心 API（在现有 v1 基础上扩展）

POST /api/v1/session/start → 创建对局（人类 + 机器人），返回 session_id、初始 stacks、按钮位；

POST /api/v1/hand/start → 参数：session_id, seed?；发盲注与底牌，返回 hand_id + 初始 state；

GET  /api/v1/hand/{hand_id}/state → 查询当前状态（含合法动作 legal_actions）；

POST /api/v1/hand/{hand_id}/act → 执行动作 {actor, action, amount?}，返回新 state/steps；若进入下一街，自动发公共牌；结束则返回 outcome；

GET  /api/v1/hand/{hand_id}/replay → 完整时间线（兼容现有 Replay）；

GET  /api/v1/session/{session_id}/state → 对局层状态（按钮位、当前手数、两侧筹码）；

POST /api/v1/suggest → {hand_id, actor} 返回 简单建议（见 19.6）；

POST /api/v1/session/next → 结束一手后开始下一手（或在 act 检测结束即自动触发 next）。

幂等性：写操作支持 Idempotency-Key（请求头），避免重复提交导致双记账。

19.4 数据持久化与联动

继续沿用 Replay(hand_id) JSON 一等公民（兼容 v0.4），扩展字段：

session_id、button_pos、stacks_before/after、board、actions[]（带街、序号、金额）、outcome；

新增 Session 表（最小 JSON）：players[]/{id,name,is_bot}, config, stacks, button_pos, hand_counter, status；

联动：seed 存在 Hand/Replay；相同 seed + 相同动作序列 ⇒ 可复现；engine_commit/schema_version 继续写入；

账本原则：两人对局恒定总筹码守恒。可加一张 chip_ledger（可后置）做审计；MVP 先用 stacks_after 校验即可。

19.5 质量门槛（MVP 必过）

领域层覆盖率：poker_core ≥ 85%（状态转移/筹码结算/胜者判定）；

端到端：

完整打一手（弃牌结束）；

完整打一手（摊牌结束）并校验赢家与筹码守恒；

连续两手（按钮位轮转、生效）；

不变量测试：

sum(stacks) + pot == constant 在任意时刻成立；

legal_actions 与状态一致（无非法 check/raise）；

契约：OpenAPI 更新 + /api/docs 可交互；

性能门：单手 95% 延迟 < 100ms（本地）。

19.6 教学建议（最低可用规则）

Preflop 起手分类（Premium/Pair/Suited Connector/Trash）→ 建议 open/fold；

位置与先后：按钮位倾向更激进（同样牌力建议不同）；

跟注价位：基于 底池赔率 与 最小牌力阈值 的二元决策（简化版，会在文档给表格）；

C‑bet 提示：Flop 作为进攻者有 1 次标准 C‑bet 建议（量级统一成底池 1/2）；

危险板面：同花/顺听面给 WARN 级提示。

机器人（可选开关）：使用同一套规则 + 随机扰动（ε‑greedy），便于模拟对局；接口位于 AnalysisProvider(bot=True)。

19.7 KPI 药丸（MVP 版）

Session deals（会话）：本进程打了多少手；

Replays total（持久）：累计保存的手数；

Stacks（P1/P2）：两侧当前筹码（可做成两个小药丸）；

Avg pot（本会话均值）；

Win rate（近 N 手，简单占比）。

19.8 验收门（V1 必须看到的“可见价值”）

在 UI 上，从 Start Session → Deal → 多个 Act → 结束 → Next 一气呵成；

数据库里新增 Session + Replay，且 筹码守恒；

/api/docs 覆盖所有新端点，能点“Try it out”；

自测题：解释一次结算细节（押注、底池、摊牌）并复盘建议为何如此。

19.9 你的 6 个问题（落地答复）

核心 API 需要拓展什么？ 见 19.3；增：session/start、hand/start、hand/act、session/state、suggest、session/next。

一手牌/seed 如何与库联动？ Replay(hand_id) 写入 session_id/seed/engine_commit/schema_version/actions/outcome；同 seed + 动作序列 可重放；Session 记录两侧 stacks 与按钮，手结束后更新。

质量门槛：领域覆盖 ≥85%；E2E 3 条必过；筹码守恒 property；OpenAPI 契约全；95p 延迟 <100ms（本地）。

KPI 药丸：新增 Stacks(P1/P2)、Avg pot、Win rate（近 N 手）；保留 Session deals / Replays total。

注释规则：起手分类、位置差异、底池赔率阈值、标准 C‑bet、危险面板 WARN。后续逐步细化到 Turn/River。

单人对战要不要机器人？ 建议 开：同一套规则 + ε 随机。先可视化 + 可复现，再考虑更强策略。

19.10 下一步执行建议（v1‑alpha 迭代顺序）

领域状态机雏形（poker_core）+ 评牌接入（PokerKit）；

扩展 API：session/start、hand/start、hand/act、state；

UI：动作面板（按钮自动禁用非法动作）、时间线可视化、Stacks 药丸；

E2E 三条用例 + 筹码守恒 property；

Replay/Session JSON 入库；

（可选）机器人与 suggest。