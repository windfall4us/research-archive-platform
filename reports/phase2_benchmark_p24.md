# P2.4 Phase 2 总 Benchmark — **Overall = `GO`**

硬 Gate **12/12**

| Gate | 判定 | 关键值 |
| --- | --- | --- |
| G1 Market View eligible 口径 | ✅ | market 行=72, UNKNOWN=9, eligible=63; P2.0D 固化 aggregation_eligible_market_views=63 |
| G2 Theme Mention lineage | ✅ | mentions=193, orphan_record=0, orphan_snapshot=0 |
| G3 Stock-theme mapping eligible | ✅ | eligible=350, heat_stocks=337, coverage=96.3%（P2.2A benchmark 要求 ≥95%）; unmapped=13 只（P2.2A 判定可接受） |
| G4 3 治理事件泄漏 | ✅ | exclusions 表命中=3（应 3）; 泄漏进 eligible 计算集合=0（应 0，即 3 事件全部被 exclusions 表覆盖） |
| G5 Theme Factors 重算 | ✅ | P2.2B benchmark exit=0（0=GO） |
| G6 Theme Heat 重算 | ✅ | P2.2D benchmark exit=0（0=GO） |
| G7 Momentum Δ1/Δ3 重算 | ✅ | P2.3 benchmark exit=0（0=GO） |
| G8 LOW_SIGNAL/Missing 语义 | ✅ | 08-16 19 行全 LOW_SIGNAL（非状态=无，高置信=无）; heat=0 行 49 全可解释（49） |
| G9 Transition graph 合法 | ✅ | 非法跳转=无 |
| G10 全链路重跑新增记录 | ✅ | 重跑成功; 行数差异=无 |
| G11 关键输出 hash 一致 | ✅ | hash 差异=无（4 个输出） |
| G12 原始事实层被修改 | ✅ | 原始快照被修改=无（5 个） |

## Phase 2 分层总结
- **Data/Parser Readiness**: {"p20b": {"overall": "GO (P2.0B)"}, "p20c": {"overall": "GO (P2.0C)"}, "p20d": {"overall": "GO (P2.0D)"}, "key": {"mv_total": 72, "mv_eligible": 63, "tm_total": 193, "stock_events": 937, "exclusions": 3}}
- **Market Direction**: {"overall": "GO (P2.1)", "notes": "按日聚合 + 三轴独立 + Coverage Gate；风格分组解释层"}
- **Theme Heat**: {"overall": "GO (P2.2C/P2.2D)", "grid": "171 行（9 日期 × 19 L2）", "zero_explainable": "49/49"}
- **Theme Momentum**: {"overall": "GO (P2.3)", "rows": 171, "eff_dist": {"FADING": 16, "DISCOVERY": 28, "COOLING": 23, "HEATING": 4, "EMERGING": 6, "STABLE": 1}}

## 审计
- **A1_0816_low_signal_isolation**: "08-16 全 19 行 LOW_SIGNAL；Top1 半导体 热度 67.71 但仅 1 位分析师有有效信号 → 低置信而非加热"
- **A2_tech_ai_compute_cooling_boundary**: "已明显回暖(d1=+11.97,d3=+10.27,heat=24.93)但 effective 仍 COOLING：transition graph 中 COOLING 只能经 HEATING(≥25) 回暖，24.93 差 0.07 未到阈值。这是 v1 保守规则（不因单次 EMERGING 跳出 COOLING）的预期结果，非 bug。留待样本 15-20 日后观察是否需加 COOLING→EMERGING 边。"
- **A3_daily_top_theme_momentum_explainable**: {"by_date": {"2026-08-14": {"top_theme": "TECH_AI_COMPUTE", "top_heat": 36.61, "top_level": "COOL", "top_status": "VALID", "momentum_eff": null, "momentum_obs": "UNCLASSIFIED_BASELINE"}, "2026-08-16": {"top_theme": "TECH_SEMI", "top_heat": 67.71, "top_level": "HEATING", "top_status": "LOW_SIGNAL", "

**Phase 2 Overall = `GO`**
