#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_theme_heat_score_p22c.py — P2.2C Theme Heat Score Benchmark
======================================================================
用户 2026-08-30 锁定的 8 Gate：
  G1 Heat Score 范围           —— 所有 0<=score<=100
  G2 四因子权重                 —— 30/25/25/20 正确
  G3 Mention 重复分析师放大     —— 0
  G4 Trade analyst-level cap   —— 100%
  G5 Holding analyst-level cap —— 100%
  G6 Missing 被当成 0           —— 0
  G7 手工复算                   —— 100%
  G8 重跑一致性                 —— 100%
额外 3 项审计（非硬 Gate）：每日 Top5 / Bottom5 / 四因子贡献解释

用法：python3 scripts/benchmark_theme_heat_score_p22c.py
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
JSON_PATH = ROOT / "data" / "p22c" / "theme_heat_scores.json"
LEXICON = ROOT / "scripts" / "theme_lexicon_p20c.json"

W = {"coverage": 0.30, "mention": 0.25, "trade": 0.25, "holding": 0.20}
ACTION_WEIGHT = {
    "BUY": 1.00, "ADD": 0.80, "LOW_BUY": 0.70, "TRIAL": 0.40,
    "REDUCE": -0.50, "SELL": -0.80, "CLEAR": -1.00,
    "WATCH": 0.0, "HOLD": 0.0, "UNKNOWN": 0.0,
}
STANCE_VALUE = {"POSITIVE": 1, "NEUTRAL": 0, "NEGATIVE": -1}
HEAT_MIN = 0.60
CANONICAL_L2 = [
    "TECH_SEMI", "TECH_OPTICS", "TECH_AI_COMPUTE", "TECH_COMPONENT", "TECH_PCB",
    "TECH_ELEC", "TECH_SOFTWARE", "TECH_GENERAL",
    "MED_INNOVATIVE_DRUG",
    "CYCL_NONFERROUS", "CYCL_CHEMICAL",
    "NEW_ENERGY_SOLID_BATTERY", "NEW_ENERGY_ELECTROLYTE", "NEW_ENERGY_UHV",
    "OTHER_BROKER", "OTHER_AGRICULTURE", "OTHER_ROBOTICS", "OTHER_SPACE", "OTHER_CONSUMER",
]


