# P4.2 Consensus / Divergence Benchmark

Overall = **GO**（9/9 Gate）

| Gate | 判定 | 说明 |
| --- | --- | --- |
| G1 | ✅ | 覆盖 350/350 |
| G2 | ✅ | divergence_score = 4 维均分（容差 0.001） |
| G3 | ✅ | consensus_strength 公式复算一致 |
| G4 | ✅ | analyst_divergence 复算一致 |
| G5 | ✅ | theme_stock_divergence = |S−T|/2 复算一致 |
| G6 | ✅ | view_action_divergence（INTENDED vs EXECUTED）复算一致 |
| G7 | ✅ | holding_action_divergence 复算一致 |
| G8 | ✅ | 幂等：重跑前后 hash 一致 |
| G9 | ✅ | excluded 3 条隔离 |

高分歧(≥0.5): 37　多分析师同向: 57　分析师分裂: 29
主题个股反向: 54　观点操作异号: 37　持仓转负: 18

**P4.2 Overall = `GO`**