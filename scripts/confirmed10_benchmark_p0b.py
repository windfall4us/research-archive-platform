#!/usr/bin/env python3
"""0B.5 已确认 10 行真值基准（gold_sample_10 + schema_v1 确认标注）。

输入: gold_sample_10.csv 的 raw_text（结构 = 操作短语 + 方向标签 + 逻辑）
真值: docs/gold_sample_schema_v1.md 用户确认标注
对比: parser 的 主动作 / 状态 / temporal vs 确认值

这组是用户逐条确认的真值，是 Action/Status/Temporal 的权威基准
（100 行 draft 的 temporal 83% UNKNOWN，不作 temporal 基准）。
"""
import csv, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from action_temporal_parser_p0b import parse

ROOT = Path("/home/windfall/workspace/research-archive-platform")
GS10 = ROOT / "data/analyst_snapshots/gold_sample_10.csv"

# 用户确认真值（来自 gold_sample_schema_v1.md）
CONFIRMED = {
    "1":  ("ADD", "INTENDED", "TODAY"),
    "2":  ("BUY", "CONDITIONAL", "FUTURE_PLAN"),   # 打底仓=首次建仓→BUY；LOW_BUY 需明确价格语义（低吸/回踩吸/低位接）
    "3":  ("ADD", "INTENDED", "TODAY"),
    "4":  ("HOLD", "POSITION_STATE", "CURRENT_STATE"),
    "5":  ("TRIAL", "INTENDED", "TODAY"),
    "6":  ("REDUCE", "EXECUTED", "TODAY"),
    "7":  ("CLEAR", "EXECUTED", "TODAY"),
    "8":  ("WATCH", "INTENDED", "CONDITIONAL"),
    "9":  ("DO_T", "INTENDED", "TODAY"),
    "10": ("UNKNOWN", "UNKNOWN", "TODAY"),   # 大盘 → MARKET，无个股动作
}

# 方向标签（用于把 raw_text 切成 操作短语 + 逻辑）
DIR_TAGS = ["买入", "低吸", "减仓", "卖出", "持有", "观察", "网格", "建仓", "加仓", "清仓"]

def split_raw_text(txt):
    """按方向标签切分：操作短语 / 逻辑。取所有标签中最大索引（标签总在短语末尾、逻辑之前）"""
    best = None
    for tag in DIR_TAGS:
        idx = txt.rfind(tag)
        if idx > 0 and (best is None or idx > best[0]):
            best = (idx, tag)
    if best:
        idx, tag = best
        return txt[:idx].strip(" ，,；;"), txt[idx:].strip(), tag
    return txt.strip(), "", None

rows = list(csv.DictReader(open(GS10, encoding="utf-8")))
results = []
n_action = n_status = n_temporal = n_temporal_couple = 0
n = len(rows)
mismatch_list = []

# CONDITIONAL / FUTURE_PLAN 是"未执行"语义对（用户协议② 并列），temporal 评分加容差口径
COUPLE = {"CONDITIONAL", "FUTURE_PLAN"}
def temporal_ok(parser_t, exp_t):
    if parser_t == exp_t:
        return True, True   # (严格, 容差)
    if parser_t in COUPLE and exp_t in COUPLE:
        return False, True  # 严格不等，容差相等
    return False, False

for r in rows:
    sid = r["sample_id"]
    is_market = (sid == "10")   # 大盘 → MARKET 实体，个股动作不计（实体门控，非 parser 职责）
    exp_act, exp_status, exp_temporal = CONFIRMED[sid]
    action_phrase, logic, tag = split_raw_text(r["raw_text"])
    p = parse(action_phrase, logic)
    acts = [a for a, _ in p["actions"]]
    statuses = [s for _, s in p["actions"]]
    primary = acts[0] if acts else "UNKNOWN"
    primary_status = statuses[0] if statuses else "UNKNOWN"
    temporal = p["temporal_type"]

    if is_market:
        # MARKET：action/status 不参与个股动作评分，仅报告 temporal
        a_ok = s_ok = None
        t_ok, t_couple = temporal_ok(temporal, exp_temporal)
        n_temporal += t_ok; n_temporal_couple += t_couple
    else:
        a_ok = primary == exp_act
        s_ok = primary_status == exp_status
        t_ok, t_couple = temporal_ok(temporal, exp_temporal)
        n_action += a_ok; n_status += s_ok; n_temporal += t_ok; n_temporal_couple += t_couple

    results.append({
        "sample_id": sid, "target": r["raw_target"], "action_phrase": action_phrase,
        "direction_tag": tag, "parser": p["actions"], "parser_temporal": temporal,
        "parser_position": p["position_state"],
        "confirmed": (exp_act, exp_status, exp_temporal),
        "match": (a_ok, s_ok, t_ok),
    })
    if not is_market and not (a_ok and s_ok and t_ok):
        mismatch_list.append(results[-1])

n_non_market = len([r for r in rows if r["sample_id"] != "10"])
print(f"已确认 10 行真值基准 (个股 {n_non_market} 行 + 大盘 1 行, n={n})")
print(f"  Action   一致率: {n_action}/{n_non_market} = {n_action/n_non_market:.0%}")
print(f"  Status   一致率: {n_status}/{n_non_market} = {n_status/n_non_market:.0%}")
print(f"  Temporal 一致率: {n_temporal}/{n} = {n_temporal/n:.0%}  (CONDITIONAL≡FUTURE_PLAN 容差: {n_temporal_couple}/{n} = {n_temporal_couple/n:.0%})")
print()
for res in results:
    flag = "✓" if all(m is not False for m in res["match"]) else "✗"
    print(f"{flag} [{res['sample_id']}] {res['target'][:10]} | P:{res['parser']}/{res['parser_temporal']} "
          f"vs C:{res['confirmed']} | 短语='{res['action_phrase'][:35]}'")
