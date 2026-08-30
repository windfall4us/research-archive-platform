# P3.4 Phase 3 总 Benchmark — **Overall = `GO`**

硬 Gate **10/10**

| Gate | 判定 | 关键值 |
| --- | --- | --- |
| G1 | ✅ | 事件全量 934 = 934 = 934（P3.1/P3.2/P3.3） |
| G2 | ✅ | 净买入 205 = 205 = 205（P3.1 positive / P3.2 net_buy / P3.3 pos） |
| G3 | ✅ | 净卖出 149 = 149（P3.1 negative / P3.2 net_sell） |
| G4 | ✅ | STRONG 56 == P3.0 S1 56 |
| G5 | ✅ | 分母 350 = 350 = 350（P3.0/P3.1/P3.3） |
| G6 | ✅ | 覆盖完整：P3.1 cell 716 / P3.3 股票 350 |
| G7 | ✅ | DO_T/WATCH/HOLD 进净买入 = 0/0/0 |
| G8 | ✅ | 全链路重跑 hash 一致（4 输出） |
| G9 | ✅ | 原始层未改：source_snapshots 2 行不变 + 快照 hash 不变 |
| G10 | ✅ | 子 benchmark P3.1/P3.2/P3.3 exit = 0/0/0（0=GO） |

## Phase 3 分层总结
- **Readiness (P3.0)**: GO — 934 eligible events / 350 股 / 10 分析师 / 8 交易日；124 持仓 / 79 股；双证据 79 全重叠
- **Factors (P3.1)**: GO — 四类事实 716 cell；正 205 / 负 149；DO_T/WATCH/HOLD 隔离
- **Action Flow (P3.2)**: GO — 474 分析师×股票对；stage 生命周期 SCAN→ENTRY→ACCUMULATE→HOLD→REDUCE→EXIT→TACTICAL
- **Score/State (P3.3)**: GO — 350 只；{"NEUTRAL": 203, "NEGATIVE": 56, "POSITIVE": 82, "STRONG_POSITIVE": 9}

## 业务审计
- **A1 Top 正共识可解释**: ✅ STRONG_POSITIVE 9 只，全部 positive_weighted ≥ 1.0
- **A2 Top 负共识可解释**: ✅ NEGATIVE 56 只，全部 negative_weighted ≤ -0.5
- **A3 无 STRONG_NEGATIVE 边界**: 最负 action_net = -1.3（STRONG_NEGATIVE 需 ≤ -2.0 且 strength∈STRONG/MEDIUM，数据未达 → 无强负共识，分析师群体偏多头）

**Phase 3 Overall = `GO`**