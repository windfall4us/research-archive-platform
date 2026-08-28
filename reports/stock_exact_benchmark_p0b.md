# Stock Resolver Benchmark (0B.3 EXACT+ALIAS 分层)

## 桶分布
- Gold Total (STOCK): 97
- A_SHARE_RESOLVABLE: 89
- OUT_OF_SCOPE: 1
- AMBIGUOUS: 0
- EXCLUDED (题材类): 7

## 各层命中
- EXACT matched: 86
- ALIAS matched: 3
- CONTEXT matched: 0 (未启用)
- FUZZY matched: 0 (未启用)
- UNRESOLVED: 0
- WRONG_MATCH: 0

## 分层指标（A_SHARE_RESOLVABLE = 89）
| 层 | Precision | Recall |
|---|---|---|
| EXACT | 100.0% | 96.6% |
| EXACT+ALIAS | 100.0% | 100.0% |
| Overall (含CONTEXT/FUZZY) | 100.0% | 100.0% |

## UNRESOLVED TOP（下一阶段输入）
(无)
