# Phase 0B：Gold Sample + 代码解析 + Diff/Revision（v2，纳入用户决策）

> 前置：Phase 0A 完成（No-Go 进 Phase 1）。数据边界 = 22:40 日终快照（22:30 夜盘成品）。
> 本版本按用户 2026-08-28 决策全面修订：双轨数据模型、并行执行、7 个子版本、Precision 优先。

## 核心原则（全引擎硬规则）
1. **UNKNOWN 可以存在，错误识别成 STOCK 不可以**——不猜代码，保留原文
2. **操作事件 ≠ 持仓状态**（用户决策 1 修订）：
   - ①「最新持仓汇总」本身**不得**生成 BUY/ADD/LOW_BUY 等当日操作事件
   - ② 持仓汇总只生成 `position_state = HOLDING`
   - ③ 当日正文明确出现 买入/低吸/加仓/减仓/卖出 → 额外生成 `analyst_stock_event`
   - ④ 同一股票可同时：`TODAY + EXECUTED + LOW_BUY` 与 `CURRENT_STATE + HOLDING`
   - ⑤ 不能因股票出现在持仓汇总，就删除正文真实发生的当日操作
3. **Precision 优先于 Recall**：漏掉 1 条 = 少一点信号；把 A 识别成 B = 制造错误共识
4. 时间语义必须保留：TODAY / PAST / CURRENT_STATE / FUTURE_PLAN / CONDITIONAL / UNKNOWN

## ⚠️ 关键数据发现（2026-08-28）
`render_vip0_timeline.py:178-198`：**「最新持仓汇总」并非独立数据，而是把最新一天的 `days[latest_day].ops` 重新渲染一遍**。
- 当前 JSON（vip0_timeline.json）**没有独立的持仓状态表**
- 「持仓汇总」与「日内操作」同源同表 → 无法区分「当前持有」vs「今日买入」
- 结论：双轨数据模型不能只在解析层做，**必须在 Phase 1 数据层单独建 `analyst_position_snapshots` 表**
- Gold Sample 第 4/5 类（当前持仓/今日买入+仍持）需要人工结合正文判断，不能依赖现有 latest-summary 字段

---

## Phase 0B 拆成 7 个子版本（用户决策 8）

```
Phase 0B.1  Gold Schema + 10 条高难度样例          ✅ PASS
Phase 0B.2  100 条 Gold Sample（分层扩展）         ✅ 已锁定（gold_sample_100_final.json 事件级，P1-P6 仲裁94条）
Phase 0B.3  Stock Master + EXACT 匹配             ✅ PASS
Phase 0B.4  Alias + Entity Type                   ✅ PASS
Phase 0B.5  Action / Temporal Parser              ✅ PASS / LOCKED（v1.1，Gold 112/112，High-risk=0，confirmed10 100%）
Phase 0B.6  Cross-day Diff + Revision（MODIFIED）  ✅ PASS（真实跨天 08-27→08-28：role 翻转→MODIFIED(ROLE)，内容修改=0，增量完整性✓）
Phase 0B.7  Accuracy Benchmark（成绩单）           ⏳
```

### 执行策略（用户决策 3/4/5）：三线并行，不等快照
```
快照持续积累 ──┬─→ B1/B0B.6 跨天 Diff（等 ≥3 天后正式验收，但模型现在先写好）
              └─→ 每天 22:40 自动归档（已有）
立即开始：
  B2.1/0B.1 10 行 Gold Sample → 确认 Schema → 0B.2 100 条
  并行 0B.3 Stock Master → 0B.4 Alias → 0B.6 Diff/Revision 模型设计
```

---

## 0B.1：Gold Sample Schema v1（用户决策 2）

必填字段（尤其 actions[] / action_status / temporal_type 不能省）：

