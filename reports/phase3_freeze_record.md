# Phase 3 Freeze Record

> 收口记录 — 只**固化** Phase 3 的版本/结论/已知边界，**不修改任何算法**。
> 日期：2026-08-30　范围：P3.0 → P3.4

## 1. 最终状态

```
Phase 3 — Stock Consensus + Analyst Action Flow
Overall = GO（10/10 硬 Gate PASS）
```

## 2. 关键版本 / Commit

| 子阶段 | 提交 | 内容 |
| --- | --- | --- |
| P3.0 Readiness | `e8b5e30` | 934 eligible events / 350 股 / 10 分析师 / 8 交易日；124 持仓 / 79 股；定义分层分母 350 |
| P3.1 Factors | `ddfa958` | 个股四类事实（Attention/Positive/Negative/Holding Support）GO 8/8 |
| P3.2 Action Flow | `95a92ec` | 474 分析师×股票动作流 + stage 生命周期 GO 8/8 |
| P3.3 Score/State | `4beb36c` | consensus_raw + strength + divergence + 5 档 State GO 8/8 |
| P3.4 Benchmark | `00a9911` | Phase 3 总 Benchmark 10/10 GO — Phase 3 冻结 |

## 3. 冻结规则（不得改动）

- **分层分母**：主分母 = 350 eligible 股票；S1 强证据（双证据&事件日≥3）=56 / S2 中（事件日≥2）=163 / S3 弱（单日单分析师）=187
- **方向判定**：以 action_type 语义为准（P2.2B ACTION_WEIGHT）；WATCH/HOLD/DO_T/UNKNOWN 不进正负；WATCH stance 单列软信号；direction 字段仅审计
- **P3.2 语义契约**：DO_T ≠ 净买入（tactical 活动单独计）；WATCH ≠ BUY（stage=SCAN）；HOLD ≠ 新建仓（持仓状态）
- **P3.3 Score 公式**：`consensus_raw = action_net + holding_net`；action_net = positive_weighted + negative_weighted（P2.2B 权重）；holding_net = unique_holding_analysts × 0.5（软证据半权重）
- **P3.3 State 5 档（固定语义阈值）**：STRONG_POSITIVE（≥+2.0 且 strength∈{STRONG,MEDIUM}）/ STRONG_NEGATIVE（≤−2.0）/ POSITIVE（≥+0.5）/ NEGATIVE（≤−0.5）/ NEUTRAL（其余）
- **consensus_strength**：S1→STRONG / S2→MEDIUM / S3→WEAK / 无观测→NO_DATA
- **divergence** = min(pos_a,neg_a)/max(pos_a,neg_a)，仅 ≥2 分析师可算，单分析师=0（低置信语义）

## 4. 已知边界（记录在案，不作改动）

| 边界 | 描述 | 处置 |
| --- | --- | --- |
| **无 STRONG_NEGATIVE** | 数据最负 action_net 仅 −1.3（需 ≤−2.0 且强度达标）→ 分析师群体整体偏多，无强负共识 | 维持，样本扩大后再观察 |
| **方向冲突 14 条** | 老樊/天赢居的 direction 字段与 action_type 相悖（如 ADD+dir=减仓），计算以 action_type 为准，仅审计 | 维持 |
| **S3 弱证据 187 只** | 单日单分析师事件，只出 consensus_score 低置信，不参与时间序列比较 | 维持 |
| **持仓全部 HOLDING** | 124 持仓 position_state 全为 HOLDING，无增/减/清状态区分（持仓作为软证据，不作方向） | 维持 |

## 5. 冻结判定

```
PASS → Phase 3 = GO，正式冻结
下一阶段：Phase 4 — Cross-Layer Consensus（个股×主题联动 + 分歧状态机）
看板部署：安排在 Phase 4 收口后
```
