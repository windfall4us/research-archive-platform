# P4.1 Stock × Theme Linkage Benchmark

Overall = **GO**（8/8 Gate）

| Gate | 判定 | 说明 |
| --- | --- | --- |
| G1 | ✅ | mapped=337/337, unmapped=13/13（P4.0 337） |
| G2 | ✅ | S/T/A 三维信号复算一致（全 mapped 股票） |
| G3 | ✅ | linkage 标签与规则矩阵复算一致（全 mapped 股票） |
| G4 | ✅ | 最近3动作净方向复算一致（checked 337 只） |
| G5 | ✅ | 主主题 = confidence 最高映射 |
| G6 | ✅ | excluded 3 条隔离；p32 动作流 934/934 |
| G7 | ✅ | 幂等：重跑前后 hash 一致 |
| G8 | ✅ | 覆盖 350/350，全部有 linkage_signal |

联动分布: {"NEUTRAL": 261, "CONFIRMED_BULLISH": 14, "STOCK_THEME_DIVERGENCE": 54, "UNMAPPED": 13, "THEME_CONFIRMED_STOCK": 2, "CONFIRMED_BEARISH": 6}

**P4.1 Overall = `GO`**