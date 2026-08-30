# P4.4 Phase 4 总 Benchmark — **Overall = `GO`**

硬 Gate **10/10**

| Gate | 判定 | 关键值 |
| --- | --- | --- |
| G1 | ✅ | 全链路重跑 hash 一致（4 输出，rerun {"p40": 0, "p41": 0, "p42": 0, "p43": 0}） |
| G2 | ✅ | 原始层未改：source_snapshots 2 行 + 快照 hash 不变 |
| G3 | ✅ | 分母 350 = 350 = 350 = 350（P4.0/P4.1/P4.2/P4.3） |
| G4 | ✅ | 映射 337 = 337，UNMAPPED 13 |
| G5 | ✅ | CONFIRMED_BULLISH 14 全→CONFIRMED；STOCK_THEME_DIVERGENCE 54 全→DIVERGING/REVERSING |
| G6 | ✅ | DIVERGENCE linkage 54 = P4.2 theme_stock_mismatch 54（54），全落入 DIVERGING/REVERSING |
| G7 | ✅ | 动作流事件 934/934 |
| G8 | ✅ | 子 benchmark P4.1/P4.2/P4.3 exit = 0/0/0 |
| G9 | ✅ | excluded 3 条隔离 |
| G10 | ✅ | state 分布无漂移 |

## Phase 4 分层总结
- **Cross-Layer Readiness (P4.0)**: GO — 337/350 可连接；每股 distinct 主题 {1:99, 2:131, 3:107}（Top3 治理）；canonical 缺 TECH_GENERAL/NEW_ENERGY_ELECTROLYTE
- **Stock×Theme Linkage (P4.1)**: GO — 三维信号 S/T/A → 联动标签；{"NEUTRAL": 261, "CONFIRMED_BULLISH": 14, "STOCK_THEME_DIVERGENCE": 54, "UNMAPPED": 13, "THEME_CONFIRMED_STOCK": 2, "CONFIRMED_BEARISH": 6}
- **Consensus/Divergence (P4.2)**: GO — 5 维分歧量化；高分歧 37 / 持仓转负 18
- **Cross-Layer State (P4.3)**: GO — 6 状态机；{"NEUTRAL": 143, "WEAKENING": 87, "CONFIRMED": 19, "DISCOVERY": 27, "DIVERGING": 45, "UNMAPPED": 13, "REVERSING": 13, "CONFIRMING": 3}

## 业务审计
- **A1 CONFIRMED 可解释**: ✅ 19 只全为三维共振低分歧
- **A2 REVERSING 可解释**: ✅ 13 只全为持仓转负/观点异号转折
- **A3 状态分布合理性**: 分布 {"NEUTRAL": 143, "WEAKENING": 87, "CONFIRMED": 19, "DISCOVERY": 27, "DIVERGING": 45, "UNMAPPED": 13, "REVERSING": 13, "CONFIRMING": 3}：CONFIRMED+DIVERGING+REVERSING 共 77（有信号占比合理），NEUTRAL 143（无信号/弱信号池）

**Phase 4 Overall = `GO`**