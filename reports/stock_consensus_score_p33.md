# P3.3 Stock Consensus Score / State

日期：2026-08-30　数据源：data/p31 + data/p32 同源（eligible events + positions）

## Score 构成（每股，有符号净共识）
- `action_net` = positive_weighted + negative_weighted（P2.2B 动作权重，负为负）
- `holding_net` = unique_holding_analysts × 0.5（持仓软证据，半权重，Missing≠Zero 不补零）
- `consensus_raw` = action_net + holding_net
- `consensus_strength` = S1(双证据&事件日≥3)→STRONG / S2(事件日≥2)→MEDIUM / 其他→WEAK / 无观测→NO_DATA
- `divergence` = min(pos_a,neg_a)/max(pos_a,neg_a)，仅 ≥2 分析师可算，否则 0（单分析师=低置信语义）

## State 判定（固定语义阈值，v1）
| State | 条件 |
| --- | --- |
| STRONG_POSITIVE | action_net ≥ +2.0 且 strength ∈ {STRONG, MEDIUM} |
| STRONG_NEGATIVE | action_net ≤ −2.0 且 strength ∈ {STRONG, MEDIUM} |
| POSITIVE | action_net ≥ +0.5 |
| NEGATIVE | action_net ≤ −0.5 |
| NEUTRAL | 其余（含弱证据正负抵消） |
| NO_DATA | 无任何事件且无持仓 |

## 分布
- 覆盖股票：350
- State 分布：{"NEUTRAL": 203, "NEGATIVE": 56, "POSITIVE": 82, "STRONG_POSITIVE": 9}
- Strength 分布：{"STRONG": 56, "MEDIUM": 107, "WEAK": 187}

## Top 正共识（consensus_raw）
| 股票 | state | action_net | holding_net | raw | strength | divergence | 分析师(+/-) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 000506 | STRONG_POSITIVE | 3.2 | 0.5 | 3.7 | STRONG | 0.0 | 1/0 |
| 688008 | STRONG_POSITIVE | 3.5 | 0.0 | 3.5 | MEDIUM | 0.0 | 1/1 |
| 688041 | STRONG_POSITIVE | 2.3 | 1.0 | 3.3 | STRONG | 0.0 | 2/0 |
| 603296 | STRONG_POSITIVE | 2.7 | 0.5 | 3.2 | STRONG | 0.0 | 2/0 |
| 688432 | STRONG_POSITIVE | 2.1 | 1.0 | 3.1 | STRONG | 1.0 | 1/1 |
| 002532 | STRONG_POSITIVE | 2.4 | 0.5 | 2.9 | STRONG | 0.0 | 1/0 |
| 920045 | STRONG_POSITIVE | 2.2 | 0.5 | 2.7 | STRONG | 0.0 | 1/0 |
| 600522 | STRONG_POSITIVE | 2.7 | 0.0 | 2.7 | MEDIUM | 0.0 | 1/1 |

## Top 负共识（consensus_raw）
| 股票 | state | action_net | holding_net | raw | strength | divergence | 分析师(+/-) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 688530 | NEGATIVE | -1.3 | 0.0 | -1.3 | MEDIUM | 0.0 | 0/1 |
| 688037 | NEGATIVE | -1.3 | 0.0 | -1.3 | MEDIUM | 0.0 | 0/1 |
| 002192 | NEGATIVE | -1.3 | 0.0 | -1.3 | WEAK | 0.0 | 0/1 |
| 688167 | NEGATIVE | -1.3 | 0.0 | -1.3 | MEDIUM | 0.0 | 0/1 |
| 688485 | NEGATIVE | -1.0 | 0.0 | -1.0 | WEAK | 0.0 | 0/1 |
| 002412 | NEGATIVE | -0.8 | 0.0 | -0.8 | WEAK | 0.0 | 0/1 |
| 688729 | NEGATIVE | -1.3 | 0.5 | -0.8 | STRONG | 0.0 | 1/1 |
| 603118 | NEGATIVE | -1.3 | 0.5 | -0.8 | MEDIUM | 0.0 | 0/2 |
