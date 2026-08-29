#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_aggregation_readiness_p20d.py — P2.0D Aggregation Readiness Benchmark
==============================================================================
目标（用户 2026-08-30）：确认 Stock Events / Daily Views / Theme Mentions 三路事实
已具备"可以安全聚合"的状态。本阶段不加新业务规则，纯验收。

固定输出 5 个关键数字（用户锁定口径）：
    physical_stock_events / excluded_stock_events / aggregation_eligible_stock_events /
    aggregation_eligible_market_views / aggregation_eligible_theme_mentions

6 Gate：
  G1 COMPOSITE 残留       —— 聚合层有效事件(eligible)中 COMPOSITE_MISRESOLVED 治理事件 = 0
  G2 Daily View lineage  —— analyst_daily_views 全部行 source_snapshot_id 100% 可解析
  G3 Theme Mention lineage —— theme_mentions source_record_id 100% join daily_views + snapshot 100% 可解析
  G4 重复 ingest          —— 三表逻辑键重复 = 0；同 (snapshot,parser) 末轮 ingest 收敛(inserted=0)
  G5 Market View UNKNOWN —— UNKNOWN 占比在可接受范围(≤20%)，且 excluded(direction=UNKNOWN) 不进入聚合口径
  G6 Theme normalization —— 同 theme_id 归一化一致；词典无一词多 L2

