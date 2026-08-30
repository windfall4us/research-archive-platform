# P4.3 Cross-Layer State — 个股×主题联动状态机

日期：2026-08-30　数据源：P4.1 linkage + P4.2 divergence + P2.3 momentum + P3.3 consensus

## 6 状态（用户锁定）
| 状态 | 判定（v1） |
| --- | --- |
| DISCOVERY | 主题刚开始升温（HEATING/EMERGING/DISCOVERY）但个股未跟上（S∈{0,−1}） |
| CONFIRMING | 个股主题同向但分歧≥0.5 或仅 THEME_CONFIRMED_STOCK |
| CONFIRMED | 三维共振（个股+主题+动作同向）+ 分歧<0.5 |
| DIVERGING | 个股与主题方向相反（S·T<0） |
| WEAKENING | 主题退潮（COOLING/FADING）但个股残留/中性 |
| REVERSING | 曾看多但持仓/观点操作转负，且主题未升温支撑 |

## 状态分布
{"NEUTRAL": 143, "WEAKENING": 87, "CONFIRMED": 19, "DISCOVERY": 27, "DIVERGING": 45, "UNMAPPED": 13, "REVERSING": 13, "CONFIRMING": 3}

## linkage → state 映射
{
 "CONFIRMED_BULLISH": {
  "CONFIRMED": 14
 },
 "STOCK_THEME_DIVERGENCE": {
  "DIVERGING": 45,
  "REVERSING": 9
 },
 "CONFIRMED_BEARISH": {
  "CONFIRMED": 5,
  "CONFIRMING": 1
 },
 "THEME_CONFIRMED_STOCK": {
  "CONFIRMING": 2
 },
 "NEUTRAL": {
  "NEUTRAL": 143,
  "WEAKENING": 87,
  "DISCOVERY": 27,
  "REVERSING": 4
 },
 "UNMAPPED": {
  "UNMAPPED": 13
 }
}

## 样本
### CONFIRMED（19）
| 股票 | state | 主题 | theme_mom | consensus | div | notes |
| --- | --- | --- | --- | --- | --- | --- |
| 603118 | CONFIRMED | TECH_SEMI | COOLING | NEGATIVE | 0.375 | bearish_resonance_low_divergence |
| 300139 | CONFIRMED | CYCL_NONFERROUS | HEATING | POSITIVE | 0.25 | bullish_resonance_low_divergence |
| 300618 | CONFIRMED | CYCL_NONFERROUS | HEATING | POSITIVE | 0.25 | bullish_resonance_low_divergence |
| 000426 | CONFIRMED | CYCL_NONFERROUS | HEATING | POSITIVE | 0.125 | bullish_resonance_low_divergence |
| 000506 | CONFIRMED | CYCL_NONFERROUS | HEATING | STRONG_POSITIVE | 0.125 | bullish_resonance_low_divergence |
| 002155 | CONFIRMED | CYCL_NONFERROUS | HEATING | POSITIVE | 0.125 | bullish_resonance_low_divergence |
| 002203 | CONFIRMED | CYCL_NONFERROUS | HEATING | POSITIVE | 0.125 | bullish_resonance_low_divergence |
| 002428 | CONFIRMED | CYCL_NONFERROUS | HEATING | POSITIVE | 0.125 | bullish_resonance_low_divergence |

### REVERSING（13）
| 股票 | state | 主题 | theme_mom | consensus | div | notes |
| --- | --- | --- | --- | --- | --- | --- |
| 688432 | REVERSING | TECH_SEMI | COOLING | STRONG_POSITIVE | 0.875 | positive_but_holding_or_view_turning_negative |
| 301205 | REVERSING | TECH_SEMI | COOLING | POSITIVE | 0.75 | positive_but_holding_or_view_turning_negative |
| 601869 | REVERSING | TECH_AI_COMPUTE | COOLING | POSITIVE | 0.6667 | positive_but_holding_or_view_turning_negative |
| 600103 | REVERSING | TECH_AI_COMPUTE | COOLING | STRONG_POSITIVE | 0.625 | positive_but_holding_or_view_turning_negative |
| 002015 | REVERSING | TECH_AI_COMPUTE | COOLING | POSITIVE | 0.5 | positive_but_holding_or_view_turning_negative |
| 300607 | REVERSING | OTHER_ROBOTICS | None | POSITIVE | 0.5 | positive_but_holding_or_view_turning_negative |
| 600460 | REVERSING | TECH_SEMI | COOLING | POSITIVE | 0.5 | positive_but_holding_or_view_turning_negative |
| 600522 | REVERSING | TECH_AI_COMPUTE | COOLING | STRONG_POSITIVE | 0.5 | positive_but_holding_or_view_turning_negative |

### DISCOVERY（27）
| 股票 | state | 主题 | theme_mom | consensus | div | notes |
| --- | --- | --- | --- | --- | --- | --- |
| 301217 | DISCOVERY | CYCL_NONFERROUS | HEATING | NEUTRAL | 0.625 | theme_rising_stock_not_yet |
| 603259 | DISCOVERY | MED_INNOVATIVE_DRUG | EMERGING | NEUTRAL | 0.625 | theme_rising_stock_not_yet |
| 002266 | DISCOVERY | CYCL_NONFERROUS | HEATING | NEUTRAL | 0.25 | theme_rising_stock_not_yet |
| 301026 | DISCOVERY | CYCL_NONFERROUS | HEATING | NEUTRAL | 0.25 | theme_rising_stock_not_yet |
| 600362 | DISCOVERY | CYCL_NONFERROUS | HEATING | NEUTRAL | 0.25 | theme_rising_stock_not_yet |
| 600711 | DISCOVERY | CYCL_NONFERROUS | HEATING | NEUTRAL | 0.25 | theme_rising_stock_not_yet |
| 601899 | DISCOVERY | CYCL_NONFERROUS | HEATING | NEUTRAL | 0.25 | theme_rising_stock_not_yet |
| 603087 | DISCOVERY | MED_INNOVATIVE_DRUG | EMERGING | NEUTRAL | 0.25 | theme_rising_stock_not_yet |

## 说明
当前为**横截面状态**（8 天样本，个股观测稀疏）；时间序列转移状态机（如 DISCOVERY→CONFIRMING→CONFIRMED 的跨日转移）待样本 15-20 日后升级 v2。
