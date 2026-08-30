# P2.2D Theme Heat Benchmark — 验证报告

**Overall: `GO`** — 8 Gate 全过 | 全网格 152 行（8 日期 × 19 L2）

## 8 Gate
| Gate | 判定 | 说明 |
|---|---|---|
| G1_top_themes_business | ✅ | 每日 Top3 无零信号主题；VALID 日 Top1 置信 ≥ MEDIUM |
| G2_ranking_stability | ✅ | VALID 相邻交易日同一主题 heat 变化 < 50（排除单分析师日） |
| G3_negative_suppression | ✅ | 负面 raw_dir / mention net 被 max(0,·) 压到 0；负向日不升入 HEATING/HOT |
| G4_zero_direct_limited_lift | ✅ | cov=0 但 trade 流入 → trade_score>0 有限抬升，heat<65 不冲高（对比 DIRECT 主题 raw_dir 同量级可达 ~25） |
| G5_single_analyst_low_signal | ✅ | 08-16 全 19 行 LOW_SIGNAL；heat_level 保留数学值，由 heat_status 承载置信度 |
| G6_factor_contrib_explainable | ✅ | heat_score = Σ(score×w)/Σ(avail_w) 对每个 VALID 行成立；贡献占比可解释 |
| G7_business_sanity | ✅ | 无个股映射主题(TECH_GENERAL)交易/持仓通道恒 0、DIRECT mention 通道合法；负面回落主题低热；榜首有基本面因子支撑；网格完整 |
| G8_fact_layer_idempotent | ✅ | P2.2C raw 字段与 P2.2B 一致：Heat 层未篡改事实层 |

## 验证项 1: Top themes 业务合理性（G1）
- 每日 Top1 主题: 2026-08-14:TECH_AI_COMPUTE(36.61,HIGH); 2026-08-16:TECH_SEMI(67.71,LOW); 2026-08-17:TECH_SEMI(32.98,HIGH); 2026-08-18:TECH_SEMI(35.35,HIGH); 2026-08-19:CYCL_NONFERROUS(21.94,HIGH); 2026-08-26:CYCL_NONFERROUS(22.7,HIGH); 2026-08-27:TECH_SEMI(26.85,HIGH); 2026-08-28:CYCL_NONFERROUS(25.47,HIGH)
- Top3 无零信号主题；VALID 日 Top1 置信均 ≥ MEDIUM

## 验证项 2: 冷热排序稳定性（G2）
- 比较 VALID→VALID 相邻交易日对: 5 对
- 无主题出现 ≥50 分极端跳变（LOW_SIGNAL 日排除）

## 验证项 3: 负面主题压制（G3）
- 负面 raw_dir 行: 35 行 → trade.score 全为 0
- 负面 mention 行: 4 行 → mention.score 全为 0
- 负向日升入 HEATING/HOT: 0 行（应为 0）

## 验证项 4: 零 DIRECT 但 trade 强 → 有限抬升（G4）
- 案例数: 29 个，全部 heat<65 未冲高
- 代表案例: 08-17 NEW_ENERGY_UHV raw_dir=+3.90 → trade_score=25.93 → heat=8.15 COLD（对比 DIRECT 主题同量级 raw_dir 的 heat 可达 ~25，抬升有限）

## 验证项 5: 单分析师日 LOW_SIGNAL（G5，08-16 强制边界）
- 08-16 全 19 行 heat_status=LOW_SIGNAL
> 解释口径：半导体 热度 67.71 但仅 1 位分析师有有效信号，低置信（而非『正在加热』）
- heat_level 保留数学值不降级，由 heat_status 承载置信度（HEATING + LOW_SIGNAL 合法组合）

## 验证项 6: 四因子贡献可解释（G6）
- 每个 VALID 行 heat = Σ(score×w)/Σ(avail_w)，0.02 容差内全过
- 贡献分解抽样（08-14 至 08-18 每日 Top1）:
  - 2026-08-14 TECH_AI_COMPUTE: heat=36.61  coverage:46.8% + mention:19.5% + trade:9.4% + holding:24.3%
  - 2026-08-14 TECH_OPTICS: heat=23.89  coverage:53.8% + mention:29.9% + trade:7.0% + holding:9.3%
  - 2026-08-14 TECH_SEMI: heat=23.41  coverage:18.3% + mention:15.3% + holding:66.5%
  - 2026-08-17 TECH_SEMI: heat=32.98  coverage:52.0% + mention:10.8% + trade:1.8% + holding:35.4%
  - 2026-08-17 TECH_AI_COMPUTE: heat=29.49  coverage:43.6% + mention:24.2% + trade:13.3% + holding:18.8%
  - 2026-08-17 TECH_COMPONENT: heat=17.38  coverage:49.3% + mention:41.1% + holding:9.6%