```
sample_id
analyst_id
analysis_date
raw_text
raw_target
entity_type              STOCK/THEME/MARKET/UNKNOWN
stock_code
stock_name
stock_match_method        EXACT/ALIAS/CONTEXT/FUZZY/UNRESOLVED
stock_match_confidence
actions[]                多动作数组（BUY/ADD/LOW_BUY/TRIAL/HOLD/WATCH/DO_T/REDUCE/SELL/CLEAR/STOP_LOSS）
action_status             EXECUTED/INTENDED/CONDITIONAL/POSITION_STATE/UNKNOWN
temporal_type             TODAY/PAST/CURRENT_STATE/FUTURE_PLAN/CONDITIONAL/UNKNOWN
position_state            持仓状态（HOLDING/无）
raw_theme
normalized_theme
human_confidence
review_note
```

### 10 行高难度样本覆盖矩阵（用户指定）
| # | 必须覆盖 | 说明 |
|--|--|--|
| 1 | 明确买入 | 买点/建仓/扫货 |
| 2 | 明确低吸 | 低吸 |
| 3 | 明确加仓 | 加仓/补仓 |
| 4 | 当前持仓、今天没买 | position=HOLDING, 无当日操作事件 |
| 5 | 今日买入+当前仍持仓 | 双轨：TODAY+EXECUTED+LOW_BUY 且 CURRENT_STATE+HOLDING |
| 6 | 减仓但未清仓 | REDUCE, position 仍在 |
| 7 | 已走/清仓 | CLEAR/SELL |
| 8 | "回踩可买"等条件计划 | CONDITIONAL / INTENDED |
| 9 | "做T/低吃+做T"等复合动作 | actions=[LOW_BUY, DO_T] |
| 10 | 非个股/无法解析对象 | entity_type=THEME/MARKET/UNKNOWN |

### 动作归一化字典（固定）
BUY +2.0 / ADD +1.5 / LOW_BUY +1.2 / TRIAL +0.8 / HOLD +0.5 / WATCH 0 / DO_T 0 / REDUCE -1.0 / SELL -1.5 / CLEAR -2.0 / STOP_LOSS -2.0

---

## 0B.6：Diff + Revision 模型（用户决策 4/5/6，现在先设计，等快照验收）

### 双层 ID（用户决策 4）
```
logical_key  = vip0:{analyst}:{date}:{section_type}:{entity}   # 判断"可能同一逻辑记录"
record_id    = vip0:{analyst}:{date}:{section_type}:{entity}:action:{NNN}  # 记录指纹
```
- 不能用 `analyst+date+stock` 当唯一 key（同一天 上午低吸/下午减仓 是两条，不是 revision）
- Diff 状态：ADDED / REMOVED / UNCHANGED / **MODIFIED**

### Revision 记录字段（用户决策 5）
```
revision_id
logical_record_id
snapshot_date
detected_at
revision_no
change_type
old_hash / new_hash
old_value / new_value
changed_fields        ← 关键：区分「股票名称变化」vs「操作 HOLD→SELL」严重程度
```

### 跨天验收报告（用户决策 6，等 ≥3 天快照）
```
2026-08-27 → 2026-08-28
原记录：846
UNCHANGED 731 / ADDED 82 / REMOVED 21 / MODIFIED 12
拆解：新增当天 / 旧日期补录 / 旧日期文本修改 / 持仓汇总修改 / 操作动作修改
Historical Mutation Rate = 旧日期修改数 / 旧日期记录总数
   <1%  → revision 是辅助机制
   5-10%+ → HTML 是持续修订产品，Revision Store 成为核心架构
```

---

## 0B.3/0B.4：股票代码解析（用户决策 7，Precision 优先）

### 分层匹配与阈值
```
EXACT    自动通过        （芯原股份 → 688521）
ALIAS    自动通过        （芯原 → 芯原股份；必须人工维护/审核，不放任模糊）
CONTEXT  高置信通过      （结合主线/逻辑消歧重名）
FUZZY    默认 review     （绝不直接判 STOCK）
UNKNOWN  不计算          （保留原文，进人工队列）
```
- Stock Master 与平台股票池/金融 API **用同一标准库**，避免 688521 一个认一个不认
- 第一版**不上大范围 FUZZY**

### B3.3 锁定（用户确认 2026-08-28）

