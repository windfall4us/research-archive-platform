#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
theme_heat_score_p22c.py — P2.2C Theme Heat Score（0-100 固定语义归一化）
===========================================================================
用户 2026-08-30 锁定口径：

1) 四因子权重（P2.2C 不调权）：
   Theme Heat = 30% Coverage + 25% Mention + 25% Trade + 20% Holding Support

2) 固定语义归一化（非 min-max，避免样本内失真与历史漂移）：
   coverage_score = 100 × theme_unique_analysts / daily_direct_theme_eligible_analysts
   mention_score  = 100 × max(0, (positive - negative) / eligible_analysts)
                    NEUTRAL 不加热不扣热（其关注价值已在 Coverage 体现）
   trade_score    = 100 × max(0, Σ clipped_analyst_trade / daily_trade_active_analysts)
                    每个 (analyst,theme,day) raw 先 clip(-1,+1) 再聚合
                    DO_T 不进方向（只进 tactical_activity）
                    fractional：1 event → N themes，每主题 weight/N
   holding_score  = 100 × Σ capped_analyst_holding / daily_position_active_analysts
                    每个 (analyst,theme,day) 先 fractional(1/N)，再 min(1.0)
                    只反映"有多少分析师持仓支持"，不反映股票数量竞赛

3) Missing ≠ Zero（P1.3 已确定：没看到 snapshot 不能推断无持仓）：
   某日整个数据源缺失 → score = NULL, available = false
   只在数据可用因子间重新归一权重：
     heat_score = Σ(score_i × w_i) / Σ(available_w_i)
   data_completeness = Σ(available_w_i) / 100
     >= 0.80 NORMAL | 0.60~0.79 LOW_CONFIDENCE | <0.60 INSUFFICIENT_DATA

4) 输出档位（无时间序列含义，趋势留 P2.3）：
   80-100 HOT | 65-79.99 HEATING | 45-64.99 ACTIVE | 25-44.99 COOL | 0-24.99 COLD

输入：data/analyst_consensus.db（analyst_theme_mentions / analyst_stock_events /
      analyst_position_snapshots / stock_theme_mapping / consensus_event_exclusions）
输出：data/p22c/theme_heat_scores.json + reports/theme_heat_scores_p22c.json/.md

用法：python3 scripts/theme_heat_score_p22c.py
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
LEXICON = ROOT / "scripts" / "theme_lexicon_p20c.json"
OUT_DIR = ROOT / "data" / "p22c"
HEAT_MIN = 0.60

# 四因子权重
W_COVERAGE = 0.30
W_MENTION = 0.25
W_TRADE = 0.25
W_HOLDING = 0.20

# 动作权重（与 P2.2B 一致）
ACTION_WEIGHT = {
    "BUY": 1.00, "ADD": 0.80, "LOW_BUY": 0.70, "TRIAL": 0.40,
    "REDUCE": -0.50, "SELL": -0.80, "CLEAR": -1.00,
    "WATCH": 0.0, "HOLD": 0.0, "UNKNOWN": 0.0,
}
STANCE_VALUE = {"POSITIVE": 1, "NEUTRAL": 0, "NEGATIVE": -1}

# 19 canonical L2
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


def load_theme_names():
    lex = json.load(open(LEXICON, encoding="utf-8"))
    return {f"{l1k}_{l2k}": l2["name"] for l1k, l1 in lex["l1"].items()
            for l2k, l2 in l1["l2"].items()}


def load_heat_mapping(cur):
    """stock_code -> [theme_id,...]（confidence>=0.60，唯一）"""
    m = defaultdict(list)
    for r in cur.execute(
        "SELECT stock_code, theme_id FROM stock_theme_mapping WHERE confidence>=? ORDER BY confidence DESC",
        (HEAT_MIN,)):
        if r[1] not in m[r[0]]:
            m[r[0]].append(r[1])
    return m


