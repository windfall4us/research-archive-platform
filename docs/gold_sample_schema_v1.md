# Gold Sample Schema v1（2026-08-28 锁定，用户确认 10 行标注判断正确）

## 必填字段
```
sample_id
analyst_id
analysis_date
raw_text
raw_target
entity_type              STOCK/THEME/MARKET/UNKNOWN
stock_code
stock_name
stock_match_method        EXACT/ALIAS/CONTEXT/FUZZY/UNRESOLVED
stock_match_confidence
actions[]                多动作数组
action_status             EXECUTED/INTENDED/CONDITIONAL/POSITION_STATE/UNKNOWN
temporal_type             TODAY/PAST/CURRENT_STATE/FUTURE_PLAN/CONDITIONAL/UNKNOWN
position_state            HOLDING/无
raw_theme
normalized_theme
human_confidence
review_note
```

## 动作归一化字典（固定）
BUY +2.0 / ADD +1.5 / LOW_BUY +1.2 / TRIAL +0.8 / HOLD +0.5 / WATCH 0 / DO_T 0 / REDUCE -1.0 / SELL -1.5 / CLEAR -2.0 / STOP_LOSS -2.0

## 已确认标注值（2026-08-28 用户确认）
| # | 分析师 | 日期 | 目标 | actions[] | action_status | temporal_type | position_state | entity_type |
|---|---|---|---|---|---|---|---|---|
| 1 | 老樊 | 08-13 | 三环集团 | [ADD] | INTENDED | TODAY | — | STOCK |
| 2 | 老樊 | 08-16 | 华勤技术 | [LOW_BUY] | CONDITIONAL | FUTURE_PLAN | — | STOCK |
| 3 | 老樊 | 08-16 | 利通电子 | [ADD] | INTENDED | TODAY | — | STOCK |
| 4 | 老樊 | 08-13 | 新洁能 | [HOLD] | POSITION_STATE | CURRENT_STATE | HOLDING | STOCK |
| 5 | 格兰投研 | 08-27 | 兴森科技 | [TRIAL] | INTENDED | TODAY | — | STOCK |
| 6 | 老樊 | 08-14 | 凯莱英 | [REDUCE] | EXECUTED | TODAY | — | STOCK |
| 7 | 震哥本尊 | 08-18 | 宏景科技 | [CLEAR] | EXECUTED | TODAY | — | STOCK |
| 8 | 老樊 | 08-17 | 易点天下 | [WATCH] | INTENDED | CONDITIONAL | — | STOCK |
| 9 | 天赢居 | 08-17 | 博睿数据 | [DO_T] | INTENDED | TODAY | — | STOCK |
| 10 | 老樊 | 08-27 | 大盘 | [] | UNKNOWN | TODAY | — | MARKET |

## 标注协议要点
1. 「顺势加仓/小幅加仓」未明说已执行 → INTENDED（区别于明确写「已加」「加至X成仓」的 EXECUTED）
2. 「回调结束可…打底仓」「若/等/逢…」条件句式 → CONDITIONAL / FUTURE_PLAN
3. 「继续持股/持有观察」且当日无买入 → POSITION_STATE / CURRENT_STATE / HOLDING（绝不出操作事件）
4. 「想干的可以动」= 博主本人意向模糊、仓量小的试错 → TRIAL / INTENDED
5. 「回踩买点跟踪」无买卖动作 → WATCH（权重0）
6. 「高抛低吸」= DO_T，不拆 SELL+LOW_BUY
7. 「大盘/市场/指数」→ MARKET，不进个股共识
8. 持仓汇总只生成 position_state=HOLDING，不生成当日操作事件（双轨，见 phase0b_plan v2）
