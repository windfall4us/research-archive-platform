#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark_theme_heat_p22d.py — P2.2D Theme Heat Benchmark
==========================================================
用户 2026-08-30 锁定的 P2.2D 验证范围（先验证业务合理性，再决定 P2.3 是否需要分位数 Momentum）：

  验证项 1: Top themes 是否业务合理
  验证项 2: 冷热排序是否稳定
  验证项 3: 负面主题是否被正确压制
  验证项 4: 零 DIRECT 但 trade 强的主题是否仍能有限抬升
  验证项 5: 单分析师日是否被 LOW_SIGNAL 标记（08-16 强制边界样本）

Gate 设计（G1-G8，全部硬 Gate；Top5/Bottom5/贡献解释为审计输出）：
  G1 每日 Top 主题业务合理性  —— Top3 全部真实信号主题；VALID 日 Top1 置信 HIGH/MEDIUM
  G2 冷热排序稳定性           —— VALID→VALID 相邻日 heat 变化 < 50（无极端跳变）
  G3 负面主题压制             —— raw_dir<0 → trade.score=0；mention net<0 → mention.score=0；负向日不升入 HEATING/HOT
  G4 零 DIRECT trade 强有限抬升 —— cov=0 & raw_dir>0 → trade.score>0 且 heat<65（不单因子冲高）
  G5 单分析师日 LOW_SIGNAL 标记  —— 08-16 全行 LOW_SIGNAL + 解释口径（不降级 heat_level）
  G6 四因子贡献可解释性       —— Σ(score_i×w_i)/den == heat_score 且贡献占比输出
  G7 业务 sanity 抽查         —— TECH_GENERAL 恒 0；MED_DRUG 08-28 负面回落后低热；已知关系成立
  G8 事实层幂等               —— P2.2C 的 raw 字段（raw_directional_value/weighted_support/stocks）与 P2.2B 一致
审计输出（非 Gate）：每日 Top5 / Bottom5 / 四因子贡献解释。

用法：python3 scripts/benchmark_theme_heat_p22d.py
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
HEAT_JSON = ROOT / "data" / "p22c" / "theme_heat_scores.json"
P22B_JSON = ROOT / "data" / "p22b" / "theme_daily_factors.json"

W = {"coverage": 0.30, "mention": 0.25, "trade": 0.25, "holding": 0.20}
CANONICAL_L2 = [
    "TECH_SEMI", "TECH_OPTICS", "TECH_AI_COMPUTE", "TECH_COMPONENT", "TECH_PCB",
    "TECH_ELEC", "TECH_SOFTWARE", "TECH_GENERAL",
    "MED_INNOVATIVE_DRUG",
    "CYCL_NONFERROUS", "CYCL_CHEMICAL",
    "NEW_ENERGY_SOLID_BATTERY", "NEW_ENERGY_ELECTROLYTE", "NEW_ENERGY_UHV",
    "OTHER_BROKER", "OTHER_AGRICULTURE", "OTHER_ROBOTICS", "OTHER_SPACE", "OTHER_CONSUMER",
]


