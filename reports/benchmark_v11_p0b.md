# Parser v1.1 正式 Benchmark 报告（0B.5，2026-08-28）

> 输入 = 冻结 Gold Sample v1 FINAL 的 **CORE events**（程序化计数，不硬编码）
> 匹配 = multiset/Counter（非普通集合交集）；Gold v1 FINAL 冻结，只改 Parser 不改真值

## 结果（满分）
```
Gold CORE rows 95 | CORE events 112（程序化计数）
Event Precision 1.0000 | Recall 1.0000 | F1 1.0000
  Gold 112 | Pred 112 | matched 112 | Missing 0 | Extra 0
Action exact      1.0000  (门槛 ≥0.95 ✓)
Action family     1.0000
Status accuracy   1.0000  (门槛 ≥0.97 ✓)
Temporal accuracy 1.0000  (门槛 ≥0.95 ✓)
Event-count 行一致率 95/95 = 1.0000
事件内容完全一致行    95/95 = 1.0000
```

## 高风险错误矩阵（全部 = 0）
| 项 | 计数 |
|---|---:|
| false executed buy | 0 |
| false executed sell | 0 |
| 持仓→今日BUY（凭空制造已执行买入） | 0 |
| WATCH→BUY族 | 0 |
| INTENDED→EXECUTED | 0 |
| CONDITIONAL→EXECUTED | 0 |
| PAST BUY→TODAY BUY | 0 |
| 推荐→BUY(executed) | 0 |

## confirmed10 交叉回归（v1.1）
```
Action 9/9=100% | Status 9/9=100% | Temporal 10/10=100%（严格，无需容差）
```
（confirmed10_benchmark_p0b.py 已从 v1 切换到 v1.1）

## v1.1 关键规则落地（backlog A–P 全部关闭）
- 事件级架构（协议11）：每个事件独立 action/status/temporal；条件/持有子句不覆盖前序完成动作
- Status scope-first（用户修正点 2）：条件作用域 > 完成态证据 > 为主/倾向 > 动作族默认
- 完成态证据（用户修正点 1）：时段词≠EXECUTED，但 买入建仓/介入/上车/买进/低吸进场 等成交进场型动作可构成 EXECUTED；低吸了(小量)除外
- 卖出程度分级（协议13/J）：CLEAR > 退出词(离场/出局/断走/可考虑出) > 止盈/卖出(止盈优先→REDUCE) > 减仓/落袋/兑现
- multiset 事件匹配（用户修正点 3）
- 跨分句条件（回踩...买点→拿筹码；突破...后→小仓位博弈）；未来条件（回调结束→FUTURE_PLAN）
- logic 只补强同 action（N）；logic-PAST 需 raw 完成态证据（防 昨日/昨天 误判 PAST）

## 生产全量鲁棒性（902 ops，vip0_timeline_20260828）
```
Action: WATCH485/HOLD148/REDUCE128/ADD92/LOW_BUY51/BUY42/TRIAL32/SELL27/DO_T19/CLEAR6/UNKNOWN2
Status: INTENDED673/POSITION_STATE138/EXECUTED129/CONDITIONAL92
Temporal: TODAY758/CURRENT_STATE128/CONDITIONAL127/FUTURE_PLAN13/PAST4/UNKNOWN2
多事件 124 行 | HOLDING持仓 138 = POSITION_STATE 138（自洽）
```
> 注：REDUCE/LOW_BUY 与首版报告（131/54）差 3 —— 因高抛低吸抑制补丁（[博睿数据][昆仑万维×2]
> 共 3 条 高抛低吸 → DO_T，不再拆子词 REDUCE/LOW_BUY），本行已用补丁后 parser 重算。
WATCH 47% 高于 Gold 28% —— 反映生产语料真实分布（观察/关注为主），非解析缺陷。

## 文件
- `scripts/action_temporal_parser_v11_p0b.py` — 事件级 parser v1.1
- `scripts/benchmark_v11_p0b.py` — multiset 事件级 Benchmark（可复现）
- `reports/benchmark_v11_mismatches.csv` — 0 行（满分）
- `scripts/confirmed10_benchmark_p0b.py` — 已切 v1.1 交叉回归
