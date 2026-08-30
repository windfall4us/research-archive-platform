# P3.2 Analyst Action Flow Benchmark

Overall = **GO**（8/8 Gate）

| Gate | 判定 | 说明 |
| --- | --- | --- |
| G1 | ✅ | DO_T 进净买入=0（应 0） |
| G2 | ✅ | WATCH 进净买入=0（应 0） |
| G3 | ✅ | HOLD 进净买入=0（应 0） |
| G4 | ✅ | 净买入 205 == P3.1 positive 205（205） |
| G5 | ✅ | 查询层 NOT IN exclusions（3 治理事件不进动作流） |
| G6 | ✅ | 动作流事件 934/934（应 934） |
| G7 | ✅ | 未映射 stage 事件=0（应 0；UNKNOWN action 自身 2 条除外） |
| G8 | ✅ | 幂等：重跑前后 hash 一致 |

分析师×股票对 = 474　DO_T 对 = 16
净买入加权 = 156.4　净卖出事件 = 149
动作流 Top5: tianyingju×300607(11)；tianyingju×600988(10)；tianyingju×300418(10)；tianyingju×000506(9)；tianyingju×300618(9)

**P3.2 Overall = `GO`**