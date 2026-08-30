#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
theme_daily_factors_p22b.py — P2.2B Theme Daily Factors（原始四因子，非 Heat Score）
===============================================================================
用户 2026-08-30 锁定口径：
  1) coverage_factor   = theme_analyst_count / daily_theme_eligible_analysts
                         当日提及该主题的 unique analysts / 当日有有效主题输出的分析师数（不固定 /10）
                         保留 direct_analyst_count（同分析师重复提同主题只计 1）
  2) mention_factor    = DIRECT 聚合到 analyst-theme-day 级：POSITIVE=+1 NEUTRAL=0 NEGATIVE=-1
                         同分析师·同日·同主题多条 → 合并为 1 单位（避免话多分析师隐性权重）
                         保存 positive/neutral/negative/net，不归一 0-100
  3) trade_factor      = aggregation_eligible_stock_events × confidence>=0.60 mapping
                         动作权重：BUY +1.00 ADD +0.80 LOW_BUY +0.70 TRIAL +0.40 /
                                   REDUCE -0.50 SELL -0.80 CLEAR -1.00 / WATCH·HOLD·UNKNOWN 0
                         DO_T: 方向 0，tactical_activity += 1（不做成净看多）
                         ⚠️ 一股多主题 fractional allocation：每主题贡献 = weight/N（防膨胀）
  4) holding_factor    = analyst_position_snapshots × mapping
                         holding_stock_count / holding_analyst_count / weighted_support
                         一股映射 N 主题 → 每主题 holding contribution = 1/N
                         ⚠️ 不做 continuity（留 P2.3 Momentum），第一版名 Holding Support

输出：data/p22b/theme_daily_factors.json（全网格零填充，19 L2 × 全日期）
      reports/theme_daily_factors_p22b.json + .md（汇总 + 抽样本）
Gate（benchmark 另脚本执行）：DIRECT analyst-theme-day 重复计权=0 / conf<0.6 参与=0 /
      excluded 3 events 参与=0 / COMPOSITE 拆分=0 / DO_T 进净方向=0 /
      一股多主题总贡献>原事件贡献=0 / lineage=100% / 重跑 duplicate=0

用法：python3 scripts/theme_daily_factors_p22b.py
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "analyst_consensus.db"
OUT_DIR = ROOT / "data" / "p22b"

# 动作权重（用户锁定）
ACTION_WEIGHT = {
    "BUY": 1.00, "ADD": 0.80, "LOW_BUY": 0.70, "TRIAL": 0.40,
    "REDUCE": -0.50, "SELL": -0.80, "CLEAR": -1.00,
    "WATCH": 0.0, "HOLD": 0.0, "UNKNOWN": 0.0,
}
# 动作计数桶（trade 输出里的 buy/add/reduce/sell 等）
TRADE_BUCKETS = ["BUY", "ADD", "LOW_BUY", "TRIAL", "REDUCE", "SELL", "CLEAR", "WATCH", "HOLD", "UNKNOWN"]
# 19 canonical L2
CANONICAL_L2 = [
    "TECH_SEMI", "TECH_OPTICS", "TECH_AI_COMPUTE", "TECH_COMPONENT", "TECH_PCB",
    "TECH_ELEC", "TECH_SOFTWARE", "TECH_GENERAL",
    "MED_INNOVATIVE_DRUG",
    "CYCL_NONFERROUS", "CYCL_CHEMICAL",
    "NEW_ENERGY_SOLID_BATTERY", "NEW_ENERGY_ELECTROLYTE", "NEW_ENERGY_UHV",
    "OTHER_BROKER", "OTHER_AGRICULTURE", "OTHER_ROBOTICS", "OTHER_SPACE", "OTHER_CONSUMER",
]
HEAT_MIN = 0.60


def load_heat_mapping(cur):
    """stock_code -> [theme_id,...]（confidence>=0.60，唯一）"""
    m = defaultdict(list)
    for r in cur.execute(
        "SELECT stock_code, theme_id FROM stock_theme_mapping WHERE confidence>=? ORDER BY confidence DESC",
        (HEAT_MIN,)):
        if r[1] not in m[r[0]]:
            m[r[0]].append(r[1])
    return m


