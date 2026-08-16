#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2.3.4 Observation Mode — 研究系统观察期仪表盘（每日快照 + RS 分层观察）
非功能模块：只读数据 + 写入每日快照表，不修改任何评分/算法。
三个观察指标：
  ① RS 排序能力：RS 分层 × T+1/T+3/T+5 表现
  ② Graph Score 额外价值：RS×GS 四象限组合观察
  ③ Research Confidence 有效性：高/低 Confidence 样本对比
每日快照写入 research_system_snapshot，供 v2.4 调参做历史对比。
"""
import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

DB = "/root/workspace/research_archive.db"
TZ = ZoneInfo("Asia/Shanghai")
VERSION = "v2.3.4"


def main():
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # ── 建快照表 ──
    con.execute("""
    CREATE TABLE IF NOT EXISTS research_system_snapshot (
        snap_date TEXT PRIMARY KEY,
        system_version TEXT,
        doc_total INTEGER, doc_high INTEGER,
        industry_total INTEGER, graph_relations INTEGER,
        validation_total INTEGER, t1_done INTEGER, t3_done INTEGER, t5_done INTEGER,
        rs_80 INTEGER, rs_60_79 INTEGER, rs_40_59 INTEGER, rs_lt40 INTEGER,
        rs_layers TEXT, gs_combos TEXT, confidence_comp TEXT,
        momentum_layers TEXT, model_contrib TEXT,
        market_regime TEXT,
        created_at TEXT
    )""")
    # 幂等补列（旧快照表缺新字段）
    for _col, _ddl in [("momentum_layers", "TEXT"), ("model_contrib", "TEXT"), ("market_regime", "TEXT")]:
        try:
            con.execute(f"ALTER TABLE research_system_snapshot ADD COLUMN {_col} {_ddl}")
        except Exception:
            pass
    con.commit()

    lines = []
    lines.append("=" * 56)
    lines.append(f"🧭 v2.3.4 Observation Mode · {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 56)

    # ── ① 系统健康总览 ──
    doc_total = con.execute("SELECT COUNT(*) FROM research_document").fetchone()[0]
    doc_high = con.execute("SELECT COUNT(*) FROM research_document WHERE quality_score>=50").fetchone()[0]
    ind_total = con.execute("SELECT COUNT(*) FROM industry_entity WHERE status='active'").fetchone()[0]
    graph_n = con.execute("SELECT COUNT(*) FROM research_graph_relation").fetchone()[0]
    val_total = con.execute("SELECT COUNT(*) FROM research_validation").fetchone()[0]
    t1_done = con.execute("SELECT COUNT(*) FROM research_validation WHERE t1_pct IS NOT NULL").fetchone()[0]
    t3_done = con.execute("SELECT COUNT(*) FROM research_validation WHERE t3_pct IS NOT NULL").fetchone()[0]
    t5_done = con.execute("SELECT COUNT(*) FROM research_validation WHERE t5_pct IS NOT NULL").fetchone()[0]

    lines.append("")
    lines.append("📊 系统健康总览")
    lines.append(f"  研究对象:        {doc_total}（高质量≥50: {doc_high}）")
    lines.append(f"  行业实体:        {ind_total}")
    lines.append(f"  图谱关系:        {graph_n}")
    lines.append(f"  验证样本:        {val_total}（T+1: {t1_done} / T+3: {t3_done} / T+5: {t5_done}）")
    lines.append(f"  当前阶段:        稳定积累期（目标 T+5≥100 / 交易日≥20）")

    # ── ② RS 分层观察 ──
    def rs_layer_stats(min_s, max_s):
        rows = con.execute("""
            SELECT research_score, t1_pct, t3_pct, t5_pct, result FROM research_validation
            WHERE research_score >= ? AND research_score < ?""", (min_s, max_s)).fetchall()
        n = len(rows)
        if n == 0:
            return {"n": 0}
        t1s = [r["t1_pct"] for r in rows if r["t1_pct"] is not None]
        t3s = [r["t3_pct"] for r in rows if r["t3_pct"] is not None]
        t5s = [r["t5_pct"] for r in rows if r["t5_pct"] is not None]
        hits = sum(1 for r in rows if r["result"] == "hit")
        done = sum(1 for r in rows if r["result"] in ("hit", "miss", "flat"))
        return {
            "n": n,
            "t1_n": len(t1s), "t1_avg": round(sum(t1s) / len(t1s), 2) if t1s else None,
            "t3_n": len(t3s), "t3_avg": round(sum(t3s) / len(t3s), 2) if t3s else None,
            "t5_n": len(t5s), "t5_avg": round(sum(t5s) / len(t5s), 2) if t5s else None,
            "hit_rate": round(hits / done * 100, 1) if done else None,
            "done": done,
        }

    layers = {
        "90+": rs_layer_stats(90, 101),
        "80-89": rs_layer_stats(80, 90),
        "70-79": rs_layer_stats(70, 80),
        "60-69": rs_layer_stats(60, 70),
        "<60": rs_layer_stats(0, 60),
    }
    lines.append("")
    lines.append("🎯 RS 分层观察（高 RS 是否未来表现更好？）")
    lines.append(f"  {'区间':<8}{'样本':>6}{'T+1':>9}{'T+3':>9}{'T+5':>9}{'命中率':>9}")
    for k, v in layers.items():
        if v["n"] == 0:
            lines.append(f"  {k:<10}{0:>6}")
            continue
        lines.append(f"  {k:<10}{v['n']:>6}"
                     f"{str(v['t1_avg']):>9}{str(v['t3_avg']):>9}{str(v['t5_avg']):>9}"
                     f"{str(v['hit_rate']):>9}")

    # ── ③ GS 组合观察（RS×GS 四象限）──
    gs_combos = {"high_rs_high_gs": {"n": 0, "t5": [], "hit": 0, "done": 0},
                 "high_rs_low_gs": {"n": 0, "t5": [], "hit": 0, "done": 0},
                 "low_rs_high_gs": {"n": 0, "t5": [], "hit": 0, "done": 0},
                 "low_rs_low_gs": {"n": 0, "t5": [], "hit": 0, "done": 0}}
    # 股票 → GS（图谱）
    stock_gs = {}
    for r in con.execute("SELECT DISTINCT target_id FROM research_graph_relation WHERE target_type='stock'"):
        c = str(r["target_id"])
        if c not in stock_gs:
            # GS = 事件数×2 + 行业数（简化，图谱 centrality 的事件/行业因子）
            evs = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='event' AND target_type='stock' AND target_id=?", (c,)).fetchone()[0]
            inds = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='stock' AND target_type='industry' AND source_id=?", (c,)).fetchone()[0]
            stock_gs[c] = min(100, evs * 5 + inds * 2)
    for r in con.execute("SELECT stock_code, research_score, t5_pct, result FROM research_validation"):
        gs = stock_gs.get(str(r["stock_code"]), 0)
        rs = r["research_score"] or 0
        high_rs = rs >= 60
        high_gs = gs >= 40
        key = ("high_rs_" if high_rs else "low_rs_") + ("high_gs" if high_gs else "low_gs")
        c = gs_combos[key]
        c["n"] += 1
        if r["t5_pct"] is not None:
            c["t5"].append(r["t5_pct"])
        if r["result"] in ("hit", "miss", "flat"):
            c["done"] += 1
            if r["result"] == "hit":
                c["hit"] += 1
    lines.append("")
    lines.append("🧩 RS×GS 四象限（主题强≠个股好）")
    for k, v in gs_combos.items():
        t5avg = round(sum(v["t5"]) / len(v["t5"]), 2) if v["t5"] else None
        hr = round(v["hit"] / v["done"] * 100, 1) if v["done"] else None
        lines.append(f"  {k:<20} n={v['n']:<5} T+5={t5avg} 命中率={hr}")

    # ── ④ Confidence 对比（经文档 published_by 机构数分组）──
    conf_comp = {"high_conf": {"n": 0, "t5": [], "hit": 0, "done": 0},
                 "low_conf": {"n": 0, "t5": [], "hit": 0, "done": 0}}
    for r in con.execute("SELECT stock_code, t5_pct, result FROM research_validation"):
        c = str(r["stock_code"])
        insts = con.execute("""SELECT COUNT(DISTINCT target_id) FROM research_graph_relation
                               WHERE source_type='stock' AND relation_type='followed_by' AND source_id=?""", (c,)).fetchone()[0]
        evs = con.execute("""SELECT COUNT(*) FROM research_graph_relation
                             WHERE source_type='event' AND target_type='stock' AND target_id=?""", (c,)).fetchone()[0]
        conf = min(100, insts * 20 + evs * 10)
        key = "high_conf" if conf >= 40 else "low_conf"
        cc = conf_comp[key]
        cc["n"] += 1
        if r["t5_pct"] is not None:
            cc["t5"].append(r["t5_pct"])
        if r["result"] in ("hit", "miss", "flat"):
            cc["done"] += 1
            if r["result"] == "hit":
                cc["hit"] += 1
    lines.append("")
    lines.append("✅ Confidence 对比（市场认可度）")
    for k, v in conf_comp.items():
        t5avg = round(sum(v["t5"]) / len(v["t5"]), 2) if v["t5"] else None
        hr = round(v["hit"] / v["done"] * 100, 1) if v["done"] else None
        lines.append(f"  {k:<12} n={v['n']:<5} T+5={t5avg} 命中率={hr}")

    # ── ⑤ Event Momentum 分层验证（v1.7 事件热度是否有效）──
    mom_layers = {"80+": {"n": 0, "hit": 0, "done": 0, "t5": []},
                  "60-79": {"n": 0, "hit": 0, "done": 0, "t5": []},
                  "<60": {"n": 0, "hit": 0, "done": 0, "t5": []}}
    for r in con.execute("""SELECT v.t5_pct, v.result,
        (SELECT MAX(momentum_score) FROM event_momentum WHERE event_id=v.event_id) peak
        FROM research_validation v WHERE v.event_id IS NOT NULL"""):
        peak = r["peak"]
        if peak is None:
            continue
        key = "80+" if peak >= 80 else ("60-79" if peak >= 60 else "<60")
        c = mom_layers[key]
        c["n"] += 1
        if r["t5_pct"] is not None:
            c["t5"].append(r["t5_pct"])
        if r["result"] in ("hit", "miss", "flat"):
            c["done"] += 1
            if r["result"] == "hit":
                c["hit"] += 1
    lines.append("")
    lines.append("🔥 Event Momentum 分层（事件热度是否有效？）")
    lines.append(f"  {'Momentum':<12}{'样本':>6}{'T+5':>9}{'命中率':>9}")
    for k, v in mom_layers.items():
        t5avg = round(sum(v["t5"]) / len(v["t5"]), 2) if v["t5"] else None
        hr = round(v["hit"] / v["done"] * 100, 1) if v["done"] else None
        lines.append(f"  {k:<14}{v['n']:>6}{str(t5avg):>9}{str(hr):>9}")

    # ── ⑥ 十大模型贡献分析（research_scores.model_detail → validation 表现）──
    model_contrib = {}
    for r in con.execute("SELECT stock_code, model_detail FROM research_scores WHERE model_detail IS NOT NULL AND model_detail != '{}'"):
        try:
            md = json.loads(r["model_detail"] or "{}")
            m = md.get("model") if isinstance(md, dict) else None
        except Exception:
            m = None
        if not m:
            continue
        c = model_contrib.setdefault(m, {"n": 0, "hit": 0, "done": 0, "t5": []})
        # 该股票的 validation 表现（可能有多个样本，取最新）
        v = con.execute("SELECT t5_pct, result FROM research_validation WHERE stock_code=? ORDER BY id DESC LIMIT 1", (r["stock_code"],)).fetchone()
        if not v:
            continue
        c["n"] += 1
        if v["t5_pct"] is not None:
            c["t5"].append(v["t5_pct"])
        if v["result"] in ("hit", "miss", "flat"):
            c["done"] += 1
            if v["result"] == "hit":
                c["hit"] += 1
    lines.append("")
    lines.append("🧮 十大模型贡献（当前模型 × 验证表现，权重不变）")
    lines.append(f"  {'模型':<16}{'样本':>6}{'T+5':>9}{'命中率':>9}")
    for m, v in sorted(model_contrib.items(), key=lambda x: -x[1]["n"])[:10]:
        t5avg = round(sum(v["t5"]) / len(v["t5"]), 2) if v["t5"] else None
        hr = round(v["hit"] / v["done"] * 100, 1) if v["done"] else None
        lines.append(f"  {m:<18}{v['n']:>6}{str(t5avg):>9}{str(hr):>9}")

    lines.append("")
    lines.append("📌 观察期规则：只修必要问题，不改算法/评分/状态机。")
    lines.append("   v2.4 启动条件补充：市场环境覆盖（强势/震荡/弱势周期）")
    lines.append("=" * 56)

    # ── 写快照 ──
    # v2.3.4e 市场环境（复用日报同款逻辑：研究池等权代理）
    regime = "未标注"
    try:
        _kd = json.load(open("/root/vip1_reports/kline_data.json", encoding="utf-8")).get("kline_data") or {}
        _daily = {}
        for _code, _info in _kd.items():
            _hist = _info.get("kline_history") or []
            _prev = None
            for _b in _hist:
                _c = _b.get("close")
                _d = _b.get("trade_date")
                if not _c or not _d:
                    _prev = _c; continue
                _pct = (_c / _prev - 1) * 100 if _prev else 0.0
                _rec = _daily.setdefault(_d, {"up": 0, "down": 0, "flat": 0, "limit_up": 0})
                if _pct >= 1.0: _rec["up"] += 1
                elif _pct <= -1.0: _rec["down"] += 1
                else: _rec["flat"] += 1
                if _pct >= 9.5: _rec["limit_up"] += 1
                _prev = _c
        if _daily:
            _last = max(_daily.keys())
            _r = _daily[_last]
            _tot = max(_r["up"] + _r["down"] + _r["flat"], 1)
            _up_ratio = _r["up"] / _tot
            _label = "强势" if (_up_ratio >= 0.6) else ("弱势" if _up_ratio <= 0.4 else "震荡")
            regime = f"{_label}（上涨{_r['up']}/{_tot} {_up_ratio*100:.0f}% 涨停≈{_r['limit_up']}）"
    except Exception:
        pass
    con.execute("""
    INSERT OR REPLACE INTO research_system_snapshot
        (snap_date, system_version, doc_total, doc_high, industry_total, graph_relations,
         validation_total, t1_done, t3_done, t5_done,
         rs_80, rs_60_79, rs_40_59, rs_lt40, rs_layers, gs_combos, confidence_comp,
         momentum_layers, model_contrib, market_regime, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (today, VERSION, doc_total, doc_high, ind_total, graph_n,
         val_total, t1_done, t3_done, t5_done,
         layers["90+"]["n"] + layers["80-89"]["n"], layers["70-79"]["n"] + layers["60-69"]["n"],
         layers["<60"]["n"], 0,
         json.dumps(layers, ensure_ascii=False), json.dumps(gs_combos, ensure_ascii=False),
         json.dumps(conf_comp, ensure_ascii=False),
         json.dumps(mom_layers, ensure_ascii=False), json.dumps(model_contrib, ensure_ascii=False),
         regime, now.strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    con.close()

    report = "\n".join(lines)
    print(report)
    with open("/var/log/research-obs.log", "a", encoding="utf-8") as f:
        f.write(report + "\n\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
