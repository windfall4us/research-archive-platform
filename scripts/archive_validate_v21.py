#!/usr/bin/env python3
"""资讯研究档案库 v2.1 - Research Validation 验证引擎
对 research_scores 快照做后验验证：用 kline_data.json 日线计算 T+1/T+3/T+5 表现、
最大涨幅/回撤，判定验证结果（hit=区间最大涨幅>=5% / miss=最大回撤>=-5% / pending / insufficient）。
安全边界：纯研究回测，不生成交易信号。
2026-08-12
"""
import json, sqlite3, sys
from datetime import datetime, timedelta

DB = "/root/workspace/research_archive.db"
KLINE = "/root/vip1_reports/kline_data.json"
SYSTEM_VERSION = "v2.0.0"

HIT_THRESHOLD = 5.0    # 最大涨幅 >=5% → hit
MISS_THRESHOLD = -5.0  # 最大回撤 <=-5% → miss


def load_kline():
    """{code: {date: {close, high, low}}}"""
    try:
        d = json.load(open(KLINE))
        out = {}
        for code, info in (d.get("kline_data") or {}).items():
            bars = {}
            for b in (info.get("kline_history") or []):
                bars[b["trade_date"]] = {"close": b.get("close"), "high": b.get("high"), "low": b.get("low")}
            out[code] = bars
        return out
    except Exception as e:
        print("kline 加载失败:", e)
        return {}


def next_trading_days(dates_sorted, from_date, n):
    """从 from_date 之后找 n 个交易日"""
    out = []
    for d in dates_sorted:
        if d > from_date:
            out.append(d)
            if len(out) >= n:
                break
    return out


def validate_one(con, row, kline):
    """对单条 research_scores 快照做验证（v2.3.4c 起带 3 个快照字段）"""
    code, name, rscore, status, state, eid, etitle, created, model_detail, explanation_json, event_score, model_score, technical_score, capital_score, momentum_score = row
    trigger_date = created[:10]
    bars = kline.get(code)
    if not bars or not bars.get(trigger_date):
        return None  # 无行情
    dates = sorted(bars.keys())
    base = bars[trigger_date]["close"]
    if not base:
        return None
    # 找 T+1/T+3/T+5
    after = [d for d in dates if d > trigger_date]
    t1 = after[0] if len(after) >= 1 else None
    t3 = after[2] if len(after) >= 3 else None
    t5 = after[4] if len(after) >= 5 else None
    # 区间（T+1~T+5 或到数据末尾）：最大涨幅/回撤
    window = after[:5] if len(after) >= 1 else []
    max_up = 0.0
    max_dd = 0.0
    if window:
        highs = [bars[d]["high"] for d in window if bars[d].get("high")]
        lows = [bars[d]["low"] for d in window if bars[d].get("low")]
        if highs:
            max_up = round((max(highs) / base - 1) * 100, 2)
        if lows:
            max_dd = round((min(lows) / base - 1) * 100, 2)
    # 判定
    if not t1:
        result = "pending"
    elif len(after) < 3:
        result = "pending"
    else:
        if max_up >= HIT_THRESHOLD:
            result = "hit"
        elif max_dd <= MISS_THRESHOLD:
            result = "miss"
        else:
            result = "flat"
    note = ""
    if t1:
        note = f"T+1:{t1}({(bars[t1]['close']/base-1)*100:+.1f}%)"
    if t3:
        note += f" T+3:{t3}({(bars[t3]['close']/base-1)*100:+.1f}%)"
    if t5:
        note += f" T+5:{t5}({(bars[t5]['close']/base-1)*100:+.1f}%)"
    # v2.3.4c 快照：模型/事件/图谱（保存"当时"状态，供 v2.4 解释）
    import re as _re
    try:
        md = json.loads(model_detail or "{}") or {}
        models = [{"name": md.get("model", ""), "score": round(md.get("final_score") or 0, 1),
                   "matched": bool(md.get("matched"))}]
    except Exception:
        md = {}; models = []
    model_snap = {"models": models, "model_score": model_score or 0,
                  "technical_score": technical_score or 0, "capital_score": capital_score or 0}
    inst_n = 0
    try:
        exp = json.loads(explanation_json or "{}") or {}
        for c in (exp.get("contributions") or []):
            lbl = str(c.get("label", ""))
            m = _re.search(r"(\d+)家机构", lbl)
            if m:
                inst_n = int(m.group(1))
    except Exception:
        pass
    event_snap = {"event_score": event_score or 0, "momentum": momentum_score or 0,
                  "institution_count": inst_n, "event_title": (etitle or "")[:120]}
    c_stk = str(code)
    gs_evs = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='event' AND target_type='stock' AND target_id=?", (c_stk,)).fetchone()[0]
    gs_inds = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='stock' AND target_type='industry' AND source_id=?", (c_stk,)).fetchone()[0]
    gs_insts = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='stock' AND relation_type='followed_by' AND source_id=?", (c_stk,)).fetchone()[0]
    graph_snap = {"stock_centrality": min(100, gs_evs * 5 + gs_inds * 2),
                  "confidence": min(100, gs_insts * 20)}

    return {
        "stock_code": code, "stock_name": name or "", "research_score": rscore,
        "score_status": status, "research_state": state, "event_id": eid,
        "event_title": etitle or "", "trigger_date": trigger_date,
        "model_snapshot_json": json.dumps(model_snap, ensure_ascii=False),
        "event_snapshot_json": json.dumps(event_snap, ensure_ascii=False),
        "graph_snapshot_json": json.dumps(graph_snap, ensure_ascii=False),
        "base_price": round(base, 2),
        "t1_date": t1, "t1_pct": round((bars[t1]["close"] / base - 1) * 100, 2) if t1 else None,
        "t3_date": t3, "t3_pct": round((bars[t3]["close"] / base - 1) * 100, 2) if t3 else None,
        "t5_date": t5, "t5_pct": round((bars[t5]["close"] / base - 1) * 100, 2) if t5 else None,
        "max_up": max_up, "max_drawdown": max_dd, "result": result, "note": note,
    }


