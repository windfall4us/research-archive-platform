# Action/Temporal Parser v1 Benchmark (0B.5)

生成: 2026-08-28 | 规则版 parser，无 LLM 推理 | 状态: **parser v1 + benchmark baseline（未标 PASS）**

## Parser 架构
```
输入: raw_action + raw_logic
① 动作词典扫描（长词优先，91 种句式 → 11 类动作）
② 分句级状态判定（已/时段→EXECUTED；若/等/回踩/站上→CONDITIONAL；持有→POSITION_STATE；清/减/卖默认 EXECUTED）
③ 时间词（今日/早盘/尾盘→TODAY；之前/昨日→PAST；持有→CURRENT_STATE；明天/将→FUTURE_PLAN；默认 TODAY）
④ 双轨：持有类→position_state=HOLDING（不产出当日买入事件）
⑤ 复合动作拆分（低吸持有→[LOW_BUY,HOLD]；减仓+条件加仓→[REDUCE,ADD(COND)]）
```
动作词典覆盖: BUY/LOW_BUY/ADD/TRIAL/HOLD/WATCH/DO_T/REDUCE/SELL/CLEAR/STOP_LOSS + UNKNOWN
**LOW_BUY 边界规则（用户 2026-08-28 锁定）**: 打底仓/建底仓/建仓 = BUY（首次建仓）；LOW_BUY 仅当文本明确含"低吸/回踩吸/低位接"等价格语义。

## 基准 1: 已确认 10 行真值（权威，用户逐条确认）
| 指标 | 结果 | 门槛 |
|---|---|---|
| Action | 9/9 = **100%** | ≥95% ✅ |
| Status | 9/9 = **100%** | ≥97% ✅ |
| Temporal | 9/10 = 90%（严格）/ **10/10 = 100%**（CONDITIONAL≡FUTURE_PLAN 容差） | ≥95% |

- 9 行个股 + 1 行大盘(MARKET, 个股动作不计)
- 唯一严格 temporal 差异: 华勤[2] parser CONDITIONAL vs 真值 FUTURE_PLAN —— 二者同属"未执行"语义对（用户协议② 并列「若/等/逢…→ CONDITIONAL / FUTURE_PLAN」），容差口径 100%
- 华勤真值修订: 打底仓=首次建仓 → BUY（非 LOW_BUY）

## 基准 2: 100 行 vs draft（draft 待人工锁定，含已知错误）
| 指标 | 一致率 |
|---|---|
| Action | 68% |
| Status | 69% |
| Temporal | 15%（draft 83% UNKNOWN，不可作基准）|

⚠️ 大量分歧为 draft 自身错误（parser 更准），典型:
- [65] 华勤"控制好仓位持有" draft 误标 LOW_BUY → parser HOLD ✓
- [26] 黄河旋风 draft 把"已涨停"(市场状态) 当 EXECUTED → parser WATCH ✓
- [84][85] "关注龙头/关注支撑" draft 误标 BUY → parser WATCH ✓
- [77][79][81] 打板/上车/能板就加 draft 标 UNKNOWN → parser BUY/ADD ✓

## 高风险专项（首轮验收重点）
| 项 | 结果 |
|---|---|
| R1 WATCH→HOLD 误判 | **0** ✅ |
| R2 持仓→今日BUY 误判 | **0** ✅ |
| R3 计划加仓→EXECUTED ADD | **0** ✅ |
| R4 回踩可买→已执行 LOW_BUY | **0** ✅ |
| R5 过去买入持有→今日BUY | **0** ✅ |

## 结论
- 5 项高风险全部 = 0；Status 100%；Action 100%（确认真值修订后）
- Temporal: 严格 90% 为华勤 CONDITIONAL/FUTURE_PLAN 耦合差；容差口径 100%
- **未标 PASS**：Action/Temporal 门槛需在 100 行 Gold 真值锁定后重跑正式 Benchmark 才能最终判定
- 下一步: 生成 60 条逐条仲裁清单 → 人工补齐 100 行 temporal/status/action 真值 → 锁定 Gold Sample v1 → 重跑正式 Benchmark