```text
Phase 0B.3 Security Master / Stock Resolver
Status: PASS

Scope:
- A股 Security Master：5563
- EXACT Resolver：PASS
- ALIAS Resolver：PASS
- OUT_OF_SCOPE 分流：PASS
- FUZZY：Disabled by design

Benchmark:
- A_SHARE_RESOLVABLE = 89
- EXACT matched = 86
- ALIAS matched = 3
- UNRESOLVED = 0
- WRONG_MATCH = 0
- EXACT Precision = 100%
- EXACT Recall = 96.6%
- EXACT+ALIAS Precision = 100%
- EXACT+ALIAS Recall = 100%

Decision:
Precision-first gate passed.
No need to enable FUZZY in Phase 0B.
```

**已批准 ALIAS（stock_aliases, CONFIRMED）**：华虹公司→688347 (COMMON_NAME 1.00) / 宏景→301396 (SHORT_NAME 0.98) / ST闻泰→600745 (NAME_VARIANT 0.99)。中国金茂→OUT_OF_SCOPE（不进 stock_aliases）。

**解析状态枚举（正式）**：`EXACT / ALIAS / CONTEXT / FUZZY / UNRESOLVED / OUT_OF_SCOPE`

### 🔒 设计边界（锁定，禁止"优化"时误改）

```text
1. EXACT 不删除 * / ST / U 等证券名称标记
2. 人工确认简称进入 ALIAS，不放宽 EXACT
3. OUT_OF_SCOPE 不计入 A 股 Resolver Recall 分母
4. UNRESOLVED 与 OUT_OF_SCOPE 严格分离
5. FUZZY 默认关闭
6. 只有未来真实 UNRESOLVED 样本证明有必要时才评估 CONTEXT/FUZZY
```

---

## 0B.5：Action / Temporal Parser（规则版 v1，2026-08-28）

脚本: `scripts/action_temporal_parser_p0b.py` + `action_temporal_benchmark_p0b.py` + `confirmed10_benchmark_p0b.py`

### v1 规则（从已确认 10 行协议推导）
```text
动作: 长词优先词典扫描（91句式→11类），分句扫描
状态: 已/时段→EXECUTED；若/等/回踩/站上→CONDITIONAL；持有→POSITION_STATE(双轨)；WATCH恒INTENDED；清仓默认EXECUTED；减/卖默认EXECUTED(除非条件/计划标记 左右/以上/以下)
时间: 明日/将→FUTURE_PLAN；动作分句条件词→CONDITIONAL；今日/早盘/尾盘→TODAY；持有→CURRENT_STATE；之前→PAST；默认 TODAY(当日分析)
```

### v1 成绩
```text
确认10行: Status 9/9=100% ✅ | Action 8/9=89%(唯一差=BUY vs LOW_BUY 子类) | Temporal 9/10=90%
100行 vs draft: Action 68% / Status 69%（draft 有已知错误，parser 常更准）
5项高风险: 全部 0 ✅（WATCH→HOLD / 持仓→BUY / 计划→EXECUTED / 回踩→EXECUTED / 过去→今日BUY）
```

### ⚠️ temporal 基准问题
100 行 draft 的 temporal_type_draft **83% 是 UNKNOWN**，无法作 temporal 基准。已确认 10 行才是权威时间真值。0B.2 人工锁定时需补标 temporal 列。

### 已知接受差异（非高风险）
- [华勤] BUY vs LOW_BUY（买入族子类）+ CONDITIONAL vs FUTURE_PLAN（语义细微差）
- 大盘/市场实体 → 动作不计（实体门控，非 parser 职责）

---

## 0B.5 仲裁 + Gold Sample v1 FINAL（2026-08-28）

### P1-P6 仲裁（94 条分歧全部人工锁定）
```text
PARSER_CORRECT 71 | BOTH_WRONG 13 | DRAFT_CORRECT 5 | AMBIGUOUS 4 | MARKET_EXCLUDED 1
5 项高风险 = 0；exclude 5 条（[10][57][58][61][87]）
```
仲裁期间新增协议: 协议9(推荐≠买入) / 10(今日XX为主≠已执行) / 11(动作级Temporal/Status隔离) / 12(时段词≠执行态) / 13(仓位动作程度分级)
backlog A-P（parser v1.1 待办，仲裁期间不改代码）: docs/parser_gap_backlog.md

