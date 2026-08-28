#!/usr/bin/env python3
"""0B.5 P5/P6 仲裁锁定 — 用户 2026-08-28 确认（含精修）。

规则：
- P5 非特殊行（48 条）: final = parser 值（action/status 双方一致或 parser 更准，draft temporal 补自 parser）
- P5 特殊行（5 条）: 显式裁决
- P6（5 条）: 显式裁决
不覆盖已锁定的 P1-P4 行（arbiter_result 非空）。
"""
import csv, json, sys
from pathlib import Path

ROOT = Path("/home/windfall/workspace/research-archive-platform")
ARB = ROOT / "reports/arbitration_list_p0b.csv"

def first_action_parser(parser_actions_field):
    try:
        v = json.loads(parser_actions_field)
        return v[0][0], v[0][1]
    except Exception:
        return "UNKNOWN", "UNKNOWN"

# P5 特殊行 (sample_id -> (arbiter, action, status, temporal, exclude, note))
P5_SPECIAL = {
    "61": ("MARKET_EXCLUDED", "UNKNOWN", "UNKNOWN", "TODAY", "true",
           "大盘=MARKET实体(协议7), '低吸为主'=市场级操作风格不生成个股动作; 与确认10行[10]同原文同裁; exclude_from_stock_consensus"),
    "10": ("AMBIGUOUS", "REDUCE", "CONDITIONAL", "FUTURE_PLAN", "true",
           "⚠️动作窗口/持有期限歧义: '73.5左右减一半'=条件/计划动作(REDUCE/CONDITIONAL), '本月结束'可能是持有周期/退出窗口而非明确执行日期; "
           "FUTURE_PLAN 暂落地但不当强规则样本(缺口O); holding_horizon=MONTH_END"),
    "75": ("BOTH_WRONG", "ADD", "EXECUTED", "TODAY", "",
           "双事件: ADD/EXECUTED/TODAY(logic'只回了有研硅'=完成态证据,缺口N) + HOLD/POSITION_STATE/CURRENT_STATE(持有); "
           "draft/parser 都标 INTENDED 错"),
    "28": ("BOTH_WRONG", "BUY", "INTENDED", "TODAY", "",
           "'提前拿筹码控仓位'=获取仓位意图→BUY/INTENDED(缺口L: 拿筹码是上下文词非固定动作); "
           "parser 命中'拿筹码'→HOLD 词典歧义, draft WATCH 错"),
    "76": ("BOTH_WRONG", "TRIAL", "CONDITIONAL", "CONDITIONAL", "",
           "'突破买点结构后…可小仓位博弈'→TRIAL(小仓位博弈=试错,缺口M); "
           "'突破…后'前置条件→status/temporal=CONDITIONAL(用户精修); parser BUY/CONDITIONAL, draft UNKNOWN"),
}

# P6 裁决 (5 条)
P6_VERDICTS = {
    "15": ("DRAFT_CORRECT", "WATCH", "INTENDED", "TODAY", "",
           "姿态句'主题催化弹性大，仓位上控制'→WATCH(缺口K); parser UNKNOWN 过于保守; "
           "review: negative_watch/stance=CAUTION"),
    "31": ("DRAFT_CORRECT", "WATCH", "INTENDED", "TODAY", "",
           "姿态句'换板可以操作'+logic加自选观察→WATCH; parser UNKNOWN 过于保守"),
    "33": ("DRAFT_CORRECT", "WATCH", "INTENDED", "TODAY", "",
           "'回避'=负向姿态→WATCH/INTENDED(枚举暂无AVOID,留stance扩展点,缺口P); "
           "review: stance=AVOID(negative_watch)"),
    "35": ("DRAFT_CORRECT", "WATCH", "INTENDED", "TODAY", "",
           "姿态句'一字预期，相信'→WATCH(关注无交易动作); parser UNKNOWN 过于保守; review: stance=POSITIVE"),
    "80": ("BOTH_WRONG", "HOLD", "POSITION_STATE", "CURRENT_STATE", "",
           "双事件(用户确认): HOLD/POSITION_STATE/CURRENT_STATE(condition=秒板不用动) + "
           "SELL/CONDITIONAL/CONDITIONAL(condition=断板/不能回封可考虑出); "
           "draft UNKNOWN/CONDITIONAL, parser UNKNOWN 都漏 HOLD"),
}

rows = list(csv.DictReader(open(ARB, encoding="utf-8")))
done = []
for r in rows:
    if r["arbiter_result"]:      # 已锁定（P1-P4）不覆盖
        continue
    pid = r["priority"]
    sid = r["sample_id"]
    if pid == "P5_DRAFT_UNKNOWN_TEMPORAL":
        if sid in P5_SPECIAL:
            (r["arbiter_result"], r["final_action"], r["final_status"],
             r["final_temporal"], r["exclude_from_core_benchmark"], r["review_note"]) = P5_SPECIAL[sid]
        else:
            r["arbiter_result"] = "PARSER_CORRECT"
            r["final_action"], r["final_status"], r["final_temporal"] = r["parser_action"], r["parser_status"], r["parser_temporal"]
        done.append(f"P5#{sid}")
    elif pid == "P6_OTHER":
        v = P6_VERDICTS.get(sid)
        if not v:
            print(f"⚠️ P6 行 {sid} 无裁决"); continue
        (r["arbiter_result"], r["final_action"], r["final_status"],
         r["final_temporal"], r["exclude_from_core_benchmark"], r["review_note"]) = v
        done.append(f"P6#{sid}")

with open(ARB, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

left = [f"{r['priority'][:2]}#{r['sample_id']}" for r in rows if not r["arbiter_result"]]
print(f"P5/P6 锁定 {len(done)} 条")
print(f"剩余未锁定: {len(left)} {' '.join(left) if left else '(0, 全部锁定)'}")
