# P4.0 Cross-Layer Readiness — 个股×主题联动盘点

日期：2026-08-30　连接键：stock_theme_mapping（conf>=0.60 heat 映射）

## 主题层（Phase 2）
- 8 个交易日 × 19 个主题（heat+momentum 均有）= 152 行
- 日期：2026-08-14 ~ 2026-08-28

## 个股层（Phase 3）
- eligible 股票：350（全有 consensus）

## 映射
- 有 heat 映射：**337/350**（96.29%）
- 无映射：13 只 → ['000802', '002487', '002674', '300191', '300314', '300615', '600272', '600613', '601288', '601777', '601988', '603063', '603268']
- 映射涉及主题数：17；canonical 19 中缺（无股票映射）：['NEW_ENERGY_ELECTROLYTE', 'TECH_GENERAL']
- 映射源分布：{"MASTER_CONCEPT": 503, "MASTER_INDUSTRY": 168, "MANUAL": 4, "DIRECT_CONTEXT": 7}

## 跨层可连接性
| 指标 | 值 |
| --- | --- |
| 有主题链接的股票 | 337 |
| 链接主题有 heat 的股票 | 337 |
| 链接主题有 momentum 的股票 | 337 |
| 每股主题数分布 | {"0": 13, "1": 99, "2": 131, "3": 107} |

## 每主题覆盖（eligible 股票 consensus state 分布）
| 主题 | 映射股票数 | eligible 数 | consensus 分布 |
| --- | --- | --- | --- |
| CYCL_CHEMICAL | 43 | 43 | {"NEUTRAL": 28, "NEGATIVE": 5, "POSITIVE": 10} |
| CYCL_NONFERROUS | 43 | 43 | {"NEUTRAL": 23, "POSITIVE": 14, "STRONG_POSITIVE": 2, "NEGATIVE": 4} |
| MED_INNOVATIVE_DRUG | 21 | 21 | {"NEGATIVE": 8, "NEUTRAL": 11, "POSITIVE": 2} |
| NEW_ENERGY_ELECTROLYTE | 0 | 0 | {} |
| NEW_ENERGY_SOLID_BATTERY | 19 | 19 | {"NEUTRAL": 11, "POSITIVE": 6, "NEGATIVE": 2} |
| NEW_ENERGY_UHV | 27 | 27 | {"NEUTRAL": 13, "POSITIVE": 11, "NEGATIVE": 2, "STRONG_POSITIVE": 1} |
| OTHER_AGRICULTURE | 12 | 12 | {"NEUTRAL": 7, "NEGATIVE": 3, "POSITIVE": 2} |
| OTHER_BROKER | 18 | 18 | {"NEUTRAL": 12, "POSITIVE": 4, "NEGATIVE": 2} |
| OTHER_CONSUMER | 20 | 20 | {"NEUTRAL": 15, "NEGATIVE": 3, "POSITIVE": 2} |
| OTHER_ROBOTICS | 44 | 44 | {"NEGATIVE": 6, "NEUTRAL": 29, "POSITIVE": 9} |
| OTHER_SPACE | 21 | 21 | {"NEUTRAL": 14, "POSITIVE": 3, "NEGATIVE": 4} |
| TECH_AI_COMPUTE | 134 | 134 | {"NEUTRAL": 78, "POSITIVE": 33, "NEGATIVE": 17, "STRONG_POSITIVE": 6} |
| TECH_COMPONENT | 8 | 8 | {"POSITIVE": 2, "NEUTRAL": 5, "NEGATIVE": 1} |
| TECH_ELEC | 57 | 57 | {"NEUTRAL": 37, "NEGATIVE": 7, "POSITIVE": 12, "STRONG_POSITIVE": 1} |
| TECH_GENERAL | 0 | 0 | {} |
| TECH_OPTICS | 19 | 19 | {"NEUTRAL": 8, "POSITIVE": 7, "STRONG_POSITIVE": 3, "NEGATIVE": 1} |
| TECH_PCB | 25 | 25 | {"NEUTRAL": 15, "POSITIVE": 7, "NEGATIVE": 3} |
| TECH_SEMI | 122 | 122 | {"NEGATIVE": 22, "NEUTRAL": 71, "POSITIVE": 26, "STRONG_POSITIVE": 3} |
| TECH_SOFTWARE | 49 | 49 | {"NEUTRAL": 30, "NEGATIVE": 10, "POSITIVE": 9} |

## P4.0 结论
- 跨层连接可用：337/350 股票可经主题链接到 heat+momentum（覆盖率 96.29%）
- 空白：13 只无映射（P2.2A 保留 unmapped 的决策维持）；['NEW_ENERGY_ELECTROLYTE', 'TECH_GENERAL'] canonical L2 无股票映射（TECH_GENERAL 等无个股映射主题，靠 DIRECT mention 舆情通道）
