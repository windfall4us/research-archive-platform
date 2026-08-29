#!/usr/bin/env python3
"""P1.3 补充审计：Parser-only / direction-only 差异清单（用户 2026-08-29 要求）。

口径（用户裁决 B）：
- position_snapshots 只由 Parser 确认的 HOLD + POSITION_STATE 生成 HOLDING（=hold 口径，已落库 124 条）
- direction=持有 仅作辅助 evidence 与一致性审计，不直接落库
- 不采用 union（229）/ inter（96）

本脚本输出（只读，不落库）：
  1) 四集合关系：hold(124) / direction(201) / union(229) / inter(96)
  2) Parser-only（hold 有、direction 无）清单
  3) direction-only（direction=持有、Parser 无 POSITION_STATE）105 条抽查：
     每条 action 文本 + Parser 实际输出事件（action_type/status/temporal）
     按语义分类（条件加/减仓 / 卖出减仓 / 纯持仓 / 观察计划 / 其他）
     汇总作为 Parser 规则完善依据（对照已知 gap A/B/C）

用法: python3 scripts/audit_position_difference_p13.py
输出: reports/position_diff_p13_report.md / .json
"""
import json, re, sqlite3, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from action_temporal_parser_v11_p0b import parse as parse_v11
from ingest_consensus_p12 import Resolver, collect_source_records
from ingest_position_p13 import position_sources

SNAP = ROOT / "data/analyst_snapshots/vip0_timeline_20260828.json"
DB = ROOT / "data/analyst_consensus.db"

# direction-only 语义分类规则（面向 action 文本）
COND_RX = re.compile(r"(等|若|如果|突破|跌破|回落|站稳|冲高|回踩|站稳|不破|放量|突破后|若站)")
SELL_RX = re.compile(r"(卖出|减仓|止盈|离场|出局|减持|出掉|清仓)")
HOLD_RX = re.compile(r"(持有|持股|底仓|拿着|持仓|可留|拿住|留)")
PLAN_RX = re.compile(r"(为主|倾向|准备|打算|计划|关注|观察|跟踪|看)")


def classify_action(action):
    """direction-only action 文本分类（可能多命中，按优先级）。"""
    if not action:
        return "空文本"
    has_cond = bool(COND_RX.search(action))
    has_sell = bool(SELL_RX.search(action))
    has_hold = bool(HOLD_RX.search(action))
    if has_sell and (has_cond or has_hold):
        return "减/卖+持仓或条件" if has_hold else "减/卖+条件"
    if has_sell:
        return "卖出/减仓"
    if has_cond and has_hold:
        return "条件+持仓"
    if has_hold:
        return "纯持仓确认"
    if has_cond:
        return "纯条件/计划"
    if PLAN_RX.search(action):
        return "观察/计划"
    return "其他"


def parser_events(action, logic):
    pr = parse_v11(action or "", logic or "")
    return [(ev.get("action"), ev.get("action_status"), ev.get("temporal_type")) for ev in pr["events"]]


