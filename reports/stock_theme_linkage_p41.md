# P4.1 Stock × Theme Linkage — 个股×主题联动信号

日期：2026-08-30　数据源：P2.2C heat + P2.3 momentum + P3.2 action flow + P3.3 consensus

## 三维信号（主主题 = confidence 最高映射）
- **S stock_direction**：+1(POSITIVE/STRONG_POSITIVE) / 0(NEUTRAL) / −1(NEGATIVE/STRONG_NEGATIVE)
- **T theme_direction**：+1(momentum_eff∈{HEATING,EMERGING}) / 0(STABLE/DISCOVERY/BASELINE) / −1(COOLING/FADING)
- **A action_net_recent**：每股最近 3 事件动作加权（BUY/ADD/LOW_BUY/TRIAL=+，REDUCE/SELL/CLEAR=−）

## 联动标签分布
{"NEUTRAL": 261, "CONFIRMED_BULLISH": 14, "STOCK_THEME_DIVERGENCE": 54, "UNMAPPED": 13, "THEME_CONFIRMED_STOCK": 2, "CONFIRMED_BEARISH": 6}

## 规则（v1）
| 信号 | 规则 |
| --- | --- |
| CONFIRMED_BULLISH | S+1 & T+1 & A+1（三维共振看多） |
| CONFIRMED_BEARISH | S−1 & T−1 & A−1（三维共振看空） |
| STOCK_THEME_DIVERGENCE | 个股与主题方向矛盾（S+1T−1 或 S−1T+1） |
| LAGGING_OR_DISTRIBUTION | 主题升温但个股动作转负（T+1 & A−1） |
| THEME_CONFIRMED_STOCK | 个股主题一致看多，动作中性（S+1 & T+1 & A0） |
| NEUTRAL | 其他组合 |
| UNMAPPED | 无主题映射（13 只） |

## 样本
### CONFIRMED_BULLISH（14）
| 股票 | state | raw | 主题 | theme_heat | theme_mom | 近3动作 | A |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 000506 | STRONG_POSITIVE | 3.7 | CYCL_NONFERROUS | 51.52 | HEATING | HOLD→ADD→WATCH | 1 |
| 002532 | STRONG_POSITIVE | 2.9 | CYCL_NONFERROUS | 51.52 | HEATING | ADD→HOLD→HOLD | 1 |
| 300139 | POSITIVE | 2.1 | CYCL_NONFERROUS | 51.52 | HEATING | HOLD→ADD→ADD | 1 |
| 601168 | POSITIVE | 1.4 | CYCL_NONFERROUS | 51.52 | HEATING | REDUCE→ADD→ADD | 1 |
| 603799 | POSITIVE | 1.4 | CYCL_NONFERROUS | 51.52 | HEATING | TRIAL→BUY | 1 |
| 002428 | POSITIVE | 1.2 | CYCL_NONFERROUS | 51.52 | HEATING | HOLD→LOW_BUY | 1 |

### STOCK_THEME_DIVERGENCE（54）
| 股票 | state | raw | 主题 | theme_heat | theme_mom | 近3动作 | A |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 688008 | STRONG_POSITIVE | 3.5 | TECH_SEMI | 18.18 | COOLING | ADD→ADD→ADD | 1 |
| 688041 | STRONG_POSITIVE | 3.3 | TECH_SEMI | 18.18 | COOLING | ADD→WATCH→WATCH | 1 |
| 603296 | STRONG_POSITIVE | 3.2 | TECH_AI_COMPUTE | 18.18 | COOLING | WATCH→BUY→WATCH | 1 |
| 688432 | STRONG_POSITIVE | 3.1 | TECH_SEMI | 18.18 | COOLING | LOW_BUY→HOLD→SELL | 0 |
| 600522 | STRONG_POSITIVE | 2.7 | TECH_AI_COMPUTE | 18.18 | COOLING | ADD→WATCH→ADD | 1 |
| 920045 | STRONG_POSITIVE | 2.7 | TECH_AI_COMPUTE | 18.18 | COOLING | HOLD→LOW_BUY→ADD | 1 |

### LAGGING_OR_DISTRIBUTION（0）
| 股票 | state | raw | 主题 | theme_heat | theme_mom | 近3动作 | A |
| --- | --- | --- | --- | --- | --- | --- | --- |

