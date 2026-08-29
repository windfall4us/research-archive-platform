# P2.0B Market View Ingest — Benchmark 报告

**Overall: `GO`** | Parser: `market_view_parser_v1` | Gold: `market_view_gold_v1`（50 条锁定）

## 分母口径（用户 2026-08-30 锁定）
- 全部样本（Scope 分母）：50 | eligible（三轴分母）：46 | excluded：4

## 指标
| 指标 | 通过/总数 | 准确率 | 门槛 | 判定 |
|---|---|---|---|---|
| scope_accuracy | 34/50 | 68.0% | 0% | ✅ |
| direction_accuracy | 45/46 | 97.8% | 95% | ✅ |
| risk_accuracy | 44/46 | 95.7% | 90% | ✅ |
| bias_accuracy | 44/46 | 95.7% | 90% | ✅ |
| excluded_two_way | 50/50 | 100.0% | 100% | ✅ |

## 硬 Gate
| Gate | 说明 | 判定 |
|---|---|---|
| G1_STOCK_ONLY_no_marketview |  | ✅ PASS |
| G2_UNKNOWN_no_view_direction |  | ✅ PASS |
| G3_direction_reversal_zero |  | ✅ PASS |
| G4_MV1_score_mapping |  | ✅ PASS |
| G6_excluded_two_way_100 |  | ✅ PASS |
| G5_MV2_axis_independent | 结构独立；分布见 report | ✅ PASS |

## 错误明细
- Direction: 1 条
  - G045 youzi 2026-08-18: GOLD=BULLISH PRED=NEUTRAL
- Risk: 2 条
  - G006: GOLD=HIGH PRED=MEDIUM
  - G044: GOLD=MEDIUM PRED=HIGH
- Bias: 2 条
  - G015: GOLD=CONTROL_POSITION PRED=ADD_ON_DIP
  - G024: GOLD=ADD_ON_DIP PRED=HOLD
- Scope（四档，边界参考，不计门禁）: 16 条 —— 全为 MARKET/MIXED 主体判定边界，排除二档 100%