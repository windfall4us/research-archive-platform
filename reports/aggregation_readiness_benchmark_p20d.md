# P2.0D Aggregation Readiness — Benchmark 报告

**Overall: `GO`** | Schema: v6 | 三路事实盘点→聚合准备验收

## 5 关键数字（用户锁定口径）
| 数字 | 值 |
|---|---|
| physical_stock_events | 937 |
| excluded_stock_events | 3 |
| aggregation_eligible_stock_events | 934 |
| aggregation_eligible_market_views | 63 |
| aggregation_eligible_theme_mentions | 193 |

## 三路盘点链路
- Stock Events: 937 physical → 3 excluded → **934 eligible**
- Daily Views: 274 行（core_theme 72 / trend 65 / logic 65 / market 72）
- Theme Mentions: 193（全部 DIRECT eligible）
- Source Snapshots: 3 | ingest_runs: 43

## 6 Gate
| Gate | 判定 | 关键值 |
|---|---|---|
| G1 COMPOSITE 残留 | ✅ | MISRESOLVED 进入 eligible = 0；合法 COMPOSITE_TACTICAL = 18（非残留） |
| G2 Daily View lineage | ✅ | 274 行，NULL snapshot=0，orphan=0 |
| G3 Theme Mention lineage | ✅ | 193 行，orphan record=0，snapshot 解析 100% |
| G4 重复 ingest | ✅ | dup key 全 0，ingest 收敛 |
| G5 Market View UNKNOWN | ✅ | 9/72=12.5%（阈值≤20%），eligible=63 |
| G6 Theme normalization | ✅ | id 不一致=0，一词多 L2=0 |

## 结论
**GO** —— 三路事实达到可安全聚合状态，Phase 2 输入层完整，可进入 P2.1 Market Direction + P2.2 Theme Heat。