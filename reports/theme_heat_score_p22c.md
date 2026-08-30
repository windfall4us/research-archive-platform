# P2.2C Theme Heat Score — 计算报告

**Overall: `GO`** | 8-Gate 全过 | 全网格 152 行（8 日期 × 19 L2）

## 8 Gate
| Gate | 判定 | 说明 |
|---|---|---|
| G1_score_range | ✅ |  |
| G2_weights | ✅ |  |
| G3_mention_no_dup | ✅ | mention.pos/neg/neu 按 (analyst,theme,day) 聚合后分桶，单分析师不重复计权 |
| G4_trade_analyst_cap | ✅ | 每个 (analyst,theme,day) raw 先 clip(-1,+1) 再聚合；防止高频分析师等价于多分析师共识 |
| G5_holding_analyst_cap | ✅ | 每个 (analyst,theme,day) fractional(1/N) 后 min(1.0)；防止持仓股数竞赛 |
| G6_missing_not_zero | ✅ | Missing≠Zero：数据源缺失 → score=None 且权重从分母剔除（P1.3 契约） |
| G7_manual_recalc | ✅ | 对每个 scored 行独立重算 coverage/mention/trade/holding score 与 heat，容差 0.02 |
| G8_rerun_consistency | ✅ | 重算每个 factor score 与 JSON 比对，验证幂等一致性 |

## 2026-08-28 排序
| 主题 | Heat | 档位 | cov | men | trd | hold |
|---|---:|---|---:|---:|---:|---:|
| CYCL_NONFERROUS | 25.47 | COOL | 44.44 | 22.22 | 13.0 | 16.67 |
| TECH_AI_COMPUTE | 24.93 | COLD | 33.33 | 11.11 | 30.83 | 22.22 |
| TECH_OPTICS | 20.01 | COLD | 44.44 | 11.11 | 11.17 | 5.56 |
| CYCL_CHEMICAL | 18.26 | COLD | 33.33 | 11.11 | 10.83 | 13.89 |
| TECH_SEMI | 11.11 | COLD | 22.22 | 0.0 | 0.0 | 22.22 |
| OTHER_AGRICULTURE | 10.15 | COLD | 22.22 | 11.11 | 2.83 | 0.0 |
| TECH_ELEC | 9.11 | COLD | 11.11 | 0.0 | 12.0 | 13.89 |
| TECH_PCB | 8.53 | COLD | 11.11 | 0.0 | 9.67 | 13.89 |
| OTHER_ROBOTICS | 8.33 | COLD | 11.11 | 11.11 | 0.0 | 11.11 |
| TECH_SOFTWARE | 7.5 | COLD | 11.11 | 0.0 | 10.0 | 8.33 |
| OTHER_SPACE | 7.44 | COLD | 11.11 | 0.0 | 5.33 | 13.89 |
| MED_INNOVATIVE_DRUG | 6.67 | COLD | 22.22 | 0.0 | 0.0 | 0.0 |
| OTHER_BROKER | 6.67 | COLD | 11.11 | 0.0 | 13.33 | 0.0 |
| NEW_ENERGY_UHV | 6.15 | COLD | 0.0 | 0.0 | 13.5 | 13.89 |
| NEW_ENERGY_SOLID_BATTERY | 5.19 | COLD | 0.0 | 0.0 | 16.33 | 5.56 |
| TECH_COMPONENT | 5.17 | COLD | 11.11 | 0.0 | 7.33 | 0.0 |
| OTHER_CONSUMER | 3.33 | COLD | 11.11 | 0.0 | 0.0 | 0.0 |
| TECH_GENERAL | 0.0 | COLD | 0.0 | 0.0 | 0.0 | 0.0 |
| NEW_ENERGY_ELECTROLYTE | 0.0 | COLD | 0.0 | 0.0 | 0.0 | 0.0 |

## 全期 Top5 主题日
- 2026-08-16 TECH_SEMI 67.71 (HEATING)
- 2026-08-16 TECH_AI_COMPUTE 61.98 (ACTIVE)
- 2026-08-16 TECH_OPTICS 37.5 (COOL)
- 2026-08-14 TECH_AI_COMPUTE 36.61 (COOL)
- 2026-08-18 TECH_SEMI 35.35 (COOL)

## 档位与完备度分布
- 档位: {'COLD': 141, 'COOL': 9, 'HEATING': 1, 'ACTIVE': 1}
- 完备度: {'NORMAL': 152}
- 分数区间: [0.0, 67.71]

## 边界案例审计
### 案例1: coverage 高但 trade 低
- TECH_OPTICS: cov=44.44 trd_score=11.17 (raw_dir=1.3667)
- CYCL_NONFERROUS: cov=44.44 trd_score=13.0 (raw_dir=3.7333)
- TECH_AI_COMPUTE: cov=33.33 trd_score=30.83 (raw_dir=6.6833)
- CYCL_CHEMICAL: cov=33.33 trd_score=10.83 (raw_dir=1.4333)
- TECH_SEMI: cov=22.22 trd_score=0.0 (raw_dir=1.0333)
### 案例3: mention 热但无持仓
- OTHER_AGRICULTURE: men=+1 hold_support=0
### 案例4: 持仓多但有负面评价
- TECH_AI_COMPUTE: hold=1.3333(3只) neg=1 pos=2

## Missing≠Zero 验证（P1.3 契约）
- **2026-08-16** 当日 position snapshot 源缺失 → holding.available=false, holding.score=null
- 该日 heat 分母从 1.0 降为 0.8（剔除 holding 的 0.20 权重），在 coverage+mention+trade 三因子间重新归一
- 避免把「未采集到持仓」误解释为「主题突然降温」