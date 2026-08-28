#!/usr/bin/env python3
"""0B.5 P2/P3/P4 仲裁锁定 — 用户 2026-08-28 确认（含 [9][69][73] 双事件修订）。

只处理 arbiter_result 为空的行（不覆盖已锁定的 P1）。
双事件真值完整表达写 review_note，final_* 存基准比对用主动作。
"""
import csv, sys
from pathlib import Path

ROOT = Path("/home/windfall/workspace/research-archive-platform")
ARB = ROOT / "reports/arbitration_list_p0b.csv"

# (arbiter_result, final_action, final_status, final_temporal, exclude, review_note)
VERDICTS = {
    # ---- P2 状态冲突 14 ----
    "5":  ("PARSER_CORRECT", "REDUCE", "EXECUTED", "TODAY", "",
           "双事件(协议11): REDUCE/EXECUTED/TODAY + ADD/CONDITIONAL/CONDITIONAL(放量突破则小幅加仓); "
           "parser temporal CONDITIONAL 被条件子句带偏→主动作TODAY(缺口H)"),
    "9":  ("BOTH_WRONG", "REDUCE", "EXECUTED", "PAST", "",
           "双事件(用户修订): REDUCE/EXECUTED/PAST(之前减仓=历史事实) + HOLD/INTENDED/TODAY(可以继续跑=剩余仓位持有建议); "
           "draft状态对但漏HOLD; parser CONDITIONAL错(可以=许可非条件,缺口F)"),
    "11": ("PARSER_CORRECT", "REDUCE", "EXECUTED", "TODAY", "",
           "尾盘减仓→EXECUTED(减仓=完成态,协议12不冲突)"),
    "13": ("PARSER_CORRECT", "REDUCE", "EXECUTED", "TODAY", "",
           "止盈卖出(logic已卖)→EXECUTED"),
    "26": ("PARSER_CORRECT", "WATCH", "INTENDED", "TODAY", "",
           "开盘零进已涨停=市场状态非动作; 短线强势跟踪→WATCH/INTENDED; draft EXECUTED错"),
    "69": ("BOTH_WRONG", "BUY", "INTENDED", "TODAY", "",
           "双事件(用户修订): BUY/INTENDED/TODAY(打底仓=计划,盘中时段词≠EXECUTED,协议12) + "
           "ADD/CONDITIONAL/CONDITIONAL(等确认突破后小加仓); parser'盘中'误升EXECUTED(缺口I), draft动作错"),
    "79": ("PARSER_CORRECT", "BUY", "EXECUTED", "TODAY", "",
           "早盘强承接上车→EXECUTED(上车=完成态,协议12不冲突)"),
    "83": ("PARSER_CORRECT", "BUY", "EXECUTED", "TODAY", "",
           "尾盘买入建仓→EXECUTED(买入=完成态)"),
    "88": ("PARSER_CORRECT", "BUY", "EXECUTED", "TODAY", "",
           "早盘介入→EXECUTED(介入=完成态)"),
    "92": ("PARSER_CORRECT", "REDUCE", "EXECUTED", "TODAY", "",
           "减仓止盈→EXECUTED(协议6); 多事件: 短线同学清仓=secondary CLEAR, 突破后接回=secondary ADD/COND; draft CLEAR过头"),
    "93": ("PARSER_CORRECT", "CLEAR", "EXECUTED", "TODAY", "",
           "清仓兑现→EXECUTED(协议7)"),
    "94": ("BOTH_WRONG", "SELL", "EXECUTED", "TODAY", "",
           "止盈离场→SELL(协议13: 离场优先于止盈→REDUCE); parser动作错(受止盈), draft动作错(CLEAR过头), 状态均EXECUTED(缺口J)"),
    "95": ("PARSER_CORRECT", "SELL", "EXECUTED", "TODAY", "",
           "回本离场→SELL/EXECUTED(协议13); draft CLEAR过头"),
    "99": ("PARSER_CORRECT", "SELL", "EXECUTED", "TODAY", "",
           "卖出→EXECUTED(logic早盘判断)"),
    # ---- P3 时间冲突 5 ----
    "1":  ("PARSER_CORRECT", "TRIAL", "INTENDED", "TODAY", "",
           "试错思维对待→TRIAL/INTENDED/TODAY; draft CONDITIONAL是logic'突破买点'干扰"),
    "6":  ("PARSER_CORRECT", "REDUCE", "EXECUTED", "TODAY", "",
           "已减仓→EXECUTED/TODAY(logic早盘减仓位置); draft CURRENT_STATE错"),
    "73": ("BOTH_WRONG", "ADD", "EXECUTED", "PAST", "",
           "双事件(协议11): ADD/EXECUTED/PAST(圈友周三已加仓) + HOLD/INTENDED/CONDITIONAL(走独立行情可继续持有=条件建议); "
           "draft CURRENT_STATE被持有子句带偏, parser CONDITIONAL(缺口G+H)"),
    "97": ("PARSER_CORRECT", "CLEAR", "EXECUTED", "TODAY", "",
           "已清仓(logic开盘全部卖出)→EXECUTED/TODAY"),
    "98": ("PARSER_CORRECT", "CLEAR", "EXECUTED", "TODAY", "",
           "已走→CLEAR/EXECUTED/TODAY; ⚠️特高压方向=题材实体,个股共识层面可能OUT_OF_SCOPE(0B.7裁决),动作解析照常"),
    # ---- P4 买入族细分 1 ----
    "63": ("PARSER_CORRECT", "BUY", "INTENDED", "TODAY", "",
           "分批慢慢建底仓→BUY(建底仓=BUY规则,无低吸/回踩吸价格语义→非LOW_BUY)/INTENDED/TODAY; draft LOW_BUY错"),
}

rows = list(csv.DictReader(open(ARB, encoding="utf-8")))
done = []
for r in rows:
    if r["arbiter_result"]:       # 已锁定（P1）不覆盖
        continue
    v = VERDICTS.get(r["sample_id"])
    if not v:
        continue
    (r["arbiter_result"], r["final_action"], r["final_status"],
     r["final_temporal"], r["exclude_from_core_benchmark"], r["review_note"]) = v
    done.append(f"{r['priority'][:2]}#{r['sample_id']}")

with open(ARB, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

print(f"P2/P3/P4 锁定 {len(done)} 条: {', '.join(done)}")
# 统计未锁定
left = [r["sample_id"] for r in rows if not r["arbiter_result"]]
print(f"剩余未锁定: {len(left)} 条 → 应为 P5({sum(1 for r in rows if r['priority']=='P5_DRAFT_UNKNOWN_TEMPORAL' and not r['arbiter_result'])}) + P6({sum(1 for r in rows if r['priority']=='P6_OTHER' and not r['arbiter_result'])})")
