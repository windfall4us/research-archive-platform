# P3.1 Stock Consensus Factors Benchmark

Overall = **GO**（8/8 Gate）

| Gate | 判定 | 说明 |
| --- | --- | --- |
| G1 | ✅ | excluded 泄漏=0（应 0） |
| G2 | ✅ | DO_T 进正负=0 / WATCH 进正负=0（应 0/0） |
| G3 | ✅ | pos 205/205 · neg 149/149 |
| G4 | ✅ | 持仓使用 124/124（应 124/124） |
| G5 | ✅ | 事件使用 934/934（应 934/934） |
| G6 | ✅ | 方向冲突 14 条，仅审计不主导（正负桶一致性保持） |
| G7 | ✅ | 覆盖股票 350 == P3.0 eligible 350（350） |
| G8 | ✅ | 幂等：重跑前后 hash 一致 |

每股每日 cell = 716（350 股 × 8 日）
方向冲突 14 条样本：ADD/减仓(laofan)；ADD/减仓(laofan)；ADD/减仓(laofan)；REDUCE/买入(laofan)；ADD/卖出(tianyingju)；ADD/减仓(tianyingju)

**P3.1 Overall = `GO`**