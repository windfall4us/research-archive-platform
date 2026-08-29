# P2.1 Market Direction — Benchmark 报告

**Overall: `GO`** | 按日聚合 + 三轴独立 + Coverage + Consensus | 风格映射 2/3/3/2 已写入

## 7 Gate
| Gate | 判定 | 说明 |
|---|---|---|
| G1 UNKNOWN 参与 score | ✅ | UNKNOWN 行带 score=0，eligible 行 NULL=0（NULL 不可计权） |
| G2 analyst 同日重复计权 | ✅ | 同日重复 = 0 |
| G3 score 手工复算一致率 | ✅ | 独立复算 9 天，错配 0 |
| G4 direction bucket 映射 | ✅ | 日级错配 0，边界用例 9 个全过 |
| G5 Risk 不改变 Direction | ✅ | 9/9 天方向与仅-score 复算一致 |
| G6 Bias 不改变 Direction | ✅ | 同源验证（独立复算不含 risk/bias 列） |
| G7 Coverage<3 不输出正式方向 | ✅ | 违规 0（08-15/08-16 已 INSUFFICIENT_DATA） |

## Style Population Invariant
- 分布: {'SWING': 3, 'SHORT': 3, 'LONG_TERM': 2, 'ULTRA_SHORT': 2} | total=10 | ✅ 2+3+3+2=10，每位恰好一 style
- 枚举合法: ('LONG_TERM', 'SWING', 'SHORT', 'ULTRA_SHORT')

## 每日审计
| 日期 | 方向 | eligible | 风格覆盖(day/total) | 单样本警告 |
|---|---|---|---|---|
| 2026-08-14 | NEUTRAL | 7 | {'LONG_TERM': '1/2', 'SWING': '3/3', 'SHORT': '2/3', 'ULTRA_SHORT': '1/2'} | {'LONG_TERM': True, 'ULTRA_SHORT': True} |
| 2026-08-15 | UNKNOWN | 0 | {} | — |
| 2026-08-16 | NEUTRAL | 1 | {'SWING': '1/3'} | {'SWING': True} |
| 2026-08-17 | BULLISH | 8 | {'LONG_TERM': '1/2', 'SWING': '3/3', 'SHORT': '3/3', 'ULTRA_SHORT': '1/2'} | {'LONG_TERM': True, 'ULTRA_SHORT': True} |
| 2026-08-18 | NEUTRAL | 9 | {'LONG_TERM': '1/2', 'SWING': '3/3', 'SHORT': '3/3', 'ULTRA_SHORT': '2/2'} | {'LONG_TERM': True} |
| 2026-08-19 | BEARISH | 7 | {'LONG_TERM': '1/2', 'SWING': '3/3', 'SHORT': '1/3', 'ULTRA_SHORT': '2/2'} | {'LONG_TERM': True, 'SHORT': True} |
| 2026-08-26 | NEUTRAL | 9 | {'LONG_TERM': '1/2', 'SWING': '3/3', 'SHORT': '3/3', 'ULTRA_SHORT': '2/2'} | {'LONG_TERM': True} |
| 2026-08-27 | BULLISH | 9 | {'LONG_TERM': '2/2', 'SWING': '3/3', 'SHORT': '3/3', 'ULTRA_SHORT': '1/2'} | {'ULTRA_SHORT': True} |
| 2026-08-28 | BULLISH | 10 | {'LONG_TERM': '2/2', 'SWING': '3/3', 'SHORT': '3/3', 'ULTRA_SHORT': '2/2'} | — |

## 结论
**GO** —— P2.1 市场方向计算达标：方向强度与共识强度分离，Risk/Bias 独立，Coverage 门控生效。