def build_factors():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    heat_map = load_heat_mapping(cur)

    # ---------- 1. 日期全集（events∪mentions∪snapshots）----------
    dates = set()
    for r in cur.execute("SELECT DISTINCT event_date FROM analyst_stock_events"):
        dates.add(r[0])
    for r in cur.execute("SELECT DISTINCT mention_date FROM analyst_theme_mentions"):
        dates.add(r[0])
    for r in cur.execute("SELECT DISTINCT snapshot_date FROM analyst_position_snapshots"):
        dates.add(r[0])
    dates = sorted(dates)

    # ---------- 2. Coverage + Mention：DIRECT theme mentions ----------
    # 聚合到 analyst-theme-day
    adt = defaultdict(dict)   # (date, theme) -> {analyst: stance_sum}
    per_date_analysts = defaultdict(set)   # date -> 当日有 DIRECT 主题输出的分析师集合（分母）
    for r in cur.execute("""
        SELECT mention_date, analyst_id, theme_id, stance
        FROM analyst_theme_mentions WHERE mention_source='DIRECT'"""):
        d, a, t, stance = r
        st = {"POSITIVE": 1, "NEUTRAL": 0, "NEGATIVE": -1}.get(stance, 0)
        adt[(d, t)][a] = adt[(d, t)].get(a, 0) + st
        per_date_analysts[d].add(a)

    # ---------- 3. Trade：eligible events × fractional mapping ----------
    # (date, theme) -> {action_bucket: count, directional_value, tactical_activity, event_ids, conf_bad}
    trade = defaultdict(lambda: {**{b: 0.0 for b in TRADE_BUCKETS}, "DO_T": 0.0,
                                 "directional_value": 0.0, "tactical_activity": 0.0,
                                 "event_ids": set(), "conf_bad": 0})
    eligible_events = cur.execute("""
        SELECT event_id, event_date, stock_code, action_type
        FROM analyst_stock_events
        WHERE event_id NOT IN (SELECT event_id FROM consensus_event_exclusions)""").fetchall()
    for eid, d, scode, act in eligible_events:
        themes = heat_map.get(scode, [])
        if not themes:
            continue
        N = len(themes)
        w = ACTION_WEIGHT.get(act, 0.0)
        is_dot = (act == "DO_T")
        for t in themes:
            rec = trade[(d, t)]
            rec[act] += 1.0             # 动作计数：事件数（整数，描述该主题今日几笔该动作）
            if not is_dot:
                rec["directional_value"] += w / N   # 能量 fractional：防一条 BUY 创造 N 倍能量
            else:
                rec["tactical_activity"] += 1.0 / N  # DO_T 活动 fractional（Σ跨主题=1，满足 G6 守恒）
            rec["event_ids"].add(eid)

    # ---------- 4. Holding：snapshots × fractional mapping ----------
    # (date, theme) -> {stock_set, analyst_set, weighted_support, snapshot_ids}
    hold = defaultdict(lambda: {"stock_set": set(), "analyst_set": set(),
                                "weighted_support": 0.0, "snapshot_ids": set()})
    for r in cur.execute("""
        SELECT snapshot_date, analyst_id, stock_code, snapshot_id
        FROM analyst_position_snapshots WHERE position_state='HOLDING'"""):
        d, a, scode, sid = r
        themes = heat_map.get(scode, [])
        if not themes:
            continue
        N = len(themes)
        for t in themes:
            rec = hold[(d, t)]
            rec["stock_set"].add(scode)
            rec["analyst_set"].add(a)
            rec["weighted_support"] += 1.0 / N
            rec["snapshot_ids"].add(sid)

    # ---------- 5. 全网格零填充输出 ----------
    grid = []
    for d in dates:
        for t in CANONICAL_L2:
            # Coverage
            cov_analysts = set(adt.get((d, t), {}).keys())
            eligible = len(per_date_analysts.get(d, set()))
            direct_n = len(cov_analysts)
            # Mention：聚合单位按净情绪分桶
            pos = neu = neg = 0
            for a, s in adt.get((d, t), {}).items():
                if s > 0: pos += 1
                elif s < 0: neg += 1
                else: neu += 1
            net = pos - neg
            # Trade
            tr = trade.get((d, t), None)
            # Holding
            hd = hold.get((d, t), None)

            rec = {
                "date": d,
                "theme_id": t,
                "coverage": {
                    "analysts": len(cov_analysts),
                    "direct_analyst_count": direct_n,
                    "eligible_analysts": eligible,
                    "raw": round(len(cov_analysts) / eligible, 4) if eligible else 0.0,
                },
                "mention": {
                    "positive": pos, "neutral": neu, "negative": neg, "net": net,
                    "units": pos + neu + neg,
                },
                "trade": None if tr is None else {
                    "buy": round(tr["BUY"], 4), "add": round(tr["ADD"], 4),
                    "low_buy": round(tr["LOW_BUY"], 4), "trial": round(tr["TRIAL"], 4),
                    "reduce": round(tr["REDUCE"], 4), "sell": round(tr["SELL"], 4),
                    "clear": round(tr["CLEAR"], 4),
                    "watch": round(tr["WATCH"], 4), "hold": round(tr["HOLD"], 4),
                    "unknown": round(tr["UNKNOWN"], 4),
                    "directional_value": round(tr["directional_value"], 4),
                    "tactical_activity": round(tr["tactical_activity"], 4),
                    "event_count": len(tr["event_ids"]),
                },
                "holding": None if hd is None else {
                    "stocks": len(hd["stock_set"]),
                    "analysts": len(hd["analyst_set"]),
                    "weighted_support": round(hd["weighted_support"], 4),
                    "snapshot_count": len(hd["snapshot_ids"]),
                },
            }
            grid.append(rec)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "theme_daily_factors.json").write_text(
        json.dumps(grid, ensure_ascii=False, indent=2), encoding="utf-8")
    con.close()
    return grid, dates


if __name__ == "__main__":
    grid, dates = build_factors()
    # 汇总展示：每个日期·每个主题的 raw 三元组
    from collections import Counter
    active = [r for r in grid if r["mention"]["units"] > 0 or
              (r["trade"] and (r["trade"]["directional_value"] != 0 or r["trade"]["event_count"] > 0)) or
              (r["holding"] and r["holding"]["weighted_support"] > 0)]
    print(f"全网格: {len(grid)} 行 ({len(dates)} 日期 × {len(grid)//max(len(dates),1)} 主题)")
    print(f"有信号行: {len(active)}")
    # 展示 08-28 的信号主题
    print("\n=== 2026-08-28 信号摘要（按 |directional_value| 排序）===")
    day = [r for r in active if r["date"] == "2026-08-28"]
    day.sort(key=lambda r: abs((r["trade"] or {}).get("directional_value", 0)), reverse=True)
    for r in day:
        tr = r["trade"] or {}
        hd = r["holding"] or {}
        print(f"  {r['theme_id']:24s} cov={r['coverage']['raw']:.3f}({r['coverage']['analysts']}/{r['coverage']['eligible_analysts']}) "
              f"ment={r['mention']['net']:+d} dir={tr.get('directional_value',0):+.2f} tac={tr.get('tactical_activity',0):.1f} "
              f"hold={hd.get('weighted_support',0):.2f}({hd.get('stocks',0)}只/{hd.get('analysts',0)}人)")
