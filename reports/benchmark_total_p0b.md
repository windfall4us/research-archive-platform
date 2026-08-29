# Phase 0B 总 Benchmark（准入成绩单）— 2026-08-28

> 输入: 冻结 Gold Sample v1 FINAL + security_master.db + 真实跨天快照 + 902 ops 生产语料

## 1. Gold Sample（冻结 FINAL，程序化计数）

- ROW: total 100 | CORE 95 | AMBIGUOUS 4 | EXCLUDED 5
- EVENT: total 114 | **CORE 112**（0B.7 分母）| AMBIGUOUS 1 | EXCLUDED 1
- 多事件行 14

## 2. Security Master

- A股总数 5563 | security_type=STOCK 5563 | 重复代码 0 | 空名称 0

## 3. Stock Resolver（Gold STOCK 97 样本）

| 层 | Precision | Recall |
|---|---|---|
| EXACT | 100.0% | 96.6% |
| EXACT+ALIAS | 100.0% | 100.0% |
- Wrong Match 0 | UNRESOLVED 0 | OUT_OF_SCOPE 1

## 4/5/6. Parser v1.1 + Event + Risk Gate（盲测 CORE events）

| 指标 | 结果 | 门槛 |
|---|---|---|
| Action exact | 100.0% | ≥95% |
| Action family | 100.0% | 报告 |
| Status | 100.0% | ≥97% |
| Temporal | 100.0% | ≥95% |
| Event Precision/Recall/F1 | 1.0000/1.0000/1.0000 | — |
| Event-count 行一致率 | 100.0% (95/95) | — |
| 事件内容完全一致行 | 95/95 | — |

高风险矩阵（全部须 = 0）:
- false executed buy: **0**
- false executed sell: **0**
- 持仓→今日BUY: **0**
- WATCH→BUY族: **0**
- INTENDED→EXECUTED: **0**
- CONDITIONAL→EXECUTED: **0**
- PAST BUY→TODAY BUY: **0**
- 推荐→BUY(executed): **0**

## 7. Diff / Revision（真实跨天 08-27→08-28）

- before 851 → after 1088
- ADDED 237 | REMOVED 0 | UNCHANGED 752 | MODIFIED 99
- 内容修改(非role) 0（=0 → 增量完整性✓）| 角色翻转 99
- 分解: {'ROLE:role': 99}

## 8. Production sanity（902 ops 全量）

- ops 902 | 博主 10 | 多事件行 124
- Action: {'TRIAL': 32, 'REDUCE': 128, 'WATCH': 485, 'DO_T': 19, 'HOLD': 148, 'ADD': 92, 'BUY': 42, 'LOW_BUY': 51, 'CLEAR': 6, 'SELL': 27, 'UNKNOWN': 2}
- Status: {'CONDITIONAL': 92, 'EXECUTED': 129, 'INTENDED': 673, 'POSITION_STATE': 138}
- Temporal: {'CONDITIONAL': 127, 'TODAY': 758, 'PAST': 4, 'CURRENT_STATE': 128, 'FUTURE_PLAN': 13, 'UNKNOWN': 2}
- HOLDING(position_state) 138 = POSITION_STATE 自洽
- UNKNOWN action 2 (0.2%)

## 9. UNKNOWN / OOS

- Resolver UNRESOLVED 0（0%）| OUT_OF_SCOPE 1（1 样本）
- 生产 UNKNOWN action 2（0.2%）

## 10. 最终判定

| 模块 | 判定 |
|---|---|
| Security Resolver | PASS |
| Action Parser | PASS |
| Temporal Parser | PASS |
| Status Parser | PASS |
| Event Model | PASS |
| Risk Gates | PASS |
| Revision Engine | PASS |

**Overall: GO**

> 说明: 0B.6 真实跨天已验收（role 翻转→MODIFIED(ROLE)，内容修改=0），故成绩单判定 **GO**，Phase 0 → Phase 1 Consensus Data Layer 可启动。
