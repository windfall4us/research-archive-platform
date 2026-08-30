# P3.0 Stock Consensus Readiness — 盘点结论

> 日期：2026-08-30　数据源：`data/analyst_consensus.db`（只读盘点，未改 DB）
> 脚本：`scripts/stock_consensus_readiness_p30.py` → `data/p30/stock_consensus_readiness.json`

## 1. 核心数字

| 层 | 值 |
| --- | --- |
| 物理事件 | 937 |
| 治理排除（consensus_event_exclusions） | 3 |
| **eligible 事件** | **934** |
| 事件覆盖股票 | **350** |
| 事件覆盖分析师 | **10** |
| 事件覆盖交易日 | **8**（2026-08-14 ~ 08-28） |
| 持仓（analyst_position_snapshots） | **124**，全部 position_state=HOLDING |
| 持仓覆盖股票 | **79** |
| 持仓覆盖分析师 | **9**（一线天渔哥 events=13 但无持仓） |
| 持仓覆盖交易日 | **7** |

## 2. 覆盖关系（决定分母）

```
全部 350 只 eligible 股票
├── 双证据（事件+持仓）：79 只   ← 分析师真正在"跟踪"的股票
├── 仅事件：271 只
└── 仅持仓：0 只（持仓股 100% 都在事件池内）
```

- **事件日 ∩ 持仓日非空 = 79/79**（每只持仓股在持仓日附近都有事件，无"只挂持仓无动作"的僵尸股）
- 双证据中事件日≥3：**56 只**；事件日≥2 且持仓日≥2：**29 只**

## 3. 分布特征（P3.1/P3.3 必须处理）

| 维度 | 分布 | 含义 |
| --- | --- | --- |
| 每股事件数 | 1:164 / 2:66 / 3:28 / 4+:48 | **47% 股票只有 1 个事件** → consensus 证据稀薄 |
| 每股分析师数 | 1:264 / 2:59 / 3:18 / 4+:9 | **75% 股票只有 1 位分析师** → divergence 大多不可算 |
| 每股事件日数 | 1:187 / 2:71 / 3+:48 | 53% 单日观测，无时间连续性 |
| 每日事件量 | 08-17:199 / 08-28:194 高峰；08-16:14（单分析师日） | 存在明显稀疏日 |

**action_type 词表（P3.2 预备）**：WATCH 426 / HOLD 134 / REDUCE 121 / ADD 90 / LOW_BUY 46 / BUY 41 / TRIAL 28 / SELL 24 / DO_T 18 / CLEAR 4 / UNKNOWN 2
→ 与用户锁定的 P3.2 Action Flow 词表（BUY/ADD/LOW_BUY/TRIAL / REDUCE/SELL/CLEAR / DO_T / WATCH / HOLD）**完全对应**，无需映射新词。

## 4. Stock Consensus 分母定义（本阶段核心交付）

**主分母 = 350**（全部 eligible 股票，继承 Phase 2 eligible 口径，保证跨阶段 lineage 对齐）。

但 **consensus 不硬算**：每只股票按证据强度分层（继承 Phase 2「Missing ≠ Zero / 低证据不硬算」治理哲学）：

| 层级 | 判定条件 | 数量 | 计算能力 |
| --- | --- | --- | --- |
| **S1 强证据** | 双证据且事件日≥3 | 56 | 可算 consensus_score + momentum + divergence |
| **S2 中证据** | 事件日≥2（无持仓亦可） | 163（含 S1 部分） | 可算 consensus_score，divergence 看分析师数 |
| **S3 弱证据** | 单日单分析师事件 | 187 | 只出 consensus_score 低置信，标记 low-evidence |
| **NO_DATA** | 无任何观测日 | 0 | 不参与 |

**分层规则（锁定）**：
- `consensus_coverage`：S1=STRONG / S2=MEDIUM / S3=WEAK（继承 P2.2C `heat_status` 同构）
- **divergence 只在 ≥2 位分析师时计算**；单分析师股票 divergence=0 且标 `LOW_SIGNAL`-类标记
- **WATCH ≠ BUY、HOLD ≠ 新建仓、DO_T 不当净买入**（P3.2 契约，预先固化）
- 单日观测（S3）不参与 momentum 类时间序列比较（只有横截面 consensus）

## 5. P3.0 结论

```
P3.0 Stock Consensus Readiness = GO
分母 = 350 eligible 股票，按 S1/S2/S3 分层；79 只双证据股为 consensus 核心
```

**下一步 P3.1**：基于本盘点，实现个股四类事实（Attention / Positive Action / Negative Action / Holding Support），不急着打总分。
