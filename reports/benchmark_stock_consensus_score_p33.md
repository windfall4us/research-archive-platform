# P3.3 Stock Consensus Score / State Benchmark

Overall = **GO**（8/8 Gate）

| Gate | 判定 | 说明 |
| --- | --- | --- |
| G1 | ✅ | 覆盖 350/350，NO_DATA=0 |
| G2 | ✅ | 000506 手工复算 = 3.7（脚本 3.7） |
| G3 | ✅ | STRONG=56 == P3.0 S1=56（56） |
| G4 | ✅ | consensus_raw == action_net + holding_net（350 只全一致） |
| G5 | ✅ | state 与固定阈值规则全 350 只一致 |
| G6 | ✅ | divergence≠0 的股票全部 n_analysts≥2 |
| G7 | ✅ | 事件使用 934/934 |
| G8 | ✅ | 幂等：重跑前后 hash 一致 |

State 分布: {"NEUTRAL": 203, "NEGATIVE": 56, "POSITIVE": 82, "STRONG_POSITIVE": 9}
Strength 分布: {"STRONG": 56, "MEDIUM": 107, "WEAK": 187}

**P3.3 Overall = `GO`**