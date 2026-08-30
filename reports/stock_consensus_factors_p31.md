# P3.1 Stock Consensus Factors — 个股四类事实（不打总分）

日期：2026-08-30　数据源：data/analyst_consensus.db（eligible events + positions）

## 四类事实定义
- **Attention** = 当日被提及事件数 + unique 分析师数（含全部 event_category）
- **Positive Action** = BUY/ADD/LOW_BUY/TRIAL 事件数 + 加权和（ACTION_WEIGHT 同 P2.2B）
- **Negative Action** = REDUCE/SELL/CLEAR 事件数 + 加权和
- **Holding Support** = 当日持仓分析师数 + 持仓记录数（来自 positions）

## 方向判定（锁定）
以 **action_type 语义**为准；WATCH/HOLD/DO_T/UNKNOWN 不进正负；WATCH stance（FOLLOW/POSITIVE/AVOID/WAIT）单列软信号；direction 字段仅审计。

## 覆盖
- 每股每日 cell 数：716
- 覆盖股票：350　覆盖日期：8

## 治理自检
- eligible 事件使用：934（物理 934）
- 持仓使用：124（物理 124）
- excluded 泄漏进事实：0
- DO_T 事件进正负桶：0（应 0）
- WATCH 事件进正负桶：0（应 0）
- 正负桶一致性（期望 vs 观测）：True（205 vs 205 / 149 vs 149）
- 方向冲突（action_type vs direction 字段）：14 条
  - 冲突明细：[{"type": "positive_vs_negative_dir", "stock": "688347", "date": "2026-08-14", "action": "ADD", "dir": "减仓", "analyst": "laofan"}, {"type": "positive_vs_negative_dir", "stock": "601869", "date": "2026-08-19", "action": "ADD", "dir": "减仓", "analyst": "laofan"}, {"type": "positive_vs_negative_dir", "stock": "601168", "date": "2026-08-26", "action": "ADD", "dir": "减仓", "analyst": "laofan"}, {"type": "negative_vs_positive_dir", "stock": "002670", "date": "2026-08-28", "action": "REDUCE", "dir": "买入", "analyst": "laofan"}, {"type": "positive_vs_negative_dir", "stock": "300229", "date": "2026-08-14"

## Top 样本
### Top 10 Attention（事件数）
| 股票 | attention_events | attention_dates | attention_analysts |
| --- | --- | --- | --- |
| 688432 有研硅 | 12 | 6 | 3 |
| 300607 拓斯达 | 11 | 7 | 1 |
| 601869 长飞光纤 | 11 | 5 | 4 |
| 688041 海光信息 | 11 | 7 | 2 |
| 688521 芯原股份 | 11 | 5 | 4 |
| 688825 长鑫科技 | 11 | 6 | 4 |
| 300394 天孚通信 | 10 | 6 | 5 |
| 300418 昆仑万维 | 10 | 6 | 1 |
| 301165 锐捷网络 | 10 | 5 | 4 |
| 600103 青山纸业 | 10 | 7 | 2 |

### Top 10 Positive Action（加权和）
| 股票 | positive_weighted | positive_events | positive_analysts |
| --- | --- | --- | --- |
| 601869 长飞光纤 | 4.0 | 5 | 3 |
| 688008 澜起科技 | 4.0 | 5 | 1 |
| 000506 招金黄金 | 3.2 | 4 | 1 |
| 600522 中天科技 | 3.2 | 4 | 1 |
| 300139 晓程科技 | 3.1 | 4 | 1 |
| 688432 有研硅 | 2.9 | 4 | 1 |
| 603296 华勤技术 | 2.7 | 3 | 2 |
| 600103 青山纸业 | 2.6 | 3 | 2 |
| 002532 天山铝业 | 2.4 | 3 | 1 |
| 601168 西部矿业 | 2.4 | 3 | 2 |

### Top 10 Negative Action（加权和）
| 股票 | negative_weighted | negative_events | negative_analysts |
| --- | --- | --- | --- |
| 601869 长飞光纤 | -2.8 | 4 | 2 |
| 301165 锐捷网络 | -2.0 | 4 | 1 |
| 301396 宏景科技 | -2.0 | 3 | 2 |
| 688729 屹唐股份 | -2.0 | 4 | 1 |
| 000762 西藏矿业 | -1.5 | 3 | 1 |
| 300139 晓程科技 | -1.5 | 3 | 1 |
| 300394 天孚通信 | -1.5 | 3 | 3 |
| 301308 江波龙 | -1.5 | 3 | 1 |
| 688123 聚辰股份 | -1.5 | 3 | 1 |
| 002015 协鑫能科 | -1.3 | 2 | 1 |

### Top 10 Holding Support（持仓记录数）
| 股票 | holding_records | holding_dates | holding_analysts |
| --- | --- | --- | --- |
| 000506 招金黄金 | 4 | 4 | 1 |
| 002384 东山精密 | 4 | 4 | 1 |
| 600988 赤峰黄金 | 4 | 4 | 1 |
| 601899 紫金矿业 | 4 | 3 | 2 |
| 688041 海光信息 | 4 | 3 | 2 |
| 000592 平潭发展 | 3 | 3 | 1 |
| 002532 天山铝业 | 3 | 3 | 1 |
| 300142 沃森生物 | 3 | 3 | 1 |
| 300607 拓斯达 | 3 | 3 | 1 |
| 688432 有研硅 | 3 | 3 | 2 |
