# Gold Sample v1 FINAL 统计表（0B.5，2026-08-28）

来源: `gold_sample_100.csv`（原始标注） + P1-P6 人工仲裁（94 条分歧全部锁定）
输出: `data/analyst_snapshots/gold_sample_100_final.json`（事件级）

## ROW LEVEL（样本级）
```
原始样本          100
CORE rows         95
AMBIGUOUS rows     4   [10][57][58][87]
EXCLUDED rows      5   [10][57][58][61][87]
```
- EXCLUDED = 非 core 全集；其中 4 条同时 AMBIGUOUS（[10][57][58][87]），1 条仅 MARKET 排除（[61]）
- ambig ⊆ exclude（[10] 双计，去重后非 core = 5 行）

## EVENT LEVEL（事件级）
```
总事件            114   (= 100 行 + 14 多事件行，事件/行 1.14)
CORE events      112   ← Benchmark 输入（0B.7 用此分母，不用 Core rows）
AMBIGUOUS events   1   [10] REDUCE/CONDITIONAL/FUTURE_PLAN（[57][58][87] 无事件）
EXCLUDED events    1   [61] UNKNOWN/UNKNOWN/TODAY
```
- 多事件行 14 条：5/7/9/59/62/64/68/69/73/74/75/80/92/100

## 分布（CORE events 112）
| Action | 数 | Status | 数 | Temporal | 数 |
|---|---:|---|---:|---|---:|
| WATCH | 32 | INTENDED | 58 | TODAY | 69 |
| HOLD | 21 | CONDITIONAL | 19 | CONDITIONAL | 24 |
| REDUCE | 12 | POSITION_STATE | 19 | CURRENT_STATE | 15 |
| ADD | 12 | EXECUTED | 17 | FUTURE_PLAN | 3 |
| BUY | 11 | UNKNOWN | 1 | PAST | 2 |
| SELL | 6 | | | UNKNOWN | 1 |
| TRIAL | 5 | | | | |
| LOW_BUY | 5 | | | | |
| DO_T | 4 | | | | |
| CLEAR | 4 | | | | |
| UNKNOWN | 2 | | | | |

## 排除/歧义明细（Gold Edge / Ambiguous Set，保留不删除）
- [10] 融捷股份 — 动作窗口/持有期限歧义（FUTURE_PLAN 暂落地，不当强规则样本）
- [57][58] 折叠屏/冷液 — 组合层动作无法下沉到单只股票（THEME）
- [61] 大盘 — MARKET 实体，不进个股共识
- [87] 国风新材 — "三日持股吃肉"措辞含糊，不強标 BUY

## 偏斜评估
- WATCH 28% 最大（32/114）——符合语料特征（关注/观察主导，846 原始 ops 中 other232/hold162 亦居前），非合成偏斜
- INTENDED 51%（58/114）——分析师当日复盘多为意向/计划，符合"未明说已执行→INTENDED"协议
- TODAY 61%（69/114）——当日分析默认 TODAY（协议#1/#3/#5 均为 TODAY），属预期
- UNKNOWN 极低（action2/status1/temporal1）——人工仲裁后 Gold Set 本就应提供高密度可靠答案，非模拟 Parser UNKNOWN 比例
- 结论: 无显著偏斜，CORE events 112 用作 0B.7 正式 Benchmark 输入

## 双轨自洽
- POSITION_STATE 事件 19 = position_state=HOLDING 行 19（持仓状态 ≠ 交易事件）
- HOLD 21 含 HOLD/INTENDED、HOLD/CONDITIONAL 等"建议继续持有"事件，不必强求 =19