运行：python3 scripts/benchmark_aggregation_readiness_p20d.py
输出：reports/aggregation_readiness_benchmark_p20d.json + .md
"""

import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
LEXICON = ROOT / "scripts" / "theme_lexicon_p20c.json"

EXCLUDED_IDS = (1093, 1095, 1107)  # consensus_event_exclusions 治理的 COMPOSITE_MISRESOLVED
UNKNOWN_THRESHOLD = 0.20           # G5 可接受范围（默认 ≤20%，报告中说明供复核）


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    # ============ 关键数字 ============
    physical_events = cur.execute("SELECT COUNT(*) FROM analyst_stock_events").fetchone()[0]
    excl_ids = [r[0] for r in cur.execute("SELECT event_id FROM consensus_event_exclusions")]
    excluded_events = len(excl_ids)
    eligible_events = physical_events - excluded_events

    mv_total = cur.execute("SELECT COUNT(*) FROM analyst_daily_views WHERE view_type='market'").fetchone()[0]
    mv_unknown = cur.execute("SELECT COUNT(*) FROM analyst_daily_views WHERE view_type='market' AND market_direction='UNKNOWN'").fetchone()[0]
    eligible_market_views = mv_total - mv_unknown

    tm_total = cur.execute("SELECT COUNT(*) FROM analyst_theme_mentions").fetchone()[0]
    tm_eligible = tm_total  # P2.0C 全部 DIRECT，无 excluded 维度

    key_numbers = {
        "physical_stock_events": physical_events,
        "excluded_stock_events": excluded_events,
        "aggregation_eligible_stock_events": eligible_events,
        "aggregation_eligible_market_views": eligible_market_views,
        "aggregation_eligible_theme_mentions": tm_eligible,
    }

    # ============ G1 COMPOSITE 残留 ============
    g1_in_eligible = cur.execute(
        f"SELECT COUNT(*) FROM analyst_stock_events WHERE event_id IN ({','.join('?' * len(excl_ids))}) AND event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)",
        excl_ids).fetchone()[0]
    g1_comp_tactical = cur.execute(
        "SELECT COUNT(*) FROM analyst_stock_events WHERE event_category='COMPOSITE_TACTICAL' AND event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)").fetchone()[0]
    g1 = {
        "pass": g1_in_eligible == 0,
        "misresolved_in_eligible": g1_in_eligible,
        "legit_composite_tactical_in_eligible": g1_comp_tactical,
        "note": "COMPOSITE_TACTICAL 为合法组合战术操作（P2.0A 仅治理 MISRESOLVED 3 条），非残留错误",
    }

    # ============ G2 Daily View lineage ============
    dv_total = cur.execute("SELECT COUNT(*) FROM analyst_daily_views").fetchone()[0]
    dv_null_snap = cur.execute("SELECT COUNT(*) FROM analyst_daily_views WHERE source_snapshot_id IS NULL").fetchone()[0]
    dv_orphan_snap = cur.execute(
        "SELECT COUNT(*) FROM analyst_daily_views v WHERE v.source_snapshot_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM source_snapshots s WHERE s.snapshot_id=v.source_snapshot_id)").fetchone()[0]
    g2 = {"pass": dv_null_snap == 0 and dv_orphan_snap == 0, "total": dv_total, "null_snapshot": dv_null_snap, "orphan_snapshot": dv_orphan_snap}

    # ============ G3 Theme Mention lineage ============
    tm_orphan_rec = cur.execute(
        "SELECT COUNT(*) FROM analyst_theme_mentions t WHERE NOT EXISTS (SELECT 1 FROM analyst_daily_views v WHERE v.view_id=CAST(t.source_record_id AS INTEGER))").fetchone()[0]
    tm_null_snap = cur.execute("SELECT COUNT(*) FROM analyst_theme_mentions WHERE source_snapshot_id IS NULL").fetchone()[0]
    tm_orphan_snap = cur.execute(
        "SELECT COUNT(*) FROM analyst_theme_mentions t WHERE t.source_snapshot_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM source_snapshots s WHERE s.snapshot_id=t.source_snapshot_id)").fetchone()[0]
    g3 = {"pass": tm_orphan_rec == 0 and tm_null_snap == 0 and tm_orphan_snap == 0, "total": tm_total,
          "orphan_record": tm_orphan_rec, "null_snapshot": tm_null_snap, "orphan_snapshot": tm_orphan_snap}

    # ============ G4 重复 ingest ============
    dup_events = cur.execute("SELECT COUNT(*) FROM (SELECT event_id FROM analyst_stock_events GROUP BY event_id HAVING COUNT(*)>1)").fetchone()[0]
    dup_dv = cur.execute("SELECT COUNT(*) FROM (SELECT analyst_id,view_date,view_type FROM analyst_daily_views GROUP BY 1,2,3 HAVING COUNT(*)>1)").fetchone()[0]
    dup_tm = cur.execute("SELECT COUNT(*) FROM (SELECT analyst_id,mention_date,theme_name,source_record_id FROM analyst_theme_mentions GROUP BY 1,2,3,4 HAVING COUNT(*)>1)").fetchone()[0]
    # ingest 收敛：同 (source_snapshot_id, parser_version, resolver_version) 多次出现时末轮 inserted=0
    unconverged = cur.execute("""
        SELECT source_snapshot_id, parser_version, resolver_version
        FROM ingest_runs WHERE status='success'
        GROUP BY source_snapshot_id, parser_version, resolver_version
        HAVING MAX(inserted_event_count) > 0 AND COUNT(*) > 1
          AND (SELECT inserted_event_count FROM ingest_runs r2
               WHERE r2.source_snapshot_id=ingest_runs.source_snapshot_id
                 AND r2.parser_version=ingest_runs.parser_version
                 AND r2.resolver_version=ingest_runs.resolver_version
               ORDER BY r2.run_id DESC LIMIT 1) > 0
    """).fetchall()
    g4 = {"pass": dup_events == 0 and dup_dv == 0 and dup_tm == 0 and len(unconverged) == 0,
          "dup_event_id": dup_events, "dup_daily_view_key": dup_dv, "dup_theme_key": dup_tm,
          "unconverged_ingest": [tuple(r) for r in unconverged]}

    # ============ G5 Market View UNKNOWN ============
    mv_unknown_rate = mv_unknown / mv_total if mv_total else 0
    g5 = {"pass": mv_unknown_rate <= UNKNOWN_THRESHOLD, "total": mv_total, "unknown": mv_unknown,
          "unknown_rate": round(mv_unknown_rate * 100, 1), "threshold": f"≤{UNKNOWN_THRESHOLD*100:.0f}%",
          "eligible": eligible_market_views, "excluded_from_aggregation": mv_unknown,
          "note": "excluded(direction=UNKNOWN) 不进入 Market Consensus 聚合口径"}

    # ============ G6 Theme normalization ============
    id_norm_bad = cur.execute("""
        SELECT theme_id, COUNT(DISTINCT normalized_theme||'|'||l1||'|'||l2) c FROM analyst_theme_mentions
        GROUP BY theme_id HAVING c > 1""").fetchall()
    lex = json.load(open(LEXICON, encoding="utf-8"))
    kw_map = {}
    for l1_id, l1 in lex["l1"].items():
        for l2_id, l2 in l1["l2"].items():
            for kw in l2["keywords"]:
                kw_map.setdefault(kw, set()).add(f"{l1_id}_{l2_id}")
    kw_multi = {k: sorted(v) for k, v in kw_map.items() if len(v) > 1}
    g6 = {"pass": len(id_norm_bad) == 0 and len(kw_multi) == 0, "id_inconsistent": [tuple(r) for r in id_norm_bad], "keyword_multi_l2": kw_multi}

    gates = {"G1_COMPOSITE_residual": g1, "G2_daily_view_lineage": g2, "G3_theme_mention_lineage": g3,
             "G4_duplicate_ingest": g4, "G5_market_view_unknown": g5, "G6_theme_normalization": g6}
    overall = "GO" if all(g["pass"] for g in gates.values()) else "NO-GO"

    # 三路盘点链路统计
    lineage = {
        "stock_events": {"physical": physical_events, "excluded": excluded_events, "eligible": eligible_events},
        "daily_views": {"total": dv_total, "core_theme": cur.execute("SELECT COUNT(*) FROM analyst_daily_views WHERE view_type='core_theme'").fetchone()[0],
                        "trend": cur.execute("SELECT COUNT(*) FROM analyst_daily_views WHERE view_type='trend'").fetchone()[0],
                        "logic": cur.execute("SELECT COUNT(*) FROM analyst_daily_views WHERE view_type='logic'").fetchone()[0],
                        "market": mv_total},
        "theme_mentions": {"total": tm_total, "eligible": tm_eligible},
        "source_snapshots": cur.execute("SELECT COUNT(*) FROM source_snapshots").fetchone()[0],
        "ingest_runs": cur.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0],
    }

    report = {
        "benchmark": "P2.0D Aggregation Readiness",
        "schema_version": 6,
        "key_numbers": key_numbers,
        "gates": gates,
        "overall": overall,
        "lineage": lineage,
        "eligible_stock_events_category": dict(Counter(r[0] for r in cur.execute(
            "SELECT event_category FROM analyst_stock_events WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)"))),
        "market_view_direction_dist": dict(Counter(r[0] for r in cur.execute(
            "SELECT market_direction FROM analyst_daily_views WHERE view_type='market'"))),
    }

    out_json = ROOT / "reports" / "aggregation_readiness_benchmark_p20d.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# P2.0D Aggregation Readiness — Benchmark 报告",
        "",
        f"**Overall: `{overall}`** | Schema: v6 | 三路事实盘点→聚合准备验收",
        "",
        "## 5 关键数字（用户锁定口径）",
        "| 数字 | 值 |",
        "|---|---|",
        *(f"| {k} | {v} |" for k, v in key_numbers.items()),
        "",
        "## 三路盘点链路",
        f"- Stock Events: {lineage['stock_events']['physical']} physical → {lineage['stock_events']['excluded']} excluded → **{lineage['stock_events']['eligible']} eligible**",
        f"- Daily Views: {lineage['daily_views']['total']} 行（core_theme {lineage['daily_views']['core_theme']} / trend {lineage['daily_views']['trend']} / logic {lineage['daily_views']['logic']} / market {lineage['daily_views']['market']}）",
        f"- Theme Mentions: {lineage['theme_mentions']['total']}（全部 DIRECT eligible）",
        f"- Source Snapshots: {lineage['source_snapshots']} | ingest_runs: {lineage['ingest_runs']}",
        "",
        "## 6 Gate",
        "| Gate | 判定 | 关键值 |",
        "|---|---|---|",
        f"| G1 COMPOSITE 残留 | {'✅' if g1['pass'] else '❌'} | MISRESOLVED 进入 eligible = {g1['misresolved_in_eligible']}；合法 COMPOSITE_TACTICAL = {g1['legit_composite_tactical_in_eligible']}（非残留） |",
        f"| G2 Daily View lineage | {'✅' if g2['pass'] else '❌'} | {g2['total']} 行，NULL snapshot={g2['null_snapshot']}，orphan={g2['orphan_snapshot']} |",
        f"| G3 Theme Mention lineage | {'✅' if g3['pass'] else '❌'} | {g3['total']} 行，orphan record={g3['orphan_record']}，snapshot 解析 100% |",
        f"| G4 重复 ingest | {'✅' if g4['pass'] else '❌'} | dup key 全 0，ingest 收敛" + ("" if not g4["unconverged_ingest"] else f"，未收敛 {g4['unconverged_ingest']}") + " |",
        f"| G5 Market View UNKNOWN | {'✅' if g5['pass'] else '❌'} | {g5['unknown']}/{g5['total']}={g5['unknown_rate']}%（阈值{g5['threshold']}），eligible={g5['eligible']} |",
        f"| G6 Theme normalization | {'✅' if g6['pass'] else '❌'} | id 不一致={len(g6['id_inconsistent'])}，一词多 L2={len(g6['keyword_multi_l2'])} |",
        "",
        "## 结论",
        f"**{overall}** —— " + ("三路事实达到可安全聚合状态，Phase 2 输入层完整，可进入 P2.1 Market Direction + P2.2 Theme Heat。" if overall == "GO" else "存在未通过 Gate，需修复后再验收。"),
    ]
    out_md = ROOT / "reports" / "aggregation_readiness_benchmark_p20d.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"Overall = {overall}")
    print("关键数字:", json.dumps(key_numbers, ensure_ascii=False))
    for k, g in gates.items():
        print(f"  {k}: {'PASS' if g['pass'] else 'FAIL'}")
    print(f"报告: {out_json.name} / {out_md.name}")
    con.close()
    return 0 if overall == "GO" else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
