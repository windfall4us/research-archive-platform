# Phase 4 Freeze Record

> 收口记录 — 只**固化** Phase 4 的版本/结论/已知边界，**不修改任何算法**。
> 日期：2026-08-30　范围：P4.0 → P4.4

## 1. 最终状态

```
Phase 4 — Cross-Layer Consensus（个股×主题联动 + 分歧状态机）
Overall = GO（10/10 硬 Gate PASS）
```

## 2. 关键版本 / Commit

| 子阶段 | 提交 | 内容 |
| --- | --- | --- |
| P4.0 Readiness | `ba8be37` | 337/350 可连接；每股 distinct 主题 {1:99, 2:131, 3:107}（Top3 治理）；canonical 缺 TECH_GENERAL/NEW_ENERGY_ELECTROLYTE |
| P4.1 Linkage | `c2d2262` | 三维信号 S/T/A → 联动标签 GO 8/8 |
| P4.2 Divergence | `d18c077` | 5 维分歧量化（consensus_strength/analyst/theme_stock/view_action/holding_action）GO 9/9 |
| P4.3 State | `0e9a23f` | 6 状态机（DISCOVERY/CONFIRMING/CONFIRMED/DIVERGING/WEAKENING/REVERSING）GO 10/10 |
| P4.4 Benchmark | `c8959ea` | Phase 4 总 Benchmark 10/10 GO — Phase 4 冻结 |

## 3. 冻结规则（不得改动）

- **连接键**：stock_theme_mapping（conf≥0.60）；同股同主题多 source 行按最高 confidence 去重（Top3 治理按 distinct theme）
- **P4.1 三维信号**：S（个股方向 +1/0/−1，继承 P3.3 state）/ T（主题方向 +1=HEATING·EMERGING / 0=STABLE·DISCOVERY·BASELINE / −1=COOLING·FADING）/ A（最近 3 事件动作加权）
- **P4.1 联动标签 v1**：CONFIRMED_BULLISH（S+1T+1A+1）/ CONFIRMED_BEARISH（S−1T−1A−1）/ STOCK_THEME_DIVERGENCE（S·T<0）/ LAGGING_OR_DISTRIBUTION（T+1A−1）/ THEME_CONFIRMED_STOCK（S+1T+1A0）/ NEUTRAL
- **P4.2 分歧 5 维**：consensus_strength = 同向率 × min(1, n/3)（防单分析师虚高）；analyst_divergence = min(pos,neg)/max(pos,neg)；theme_stock_divergence = |S−T|/2；view_action_divergence = INTENDED vs EXECUTED 异号；holding_action_divergence = 持仓仍在但近 3 动作转负；divergence_score = 4 维均分
- **P4.3 6 状态 v1**（优先级：REVERSING > CONFIRMED > CONFIRMING > DIVERGING > WEAKENING > DISCOVERY > NEUTRAL）：
  - REVERSING：曾看多但持仓转负/观点异号，且主题未升温支撑
  - CONFIRMED：三维共振 + 分歧<0.5
  - CONFIRMING：方向同向但分歧≥0.5 或仅 THEME_CONFIRMED_STOCK
  - DIVERGING：S·T<0
  - WEAKENING：主题退潮但个股残留/中性
  - DISCOVERY：主题升温但个股未跟上

## 4. 已知边界（记录在案，不作改动）

| 边界 | 描述 | 处置 |
| --- | --- | --- |
| **LAGGING_OR_DISTRIBUTION = 0** | 样本内无"主题升温但个股被连续减仓"组合（升温主题的个股动作均偏正） | 维持，样本扩大后观察 |
| **P4.3 为横截面状态** | 8 天样本，个股观测稀疏；时间序列转移状态机（DISCOVERY→CONFIRMING→CONFIRMED 跨日转移） | 待样本 15-20 日后升级 v2 |
| **REVERSING 含 4 只 NEUTRAL linkage** | 13 只 REVERSING 中 9 只来自 DIVERGENCE、4 只来自 NEUTRAL linkage（纯持仓转负/观点异号触发） | 维持（状态判定优先级设计使然） |
| **canonical 2 主题无个股映射** | TECH_GENERAL（DIRECT mention 舆情通道）/ NEW_ENERGY_ELECTROLYTE 无覆盖 | 维持 |

## 5. 冻结判定

```
PASS → Phase 4 = GO，正式冻结
下一阶段：看板部署（市场→主题→个股→分析师动作→分歧/确认 全链路展示）
```
