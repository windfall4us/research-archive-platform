# Market Consensus Radar · Production QA Acceptance

```
Status:    PASS / RELEASED
Production: vip2.wmsora.vip
Snapshot md5: 77c53aaac385
Commit:    97a6640
```

---

## 验收范围

生产页面 4 视图展示层 QA：共识总览 / 主题联动 / 个股状态 / 分歧雷达（含 Action Flow 抽屉）。
验收维度：**数据一致性 + 产品可读性 + 风险提示**。仅记录 UI/Contract 层问题，未改动 Phase 1~4 冻结算法。

## 闭环链路

```
Phase 1~4 Freeze
→ Dashboard Contract
→ Production Deployment
→ Daily Publisher
→ Display QA
→ Acceptance Archive   ← 本文档
```

---

## 视图 1 · 共识总览 ✅ 全部一致

| 检查项 | 生产数据 | 冻结基线 | 结果 |
|---|---|---|---|
| 市场方向 | BULLISH +0.50（bullish 7 / neutral 1 / bearish 2） | 一致 | ✅ |
| 共识级别 | HIGH_CONSENSUS，dominant_share 0.7 | 一致 | ✅ |
| 分析师覆盖 | 10/10（eligible 10） | 一致 | ✅ |
| 股票口径 | 350 股 / 337 映射 / 13 unmapped | 一致 | ✅ |
| 状态分布 | 143 / 87 / 45 / 27 / 19 / 13 / 13 / 3 | 一致（=350） | ✅ |
| 分歧计数 | 29 / 54 / 37 / 18 / 37 | 一致 | ✅ |
| 低置信标识 | INSUFFICIENT_DATA=[NEW_ENERGY_ELECTROLYTE, TECH_GENERAL] | 一致 | ✅ |
| 血缘表 | 10 产物 md5 全录 | 已修复 | ✅ |

## 视图 2 · 主题联动 ✅ 四因子可展开 + 低置信到位

- **Heat / Momentum / Coverage / Mention / Trade / Holding 全字段**取数正确：
  Coverage 用 `analysts/eligible`、Mention 用净额（+/-）、Trade 用 `directional_value(event_count)`、Holding 用 `weighted_support`。
- **TECH_GENERAL**：仅 DIRECT 通道（trade/holding 为 null、coverage.analysts=0）、`heat_status=LOW_SIGNAL`、`signal_confidence=NONE`、heat=0、momentum 带 `SELF_HOLD_NO_OBSERVED` 备注 ✅
- **NEW_ENERGY_ELECTROLYTE**：同 LOW_SIGNAL 处理 ✅
- **视觉弱化已落实**：`cs-low-banner`「⚠ 低样本主题 — 数据有限，谨慎参考」+ FactorCell `low={low}` 弱化样式 ✅
- 主题表头字段：强共识/分歧股数齐全（如 CYCL_NONFERROUS 强共识 31 / TECH_SEMI 分歧 55）

## 视图 3 · 个股状态 ✅ 排序与口径精确

- **350 只，cross_layer_state 分布与冻结完全一致**（非空率 350/350）
- **排序严格单调**：`CONFIRMED(0-18)→REVERSING(19-31)→DIVERGING(32-76)→DISCOVERY(77-103)→WEAKENING(104-190)→CONFIRMING(191-193)→NEUTRAL(194-336)→UNMAPPED(337-349)` —— 前端 STATE_ORDER 与 API 返回一致
- **000506 招金黄金**：CONFIRMED / STRONG_POSITIVE / 有色(HEATING) / 5 维分歧齐全 / `state_notes=[bullish_resonance_low_divergence]` ✅
- **000506 Action Flow 抽屉**：9 条动作时间线（天赢居 08-14→08-28），`ADD/HOLD` 交替、`stage=ACCUMULATE→HOLD`、`status=INTENDED/POSITION_STATE/CONDITIONAL` 完整 ✅

## 视图 4 · 分歧雷达 ✅ 6 项全对

| 类别 | API | 基线 | 结果 |
|---|---|---|---|
| 分析师意见分裂（analyst_divergence≥0.5） | 29 | 29 | ✅ |
| 主题↔个股不同步（theme_stock==1.0） | 54 | 54 | ✅ |
| 观点↔实际操作不一致（view_action==1.0） | 37 | 37 | ✅ |
| 持仓仍在但动作转负（holding_action==1.0） | 18 | 18 | ✅ |
| 综合 Divergence 高（score≥0.5） | 37 | 37 | ✅ |
| **REVERSING 反转** | **13** | **13** | ✅ |

前端：REVERSING 置顶加 `⚠️` 标识 + 5 类中文标签 + 每行可点开个股抽屉，全部正确。

---

## QA 发现并修复（Snapshot/API 适配层，未碰算法）

### 1. meta.pipeline.rows=0 误导（已修复）
builder 对 p31（`stock_consensus_factors.json`）与 p32（`analyst_action_flow.json`）
取不存在的 `per_stock` 键 → rows=0。已修正：p31 取 `per_stock_total`、p32 取 `per_stock_flow_summary`，均=350。
**核心视图数据零变化**（md5 变化仅因 meta 字段）。

### 2. 发布管道 render 调用 bug（已修复）
`render_consensus_snapshot_html.py` 只接受 `--out-dir`，管道原用位置参数会致 HTML 用旧 snapshot。
已改 `--out-dir`。

### 修复验证
- 生产 + 测试盒同步 snapshot（md5 `77c53aaac385`）✅
- 生产 API 验证 `rows=350` ✅
- HTML 快照公网 `https://reports.wmsora.vip/consensus/{2026-08-28,latest}.html` → 200 ✅（md5 4b3e64fb60c8，与旧一致——HTML 侧重视图数据，不含血缘表，视图数据未变）

---

## 最终结论

**4 视图「数据一致性 + 产品可读性 + 风险提示」三维度全部通过，冻结口径与生产展示完全对齐。
展示层 QA 验收通过（PASS / RELEASED），市场共识雷达正式投入使用。**