def main():
    con = sqlite3.connect(DB)
    kline = load_kline()
    print(f"  kline 覆盖 {len(kline)} 只股票")

    # 待验证：所有 research_scores 快照（按日）
    rows = con.execute("""
        SELECT stock_code, stock_name, research_score, score_status, research_state,
               event_id, event_title, created_at,
               model_detail, explanation_json, event_score, model_score,
               technical_score, capital_score, momentum_score
        FROM research_scores ORDER BY created_at""").fetchall()
    print(f"  评分快照 {len(rows)} 条")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inserted = updated = skipped = 0
    for row in rows:
        v = validate_one(con, row, kline)
        if v is None:
            skipped += 1
            continue
        # UPSERT（stock_code+trigger_date+param_version 唯一）
        cur = con.execute("""SELECT id FROM research_validation
            WHERE stock_code=? AND trigger_date=? AND parameter_version='v1.9.0'""",
            (v["stock_code"], v["trigger_date"])).fetchone()
        if cur:
            con.execute("""UPDATE research_validation SET
                t1_date=?, t1_pct=?, t3_date=?, t3_pct=?, t5_date=?, t5_pct=?,
                max_up=?, max_drawdown=?, result=?, validation_note=?, updated_at=?
                WHERE id=?""",
                (v["t1_date"], v["t1_pct"], v["t3_date"], v["t3_pct"], v["t5_date"], v["t5_pct"],
                 v["max_up"], v["max_drawdown"], v["result"], v["note"], now, cur[0]))
            updated += 1
        else:
            con.execute("""INSERT INTO research_validation
                (stock_code, stock_name, research_score, score_status, research_state,
                 event_id, event_title, trigger_date, base_price,
                 t1_date, t1_pct, t3_date, t3_pct, t5_date, t5_pct,
                 max_up, max_drawdown, result, validation_note,
                 model_snapshot_json, event_snapshot_json, graph_snapshot_json,
                 system_version, parameter_version, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (v["stock_code"], v["stock_name"], v["research_score"], v["score_status"],
                 v["research_state"], v["event_id"], v["event_title"], v["trigger_date"],
                 v["base_price"], v["t1_date"], v["t1_pct"], v["t3_date"], v["t3_pct"],
                 v["t5_date"], v["t5_pct"], v["max_up"], v["max_drawdown"], v["result"],
                 v["note"], v["model_snapshot_json"], v["event_snapshot_json"], v["graph_snapshot_json"],
                 SYSTEM_VERSION, "v1.9.0", now, now))
            inserted += 1
    con.commit()

    print(f"✅ v2.1 验证: 新增 {inserted} / 更新 {updated} / 跳过(无行情) {skipped}")
    print("  结果分布:", dict(con.execute("SELECT result, COUNT(*) FROM research_validation GROUP BY 1").fetchall()))
    # 有效样本（有 T+3 的）
    done = con.execute("SELECT COUNT(*) FROM research_validation WHERE t3_date IS NOT NULL").fetchone()[0]
    print(f"  已有 T+3 数据: {done} 条")
    # 高分样本
    high = con.execute("""SELECT stock_code, stock_name, research_score, trigger_date, t1_pct, t3_pct,
        max_up, max_drawdown, result FROM research_validation
        WHERE research_score >= 70 AND t3_date IS NOT NULL ORDER BY research_score DESC LIMIT 10""").fetchall()
    print("  RS≥70 已验证样本:")
    for r in high:
        print(f"    {r[0]} {r[1]:<6} RS{r[2]} @{r[3]} | T+1:{r[4]}% T+3:{r[5]}% | maxUp:{r[6]}% maxDD:{r[7]}% [{r[8]}]")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
