# P2.2B Theme Daily Factors — Benchmark 报告

**Overall: `GO`** | 全网格 171 行（9 日期 × 19 L2），有信号 135 行

## 8 Gate
| Gate | 判定 | 关键值 |
|---|---|---|
| G1 DIRECT 重复计权 | ✅ | 193 raw → 139 analyst-theme-day 单位，mismatch=0 |
| G2 conf<0.60 参与 | ✅ | 映射行 1092，heat 股票 337，全部 conf≥0.60 |
| G3 excluded 3 events | ✅ | excluded [1093, 1095, 1107]，泄漏进 eligible=[] |
| G4 COMPOSITE 不拆分 | ✅ | COMPOSITE_TACTICAL 18（全 DO_T，方向0） |
| G5 DO_T 不进净方向 | ✅ | tactical Σ=17.9997 vs 理论 18.0；DO_T 18 条 |
| G6 fractional 守恒 | ✅ | 违规 0 |
| G7 lineage 100% | ✅ | 断裂 0 |
| G8 重跑 dedupe | ✅ | 171 行，dup=0 |

## 事实源
- eligible events: 934（937−3 excluded）
- DIRECT mentions: 193 raw → 139 analyst-theme-day
- HOLDING snapshots: 124

## 结论
**GO** —— 四因子原始数据（coverage/mention/trade/holding）可审计、防膨胀、全 lineage，可进入 P2.2C 权重合成。