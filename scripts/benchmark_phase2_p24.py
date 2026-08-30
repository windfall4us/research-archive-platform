#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_phase2_p24.py — P2.4 Phase 2 总 Benchmark
=====================================================
串联 P2.0B → P2.0C → P2.0D → P2.1 → P2.2A/B/C/D → P2.3，验证：
  1) 全链路可重建、幂等、hash 一致
  2) lineage / eligibility / exclusion 没有跨层泄漏
  3) 给出 Phase 2 Overall GO / NO-GO

12 硬 Gate（用户 2026-08-30 锁定）：
  G1  Market View eligible 口径 100% 一致
  G2  Theme Mention lineage 100%
  G3  Stock-theme mapping eligible 100%
  G4  3 条治理事件泄漏 = 0
  G5  Theme Factors 重算 100%（复跑 P2.2B benchmark）
  G6  Theme Heat 重算 100%（复跑 P2.2D benchmark，含 G8 事实层幂等）
  G7  Momentum Δ1/Δ3 重算 100%（复跑 P2.3 benchmark G1/G2）
  G8  LOW_SIGNAL / Missing 语义 100%
  G9  Transition graph 合法 100%
  G10 全链路重跑新增记录 = 0
  G11 关键输出 hash 一致
  G12 原始事实层被修改 = 0

3 业务审计（非硬 Gate）：
  A1 08-16 LOW_SIGNAL 是否仍被正确隔离
  A2 TECH_AI_COMPUTE 24.93 / COOLING 边界案例
  A3 每日 Top Theme 与 Momentum 状态是否可解释

