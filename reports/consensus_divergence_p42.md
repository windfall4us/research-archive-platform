# P4.2 Consensus / Divergence — 量化分歧指标

日期：2026-08-30　数据源：P3.3 consensus + P4.1 linkage + P3.2 action flow + events(action_status)

## 5 项重点识别（用户锁定）
| 指标 | 定义 | 命中 |
| --- | --- | --- |
| consensus_strength | 同向率 × min(1, 分析师数/3)（0~1，防单分析师虚高） | — |
| analyst_divergence | min(pos,neg)/max(pos,neg)（正负两派） | 分裂(≥0.5) **29** 只 |
| theme_stock_divergence | ｜S−T｜/2（主题与个股方向差） | 完全反向 **54** 只 |
| view_action_divergence | INTENDED vs EXECUTED 异号（观点≠操作） | 异号 **37** 只 |
| holding_action_divergence | 持仓仍在但最近3动作转负 | **18** 只 |

- 多分析师同向（≥2 且 div=0）：**57** 只
- 多分析师（≥3）：**27** 只
- 高综合分歧（divergence_score≥0.5）：**37** 只

## 高综合分歧 Top（divergence_score）
| 股票 | state | div_score | analyst_div | theme_stock | view_action | holding | strength |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 300620 | NEUTRAL | 0.875 | 1.0 | 0.5 | 1.0 | 1.0 | 0.3333 |
| 301396 | NEUTRAL | 0.875 | 1.0 | 0.5 | 1.0 | 1.0 | 0.6667 |
| 688432 | STRONG_POSITIVE | 0.875 | 1.0 | 1.0 | 0.5 | 1.0 | 0.3333 |
| 000762 | NEGATIVE | 0.75 | 0.0 | 1.0 | 1.0 | 1.0 | 0.3333 |
| 301205 | POSITIVE | 0.75 | 1.0 | 1.0 | 1.0 | 0.0 | 0.3333 |
| 600206 | NEUTRAL | 0.75 | 0.5 | 0.5 | 1.0 | 1.0 | 0.6667 |
| 688521 | POSITIVE | 0.75 | 1.0 | 1.0 | 0.5 | 0.5 | 0.25 |
| 601869 | POSITIVE | 0.6667 | 0.6667 | 1.0 | 1.0 | 0.0 | 0.75 |

## 持仓转负（holding_action_divergence=1）
| 股票 | state | 近3动作 | has_holding |
| --- | --- | --- | --- |
| 301396 | NEUTRAL | REDUCE→BUY→CLEAR | True |
| 600206 | NEUTRAL | LOW_BUY→HOLD→SELL | True |
| 603118 | NEGATIVE | SELL→REDUCE→WATCH | True |
| 000592 | NEGATIVE | HOLD→REDUCE→WATCH | True |
| 000762 | NEGATIVE | REDUCE→HOLD→WATCH | True |
| 000831 | NEGATIVE | WATCH→HOLD→REDUCE | True |
| 002156 | NEGATIVE | WATCH→WATCH→REDUCE | True |
| 002493 | NEGATIVE | HOLD→REDUCE | True |