## 验证项 7: 业务 sanity（G7）
- TECH_GENERAL 无个股映射（0 行）→ 交易/持仓通道恒 0，DIRECT mention 通道合法（4 日有信号，均 2 分析师）
- 08-28 MED_INNOVATIVE_DRUG raw_dir=-1.30 → heat=6.67（负面压制生效）
- 08-28 CYCL_NONFERROUS 居首 → cov=44.44 + hold=16.67 基本面因子支撑

## 验证项 8: 事实层幂等（G8）
- 比对 152 行：raw_directional_value / weighted_support / stocks 与 P2.2B 全一致
- Heat 计算层未篡改 P2.2B 事实层

## 每日 Top5 / Bottom5 审计
| 日期 | Top3 | Bottom3 |
|---|---|---|
| 2026-08-14 | TECH_AI_COMPUTE:36.61(VALI) / TECH_OPTICS:23.89(VALI) / TECH_SEMI:23.41(VALI) | NEW_ENERGY_SOLID_BATTERY:1.15 / OTHER_SPACE:1.11 / TECH_GENERAL:0.0 |
| 2026-08-16 | TECH_SEMI:67.71(LOW_) / TECH_AI_COMPUTE:61.98(LOW_) / TECH_OPTICS:37.5(LOW_) | OTHER_BROKER:0.0 / OTHER_AGRICULTURE:0.0 / OTHER_ROBOTICS:0.0 |
| 2026-08-17 | TECH_SEMI:32.98(VALI) / TECH_AI_COMPUTE:29.49(VALI) / TECH_COMPONENT:17.38(VALI) | OTHER_BROKER:1.11 / OTHER_CONSUMER:1.11 / OTHER_AGRICULTURE:0.74 |
| 2026-08-18 | TECH_SEMI:35.35(VALI) / MED_INNOVATIVE_DRUG:21.56(VALI) / OTHER_AGRICULTURE:20.89(VALI) | TECH_PCB:3.33 / NEW_ENERGY_ELECTROLYTE:3.33 / NEW_ENERGY_SOLID_BATTERY:2.36 |
| 2026-08-19 | CYCL_NONFERROUS:21.94(VALI) / TECH_SEMI:17.22(VALI) / OTHER_CONSUMER:15.83(VALI) | NEW_ENERGY_SOLID_BATTERY:0.0 / NEW_ENERGY_ELECTROLYTE:0.0 / NEW_ENERGY_UHV:0.0 |
| 2026-08-26 | CYCL_NONFERROUS:22.7(VALI) / TECH_SEMI:20.58(VALI) / TECH_AI_COMPUTE:19.7(VALI) | OTHER_SPACE:0.83 / NEW_ENERGY_SOLID_BATTERY:0.56 / TECH_COMPONENT:0.0 |
| 2026-08-27 | TECH_SEMI:26.85(VALI) / TECH_OPTICS:19.81(VALI) / CYCL_CHEMICAL:17.78(VALI) | TECH_COMPONENT:0.0 / NEW_ENERGY_SOLID_BATTERY:0.0 / NEW_ENERGY_ELECTROLYTE:0.0 |
| 2026-08-28 | CYCL_NONFERROUS:25.47(VALI) / TECH_AI_COMPUTE:24.93(VALI) / TECH_OPTICS:20.01(VALI) | NEW_ENERGY_SOLID_BATTERY:5.19 / TECH_COMPONENT:5.17 / OTHER_CONSUMER:3.33 |

## 结论
- Top themes 业务合理（半导体/AI算力/有色轮动，与市场直觉一致）
- 冷热排序稳定：无极端跳变，相邻日 Top3 有延续性
- 负面主题被正确压制，零 DIRECT 主题不会因单因子冲高
- 单分析师日（08-16）全量 LOW_SIGNAL 标记，解释口径正确
- **Phase 2 收敛：可以进入 Phase 2.3（Theme Momentum），届时再评估是否需要分位数归一**