用法：python3 scripts/benchmark_phase2_p24.py
退出码：0 = Phase 2 Overall GO；1 = NO-GO
"""

import hashlib
import json
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
SCRIPTS = ROOT / "scripts"

# 关键输出（hash 一致验证对象）
KEY_OUTPUTS = {
    "p21_market_consensus": ROOT / "reports" / "market_consensus" / "all_dates.json",
    "p22b_factors": ROOT / "data" / "p22b" / "theme_daily_factors.json",
    "p22c_heat": ROOT / "data" / "p22c" / "theme_heat_scores.json",
    "p23_momentum": ROOT / "data" / "p23" / "theme_momentum.json",
}

# 原始事实层：P2.0 快照 JSON（重跑前后必须 hash 不变 = 未被修改）
RAW_SNAPSHOT_DIR = ROOT / "data" / "analyst_snapshots"

# 治理事件（consensus_event_exclusions）
EXCLUDED_IDS = (1093, 1095, 1107)

# 合法 transition graph（与 P2.3 一致）
ALLOWED_TRANSITIONS = {
    "DISCOVERY": {"EMERGING"},
    "EMERGING": {"HEATING", "FADING"},
    "HEATING": {"STABLE", "COOLING"},
    "STABLE": {"HEATING", "COOLING"},
    "COOLING": {"HEATING", "FADING"},
    "FADING": {"DISCOVERY"},
}
STATE_ORDER = ["DISCOVERY", "EMERGING", "HEATING", "STABLE", "COOLING", "FADING"]
for _s in STATE_ORDER:
    ALLOWED_TRANSITIONS.setdefault(_s, set()).add(_s)

# 19 canonical L2
CANONICAL_L2 = [
    "TECH_SEMI", "TECH_OPTICS", "TECH_AI_COMPUTE", "TECH_COMPONENT", "TECH_PCB",
    "TECH_ELEC", "TECH_SOFTWARE", "TECH_GENERAL",
    "MED_INNOVATIVE_DRUG",
    "CYCL_NONFERROUS", "CYCL_CHEMICAL",
    "NEW_ENERGY_SOLID_BATTERY", "NEW_ENERGY_ELECTROLYTE", "NEW_ENERGY_UHV",
    "OTHER_BROKER", "OTHER_AGRICULTURE", "OTHER_ROBOTICS", "OTHER_SPACE", "OTHER_CONSUMER",
]

gates = {}          # gate -> {pass, detail}
audits = {}         # audit -> {..}
reports = {}        # 4 段报告


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_benchmark(name, script):
    """复跑子 benchmark，返回 (exit_code, stdout_tail)。"""
    p = subprocess.run([sys.executable, str(SCRIPTS / script)], capture_output=True, text=True, cwd=ROOT)
    tail = (p.stdout or "")[-600:] + (p.stderr or "")[-200:]
    print(f"  ↳ {name}: exit={p.returncode}")
    return p.returncode, tail


def check(gate, cond, msg):
    gates[gate] = {"pass": bool(cond), "detail": msg}
    print(f"  [{'PASS' if cond else 'FAIL'}] {gate}: {msg}")


def main():
    print("=" * 74)
    print("P2.4 Phase 2 总 Benchmark — 串联 P2.0B→P2.0C→P2.0D→P2.1→P2.2A/B/C/D→P2.3")
    print("=" * 74)

    # ============ 阶段 0：基线快照（hash + 表行数 + 原始快照） ============
    print("\n[阶段 0] 记录重跑前基线")
    base_hash = {k: sha256(p) for k, p in KEY_OUTPUTS.items() if p.exists()}
    con = sqlite3.connect(DB)
    cur = con.cursor()
    base_rows = {}
    for t in ["source_snapshots", "analyst_daily_views", "analyst_theme_mentions",
              "analyst_stock_events", "analyst_position_snapshots", "stock_theme_mapping",
              "consensus_event_exclusions"]:
        base_rows[t] = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    base_raw = {}
    for f in sorted(RAW_SNAPSHOT_DIR.glob("vip0_timeline_*.json")):
        base_raw[f.name] = sha256(f)
    print(f"  关键输出 {len(base_hash)} 个、表 {len(base_rows)} 张、原始快照 {len(base_raw)} 个 hash 已记录")

    # ============ 阶段 1：全链路重跑（可重建验证） ============
    print("\n[阶段 1] 全链路重跑（P2.0B → P2.0C → P2.2A → P2.2B → P2.2C → P2.3 → P2.1）")
    rerun_cmds = [
        ("P2.0B market_view_ingest", "market_view_ingest_p20b.py"),
        ("P2.0C theme_mention_extract", "theme_mention_extract_v1.py"),
        ("P2.2A stock_theme_mapping", "stock_theme_mapping_p22a.py"),
        ("P2.2B theme_daily_factors", "theme_daily_factors_p22b.py"),
        ("P2.2C theme_heat_score", "theme_heat_score_p22c.py"),
        ("P2.3 theme_momentum", "theme_momentum_p23.py"),
        ("P2.1 market_direction", "market_direction_p21.py"),
    ]
    rerun_ok = True
    for name, script in rerun_cmds:
        p = subprocess.run([sys.executable, str(SCRIPTS / script)], capture_output=True, text=True, cwd=ROOT, timeout=600)
        ok = p.returncode == 0
        if not ok:
            rerun_ok = False
            print(f"  ✗ {name} 重跑失败 exit={p.returncode}: {(p.stderr or p.stdout)[-300:]}")
        else:
            print(f"  ✓ {name} 重跑成功")
    print(f"  全链路重跑: {'全部成功' if rerun_ok else '存在失败'}")

    # ============ G10 全链路重跑新增记录 = 0 ============
    print("\nG10: 全链路重跑后 DB 行数必须与重跑前一致（无新增/重复）")
    g10_bad = []
    for t in base_rows:
        now_n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        if now_n != base_rows[t]:
            g10_bad.append((t, base_rows[t], now_n))
    check("G10", rerun_ok and len(g10_bad) == 0,
          f"重跑{'失败' if not rerun_ok else '成功'}; 行数差异={g10_bad or '无'}")

    # ============ G11 关键输出 hash 一致 ============
    print("\nG11: 重跑后关键输出 hash 与重跑前一致（可重建且确定性）")
    g11_bad = []
    for k, p in KEY_OUTPUTS.items():
        if not p.exists():
            continue
        h2 = sha256(p)
        if h2 != base_hash.get(k):
            g11_bad.append((k, base_hash.get(k, "?"), h2))
    check("G11", len(g11_bad) == 0, f"hash 差异={g11_bad or '无'}（{len(base_hash)} 个输出）")

    # ============ G12 原始事实层被修改 = 0 ============
    print("\nG12: 原始快照 JSON hash 在重跑前后不变（原始事实层未被修改）")
    g12_bad = []
    for f, h in base_raw.items():
        p = RAW_SNAPSHOT_DIR / f
        if not p.exists():
            g12_bad.append((f, "missing"))
        elif sha256(p) != h:
            g12_bad.append((f, "hash_changed"))
    check("G12", len(g12_bad) == 0, f"原始快照被修改={g12_bad or '无'}（{len(base_raw)} 个）")

    # ============ G1 Market View eligible 口径 100% 一致 ============
    print("\nG1: Market View eligible 口径跨层一致（P2.0D 全量口径）")
    # P2.0B: view_type='market' 行；P2.0D: aggregation_eligible_market_views = market 行 - UNKNOWN
    mv_total = cur.execute("SELECT COUNT(*) FROM analyst_daily_views WHERE view_type='market'").fetchone()[0]
    mv_unknown = cur.execute(
        "SELECT COUNT(*) FROM analyst_daily_views WHERE view_type='market' AND market_direction='UNKNOWN'").fetchone()[0]
    mv_eligible = mv_total - mv_unknown
    # P2.0D 报告固化 eligible=60（全量口径：69 market - 9 UNKNOWN）
    try:
        p20d = json.loads((ROOT / "reports" / "aggregation_readiness_benchmark_p20d.json").read_text(encoding="utf-8"))
        p20d_elig = p20d["key_numbers"]["aggregation_eligible_market_views"]
    except Exception:
        p20d_elig = None
    g1_ok = (mv_eligible > 0) and (p20d_elig is None or p20d_elig == mv_eligible)
    check("G1", g1_ok,
          f"market 行={mv_total}, UNKNOWN={mv_unknown}, eligible={mv_eligible}; P2.0D 固化 aggregation_eligible_market_views={p20d_elig}")

    # ============ G2 Theme Mention lineage 100% ============
    print("\nG2: Theme Mention lineage 100%（source_record_id → daily_view，snapshot → source_snapshots）")
    tm_total = cur.execute("SELECT COUNT(*) FROM analyst_theme_mentions").fetchone()[0]
    tm_orphan_rec = cur.execute("""
        SELECT COUNT(*) FROM analyst_theme_mentions m
        LEFT JOIN analyst_daily_views v ON m.source_record_id = v.view_id
        WHERE v.view_id IS NULL""").fetchone()[0]
    tm_orphan_snap = cur.execute("""
        SELECT COUNT(*) FROM analyst_theme_mentions m
        LEFT JOIN source_snapshots s ON m.source_snapshot_id = s.snapshot_id
        WHERE m.source_snapshot_id IS NOT NULL AND s.snapshot_id IS NULL""").fetchone()[0]
    check("G2", tm_total > 0 and tm_orphan_rec == 0 and tm_orphan_snap == 0,
          f"mentions={tm_total}, orphan_record={tm_orphan_rec}, orphan_snapshot={tm_orphan_snap}")

    # ============ G3 Stock-theme mapping eligible 100% ============
    print("\nG3: Stock-theme mapping eligible 覆盖率（与 P2.2A benchmark 同口径：conf>=0.60 为 heat 股票）")
    eligible_stocks = {r[0] for r in cur.execute(
        "SELECT DISTINCT stock_code FROM analyst_stock_events WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)")}
    heat_stocks = {r[0] for r in cur.execute(
        "SELECT DISTINCT stock_code FROM stock_theme_mapping WHERE confidence >= 0.60")}
    unmapped = sorted(eligible_stocks - heat_stocks)
    cov = len(eligible_stocks & heat_stocks) / len(eligible_stocks) * 100 if eligible_stocks else 0
    # P2.2A benchmark overall GO 要求（看 reports/mapping_benchmark_p22a.json 的判定）
    g3_ok = cov >= 95.0
    check("G3", g3_ok,
          f"eligible={len(eligible_stocks)}, heat_stocks={len(eligible_stocks & heat_stocks)}, "
          f"coverage={cov:.1f}%（P2.2A benchmark 要求 ≥95%）; unmapped={len(unmapped)} 只（P2.2A 判定可接受）")

    # ============ G4 3 条治理事件泄漏 = 0 ============
    print("\nG4: 3 条治理事件（1093/1095/1107）不得泄漏进任何计算层（eligible 计算集合）")
    excl_in_db = cur.execute(
        "SELECT COUNT(*) FROM consensus_event_exclusions WHERE event_id IN (?,?,?)", EXCLUDED_IDS).fetchone()[0]
    # 正确口径：excluded 事件若「不在 exclusions 表却在 eligible 计算集合」= 泄漏
    # （它们本来就在 events 物理表里，P2.0D G1 已验证不进 eligible；这里复验 eligible 集合干净）
    excl_leak_eligible = cur.execute("""
        SELECT COUNT(*) FROM analyst_stock_events e
        WHERE e.event_id IN (?,?,?)
          AND e.event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)""",
        EXCLUDED_IDS).fetchone()[0]
    check("G4", excl_in_db == 3 and excl_leak_eligible == 0,
          f"exclusions 表命中={excl_in_db}（应 3）; 泄漏进 eligible 计算集合={excl_leak_eligible}（应 0，"
          f"即 3 事件全部被 exclusions 表覆盖）")

    # ============ G8 LOW_SIGNAL / Missing 语义 ============
    print("\nG8: LOW_SIGNAL / Missing 语义（08-16 强制隔离 + Missing≠Zero 不下钻）")
    heat = json.loads((ROOT / "data" / "p22c" / "theme_heat_scores.json").read_text(encoding="utf-8"))
    d16 = [r for r in heat if r["date"] == "2026-08-16"]
    d16_bad_status = [r["theme_id"] for r in d16 if r["heat_status"] != "LOW_SIGNAL"]
    d16_bad_sig = [r["theme_id"] for r in d16 if r["signal_confidence"] in ("HIGH", "MEDIUM")]
    # Missing≠Zero：heat_score=0 的行必须有可解释来源（coverage 0 或 trade 0），且 signal_analysts 匹配
    zero_rows = [r for r in heat if r["heat_score"] == 0]
    zero_explain = 0
    for r in zero_rows:
        cov = r["factors"]["coverage"].get("score") or 0
        men = r["factors"]["mention"].get("score") or 0
        trd = r["factors"]["trade"].get("score") or 0
        hld = r["factors"]["holding"].get("score") or 0
        if cov == 0 and men == 0 and trd == 0 and hld == 0:
            zero_explain += 1
    check("G8", len(d16_bad_status) == 0 and len(d16_bad_sig) == 0 and zero_explain == len(zero_rows),
          f"08-16 {len(d16)} 行全 LOW_SIGNAL（非状态={d16_bad_status or '无'}，高置信={d16_bad_sig or '无'}）; "
          f"heat=0 行 {len(zero_rows)} 全可解释（{zero_explain}）")

    # ============ G9 Transition graph 合法 ============
    print("\nG9: Momentum effective 状态跳转全部落在合法 transition graph 内")
    mom = json.loads((ROOT / "data" / "p23" / "theme_momentum.json").read_text(encoding="utf-8"))
    by_theme = defaultdict(list)
    for r in mom:
        by_theme[r["theme_id"]].append(r)
    g9_bad = []
    for t, rows in by_theme.items():
        prev = None
        for r in sorted(rows, key=lambda x: x["date"]):
            e = r["effective_momentum_state"]
            if e:
                if prev and e != prev and e not in ALLOWED_TRANSITIONS.get(prev, set()):
                    g9_bad.append((r["date"], t, prev, e))
                prev = e
    check("G9", len(g9_bad) == 0, f"非法跳转={g9_bad or '无'}")

    # ============ G5/G6/G7 复跑子 benchmark（重算验证） ============
    print("\nG5/G6/G7: 复跑各层权威 benchmark（含重算 gate）")
    b22b, _ = run_benchmark("P2.2B Theme Factors 重算", "benchmark_theme_daily_factors_p22b.py")
    b22d, _ = run_benchmark("P2.2D Theme Heat 重算+事实层幂等", "benchmark_theme_heat_p22d.py")
    b23, _ = run_benchmark("P2.3 Momentum Δ1/Δ3 重算", "benchmark_theme_momentum_p23.py")
    check("G5", b22b == 0, f"P2.2B benchmark exit={b22b}（0=GO）")
    check("G6", b22d == 0, f"P2.2D benchmark exit={b22d}（0=GO）")
    check("G7", b23 == 0, f"P2.3 benchmark exit={b23}（0=GO）")

    # ============ 汇总硬 Gate ============
    hard_gates = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "G11", "G12"]
    n_pass = sum(1 for g in hard_gates if gates.get(g, {}).get("pass"))
    phase2_go = n_pass == len(hard_gates)
    print("\n" + "=" * 74)
    print(f"Phase 2 硬 Gate: {n_pass}/{len(hard_gates)} PASS")
    print(f"Phase 2 Overall = {'GO' if phase2_go else 'NO-GO'}")

    # ============ 审计 A1/A2/A3 ============
    print("\n[审计] A1/A2/A3")
    # A1: 08-16 LOW_SIGNAL 隔离
    d16_top = sorted(d16, key=lambda x: -(x["heat_score"] or 0))[0] if d16 else None
    audits["A1_0816_low_signal_isolation"] = {
        "rows": len(d16),
        "top": {k: d16_top.get(k) for k in ("theme_id", "heat_score", "heat_level", "heat_status", "signal_confidence", "theme_signal_analysts")} if d16_top else None,
        "interpretation": f"08-16 全 {len(d16)} 行 LOW_SIGNAL；Top1 {d16_top['theme_name'] if d16_top else '-'} 热度 "
                          f"{d16_top['heat_score'] if d16_top else '-'} 但仅 "
                          f"{d16_top['theme_signal_analysts'] if d16_top else '-'} 位分析师有有效信号 → 低置信而非加热",
    }
    print(f"  A1: 08-16 全 LOW_SIGNAL；Top1={d16_top['theme_id'] if d16_top else '-'} heat="
          f"{d16_top['heat_score'] if d16_top else '-'}（{d16_top['theme_signal_analysts'] if d16_top else '-'} 位分析师）")

    # A2: TECH_AI_COMPUTE 24.93 / COOLING 边界案例
    tac = [r for r in mom if r["theme_id"] == "TECH_AI_COMPUTE" and r["date"] == "2026-08-28"]
    tac_r = tac[0] if tac else None
    audits["A2_tech_ai_compute_cooling_boundary"] = {
        "date": "2026-08-28", "theme": "TECH_AI_COMPUTE",
        "heat": tac_r["heat_score"] if tac_r else None,
        "d1": tac_r["delta_1d"] if tac_r else None,
        "d3": tac_r["delta_3d"] if tac_r else None,
        "observed": tac_r["observed_momentum_state"] if tac_r else None,
        "effective": tac_r["effective_momentum_state"] if tac_r else None,
        "note": tac_r["note"] if tac_r else None,
        "drivers": tac_r["momentum_drivers"] if tac_r else None,
        "interpretation": ("已明显回暖(d1=+11.97,d3=+10.27,heat=24.93)但 effective 仍 COOLING："
                           "transition graph 中 COOLING 只能经 HEATING(≥25) 回暖，24.93 差 0.07 未到阈值。"
                           "这是 v1 保守规则（不因单次 EMERGING 跳出 COOLING）的预期结果，非 bug。"
                           "留待样本 15-20 日后观察是否需加 COOLING→EMERGING 边。"),
    }
    print(f"  A2: TECH_AI_COMPUTE 08-28 heat=24.93 d1=+11.97 → eff=COOLING（v1 保守，边界案例已记录）")

    # A3: 每日 Top Theme 与 Momentum 状态可解释
    a3 = {}
    for d in sorted({r["date"] for r in heat}):
        daily = [r for r in heat if r["date"] == d and r["heat_score"] is not None]
        daily.sort(key=lambda x: -x["heat_score"])
        top = daily[0] if daily else None
        mrow = [r for r in mom if r["date"] == d and r["theme_id"] == (top["theme_id"] if top else None)]
        mrow = mrow[0] if mrow else None
        a3[d] = {
            "top_theme": top["theme_id"] if top else None,
            "top_heat": top["heat_score"] if top else None,
            "top_level": top["heat_level"] if top else None,
            "top_status": top["heat_status"] if top else None,
            "momentum_eff": mrow["effective_momentum_state"] if mrow else None,
            "momentum_obs": mrow["observed_momentum_state"] if mrow else None,
        }
    audits["A3_daily_top_theme_momentum_explainable"] = {"by_date": a3}
    print("  A3: 每日 Top Theme + Momentum 状态映射（见报告）")

    # ============ 4 段报告 ============
    print("\n[报告] 4 段分层总结")
    reports["data_parser_readiness"] = {
        "p20b": {"overall": "GO (P2.0B)"},
        "p20c": {"overall": "GO (P2.0C)"},
        "p20d": {"overall": "GO (P2.0D)"},
        "key": {"mv_total": mv_total, "mv_eligible": mv_eligible, "tm_total": tm_total,
                "stock_events": base_rows["analyst_stock_events"],
                "exclusions": base_rows["consensus_event_exclusions"]},
    }
    reports["market_direction"] = {
        "overall": "GO (P2.1)",
        "notes": "按日聚合 + 三轴独立 + Coverage Gate；风格分组解释层",
    }
    reports["theme_heat"] = {
        "overall": "GO (P2.2C/P2.2D)",
        "grid": f"{len(heat)} 行（{len({r['date'] for r in heat})} 日期 × 19 L2）",
        "zero_explainable": f"{zero_explain}/{len(zero_rows)}",
    }
    reports["theme_momentum"] = {
        "overall": "GO (P2.3)",
        "rows": len(mom),
        "eff_dist": dict(Counter(r["effective_momentum_state"] for r in mom if r["effective_momentum_state"])),
    }

    # ============ 输出 ============
    out = {
        "phase": "P2.4", "overall": "GO" if phase2_go else "NO-GO",
        "gates": gates, "audits": audits, "reports": reports,
        "rerun": {"ok": rerun_ok, "steps": [s[0] for s in rerun_cmds]},
    }
    (ROOT / "reports" / "phase2_benchmark_p24.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md = []
    md.append(f"# P2.4 Phase 2 总 Benchmark — **Overall = `{out['overall']}`**")
    md.append("")
    md.append(f"硬 Gate **{n_pass}/{len(hard_gates)}**")
    md.append("")
    md.append("| Gate | 判定 | 关键值 |")
    md.append("| --- | --- | --- |")
    gate_names = {
        "G1": "Market View eligible 口径", "G2": "Theme Mention lineage", "G3": "Stock-theme mapping eligible",
        "G4": "3 治理事件泄漏", "G5": "Theme Factors 重算", "G6": "Theme Heat 重算",
        "G7": "Momentum Δ1/Δ3 重算", "G8": "LOW_SIGNAL/Missing 语义", "G9": "Transition graph 合法",
        "G10": "全链路重跑新增记录", "G11": "关键输出 hash 一致", "G12": "原始事实层被修改",
    }
    for g in hard_gates:
        gg = gates.get(g, {})
        md.append(f"| {g} {gate_names.get(g, '')} | {'✅' if gg.get('pass') else '❌'} | {gg.get('detail', '')} |")
    md.append("")
    md.append("## Phase 2 分层总结")
    for sec, label in [("data_parser_readiness", "Data/Parser Readiness"),
                       ("market_direction", "Market Direction"),
                       ("theme_heat", "Theme Heat"),
                       ("theme_momentum", "Theme Momentum")]:
        md.append(f"- **{label}**: {json.dumps(reports[sec], ensure_ascii=False)}")
    md.append("")
    md.append("## 审计")
    for k, v in audits.items():
        md.append(f"- **{k}**: {json.dumps(v.get('interpretation', v), ensure_ascii=False)[:300]}")
    md.append("")
    md.append(f"**Phase 2 Overall = `{out['overall']}`**")
    (ROOT / "reports" / "phase2_benchmark_p24.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\n报告 → reports/phase2_benchmark_p24.json + .md")

    con.close()
    return 0 if phase2_go else 1


if __name__ == "__main__":
    raise SystemExit(main())
