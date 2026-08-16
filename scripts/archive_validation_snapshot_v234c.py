#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2.3.4c Validation Snapshot 完整化 — 回填 research_validation 快照字段
为 v2.4 建立「解释当时为什么给这个分」的能力：validation 保存 3 个快照：
  model_snapshot_json  当时研究评分看到的模型状态（model/final_score/matched）
  event_snapshot_json  当时事件状态（event_score/momentum/机构数/industry/标题）
  graph_snapshot_json  当时图谱状态（industry_gs/stock_centrality/confidence）
只读 research_scores + 图谱，不改任何评分/算法/状态机。
"""
import json, sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

DB = "/root/workspace/research_archive.db"
TZ = ZoneInfo("Asia/Shanghai")


def main():
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # ── 幂等加列 ──
    for col in ("model_snapshot_json", "event_snapshot_json", "graph_snapshot_json"):
        try:
            con.execute(f"ALTER TABLE research_validation ADD COLUMN {col} TEXT")
        except Exception:
            pass
    con.commit()

    # ── research_scores 索引：stock_code + 日期 → 当日最新快照 ──
    rs_by_day = {}   # (code, date) -> dict(最新 id 的行)
    for r in con.execute("""SELECT id, stock_code, research_score, event_id, event_title,
            event_score, model_score, technical_score, capital_score, momentum_score,
            model_detail, explanation_json, created_at, parameter_version
            FROM research_scores ORDER BY id"""):
        d = dict(r)
        key = (d["stock_code"], (d["created_at"] or "")[:10])
        # 保留当日最后一条（id 最大）
        prev = rs_by_day.get(key)
        if prev is None or d["id"] > prev["id"]:
            rs_by_day[key] = d

    # ── 图谱索引（graph_snapshot 用）──
    # 股票 → GS（事件数×5 + 行业数×2，与 obs 一致）
    stock_gs = {}
    for r in con.execute("SELECT DISTINCT target_id FROM research_graph_relation WHERE target_type='stock'"):
        c = str(r["target_id"])
        if c not in stock_gs:
            evs = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='event' AND target_type='stock' AND target_id=?", (c,)).fetchone()[0]
            inds = con.execute("SELECT COUNT(*) FROM research_graph_relation WHERE source_type='stock' AND target_type='industry' AND source_id=?", (c,)).fetchone()[0]
            stock_gs[c] = min(100, evs * 5 + inds * 2)
    # 股票 → 机构数（followed_by）
    stock_inst = {}
    for r in con.execute("""SELECT source_id, COUNT(*) n FROM research_graph_relation
                             WHERE source_type='stock' AND relation_type='followed_by' GROUP BY 1"""):
        stock_inst[str(r["source_id"])] = r["n"]

    # ── 行业 GS（industry → 子行业 GS 聚合，简化取最高子行业 GS）──
    ind_gs = {}
    for r in con.execute("SELECT entity_id, parent_id FROM industry_entity"):
        ind_gs[r["entity_id"]] = 0

    filled = 0
    rows = con.execute("SELECT id, stock_code, event_id, trigger_date FROM research_validation").fetchall()
    for v in rows:
        # 1) 找对应 research_scores 快照（同日 + 同股票，优先 event_id 匹配）
        rs = rs_by_day.get((v["stock_code"], v["trigger_date"]))
        if rs is None:
            # 尝试 event_id 匹配
            for (c, d), row in rs_by_day.items():
                if c == v["stock_code"] and row.get("event_id") == v["event_id"]:
                    rs = row
                    break
        if rs is None:
            continue

        # ── model_snapshot ──
        try:
            md = json.loads(rs["model_detail"] or "{}") or {}
            models = [{"name": md.get("model", ""), "score": round(md.get("final_score") or 0, 1),
                       "matched": bool(md.get("matched"))}]
        except Exception:
            md = {}
            models = []
        model_snap = {"models": models, "model_score": rs["model_score"] or 0,
                      "technical_score": rs["technical_score"] or 0,
                      "capital_score": rs["capital_score"] or 0}

        # ── event_snapshot ──
        inst_n = 0
        try:
            exp = json.loads(rs["explanation_json"] or "{}") or {}
            for c in (exp.get("contributions") or []):
                lbl = str(c.get("label", ""))
                if "机构确认" in lbl:
                    import re
                    m = re.search(r"(\d+)家机构", lbl)
                    if m:
                        inst_n = int(m.group(1))
        except Exception:
            exp = {}
        event_snap = {"event_score": rs["event_score"] or 0,
                      "momentum": rs["momentum_score"] or 0,
                      "institution_count": inst_n,
                      "event_title": (rs["event_title"] or "")[:120]}

        # ── graph_snapshot ──
        c2 = str(v["stock_code"])
        graph_snap = {"stock_centrality": stock_gs.get(c2, 0),
                      "confidence": min(100, (stock_inst.get(c2, 0)) * 20)}

        con.execute("""UPDATE research_validation SET
            model_snapshot_json=?, event_snapshot_json=?, graph_snapshot_json=?, updated_at=?
            WHERE id=?""",
            (json.dumps(model_snap, ensure_ascii=False),
             json.dumps(event_snap, ensure_ascii=False),
             json.dumps(graph_snap, ensure_ascii=False), now, v["id"]))
        filled += 1

    con.commit()
    total = con.execute("SELECT COUNT(*) FROM research_validation").fetchone()[0]
    with_snap = con.execute("SELECT COUNT(*) FROM research_validation WHERE model_snapshot_json IS NOT NULL").fetchone()[0]
    con.close()
    print(f"✅ v2.3.4c Validation Snapshot 回填: {filled}/{total} 条（快照完整 {with_snap}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
