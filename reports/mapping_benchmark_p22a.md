# P2.2A Stock→Theme Mapping — Benchmark 报告

**Overall: `GO`** | 同花顺概念为主/行业为辅 | DIRECT_CONTEXT 同句语义 | Top3 治理 | 19 canonical L2

## Coverage
- eligible 股票: 350 | 参与 Heat: **333** = 95.1%
- 行数: 全量 1088 / Heat 参与 838
- 按来源: 全量 {'MASTER_INDUSTRY': 177, 'MASTER_CONCEPT': 880, 'DIRECT_CONTEXT': 31}
- 按来源 Heat: {'MASTER_INDUSTRY': 177, 'MASTER_CONCEPT': 630, 'DIRECT_CONTEXT': 31}
- **Unmapped 17 只**: 000802, 002192, 002258, 002487, 002532, 002674, 300191, 300314, 300615, 600272, 600613, 600888, 601288, 601777, 601988, 603063, 603268

## Precision（抽样人工审阅）
- 板块→L2 规则: 100.0% (20 样本) 错配 无
- DIRECT_CONTEXT: 90.0% (20 样本) 弱绑 ['603259|OTHER_CONSUMER', '600428|OTHER_CONSUMER']
  - 强绑定(股票名⊃主题词)=0.62 / 邻接(≤3字)=0.60 / 同 record 共现不落表
  - 已知弱绑: '白马'为风格词歧义（药明康德/中远海特←OTHER_CONSUMER），非消费主题 → 保留但标注

## Conflict / Top3 治理
- 每股主题数分布: {1: 95, 2: 131, 3: 107} | max=3 | Top3 强制: ✅
- 跨≥3 大类股票: 16（潜在噪音，供 P2.2B 审计）

## 保护审计
- invalid source: 0 | invalid confidence: 0
- TECH_GENERAL 映射个股: 0（必须 0）| invalid theme_id: 0
- DIRECT/INFERRED 分离 ✅（本阶段全 DIRECT，INFERRED_FROM_STOCK 留消费层）| COMPOSITE_TACTICAL 不进主题方向（P2.2B）

## 主题覆盖（Heat 层股票数）
| theme | 股票数 |
|---|---|
| TECH_SEMI | 182 |
| TECH_AI_COMPUTE | 139 |
| TECH_ELEC | 62 |
| CYCL_NONFERROUS | 58 |
| TECH_SOFTWARE | 56 |
| CYCL_CHEMICAL | 52 |
| OTHER_ROBOTICS | 52 |
| NEW_ENERGY_UHV | 37 |
| TECH_PCB | 35 |
| MED_INNOVATIVE_DRUG | 28 |
| OTHER_CONSUMER | 24 |
| OTHER_BROKER | 23 |
| TECH_OPTICS | 22 |
| OTHER_SPACE | 21 |
| NEW_ENERGY_SOLID_BATTERY | 19 |
| OTHER_AGRICULTURE | 17 |
| TECH_COMPONENT | 11 |

## 结论
**GO**