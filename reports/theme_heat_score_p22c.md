# P2.2C Theme Heat Score — 计算报告（v2，含信号治理层）

**Overall: `GO`** | 9-Gate 全过 | 全网格 152 行（8 日期 × 19 L2）

## 9 Gate
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
| G9_signal_governance | ✅ | signal_confidence 阈值一致性 + heat_status 优先级 + 08-16 强制边界样本 + 治理层不覆盖 heat_level |

## 信号治理层（P2.2C v2 新增）

### 设计原则：不改公式、不改权重、不重算四因子
- **theme_signal_analysts** = DIRECT mention ∪ TRADE ∪ HOLDING 的 unique analysts
- **signal_confidence**: ≥4 HIGH / 2~3 MEDIUM / 1 LOW / 0 NONE
- **heat_status**: completeness<0.60 → INSUFFICIENT_DATA; signal_analysts<2 → LOW_SIGNAL; 其余 VALID
- **heat_level 与 heat_status 正交**：HEATING + LOW_SIGNAL 是合法组合（例: 08-16 TECH_SEMI 67.7 HEATING 但仅 1 人信号）

## 治理层全局分布
- heat_status: {'VALID': 114, 'LOW_SIGNAL': 38}
- signal_confidence: {'HIGH': 77, 'MEDIUM': 37, 'NONE': 21, 'LOW': 17}
- VALID 行中 LOW/NONE 置信 = 0（无误伤）

## 08-16 强制边界样本（P2.2D 复测基准）
- 当日仅 laofan 1 位分析师有数据，position snapshot 源缺失
- 8 个主题 sig_analysts=1 → LOW_SIGNAL / LOW；11 个主题 sig=0 → LOW_SIGNAL / NONE
- **解释口径**：不应显示「半导体正在加热」，应显示「半导体热度 67.7，但仅 1 位分析师有有效信号，低置信」

## Missing≠Zero 验证（P1.3 契约）
- **2026-08-16** 当日 position snapshot 源缺失 → holding.available=false, holding.score=null
- heat 分母从 1.0 降为 0.80，在 coverage+mention+trade 三因子间重新归一
- 避免把「未采集到持仓」误解释为「主题突然降温」

## 2026-08-28 排序
| 主题 | Heat | 档位 | 状态 | 置信 | sig | cov | men | trd | hold |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| CYCL_NONFERROUS | 25.47 | COOL | VALID | HIGH | 8 | 44.44 | 22.22 | 13.0 | 16.67 |
| TECH_AI_COMPUTE | 24.93 | COLD | VALID | HIGH | 10 | 33.33 | 11.11 | 30.83 | 22.22 |
| TECH_OPTICS | 20.01 | COLD | VALID | HIGH | 7 | 44.44 | 11.11 | 11.17 | 5.56 |
| CYCL_CHEMICAL | 18.26 | COLD | VALID | HIGH | 7 | 33.33 | 11.11 | 10.83 | 13.89 |
| TECH_SEMI | 11.11 | COLD | VALID | HIGH | 9 | 22.22 | 0.0 | 0.0 | 22.22 |
| OTHER_AGRICULTURE | 10.15 | COLD | VALID | HIGH | 6 | 22.22 | 11.11 | 2.83 | 0.0 |
| TECH_ELEC | 9.11 | COLD | VALID | HIGH | 9 | 11.11 | 0.0 | 12.0 | 13.89 |
| TECH_PCB | 8.53 | COLD | VALID | HIGH | 7 | 11.11 | 0.0 | 9.67 | 13.89 |
| OTHER_ROBOTICS | 8.33 | COLD | VALID | HIGH | 8 | 11.11 | 11.11 | 0.0 | 11.11 |
| TECH_SOFTWARE | 7.5 | COLD | VALID | HIGH | 5 | 11.11 | 0.0 | 10.0 | 8.33 |
| OTHER_SPACE | 7.44 | COLD | VALID | HIGH | 7 | 11.11 | 0.0 | 5.33 | 13.89 |
| MED_INNOVATIVE_DRUG | 6.67 | COLD | VALID | HIGH | 6 | 22.22 | 0.0 | 0.0 | 0.0 |
| OTHER_BROKER | 6.67 | COLD | VALID | HIGH | 4 | 11.11 | 0.0 | 13.33 | 0.0 |
| NEW_ENERGY_UHV | 6.15 | COLD | VALID | HIGH | 7 | 0.0 | 0.0 | 13.5 | 13.89 |
| NEW_ENERGY_SOLID_BATTERY | 5.19 | COLD | VALID | MEDIUM | 3 | 0.0 | 0.0 | 16.33 | 5.56 |
| TECH_COMPONENT | 5.17 | COLD | VALID | MEDIUM | 2 | 11.11 | 0.0 | 7.33 | 0.0 |
| OTHER_CONSUMER | 3.33 | COLD | VALID | HIGH | 6 | 11.11 | 0.0 | 0.0 | 0.0 |
| TECH_GENERAL | 0.0 | COLD | LOW_SIGNAL | NONE | 0 | 0.0 | 0.0 | 0.0 | 0.0 |
| NEW_ENERGY_ELECTROLYTE | 0.0 | COLD | LOW_SIGNAL | NONE | 0 | 0.0 | 0.0 | 0.0 | 0.0 |

## 分数偏低说明（用户裁决：不调公式）
- 10 位分析师 / 8 交易日 / DIRECT mentions 克制 / 高置信映射 / analyst cap 抑制高频
- COLD 141 / COOL 9 / ACTIVE 1 / HEATING 1 是 Precision-first 的预期分布
- P2.2D 先验证业务合理性，再决定 Phase 2.3 是否需要分位数 Momentum