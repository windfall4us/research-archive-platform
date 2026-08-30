# P3.2 Analyst Action Flow — 分析师动作流

日期：2026-08-30　数据源：data/analyst_consensus.db（eligible events）

## 语义契约（锁定）
- **DO_T 不当净买入**：只计 tactical 活动，不进 BUY/ADD/LOW_BUY/TRIAL 净买入集合
- **WATCH 不等于 BUY**：WATCH 是关注/观察（stage=SCAN），不等于建仓
- **HOLD 不等于新建仓**：HOLD 是持仓状态，不是买入动作

## Stage 映射
WATCH→SCAN / BUY·LOW_BUY·TRIAL→ENTRY / ADD→ACCUMULATE / HOLD→HOLD / REDUCE→REDUCE / SELL·CLEAR→EXIT / DO_T→TACTICAL / UNKNOWN→UNKNOWN

## 动作流规模
- 分析师×股票对：**474**　最长序列事件数：11
- 每股每日 cell 事件流长度分布：{"1": 284, "2": 93, "3": 32, "4": 26, "5": 14, "6": 7, "7": 5, "8": 4, "9": 6, "10": 2, "11": 1}

## 动作流统计（(分析师,股票) 对出现过的动作）
- **WATCH**: 314 对
- **REDUCE**: 98 对
- **HOLD**: 90 对
- **ADD**: 63 对
- **BUY**: 41 对
- **LOW_BUY**: 39 对
- **TRIAL**: 27 对
- **SELL**: 24 对
- **DO_T**: 16 对
- **CLEAR**: 4 对
- **UNKNOWN**: 2 对

## 治理自检
- DO_T 事件进净买入：0（应 0）
- WATCH 事件进净买入：0（应 0）
- HOLD 事件进净买入：0（应 0）
- 净买入事件：205（期望 205，P3.1 positive=205）
- 净买入加权：156.4　净卖出事件：149
- 与 P3.1 一致性：True

## Top 动作流（分析师×股票，按事件数）
| 分析师 | 股票 | 事件数 | 动作序列 |
| --- | --- | --- | --- |
| tianyingju | 300607 | 11 | HOLD→WATCH→WATCH→REDUCE→ADD→WATCH→ADD→HOLD→HOLD→WATCH→REDUCE |
| tianyingju | 600988 | 10 | WATCH→WATCH→WATCH→ADD→HOLD→HOLD→HOLD→REDUCE→ADD→HOLD |
| tianyingju | 300418 | 10 | DO_T→WATCH→WATCH→DO_T→HOLD→REDUCE→HOLD→REDUCE→WATCH→ADD |
| tianyingju | 000506 | 9 | ADD→ADD→HOLD→HOLD→HOLD→ADD→HOLD→ADD→WATCH |
| tianyingju | 300618 | 9 | ADD→HOLD→WATCH→REDUCE→HOLD→REDUCE→HOLD→WATCH→ADD |
| tianyingju | 600460 | 9 | ADD→ADD→WATCH→WATCH→REDUCE→WATCH→WATCH→LOW_BUY→WATCH |
| tianyingju | 300139 | 9 | REDUCE→HOLD→REDUCE→LOW_BUY→ADD→REDUCE→HOLD→ADD→ADD |
| tianyingju | 688008 | 9 | ADD→WATCH→WATCH→REDUCE→ADD→WATCH→ADD→ADD→ADD |
| limengchen | 688432 | 9 | ADD→HOLD→WATCH→LOW_BUY→LOW_BUY→DO_T→LOW_BUY→HOLD→SELL |
| tianyingju | 688123 | 8 | REDUCE→WATCH→HOLD→REDUCE→REDUCE→WATCH→LOW_BUY→TRIAL |

## 常见 Stage 转移（Top 10）
- ('SCAN', 'SCAN'): 75
- ('HOLD', 'SCAN'): 37
- ('SCAN', 'REDUCE'): 23
- ('SCAN', 'HOLD'): 23
- ('ACCUMULATE', 'SCAN'): 22
- ('HOLD', 'HOLD'): 22
- ('HOLD', 'REDUCE'): 20
- ('SCAN', 'ENTRY'): 15
- ('REDUCE', 'SCAN'): 15
- ('SCAN', 'ACCUMULATE'): 15
