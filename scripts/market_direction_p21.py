#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_direction_p21.py — P2.1 Market Direction（每日市场共识，第一版）
========================================================================
口径（用户 2026-08-30 锁定）：
  * 按 view_date 聚合：某交易日 Market Direction = 当天所有 eligible analyst market_score 加权平均
  * analyst_weight = 1.0（全部）；UNKNOWN exclude，不参与 score
  * Direction / Risk / Position Bias 三轴独立，Risk/Bias 不参与 Direction Score
  * direction_score → 5 档状态：
        ≥ +1.20 STRONG_BULLISH | +0.35~+1.19 BULLISH | -0.34~+0.34 NEUTRAL
        | -1.19~-0.35 BEARISH | ≤ -1.20 STRONG_BEARISH
  * consensus_level（dominant_share = 最大阵营人数/eligible人数）：
        ≥70% HIGH_CONSENSUS | 50%~69% MEDIUM_CONSENSUS | <50% LOW_CONSENSUS
  * Risk / Bias 输出分布 + dominant（不平均成假精度）；Risk 内部映射 LOW=1/MEDIUM=2/HIGH=3
  * Coverage Gate：≥5 NORMAL | 3~4 LOW_COVERAGE | <3 INSUFFICIENT（保留 score 但 market_direction_status=INSUFFICIENT_DATA）
  * 风格分组：ALL/LONG_TERM/SWING/SHORT/ULTRA_SHORT，来自 analyst_profiles.style 固定映射
    （style 未填时为 NOT_AVAILABLE）；风格 Score 仅解释层，总 Score 用全部 eligible