def compute():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    theme_names = load_theme_names()
    heat_map = load_heat_mapping(cur)

    # ---------- 1. 日期全集 ----------
    dates = set()
    for r in cur.execute("SELECT DISTINCT event_date FROM analyst_stock_events"):
        dates.add(r[0])
    for r in cur.execute("SELECT DISTINCT mention_date FROM analyst_theme_mentions"):
        dates.add(r[0])
    for r in cur.execute("SELECT DISTINCT snapshot_date FROM analyst_position_snapshots"):
        dates.add(r[0])
    dates = sorted(dates)

    # ---------- 2. Coverage + Mention：分析师级聚合 ----------
    # (date, theme) -> {analyst: stance_sum}
    mention_adt = defaultdict(dict)
    per_date_mention_analysts = defaultdict(set)
    for r in cur.execute("""
        SELECT mention_date, analyst_id, theme_id, stance
        FROM analyst_theme_mentions WHERE mention_source='DIRECT'"""):
        d, a, t, stance = r
        v = STANCE_VALUE.get(stance, 0)
        mention_adt[(d, t)][a] = mention_adt[(d, t)].get(a, 0) + v
        per_date_mention_analysts[d].add(a)

    # ---------- 3. Trade：分析师级聚合 + clip ----------
    # (date, theme) -> {analyst: raw_directional}（clip 前）
    trade_adt_raw = defaultdict(dict)
    trade_tactical = defaultdict(lambda: defaultdict(float))  # (d,t) -> {analyst: tactical}
    per_date_trade_analysts = defaultdict(set)

    eligible_events = cur.execute("""
        SELECT event_id, event_date, stock_code, action_type, analyst_id
        FROM analyst_stock_events
        WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)""").fetchall()

    for eid, d, scode, act, a in eligible_events:
        themes = heat_map.get(scode, [])
        if not themes:
            continue
        per_date_trade_analysts[d].add(a)
        N = len(themes)
        w = ACTION_WEIGHT.get(act, 0.0)
        is_dot = (act == "DO_T")
        for t in themes:
            if is_dot:
                # DO_T 不进方向，只进 tactical
                trade_tactical[(d, t)][a] = trade_tactical[(d, t)].get(a, 0.0) + 1.0 / N
            else:
                trade_adt_raw[(d, t)][a] = trade_adt_raw[(d, t)].get(a, 0.0) + w / N

    # ---------- 4. Holding：分析师级聚合 + cap ----------
    # (date, theme) -> {analyst: fractional_support}（cap 前）
    hold_adt_raw = defaultdict(dict)
    per_date_holding_analysts = defaultdict(set)

    snapshots = cur.execute("""
        SELECT snapshot_date, analyst_id, stock_code
        FROM analyst_position_snapshots WHERE position_state='HOLDING'""").fetchall()

    for d, a, scode in snapshots:
        themes = heat_map.get(scode, [])
        if not themes:
            continue
        per_date_holding_analysts[d].add(a)
        N = len(themes)
        for t in themes:
            hold_adt_raw[(d, t)][a] = hold_adt_raw[(d, t)].get(a, 0.0) + 1.0 / N

    # ---------- 5. 每日数据可用性（Missing ≠ Zero）----------
    # 某日整个数据源缺失 → available=false → score=NULL → 该因子权重从分母剔除
    availability = {}
    for d in dates:
        avail = {}
        avail["coverage"] = len(per_date_mention_analysts.get(d, set())) > 0
        avail["mention"] = avail["coverage"]
        avail["trade"] = len(per_date_trade_analysts.get(d, set())) > 0
        avail["holding"] = len(per_date_holding_analysts.get(d, set())) > 0
        availability[d] = avail

    # ---------- 6. 逐 (date, theme) 计算 Heat ----------
    grid = []
    for d in dates:
        elig_cov = len(per_date_mention_analysts.get(d, set()))
        elig_trade = len(per_date_trade_analysts.get(d, set()))
        elig_hold = len(per_date_holding_analysts.get(d, set()))
        avail = availability[d]

        for t in CANONICAL_L2:
            # --- Coverage ---
            cov_analysts = set(mention_adt.get((d, t), {}).keys())
            cov_n = len(cov_analysts)
            cov_score = 100.0 * cov_n / elig_cov if avail["coverage"] and elig_cov > 0 else None

            # --- Mention ---
            pos = sum(1 for a, s in mention_adt.get((d, t), {}).items() if s > 0)
            neu = sum(1 for a, s in mention_adt.get((d, t), {}).items() if s == 0)
            neg = sum(1 for a, s in mention_adt.get((d, t), {}).items() if s < 0)
            mention_net = pos - neg
            if avail["mention"] and elig_cov > 0:
                mention_score = 100.0 * max(0.0, mention_net / elig_cov)
            else:
                mention_score = None

            # --- Trade（analyst-level clip）---
            raw_entries = trade_adt_raw.get((d, t), {})
            clipped_sum = 0.0
            clipped_per_analyst = {}
            for a, raw in raw_entries.items():
                c = clip(raw)
                clipped_per_analyst[a] = round(c, 4)
                clipped_sum += c
            raw_directional = round(sum(raw_entries.values()), 4)
            tac_sum = round(sum(trade_tactical.get((d, t), {}).values()), 4)
            active_analysts = len(set(raw_entries.keys()) | set(trade_tactical.get((d, t), {}).keys()))
            if avail["trade"] and elig_trade > 0:
                trade_score = 100.0 * max(0.0, clipped_sum / elig_trade)
            else:
                trade_score = None

            # --- Holding（analyst-level cap）---
            hold_entries = hold_adt_raw.get((d, t), {})
            capped_sum = 0.0
            capped_per_analyst = {}
            for a, support in hold_entries.items():
                c = min(1.0, support)
                capped_per_analyst[a] = round(c, 4)
                capped_sum += c
            weighted_support = round(sum(hold_entries.values()), 4)
            if avail["holding"] and elig_hold > 0:
                holding_score = 100.0 * capped_sum / elig_hold
            else:
                holding_score = None

            # 当日该主题映射到的持仓股数（distinct stock_code，仅可映射的）
            holding_stocks = {r[0] for r in cur.execute("""
                SELECT DISTINCT p.stock_code FROM analyst_position_snapshots p
                WHERE p.snapshot_date=? AND p.position_state='HOLDING'
                  AND EXISTS (SELECT 1 FROM stock_theme_mapping m
                              WHERE m.stock_code=p.stock_code AND m.theme_id=? AND m.confidence>=?)""",
                (d, t, HEAT_MIN))}

            # --- Heat 合成（Missing ≠ Zero：只在可用因子间重归一）---
            factors = [
                ("coverage", cov_score, W_COVERAGE, avail["coverage"]),
                ("mention", mention_score, W_MENTION, avail["mention"]),
                ("trade", trade_score, W_TRADE, avail["trade"]),
                ("holding", holding_score, W_HOLDING, avail["holding"]),
            ]
            num = 0.0
            den = 0.0
            for name, score, w, is_avail in factors:
                if is_avail and score is not None:
                    num += score * w
                    den += w
            heat_score = num / den if den > 0 else None
            # den 已经是可用权重之和（0.30+0.25+0.25+0.20=1.0 形式），即 completeness
            data_completeness = den
            if data_completeness >= 0.80:
                completeness = "NORMAL"
            elif data_completeness >= 0.60:
                completeness = "LOW_CONFIDENCE"
            else:
                completeness = "INSUFFICIENT_DATA"

            # 档位（无时间序列含义）
            if heat_score is None:
                level = "NO_DATA"
            elif heat_score >= 80:
                level = "HOT"
            elif heat_score >= 65:
                level = "HEATING"
            elif heat_score >= 45:
                level = "ACTIVE"
            elif heat_score >= 25:
                level = "COOL"
            else:
                level = "COLD"

            rec = {
                "date": d,
                "theme_id": t,
                "theme_name": theme_names.get(t, t),
                "heat_score": round(heat_score, 2) if heat_score is not None else None,
                "heat_level": level,
                "factors": {
                    "coverage": {
                        "score": round(cov_score, 2) if cov_score is not None else None,
                        "weight": W_COVERAGE,
                        "available": avail["coverage"],
                        "analysts": cov_n,
                        "eligible": elig_cov,
                    },
                    "mention": {
                        "score": round(mention_score, 2) if mention_score is not None else None,
                        "weight": W_MENTION,
                        "available": avail["mention"],
                        "positive": pos,
                        "neutral": neu,
                        "negative": neg,
                        "net": mention_net,
                    },
                    "trade": {
                        "score": round(trade_score, 2) if trade_score is not None else None,
                        "weight": W_TRADE,
                        "available": avail["trade"],
                        "raw_directional_value": raw_directional,
                        "analyst_capped_value": round(clipped_sum, 4),
                        "clipped_per_analyst": clipped_per_analyst,
                        "tactical_activity": tac_sum,
                        "active_analysts": active_analysts,
                        "eligible": elig_trade,
                    },
                    "holding": {
                        "score": round(holding_score, 2) if holding_score is not None else None,
                        "weight": W_HOLDING,
                        "available": avail["holding"],
                        "weighted_support": weighted_support,
                        "capped_value": round(capped_sum, 4),
                        "capped_per_analyst": capped_per_analyst,
                        "stocks": len(holding_stocks),
                        "eligible": elig_hold,
                    },
                },
                "data_completeness": round(data_completeness, 4),
                "completeness_level": completeness,
            }
            grid.append(rec)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "theme_heat_scores.json").write_text(
        json.dumps(grid, ensure_ascii=False, indent=2), encoding="utf-8")
    con.close()
    return grid, dates, availability


if __name__ == "__main__":
    grid, dates, avail = compute()
    print(f"全网格: {len(grid)} 行 ({len(dates)} 日期 × {len(grid)//max(len(dates),1)} 主题)")
    print("\n=== 每日可用性（Missing≠Zero 检查）===")
    for d in dates:
        a = avail[d]
        print(f"  {d}: cov={a['coverage']} men={a['mention']} trade={a['trade']} holding={a['holding']}")
    print("\n=== 2026-08-28 排序（按 heat_score）===")
    day = [r for r in grid if r["date"] == "2026-08-28" and r["heat_score"] is not None]
    day.sort(key=lambda r: r["heat_score"], reverse=True)
    for r in day:
        f = r["factors"]
        print(f"  {r['theme_id']:24s} {r['heat_score']:5.1f} {r['heat_level']:11s} "
              f"cov={f['coverage']['score']} men={f['mention']['score']} "
              f"trd={f['trade']['score']} hold={f['holding']['score']} comp={r['completeness_level']}")
