# Phase 2 Freeze Record

> 收口记录 — 本文件只**固化** Phase 2 的版本/结论/已知边界，**不修改任何算法**。
> 日期：2026-08-30　作者：Phase 2 全链路 P2.0B→P2.4

## 1. 最终状态

```
Phase 2 — Market Direction + Theme Heat + Theme Momentum
Overall = GO（12/12 硬 Gate PASS）
```

## 2. 关键版本 / Commit

| 子阶段 | 提交 | 内容 |
| --- | --- | --- |
| P2.0A | `08b78a7` | COMPOSITE residual governance via exclusions table |
| P2.0B | `cd2235c` `83c3740` | Market View Gold v1（50 样本 MV-1..4）+ parser benchmark GO |
| P2.0C | `5c23721` | Theme Mention Ingest（186 DIRECT mentions）GO |
| P2.0D | `7915db8` | Aggregation Readiness（schema v6 + 69 market rows）GO |
| P2.1 | `a4d8fbb` | Market Direction（按日共识 + 4 风格组）GO |
| P2.2A | `96cf3fc` + `f7fa229` | Stock→Theme Mapping GO；**P2.4 修复不可重建缺陷（MANUAL_SEEDS 固化 4 只人工补录）** |
| P2.2B | `174a9d6` | Theme Daily Factors（coverage/mention/trade/holding）GO |
| P2.2C | `60d1214` `b45190e` | Theme Heat Score + 信号治理层 GO |
| P2.2D | `a664423` | Theme Heat Benchmark GO |
| P2.3 | `8fb287e` | Theme Momentum v1（6 状态机 + 用户裁决 3+2）GO |
| P2.4 | `f7fa229` | Phase 2 总 Benchmark **12/12 GO** — Phase 2 冻结 |

## 3. 冻结规则（不得改动）

- **Market Direction (P2.1)**：按日聚合 + 三轴独立（direction/risk/position_bias）+ Coverage Gate；analyst_weight=1.0；4 风格组（analyst_profiles.style 2/3/3/2）
- **Theme Heat (P2.2C v1 + 治理层)**：固定语义归一化（禁 min-max）；权重 **30/25/25/20** 锁定；analyst-level cap（Trade clip(-1,+1)、Holding min(1.0)）；**Missing ≠ Zero**；**NEUTRAL 不加热不扣热**；档位禁用 COOLING；`heat_status` = completeness<0.60→INSUFFICIENT_DATA > sig<2→LOW_SIGNAL > VALID；`heat_level` 与 `heat_status` 正交
- **Theme Momentum (P2.3 v1)**：6 状态机 **DISCOVERY/EMERGING/HEATING/STABLE/COOLING/FADING**（不做 MAINLINE/CROWDED）；observed/effective 双轨 + confidence gate + 防抖（降级 2 日确认 / 严重恶化即时）；Δ1 跳过 LOW_SIGNAL 取上一 VALID 日；FADING 锚点 25（曾达 HEATING 级）；首日 BASELINE_ONLY；DISCOVERY 需历史；FADING→DISCOVERY 冷却窗口
- **TECH_GENERAL 双通道契约**：无个股映射 → 交易/持仓通道恒 0；DIRECT mention 为合法舆情信号通道
- **19 个 canonical L2 主题**（用户锁定）：TECH×8 / MED{INNOVATIVE_DRUG} / CYCL{2} / NEW_ENERGY{3} / OTHER{5}

## 4. 已知边界（记录在案，不作改动）

| 边界 | 描述 | 处置 |
| --- | --- | --- |
| **A2: TECH_AI_COMPUTE 24.93 / COOLING** | 08-28 该主题已明显回暖（d1=+11.97, d3=+10.27, heat=24.93）但 effective 仍 COOLING：COOLING 只能经 HEATING(≥25) 回暖，24.93 差 0.07 未到阈值。v1 保守规则（不因单次 EMERGING 跳出 COOLING）的预期结果。 | 留待样本 15-20 日后观察，届时再评估是否加 `COOLING→EMERGING` 边 |
| **A1: 08-16 LOW_SIGNAL** | 单分析师日，全 19 行 heat_status=LOW_SIGNAL；Top1 TECH_SEMI heat=67.71 但仅 1 分析师有效信号 → 低置信而非加热。Δ1 已跳过该日（ref=上一 VALID 日）。 | 隔离语义正确，维持 |
| **P2.2A unmapped 13 只** | eligible 350 只中 13 只无 heat 映射（conf<0.60），覆盖率 96.3%。保留 unmapped 不为 100% 牺牲 Precision。 | 维持 |
| **P2.2B COMPOSITE_TACTICAL** | DO_T=18 全部 0 方向（不进净买入/净卖出）。 | 维持 |

## 5. 冻结判定

```
PASS → Phase 2 = GO，正式冻结
下一阶段：Phase 3 — Stock Consensus + Analyst Action Flow
```