用法：python3 scripts/market_direction_p21.py [--json-dir reports/market_consensus]
输出：reports/market_consensus/ 下每日 <date>.json + 汇总 all_dates.json
"""

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"

# 用户锁定（P2.1）：
WEIGHT_DEFAULT = 1.0
STYLE_ENUM = ("LONG_TERM", "SWING", "SHORT", "ULTRA_SHORT")   # analyst_profiles.style 直接存英文枚举

RISK_NUM = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def direction_bucket(score):
    if score is None:
        return "UNKNOWN"
    if score >= 1.20:
        return "STRONG_BULLISH"
    if score >= 0.35:
        return "BULLISH"
    if score > -0.35:
        return "NEUTRAL"      # -0.34 ~ +0.34
    if score > -1.20:
        return "BEARISH"      # -1.19 ~ -0.35
    return "STRONG_BEARISH"


def consensus_level(dominant_share):
    if dominant_share >= 0.70:
        return "HIGH_CONSENSUS"
    if dominant_share >= 0.50:
        return "MEDIUM_CONSENSUS"
    return "LOW_CONSENSUS"


def coverage_status(n):
    if n >= 5:
        return "NORMAL"
    if n >= 3:
        return "LOW_COVERAGE"
    return "INSUFFICIENT"


def compute_day(rows, style_of):
    """rows: 当天 market 行（已含 UNKNOWN）。style_of: 全 profiles 的 {analyst_id: style_enum}。"""
    eligible = [r for r in rows if r["market_direction"] != "UNKNOWN"]
    n = len(eligible)
    style_total = Counter(style_of.values())  # 风格组总人数（全 profiles，非当天）

    # ---- Direction ----
    score_sum = sum(r["market_score"] * WEIGHT_DEFAULT for r in eligible)
    w_sum = WEIGHT_DEFAULT * n
    direction_score = round(score_sum / w_sum, 4) if w_sum > 0 else None
    direction = direction_bucket(direction_score) if n > 0 else "UNKNOWN"

    cnt = Counter(r["market_direction"] for r in eligible)
    bullish = sum(cnt.get(k, 0) for k in ("BULLISH", "STRONG_BULLISH"))
    bearish = sum(cnt.get(k, 0) for k in ("BEARISH", "STRONG_BEARISH"))
    neutral = cnt.get("NEUTRAL", 0)
    dominant_share = round(max(cnt.values()) / n, 4) if n > 0 else 0.0
    cov_status = coverage_status(n)

    # ---- Risk 分布 + dominant ----
    risk_cnt = Counter(r["risk_level"] for r in eligible if r["risk_level"] not in (None, "UNKNOWN"))
    dominant_risk = max(risk_cnt, key=lambda k: (risk_cnt[k], -RISK_NUM.get(k, 9))) if risk_cnt else "UNKNOWN"

    # ---- Position Bias 分布（不塞单轴）----
    bias_cnt = Counter(r["position_bias"] for r in eligible if r["position_bias"] not in (None, "UNKNOWN"))

    # ---- 风格分组（解释层；来自 profiles.style 固定映射，非当天动态判断）----
    # 风格组独立 coverage：group_total=该风格分析师总人数, group_eligible=当日有效人数
    #   group_eligible==0 → NO_DATA | coverage_rate<50% → LOW_COVERAGE | ≥50% → NORMAL
    #   sample_size_warning = group_eligible < 2（单分析师样本，不构成稳定风格共识）
    style_groups = {}
    for st in STYLE_ENUM:
        members = [r for r in eligible if style_of.get(r["analyst_id"]) == st]
        if not members:
            continue
        g_total = style_total.get(st, 0)
        g_eligible = len(members)
        coverage_rate = round(g_eligible / g_total, 4) if g_total else 0.0
        if g_eligible == 0:
            g_cov = "NO_DATA"
        elif coverage_rate >= 0.50:
            g_cov = "NORMAL"
        else:
            g_cov = "LOW_COVERAGE"
        ss = sum(m["market_score"] for m in members) / g_eligible
        style_groups[st] = {
            "count": g_eligible,
            "group_total": g_total,
            "coverage_rate": coverage_rate,
            "coverage_status": g_cov,
            "sample_size_warning": g_eligible < 2,
            "direction_score": round(ss, 4),
            "direction": direction_bucket(ss),
        }

    return {
        "date": rows[0]["view_date"],
        "direction_score": direction_score,
        "direction": direction,
        "eligible_analysts": n,
        "coverage_status": cov_status,
        "market_direction_status": "INSUFFICIENT_DATA" if cov_status == "INSUFFICIENT" else direction,
        "bullish": bullish,
        "neutral": neutral,
        "bearish": bearish,
        "dominant_share": dominant_share,
        "consensus_level": consensus_level(dominant_share) if n > 0 else "LOW_CONSENSUS",
        "risk": {
            "high": risk_cnt.get("HIGH", 0),
            "medium": risk_cnt.get("MEDIUM", 0),
            "low": risk_cnt.get("LOW", 0),
            "dominant": dominant_risk,
        },
        "position_bias": {k: v for k, v in sorted(bias_cnt.items())},
        "style_groups": style_groups,
        "style_available": True,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-dir", default=str(ROOT / "reports" / "market_consensus"))
    args = ap.parse_args()
    out_dir = Path(args.json_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(DB)
    cur = con.cursor()
    rows = cur.execute(
        """SELECT analyst_id, view_date, market_direction, market_score, risk_level, position_bias, summary
           FROM analyst_daily_views WHERE view_type='market' ORDER BY view_date, analyst_id""").fetchall()
    profiles = {r[0]: r[1] for r in cur.execute("SELECT analyst_id, style FROM analyst_profiles")}
    con.close()

    # style_of: analyst_profiles.style 存英文枚举；非法/空值 → None
    style_of = {aid: s if s in STYLE_ENUM else None for aid, s in profiles.items()}

    by_date = {}
    for r in rows:
        by_date.setdefault(r[1], []).append({
            "analyst_id": r[0], "view_date": r[1], "market_direction": r[2],
            "market_score": r[3], "risk_level": r[4], "position_bias": r[5], "summary": r[6],
        })

    results = {}
    for date in sorted(by_date):
        day = compute_day(by_date[date], style_of)
        results[date] = day
        (out_dir / f"{date}.json").write_text(json.dumps(day, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "generated_at": "P2.1 v1",
        "weights": {"analyst_weight": WEIGHT_DEFAULT},
        "days": results,
    }
    (out_dir / "all_dates.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # 控制台预览
    print(f"{'日期':12} {'方向':<14} {'score':>7} {'elig':>4} {'覆盖':<11} {'多/中/空':>9} {'共识':<15} {'风险主导':>6}")
    for date, d in results.items():
        print(f"{date:12} {d['direction']:<14} {str(d['direction_score']):>7} {d['eligible_analysts']:>4} "
              f"{d['coverage_status']:<11} {d['bullish']}/{d['neutral']}/{d['bearish']:>3} {d['consensus_level']:<15} {d['risk']['dominant']:>6}")
    print(f"\n输出: {out_dir}/")
    return results


if __name__ == "__main__":
    main()