def main():
    grid = json.loads(HEAT_JSON.read_text(encoding="utf-8"))
    p22b = json.loads(P22B_JSON.read_text(encoding="utf-8"))
    dates = sorted({r["date"] for r in grid})
    scored = [r for r in grid if r["heat_score"] is not None]
    # p22b key 可能为 {"date":..., "theme_id":...} 列表
    p22b_map = {}
    for r in p22b:
        key = (r.get("date") or r.get("trade_date"), r.get("theme_id"))
        p22b_map[key] = r

    gates = {}

    # ========== G1 每日 Top 主题业务合理性 ==========
    # Top3 必须全部真实信号主题（signal_analysts>=1）；VALID 日 Top1 置信不能 LOW/NONE
    g1_bad = []
    top1_summary = {}
    for d in dates:
        daily = [r for r in grid if r["date"] == d and r["heat_score"] is not None]
        daily.sort(key=lambda x: -x["heat_score"])
        top3 = daily[:3]
        for r in top3:
            if r["theme_signal_analysts"] < 1:
                g1_bad.append((d, r["theme_id"], "top3_zero_signal", r["heat_score"]))
        # VALID 日 Top1 不可是 LOW/NONE 置信
        top1 = daily[0] if daily else None
        if top1 and top1["heat_status"] == "VALID" and top1["signal_confidence"] in ("LOW", "NONE"):
            g1_bad.append((d, top1["theme_id"], "valid_top1_low_conf", top1["signal_confidence"]))
        if top1:
            top1_summary[d] = {"theme": top1["theme_id"], "heat": top1["heat_score"],
                               "status": top1["heat_status"], "conf": top1["signal_confidence"]}
    g1 = {"pass": len(g1_bad) == 0, "violations": g1_bad[:10], "top1_by_date": top1_summary,
          "note": "每日 Top3 无零信号主题；VALID 日 Top1 置信 ≥ MEDIUM"}

    # ========== G2 冷热排序稳定性 ==========
    # VALID→VALID 相邻交易日 heat 变化 < 50（LOW_SIGNAL 日不参与，因样本不足天然不可比）
    g2_bad = []
    g2_pairs = 0
    for i in range(len(dates) - 1):
        d1, d2 = dates[i], dates[i + 1]
        rows1 = {r["theme_id"]: r for r in grid if r["date"] == d1 and r["heat_status"] == "VALID"}
        rows2 = {r["theme_id"]: r for r in grid if r["date"] == d2 and r["heat_status"] == "VALID"}
        if not rows1 or not rows2:
            continue
        g2_pairs += 1
        for t in set(rows1) & set(rows2):
            diff = abs(rows1[t]["heat_score"] - rows2[t]["heat_score"])
            if diff >= 50:
                g2_bad.append((d1, d2, t, rows1[t]["heat_score"], rows2[t]["heat_score"], round(diff, 2)))
    g2 = {"pass": len(g2_bad) == 0, "violations": g2_bad[:10], "valid_pairs_compared": g2_pairs,
          "note": "VALID 相邻交易日同一主题 heat 变化 < 50（排除单分析师日）"}

    # ========== G3 负面主题压制 ==========
    # raw_dir<0 → trade.score=0；mention net<0 → mention.score=0；负向日不升入 HEATING/HOT
    g3_bad = []
    g3_neg_trade = 0
    g3_neg_mention = 0
    g3_neg_heat_high = 0
    for r in scored:
        trd = r["factors"]["trade"]
        men = r["factors"]["mention"]
        if trd.get("raw_directional_value") is not None and trd["raw_directional_value"] < 0:
            g3_neg_trade += 1
            if trd["score"] != 0:
                g3_bad.append((r["date"], r["theme_id"], "neg_trade_not_zero", trd["score"]))
        if men.get("net", 0) < 0:
            g3_neg_mention += 1
            if men["score"] != 0:
                g3_bad.append((r["date"], r["theme_id"], "neg_mention_not_zero", men["score"]))
        if trd.get("raw_directional_value") is not None and trd["raw_directional_value"] < 0:
            if r["heat_level"] in ("HEATING", "HOT"):
                g3_neg_heat_high += 1
                g3_bad.append((r["date"], r["theme_id"], "neg_day_high_level", r["heat_level"], r["heat_score"]))
    g3 = {"pass": len(g3_bad) == 0, "violations": g3_bad[:10],
          "neg_trade_rows": g3_neg_trade, "neg_mention_rows": g3_neg_mention,
          "neg_heat_high_rows": g3_neg_heat_high,
          "note": "负面 raw_dir / mention net 被 max(0,·) 压到 0；负向日不升入 HEATING/HOT"}

    # ========== G4 零 DIRECT 但 trade 强 → 有限抬升 ==========
    g4_rows = []
    g4_bad = []
    for r in scored:
        f = r["factors"]
        if f["coverage"]["score"] == 0 and f["trade"].get("raw_directional_value", 0) > 0:
            g4_rows.append({"date": r["date"], "theme_id": r["theme_id"],
                            "raw_dir": round(f["trade"]["raw_directional_value"], 2),
                            "trade_score": f["trade"]["score"], "heat": r["heat_score"],
                            "level": r["heat_level"]})
            if f["trade"]["score"] is None or f["trade"]["score"] <= 0:
                g4_bad.append((r["date"], r["theme_id"], "no_lift", f["trade"]["score"]))
            if r["heat_score"] >= 65:
                g4_bad.append((r["date"], r["theme_id"], "overheated", r["heat_score"]))
    g4 = {"pass": len(g4_bad) == 0, "violations": g4_bad[:10], "cases": g4_rows,
          "note": "cov=0 但 trade 流入 → trade_score>0 有限抬升，heat<65 不冲高（对比 DIRECT 主题 raw_dir 同量级可达 ~25）"}

    # ========== G5 单分析师日 LOW_SIGNAL 标记（08-16 强制边界） ==========
    d16 = [r for r in grid if r["date"] == "2026-08-16" and r["heat_score"] is not None]
    g5_bad = [r["theme_id"] for r in d16 if r["heat_status"] != "LOW_SIGNAL"]
    # 解释口径：heat_level 保持数学值不被降级，由 heat_status 表达低置信
    d16_top = sorted(d16, key=lambda x: -x["heat_score"])[0]
    g5 = {"pass": len(g5_bad) == 0,
          "rows_16": len(d16),
          "violations": g5_bad[:10],
          "top_16": {"theme": d16_top["theme_id"], "heat": d16_top["heat_score"],
                     "level": d16_top["heat_level"], "status": d16_top["heat_status"],
                     "conf": d16_top["signal_confidence"], "sig_analysts": d16_top["theme_signal_analysts"]},
          "interpretation": f"解释口径：{d16_top['theme_name']} 热度 {d16_top['heat_score']} 但仅 {d16_top['theme_signal_analysts']} 位分析师有有效信号，低置信（而非『正在加热』）",
          "note": "08-16 全 19 行 LOW_SIGNAL；heat_level 保留数学值，由 heat_status 承载置信度"}

    # ========== G6 四因子贡献可解释性 ==========
    # 每个 VALID 行：heat == Σ(score_i×w_i)/Σ(available_w)；贡献占比输出
    g6_bad = []
    g6_contrib_sample = {}
    for r in scored:
        avail_w = 0.0
        num = 0.0
        contribs = {}
        for k in ("coverage", "mention", "trade", "holding"):
            f = r["factors"][k]
            if f["available"] and f["score"] is not None:
                num += f["score"] * W[k]
                avail_w += W[k]
                contribs[k] = round(f["score"] * W[k], 4)
        recompute = num / avail_w if avail_w > 0 else None
        if recompute is not None and abs(recompute - r["heat_score"]) > 0.02:
            g6_bad.append((r["date"], r["theme_id"], round(recompute, 2), r["heat_score"]))
        # 抽样展示：每个日期 Top1 的贡献分解
        if r["heat_status"] == "VALID":
            for d, dd in g6_contrib_sample.items():
                pass  # no-op
    # 重新组织贡献抽样：每日期 VALID Top3
    contrib_sample = {}
    for d in dates:
        daily = [r for r in grid if r["date"] == d and r["heat_status"] == "VALID"]
        daily.sort(key=lambda x: -x["heat_score"])
        for r in daily[:3]:
            contribs = {}
            for k in ("coverage", "mention", "trade", "holding"):
                f = r["factors"][k]
                contribs[k] = {"score": f["score"], "weight": W[k],
                               "contrib_pct": round((f["score"] * W[k] / r["heat_score"]) * 100, 1)
                               if r["heat_score"] and f["score"] is not None else None}
            contrib_sample[f"{d} {r['theme_id']}"] = {"heat": r["heat_score"], "factors": contribs}
    g6 = {"pass": len(g6_bad) == 0, "violations": g6_bad[:10], "contrib_sample": contrib_sample,
          "note": "heat_score = Σ(score×w)/Σ(avail_w) 对每个 VALID 行成立；贡献占比可解释"}

    # ========== G7 业务 sanity 抽查 ==========
    # (a) TECH_GENERAL 无个股映射（已验 0 行）→ 交易/持仓通道必须恒 0：
    #     无股票可映射 → 不产生 trade/holding 信号（但 DIRECT mention 可产生 coverage/mention，
    #     这是「个股映射=交易信号通道，DIRECT mention=舆情信号通道」双通道设计的一部分）
    g7_bad = []
    tg = [r for r in scored if r["theme_id"] == "TECH_GENERAL"]
    tg_trd_hold_viol = [(r["date"], r["factors"]["trade"]["raw_directional_value"],
                         r["factors"]["holding"]["weighted_support"], r["heat_score"])
                        for r in tg
                        if (r["factors"]["trade"]["raw_directional_value"] not in (None, 0, 0.0)
                            or (r["factors"]["holding"]["weighted_support"] or 0) > 0)]
    if tg_trd_hold_viol:
        g7_bad.append(("TECH_GENERAL_trade_or_holding_signal", tg_trd_hold_viol))
    # (a2) 反向契约：TECH_GENERAL 的非零 heat 必须有 DIRECT mention 支撑
    #     即 coverage.analysts > 0 时 mention 必须同源可解释
    tg_heat_nonzero = [r for r in tg if r["heat_score"] not in (None, 0)]
    tg_no_mention = [r["date"] for r in tg_heat_nonzero
                     if (r["factors"]["coverage"].get("analysts") or 0) < 1]
    if tg_no_mention:
        g7_bad.append(("TECH_GENERAL_heat_without_mention", tg_no_mention))
    # (b) 08-28 MED_INNOVATIVE_DRUG raw_dir=-1.30 → heat 应低（<=15）
    d28_drug = [r for r in grid if r["date"] == "2026-08-28" and r["theme_id"] == "MED_INNOVATIVE_DRUG"]
    drug_heat = d28_drug[0]["heat_score"] if d28_drug else None
    if drug_heat is not None and drug_heat > 15:
        g7_bad.append(("MED_DRUG_0828_not_low", drug_heat))
    # (c) 08-28 CYCL_NONFERROUS 居首（当时 25.5）→ 有 coverage+holding 支撑（非纯 trade）
    d28_nf = [r for r in grid if r["date"] == "2026-08-28" and r["theme_id"] == "CYCL_NONFERROUS"]
    if d28_nf:
        f = d28_nf[0]["factors"]
        g7_nf = {"cov": f["coverage"]["score"], "hold": f["holding"]["score"],
                 "trd": f["trade"]["score"], "heat": d28_nf[0]["heat_score"]}
        if f["coverage"]["score"] == 0 and f["holding"]["score"] == 0:
            g7_bad.append(("NF_0828_no_fundamental_support", g7_nf))
    else:
        g7_nf = None
    # (d) 每个日期在 19 个 L2 上都有行（全网格完整性）
    for d in dates:
        themes_d = {r["theme_id"] for r in grid if r["date"] == d}
        missing = [t for t in CANONICAL_L2 if t not in themes_d]
        if missing:
            g7_bad.append((d, "missing_themes", missing))
    g7 = {"pass": len(g7_bad) == 0, "violations": g7_bad[:10],
          "tech_general_rows": len(tg),
          "tech_general_signal_rows": [{"date": r["date"], "heat": r["heat_score"],
                                        "status": r["heat_status"], "conf": r["signal_confidence"],
                                        "cov_analysts": r["factors"]["coverage"].get("analysts"),
                                        "mention_net": r["factors"]["mention"].get("net"),
                                        "trd_raw": r["factors"]["trade"]["raw_directional_value"],
                                        "hold_support": r["factors"]["holding"]["weighted_support"]}
                                       for r in tg_heat_nonzero],
          "med_drug_0828_heat": drug_heat, "nf_0828_factors": g7_nf,
          "note": "无个股映射主题(TECH_GENERAL)交易/持仓通道恒 0、DIRECT mention 通道合法；负面回落主题低热；榜首有基本面因子支撑；网格完整"}

    # ========== G8 事实层幂等（P2.2B → P2.2C raw 一致） ==========
    # P2.2C 的 raw 字段必须与 P2.2B JSON 相同：trade.raw_directional_value / holding.weighted_support / holding.stocks
    g8_bad = []
    g8_compared = 0
    for r in scored:
        key = (r["date"], r["theme_id"])
        b = p22b_map.get(key)
        if b is None:
            continue
        # p22b 结构可能为 {date, theme_id, coverage:{raw}, trade:{directional_value}, holding:{weighted_support, stocks}}
        b_trade = b.get("trade") or {}
        b_hold = b.get("holding") or {}
        c_trd = r["factors"]["trade"]
        c_hol = r["factors"]["holding"]
        g8_compared += 1
        b_dir = b_trade.get("directional_value")
        c_dir = c_trd.get("raw_directional_value")
        if b_dir is not None and c_dir is not None and abs(b_dir - c_dir) > 0.001:
            g8_bad.append((r["date"], r["theme_id"], "directional_value", b_dir, c_dir))
        b_ws = b_hold.get("weighted_support")
        c_ws = c_hol.get("weighted_support")
        if b_ws is not None and c_ws is not None and abs(b_ws - c_ws) > 0.001:
            g8_bad.append((r["date"], r["theme_id"], "weighted_support", b_ws, c_ws))
        b_stocks = b_hold.get("stocks")
        c_stocks = c_hol.get("stocks")
        if b_stocks is not None and c_stocks is not None and b_stocks != c_stocks:
            g8_bad.append((r["date"], r["theme_id"], "stocks", b_stocks, c_stocks))
    g8 = {"pass": len(g8_bad) == 0, "violations": g8_bad[:10], "compared_rows": g8_compared,
          "note": "P2.2C raw 字段与 P2.2B 一致：Heat 层未篡改事实层"}

    gates = {"G1_top_themes_business": g1, "G2_ranking_stability": g2,
             "G3_negative_suppression": g3, "G4_zero_direct_limited_lift": g4,
             "G5_single_analyst_low_signal": g5, "G6_factor_contrib_explainable": g6,
             "G7_business_sanity": g7, "G8_fact_layer_idempotent": g8}

    # ========== 审计输出：每日 Top5 / Bottom5 ==========
    audit = {}
    for d in dates:
        daily = [r for r in grid if r["date"] == d and r["heat_score"] is not None]
        daily.sort(key=lambda x: -x["heat_score"])
        audit[d] = {
            "top5": [{"theme": r["theme_id"], "heat": r["heat_score"], "level": r["heat_level"],
                      "status": r["heat_status"], "conf": r["signal_confidence"]} for r in daily[:5]],
            "bottom5": [{"theme": r["theme_id"], "heat": r["heat_score"], "level": r["heat_level"],
                         "status": r["heat_status"], "conf": r["signal_confidence"]} for r in daily[-5:]],
        }

    overall = "GO" if all(g["pass"] for g in gates.values()) else "NO-GO"
    print(f"P2.2D Overall = {overall}")
    for k, g in gates.items():
        print(f"  {k}: {'PASS' if g['pass'] else 'FAIL'}")

    result = {"overall": overall, "gates": gates, "audit": audit}
    (ROOT / "reports" / "theme_heat_benchmark_p22d.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写出: reports/theme_heat_benchmark_p22d.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())