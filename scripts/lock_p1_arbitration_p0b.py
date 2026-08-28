#!/usr/bin/env python3
"""0B.5 P1 仲裁锁定 — 用户 2026-08-28 确认的 16 条 P1 裁决写回仲裁清单。

每项: (arbiter_result, final_action, final_status, final_temporal, exclude, review_note)
final_action 为基准比对用主动作；多动作真值完整表达写 review_note。
"""
import csv, sys
from pathlib import Path

ROOT = Path("/home/windfall/workspace/research-archive-platform")
ARB = ROOT / "reports/arbitration_list_p0b.csv"

# P1 用户确认裁决（2026-08-28）
P1_VERDICTS = {
    "7":  ("BOTH_WRONG", "HOLD", "POSITION_STATE", "CONDITIONAL", "",
           "多动作: HOLD|REDUCE(COND)|ADD(COND); '收不回减持'等13日线回补。parser仅抓HOLD(缺口A), draft仅抓REDUCE"),
    "12": ("PARSER_CORRECT", "WATCH", "INTENDED", "TODAY", "",
           "'不追高'+反弹尾声警告→无买入, WATCH。draft REDUCE 误判"),
    "27": ("PARSER_CORRECT", "DO_T", "INTENDED", "TODAY", "",
           "'持续跟踪反复做'=做T。draft WATCH 误判"),
    "29": ("BOTH_WRONG", "SELL", "INTENDED", "TODAY", "",
           "'今日兑现为主'=操作倾向→INTENDED(协议10,缺口D); draft动作错(WATCH), parser状态错(EXECUTED)"),
    "57": ("AMBIGUOUS", "", "", "", "true",
           "组合层'打地鼠模式…剩余子弹不动',无法下沉到单只股票(折叠屏=题材)"),
    "58": ("AMBIGUOUS", "", "", "", "true",
           "组合层'打地鼠模式…剩余子弹不动',无法下沉到单只股票(冷液=题材)"),
    "59": ("BOTH_WRONG", "DO_T", "INTENDED", "CONDITIONAL", "",
           "多动作: DO_T|REDUCE(COND)|ADD(COND); '涨多减/5日线之上加'条件。parser仅DO_T(缺口A), draft仅HOLD"),
    "60": ("PARSER_CORRECT", "DO_T", "INTENDED", "TODAY", "",
           "'滚动操作'=DO_T。draft HOLD 误判"),
    "65": ("PARSER_CORRECT", "HOLD", "POSITION_STATE", "CURRENT_STATE", "",
           "'控制好仓位持有'→HOLD; draft把logic'一成仓低吸'混入动作"),
    "74": ("BOTH_WRONG", "SELL", "CONDITIONAL", "CONDITIONAL", "",
           "多动作: SELL(COND)|ADD(COND); '冲涨停出局'=触发条件非已执行(缺口B); parser状态错EXECUTED, draft漏SELL"),
    "84": ("PARSER_CORRECT", "WATCH", "INTENDED", "TODAY", "",
           "'关注支撑'→WATCH。draft BUY 误判"),
    "85": ("PARSER_CORRECT", "WATCH", "INTENDED", "TODAY", "",
           "'关注龙头'→WATCH(协议9推荐≠买入)。draft BUY 误判"),
    "87": ("AMBIGUOUS", "", "", "", "true",
           "'三日持股吃肉'(本周分享标的),持股措辞含糊,不強标BUY"),
    "90": ("PARSER_CORRECT", "WATCH", "INTENDED", "TODAY", "",
           "'核心推荐标的'=推荐关系非交易动作→WATCH(协议9)。draft BUY 误判"),
    "91": ("DRAFT_CORRECT", "BUY", "INTENDED", "FUTURE_PLAN", "",
           "'参考区间410-450,仓位1成'=计划建仓(缺口C); temporal按盘后语境取FUTURE_PLAN"),
    "100":("BOTH_WRONG", "HOLD", "POSITION_STATE", "CONDITIONAL", "",
           "多动作: HOLD|REDUCE(COND); '破13日线减出'条件。parser仅HOLD(缺口A), draft仅SELL"),
}

rows = list(csv.DictReader(open(ARB, encoding="utf-8")))
done = []
for r in rows:
    if r["priority"] != "P1_ACTION_OPPOSITE":
        continue
    v = P1_VERDICTS.get(r["sample_id"])
    if not v:
        print(f"⚠️ P1 行 {r['sample_id']} 无裁决！"); continue
    (r["arbiter_result"], r["final_action"], r["final_status"],
     r["final_temporal"], r["exclude_from_core_benchmark"], r["review_note"]) = v
    done.append(r["sample_id"])

with open(ARB, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

print(f"P1 锁定 {len(done)}/16 条:", " ".join(sorted(done, key=int)))