def main() -> int:
    d = json.loads(SNAP.read_bytes().decode("utf-8"))
    resolver = Resolver()
    hold_ops = position_sources(d, "hold")
    dir_ops = position_sources(d, "direction")

    def a_share_only(ops):
        out = []
        for o in ops:
            rs = resolver.resolve(o["raw_target"])
            o["resolve"] = rs
            if rs["entity_type"] == "STOCK":
                out.append(o)
        return out

    hold_a = a_share_only(hold_ops)      # = 落库 HOLDING 124
    dir_a = a_share_only(dir_ops)        # direction=持有 且 A_SHARE

    hold_ids = {o["source_record_id"] for o in hold_a}
    dir_ids = {o["source_record_id"] for o in dir_a}

    parser_only = [o for o in hold_a if o["source_record_id"] not in dir_ids]     # hold 有 direction 无
    # direction-only 全量（105）= direction=持有 且 Parser 无 POSITION_STATE（含非 A_SHARE，用户抽查对象）
    dir_only_full = [o for o in dir_ops if o["source_record_id"] not in hold_ids]
    dir_only_a = [o for o in dir_only_full if o.get("resolve", {}).get("entity_type") == "STOCK"]   # 89
    dir_only_non_a = [o for o in dir_only_full if o.get("resolve", {}).get("entity_type") != "STOCK"]  # 16
    both = [o for o in hold_a if o["source_record_id"] in dir_ids]                # 交集

    # 逐条解析 direction-only 的 Parser 输出 + 语义分类
    dir_only_detail = []
    cat_counter = Counter()
    parser_out_counter = Counter()
    for o in dir_only_full:
        evs = parser_events(o["raw_action"], o["raw_logic"])
        cat = classify_action(o["raw_action"])
        cat_counter[cat] += 1
        for e in evs:
            parser_out_counter[f"{e[0]}/{e[1]}"] += 1
        dir_only_detail.append({
            "source_record_id": o["source_record_id"],
            "analyst": o["analyst"], "date": o["event_date"],
            "stock": o["raw_target"], "action": o["raw_action"],
            "resolve": o["resolve"]["entity_type"],
            "category": cat, "parser_events": [f"{e[0]}/{e[1]}/{e[2]}" for e in evs],
        })

    # Parser-only 同样过一遍（供对照）
    parser_only_detail = []
    for o in parser_only:
        evs = parser_events(o["raw_action"], o["raw_logic"])
        parser_only_detail.append({
            "source_record_id": o["source_record_id"], "analyst": o["analyst"],
            "date": o["event_date"], "stock": o["raw_target"], "action": o["raw_action"],
            "direction": o.get("direction", ""),
            "parser_events": [f"{e[0]}/{e[1]}/{e[2]}" for e in evs],
        })

    report = {
        "sets": {
            "hold_parser_a_share": len(hold_a), "direction_total": len(dir_ops),
            "direction_a_share": len(dir_a), "union": len(hold_a) + len(dir_only_full),
            "inter": len(both), "parser_only": len(parser_only),
            "direction_only_total": len(dir_only_full),
            "direction_only_a_share": len(dir_only_a),
            "direction_only_non_a_share": len(dir_only_non_a),
            "both": len(both),
        },
        "direction_only_non_a_share": [{"source_record_id": o["source_record_id"],
                                        "analyst": o["analyst"], "stock": o["raw_target"],
                                        "action": o["raw_action"], "resolve": o["resolve"]["entity_type"]}
                                       for o in dir_only_non_a],
        "direction_only_categories": dict(cat_counter.most_common()),
        "direction_only_parser_output": dict(parser_out_counter.most_common()),
        "direction_only": dir_only_detail,
        "parser_only": parser_only_detail,
    }
    (ROOT / "reports" / "position_diff_p13_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown 报告
    md = ["# P1.3 Position 差异审计：Parser-only / direction-only\n",
          "> 口径 B：position_snapshots 只由 Parser 确认 HOLD+POSITION_STATE 生成 HOLDING；",
          "> direction=持有 仅作审计 evidence，不落库。\n",
          "## 1. 四集合关系",
          f"- hold(Parser POSITION_STATE, A股): **{len(hold_a)}**  → 已落库 HOLDING",
          f"- direction=持有（全量 **{len(dir_ops)}**，A股 **{len(dir_a)}**）",
          f"- union(hold∪direction): **{len(hold_a) + len(dir_only_full)}**（不采用）",
          f"- inter(hold∩direction): **{len(both)}**（不采用）",
          f"- **Parser-only**（hold 有 / direction 无）: **{len(parser_only)}**",
          f"- **direction-only**（direction 有 / hold 无，抽查对象）: **{len(dir_only_full)}**（A股 {len(dir_only_a)} + 非A股 {len(dir_only_non_a)}）",
          f"- both（交集）: **{len(both)}**\n",
          f"## 2. direction-only {len(dir_only_full)} 条语义分类（Parser 未判 POSITION_STATE 的原因分布）",
          "| 分类 | 条数 | 说明 |", "|---|---:|---|",
          ]
    cat_note = {
        "减/卖+持仓或条件": "含减/卖语义但保留持仓（如'部分减仓止盈，放量突破则小幅加仓'）→ Parser 可能只出 CONDITIONAL/EXECUTED 交易事件",
        "减/卖+条件": "含减/卖语义且条件化（如'破位价差'）→ 条件卖出，gap B 场景",
        "卖出/减仓": "direction=持有 但 action 主语义是卖出（方向与动作冲突）→ 采编标记 vs action 语义不一致",
        "条件+持仓": "持仓句带条件加/减仓（如'底仓持有，等突破再加'）→ gap A 场景：条件事件可能挤掉了主 HOLD 的 POSITION_STATE",
        "纯持仓确认": "明确持仓（持有/持股/底仓/可留）→ 疑似 Parser 漏判 HOLD/POSITION_STATE",
        "纯条件/计划": "无持仓动词的条件/计划句",
        "观察/计划": "观察/跟踪/为主 类",
        "其他": "无法归入以上",
    }
    for cat, cnt in cat_counter.most_common():
        md.append(f"| {cat} | {cnt} | {cat_note.get(cat, '')} |")
    md += ["\n## 3. direction-only 的 Parser 实际输出（为什么没判成 POSITION_STATE）",
           "| Parser 输出 (action/status) | 条数 |", "|---|---:|"]
    for k, c in parser_out_counter.most_common():
        md.append(f"| {k} | {c} |")
    md += [f"\n## 4. direction-only 逐条清单（{len(dir_only_full)}，resolve 列标非 A 股）", "",
           "| # | 分析师 | 日期 | 标的 | action | 分类 | resolve | Parser 输出 |",
           "|---|---|---|---|---|---|---|---|"]
    for i, it in enumerate(dir_only_detail, 1):
        md.append(f"| {i} | {it['analyst']} | {it['date']} | {it['stock']} | {it['action'][:42]} | {it['category']} | {it['resolve']} | {'; '.join(it['parser_events'])} |")
    md += ["\n## 4b. direction-only 中非 A_SHARE 的 16 条（direction=持有 但标的不构成 A 股，本就不该进 snapshots）",
           "| # | 分析师 | 标的 | action | resolve |", "|---|---|---|---|---|"]
    for i, o in enumerate(dir_only_non_a, 1):
        md.append(f"| {i} | {o['analyst']} | {o['raw_target']} | {o['raw_action'][:40]} | {o['resolve']['entity_type']} |")
    md += ["\n## 5. Parser-only 清单（hold 有 / direction 无，供对照）", "",
           "| # | 分析师 | 日期 | 标的 | direction | action | Parser 输出 |",
           "|---|---|---|---|---|---|---|"]
    for i, it in enumerate(parser_only_detail, 1):
        md.append(f"| {i} | {it['analyst']} | {it['date']} | {it['stock']} | {it['direction'] or '-'} | {it['action'][:40]} | {'; '.join(it['parser_events'])} |")
    (ROOT / "reports" / "position_diff_p13_report.md").write_text("\n".join(md), encoding="utf-8")

    print("=== P1.3 Position 差异审计 ===")
    print(f"hold(A股)={len(hold_a)} direction(全量)={len(dir_ops)} (A股={len(dir_a)}) union={len(hold_a)+len(dir_only_full)} inter={len(both)}")
    print(f"parser_only={len(parser_only)}  direction_only(全量)={len(dir_only_full)} (A股={len(dir_only_a)} 非A={len(dir_only_non_a)})  both={len(both)}")
    print("\ndirection-only 语义分类:")
    for cat, cnt in cat_counter.most_common():
        print(f"  {cnt:4d}  {cat}")
    print("\ndirection-only Parser 输出分布:")
    for k, c in parser_out_counter.most_common():
        print(f"  {c:4d}  {k}")
    print("\n报告: reports/position_diff_p13_report.md | .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