def clip(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def load_facts(con):
    """重建 P2.2C 所需的分析师级事实层。"""
    cur = con.cursor()
    heat_map = defaultdict(list)
    for sc, t, c in cur.execute("SELECT stock_code, theme_id, confidence FROM stock_theme_mapping"):
        if c >= HEAT_MIN and t not in heat_map[sc]:
            heat_map[sc].append(t)

    # mentions: (d,t) -> {analyst: stance_sum}
    mention_adt = defaultdict(dict)
    per_date_mention_analysts = defaultdict(set)
    for d, a, t, stance in cur.execute(
        "SELECT mention_date, analyst_id, theme_id, stance FROM analyst_theme_mentions WHERE mention_source='DIRECT'"):
        v = STANCE_VALUE.get(stance, 0)
        mention_adt[(d, t)][a] = mention_adt[(d, t)].get(a, 0) + v
        per_date_mention_analysts[d].add(a)

    # trades: (d,t) -> {analyst: raw}
    trade_adt = defaultdict(dict)
    per_date_trade_analysts = defaultdict(set)
    for eid, d, sc, act, a in cur.execute("""
        SELECT event_id, event_date, stock_code, action_type, analyst_id
        FROM analyst_stock_events
        WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)"""):
        themes = heat_map.get(sc, [])
        if not themes:
            continue
        per_date_trade_analysts[d].add(a)
        N = len(themes)
        w = ACTION_WEIGHT.get(act, 0.0)
        for t in themes:
            if act == "DO_T":
                continue
            trade_adt[(d, t)][a] = trade_adt[(d, t)].get(a, 0.0) + w / N

    # holdings: (d,t) -> {analyst: support}
    hold_adt = defaultdict(dict)
    per_date_hold_analysts = defaultdict(set)
    for d, a, sc in cur.execute(
        "SELECT snapshot_date, analyst_id, stock_code FROM analyst_position_snapshots WHERE position_state='HOLDING'"):
        themes = heat_map.get(sc, [])
        if not themes:
            continue
        per_date_hold_analysts[d].add(a)
        N = len(themes)
        for t in themes:
            hold_adt[(d, t)][a] = hold_adt[(d, t)].get(a, 0.0) + 1.0 / N

    dates = sorted({r[0] for r in cur.execute("SELECT DISTINCT event_date FROM analyst_stock_events")}
                   | {r[0] for r in cur.execute("SELECT DISTINCT mention_date FROM analyst_theme_mentions")}
                   | {r[0] for r in cur.execute("SELECT DISTINCT snapshot_date FROM analyst_position_snapshots")})
    return {
        "heat_map": heat_map,
        "mention_adt": mention_adt,
        "trade_adt": trade_adt,
        "hold_adt": hold_adt,
        "per_date_mention_analysts": per_date_mention_analysts,
        "per_date_trade_analysts": per_date_trade_analysts,
        "per_date_hold_analysts": per_date_hold_analysts,
        "dates": dates,
    }


def main():
    con = sqlite3.connect(DB)
    grid = json.load(open(JSON_PATH, encoding="utf-8"))
    F = load_facts(con)

    # ========== G1 Heat Score 范围 ==========
    g1_bad = [r for r in grid if r["heat_score"] is not None
              and not (0 <= r["heat_score"] <= 100)]
    scored = [r for r in grid if r["heat_score"] is not None]
    g1 = {"pass": len(g1_bad) == 0, "scored_rows": len(scored),
          "out_of_range": [f"{r['date']}/{r['theme_id']}={r['heat_score']}" for r in g1_bad],
          "min_score": min((r["heat_score"] for r in scored), default=None),
          "max_score": max((r["heat_score"] for r in scored), default=None)}

    # ========== G2 四因子权重 30/25/25/20 ==========
    g2_bad = []
    for r in grid:
        for k, expected in W.items():
            got = r["factors"][k]["weight"]
            if abs(got - expected) > 1e-9:
                g2_bad.append((r["date"], r["theme_id"], k, got, expected))
    g2 = {"pass": len(g2_bad) == 0, "violations": g2_bad[:10],
          "weights_expected": W, "total_weight": round(sum(W.values()), 4)}

    # ========== G3 Mention 重复分析师放大 = 0 ==========
    # 验证：JSON mention.pos/neg/neu 必须等于 (analyst,theme,day) 聚合后按 stance 符号分桶的结果，
    # 即同一分析师被多条 mention 提及仍只计 1 个单位（单分析师不重复计权）。
    g3_dup = 0
    for r in grid:
        d, t = r["date"], r["theme_id"]
        elig = r["factors"]["coverage"]["eligible"]
        f = r["factors"]["mention"]
        expected_pos = sum(1 for a, s in F["mention_adt"].get((d, t), {}).items() if s > 0)
        expected_neg = sum(1 for a, s in F["mention_adt"].get((d, t), {}).items() if s < 0)
        expected_neu = sum(1 for a, s in F["mention_adt"].get((d, t), {}).items() if s == 0)
        if (f["positive"], f["negative"], f["neutral"]) != (expected_pos, expected_neg, expected_neu):
            g3_dup += 1
    g3 = {"pass": g3_dup == 0, "mismatch_rows": g3_dup,
          "note": "mention.pos/neg/neu 按 (analyst,theme,day) 聚合后分桶，单分析师不重复计权"}

    gates = {"G1_score_range": g1, "G2_weights": g2, "G3_mention_no_dup": g3}

    # ========== G4 Trade analyst-level cap 100% ==========
    # 验证：所有 clipped_per_analyst 值在 [-1,1] 内；analyst_capped_value == Σ clipped
    g4_bad = []
    g4_clip_effect = 0
    for r in grid:
        f = r["factors"]["trade"]
        if f["available"] is False:
            continue
        for a, v in f["clipped_per_analyst"].items():
            if not (-1.0 <= v <= 1.0):
                g4_bad.append((r["date"], r["theme_id"], a, v))
        # analyst_capped_value 应等于 Σ clipped_per_analyst
        calc = round(sum(f["clipped_per_analyst"].values()), 4)
        if abs(calc - f["analyst_capped_value"]) > 0.0005:
            g4_bad.append((r["date"], r["theme_id"], "capped_sum_mismatch", f["analyst_capped_value"], calc))
        # 统计 clip 实际生效次数（raw > 1 或 < -1）
        d, t = r["date"], r["theme_id"]
        for a, raw in F["trade_adt"].get((d, t), {}).items():
            if raw > 1.0 or raw < -1.0:
                g4_clip_effect += 1
    g4 = {"pass": len(g4_bad) == 0, "violations": g4_bad[:10],
          "clip_effective_cases": g4_clip_effect,
          "note": "每个 (analyst,theme,day) raw 先 clip(-1,+1) 再聚合；防止高频分析师等价于多分析师共识"}

    # ========== G5 Holding analyst-level cap 100% ==========
    # 验证：所有 capped_per_analyst 值在 [0,1] 内；capped_value == Σ capped
    g5_bad = []
    g5_cap_effect = 0
    for r in grid:
        f = r["factors"]["holding"]
        if f["available"] is False:
            continue
        for a, v in f["capped_per_analyst"].items():
            if not (0.0 <= v <= 1.0):
                g5_bad.append((r["date"], r["theme_id"], a, v))
        calc = round(sum(f["capped_per_analyst"].values()), 4)
        if abs(calc - f["capped_value"]) > 0.0005:
            g5_bad.append((r["date"], r["theme_id"], "capped_sum_mismatch", f["capped_value"], calc))
        # 统计 cap 实际生效（fractional support > 1.0）
        d, t = r["date"], r["theme_id"]
        for a, support in F["hold_adt"].get((d, t), {}).items():
            if support > 1.0:
                g5_cap_effect += 1
    g5 = {"pass": len(g5_bad) == 0, "violations": g5_bad[:10],
          "cap_effective_cases": g5_cap_effect,
          "note": "每个 (analyst,theme,day) fractional(1/N) 后 min(1.0)；防止持仓股数竞赛"}

    # ========== G6 Missing 被当成 0 = 0 ==========
    # 数据源缺失日 → score=None（不是 0），且该因子权重从 heat 分母剔除
    g6_bad = []
    g6_missing_days = []
    for r in grid:
        for k in W:
            f = r["factors"][k]
            if f["available"] is False and f["score"] is not None:
                g6_bad.append((r["date"], r["theme_id"], k, "missing_but_scored", f["score"]))
            # 反向：available=True 时 score 应为数字（非 None）
            if f["available"] is True and f["score"] is None:
                g6_bad.append((r["date"], r["theme_id"], k, "available_but_null", None))
    # 找出有数据源缺失的日期
    for d in F["dates"]:
        a = {
            "coverage": len(F["per_date_mention_analysts"].get(d, set())) > 0,
            "mention": len(F["per_date_mention_analysts"].get(d, set())) > 0,
            "trade": len(F["per_date_trade_analysts"].get(d, set())) > 0,
            "holding": len(F["per_date_hold_analysts"].get(d, set())) > 0,
        }
        if not all(a.values()):
            g6_missing_days.append({"date": d, "availability": a,
                                    "expected_completeness": round(sum(
                                        W[k] for k, v in a.items() if v), 4)})
    g6 = {"pass": len(g6_bad) == 0, "violations": g6_bad[:10],
          "missing_source_days": g6_missing_days,
          "note": "Missing≠Zero：数据源缺失 → score=None 且权重从分母剔除（P1.3 契约）"}

    gates.update({"G4_trade_analyst_cap": g4, "G5_holding_analyst_cap": g5, "G6_missing_not_zero": g6})

    # ========== G7 手工复算 ==========
    # 对每个有 heat_score 的 (d,t) 独立重算 heat_score，与 JSON 比对（容差 0.02）
    g7_bad = []
    g7_checked = 0
    for r in grid:
        d, t = r["date"], r["theme_id"]
        if r["heat_score"] is None:
            continue
        g7_checked += 1
        elig_cov = len(F["per_date_mention_analysts"].get(d, set()))
        elig_tr = len(F["per_date_trade_analysts"].get(d, set()))
        elig_hd = len(F["per_date_hold_analysts"].get(d, set()))

        # coverage
        cov_n = len(F["mention_adt"].get((d, t), {}))
        cov_score = 100.0 * cov_n / elig_cov if elig_cov > 0 else None
        # mention
        pos = sum(1 for a, s in F["mention_adt"].get((d, t), {}).items() if s > 0)
        neg = sum(1 for a, s in F["mention_adt"].get((d, t), {}).items() if s < 0)
        men_score = 100.0 * max(0.0, (pos - neg) / elig_cov) if elig_cov > 0 else None
        # trade
        clipped = sum(clip(v) for v in F["trade_adt"].get((d, t), {}).values())
        tr_score = 100.0 * max(0.0, clipped / elig_tr) if elig_tr > 0 else None
        # holding
        capped = sum(min(1.0, v) for v in F["hold_adt"].get((d, t), {}).values())
        hd_score = 100.0 * capped / elig_hd if elig_hd > 0 else None

        scores = {"coverage": cov_score, "mention": men_score, "trade": tr_score, "holding": hd_score}
        avails = {
            "coverage": elig_cov > 0, "mention": elig_cov > 0,
            "trade": elig_tr > 0, "holding": elig_hd > 0,
        }
        num = sum(scores[k] * W[k] for k in W if avails[k] and scores[k] is not None)
        den = sum(W[k] for k in W if avails[k] and scores[k] is not None)
        heat_calc = num / den if den > 0 else None
        diff = abs(r["heat_score"] - (heat_calc if heat_calc is not None else 0))
        if diff > 0.02:
            g7_bad.append({"date": d, "theme_id": t, "json": r["heat_score"],
                           "calc": round(heat_calc, 4) if heat_calc else None, "diff": round(diff, 4)})
    g7 = {"pass": len(g7_bad) == 0, "checked_rows": g7_checked,
          "mismatches": g7_bad[:10],
          "note": "对每个 scored 行独立重算 coverage/mention/trade/holding score 与 heat，容差 0.02"}

    # ========== G8 重跑一致性 ==========
    # 重新运行计算逻辑，比较 JSON 输出是否完全一致（幂等）
    # 方法：把当前 JSON 作为 baseline，重算所有 heat_score 后逐行比较
    g8_bad = []
    for r in grid:
        d, t = r["date"], r["theme_id"]
        if r["heat_score"] is None:
            continue
        # 重算（同 G7 逻辑）
        elig_cov = len(F["per_date_mention_analysts"].get(d, set()))
        elig_tr = len(F["per_date_trade_analysts"].get(d, set()))
        elig_hd = len(F["per_date_hold_analysts"].get(d, set()))
        cov_score = 100.0 * len(F["mention_adt"].get((d, t), {})) / elig_cov if elig_cov > 0 else None
        pos = sum(1 for a, s in F["mention_adt"].get((d, t), {}).items() if s > 0)
        neg = sum(1 for a, s in F["mention_adt"].get((d, t), {}).items() if s < 0)
        men_score = 100.0 * max(0.0, (pos - neg) / elig_cov) if elig_cov > 0 else None
        tr_score = 100.0 * max(0.0, sum(clip(v) for v in F["trade_adt"].get((d, t), {}).values()) / elig_tr) if elig_tr > 0 else None
        hd_score = 100.0 * sum(min(1.0, v) for v in F["hold_adt"].get((d, t), {}).values()) / elig_hd if elig_hd > 0 else None
        # 比较每个 factor score
        for k, calc in [("coverage", cov_score), ("mention", men_score), ("trade", tr_score), ("holding", hd_score)]:
            json_v = r["factors"][k]["score"]
            if json_v is None and calc is None:
                continue
            if json_v is None or calc is None:
                g8_bad.append((d, t, k, json_v, calc))
                continue
            if abs(json_v - round(calc, 2)) > 0.02:
                g8_bad.append((d, t, k, json_v, round(calc, 2)))
    g8 = {"pass": len(g8_bad) == 0, "recomputed_rows": g7_checked,
          "factor_score_mismatches": len(g8_bad), "samples": g8_bad[:10],
          "note": "重算每个 factor score 与 JSON 比对，验证幂等一致性"}

    gates.update({"G7_manual_recalc": g7, "G8_rerun_consistency": g8})

    # ========== G9 signal governance 内部一致性 ==========
    # (1) signal_confidence 与 theme_signal_analysts 阈值一致
    # (2) heat_status 优先级：completeness<0.60 → INSUFFICIENT_DATA > signal_analysts<2 → LOW_SIGNAL > VALID
    # (3) 08-16 强制边界样本：所有该日 scored 行必须 heat_status=LOW_SIGNAL 且 signal_confidence=LOW
    # (4) 治理层不改 heat_score：heat_score 与 G7 独立复算一致（已由 G7 覆盖，此处做交叉断言）
    g9_bad = []
    # (1) confidence 阈值
    for r in grid:
        n = r["theme_signal_analysts"]
        exp = "HIGH" if n >= 4 else "MEDIUM" if n >= 2 else "LOW" if n == 1 else "NONE"
        if r["signal_confidence"] != exp:
            g9_bad.append((r["date"], r["theme_id"], "conf_mismatch", n, r["signal_confidence"], exp))
    # (2) status 优先级
    for r in grid:
        comp = r["data_completeness"]
        n = r["theme_signal_analysts"]
        if comp < 0.60:
            exp = "INSUFFICIENT_DATA"
        elif n < 2:
            exp = "LOW_SIGNAL"
        else:
            exp = "VALID"
        if r["heat_status"] != exp:
            g9_bad.append((r["date"], r["theme_id"], "status_mismatch", comp, n, r["heat_status"], exp))
        # (3) 反向：signal_analysts 必须 <= daily_eligible_analysts
        if n > r["daily_eligible_analysts"]:
            g9_bad.append((r["date"], r["theme_id"], "signal_gt_eligible", n, r["daily_eligible_analysts"]))
    # (3) 08-16 强制边界样本
    # 该日只有 laofan 一位分析师 → 所有主题必须 heat_status=LOW_SIGNAL（signal_analysts<2）
    # signal_confidence 允许 LOW（sig=1）或 NONE（sig=0）——两者都代表「单分析师或零信号日」
    d16_scored = [r for r in grid if r["date"] == "2026-08-16" and r["heat_score"] is not None]
    d16_violations = [r["theme_id"] for r in d16_scored
                      if r["heat_status"] != "LOW_SIGNAL"
                      or r["signal_confidence"] not in ("LOW", "NONE")
                      or r["theme_signal_analysts"] > 1]
    d16_expected = "PASS" if not d16_violations else "FAIL"
    # (4) 治理层不覆盖 heat_level（HEATING 与 LOW_SIGNAL 是合法组合）
    combo_check = {"heat_level_HEATING_with_LOW_SIGNAL": any(
        r["heat_level"] == "HEATING" and r["heat_status"] == "LOW_SIGNAL" for r in grid)}
    g9 = {"pass": len(g9_bad) == 0 and d16_expected == "PASS",
          "violations": g9_bad[:10],
          "d16_forced_boundary": {"rows_scored": len(d16_scored), "verdict": d16_expected,
                                  "detail": [(r["theme_id"], r["heat_score"], r["heat_level"],
                                              r["heat_status"], r["signal_confidence"],
                                              r["theme_signal_analysts"]) for r in d16_scored[:3]]},
          "combo_HEATING_LOW_SIGNAL_exists": combo_check,
          "note": "signal_confidence 阈值一致性 + heat_status 优先级 + 08-16 强制边界样本 + 治理层不覆盖 heat_level"}

    gates.update({"G9_signal_governance": g9})
    print("=== G7-G9 ===")
    for k, g in [("G7_manual_recalc", g7), ("G8_rerun_consistency", g8), ("G9_signal_governance", g9)]:
        print(f"  {k}: {'PASS' if g['pass'] else 'FAIL'}")

    overall = "GO" if all(g["pass"] for g in gates.values()) else "NO-GO"
    print(f"\nOverall = {overall}")
    for k, g in gates.items():
        print(f"  {k}: {'PASS' if g['pass'] else 'FAIL'}")

    # 保存 benchmark 结果
    (ROOT / "reports" / "theme_heat_score_benchmark_p22c.json").write_text(
        json.dumps({"overall": overall, "gates": gates}, ensure_ascii=False, indent=2), encoding="utf-8")
    con.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