### Gold Sample v1 FINAL（事件级）
```text
ROW LEVEL（100 样本）
  CORE rows      95  | AMBIGUOUS rows 4 ([10][57][58][87]) | EXCLUDED rows 5 ([10][57][58][61][87])
  EXCLUDED = 非core；其中 4 条同时 AMBIGUOUS，1 条([61]) 仅 MARKET 排除；ambig ⊆ exclude（[10] 双计，去重 5 行）
EVENT LEVEL（114 事件 = 100 行 + 14 多事件行）
  CORE events    112 | AMBIGUOUS events 1 ([10]) | EXCLUDED events 1 ([61])
  （[57][58][87] 无事件；Benchmark 输入 = CORE events 112）
Action: WATCH32/HOLD21/REDUCE12/ADD12/BUY11/SELL6/TRIAL5/LOW_BUY5/DO_T4/CLEAR4/UNKNOWN2
Status: INTENDED58/CONDITIONAL19/POSITION_STATE19/EXECUTED17/UNKNOWN1
Temporal: TODAY69/CONDITIONAL24/CURRENT_STATE15/FUTURE_PLAN3/PAST2/UNKNOWN1
统计详情: reports/gold_sample_final_stats_p0b.md
```
每个事件独立 status+temporal（协议11）；position_state=HOLDING 双轨 19 行；无显著偏斜
Gold Edge / Ambiguous Set（[10][57][58][61][87]）保留为复杂语义 Parser v1.2+/v2 的进化语料，不删除

### 下一步
```text
① ✅ 用户确认 Gold FINAL 无偏斜（2026-08-28）
② ✅ backlog A-P 全部落地 → Parser v1.1（事件级）
③ ✅ 对 CORE events 112 盲测：Action 100% / Status 100% / Temporal 100% / Event F1 1.0 / 高风险 0
④ ✅ confirmed10 交叉回归 100%
⑤ → 标记 0B.5 PASS → 0B.7 总 Benchmark
```

---

## 验收成绩单（Phase 0B.7，达门槛才进 Phase 1）
Benchmark 输入 = **CORE events（112）**（Gold Sample v1 FINAL，排除 ambig/excluded 5 行），非 Core rows
| 指标 | 正式门槛 |
|---|---:|
| Entity Type | 98% |
| 股票识别 | 97% |
| Code Match | 97% |
| Action exact accuracy | ≥95% |
| Action-family accuracy | 建议同时报告（买入族/卖出族合并看） |
| Status accuracy | ≥97% |
| Temporal accuracy | ≥95% |
| Event-count accuracy | 建议新增（Gold 事件集 vs Predicted 事件集，缺/多事件判定） |
| Event Precision / Recall / F1 | 建议新增（事件级 P/R/F1） |
| 持仓→买入误判 | 0% |
| false executed buy / false executed sell | **0**（最核心 Gate，污染共识操作流） |
| High-risk error（WATCH→BUY、INTENDED→EXECUTED、推荐→BUY 等） | 0 |
| Overall | 96.x% |

> 事件级指标定义：Gold events vs Predicted events 按行对齐后统计 Missing/Extra；
> Event Precision = 正确事件/(正确+多余事件)；Recall = 正确事件/(正确+缺失事件)。
> 高风险错误矩阵单独输出，不并入 Overall 掩盖。

---

## 执行队列（当前，2026-08-28 更新）
```text
✅ 0B.1：10 行 Gold Sample + Schema 确认
✅ 0B.2：扩 100 条（规则修正完成，待最终人工锁定）
✅ 0B.3：Stock Master（5563）+ EXACT 匹配
✅ 0B.4：ALIAS（3条批准）+ OUT_OF_SCOPE 分流 —— B3.3 已锁定
→ 0B.5：Action / Temporal Parser
→ 0B.6：今晚 22:40 真实跨天 Diff 验收（08-27 → 08-28，独立提交）
→ 0B.7：Benchmark 成绩单 → Go/No-Go → Phase 1
```
不提前碰市场温度/主题热度（数据基础未就绪）。FUZZY 保持关闭。
