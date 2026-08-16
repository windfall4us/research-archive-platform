#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2.3.3 研究图谱融合（Research Graph）
目标：把已成熟的 5 个实体（document/industry/event/stock/institution）串成统一图谱。
冻结期约束：不改 RS/Momentum/十模型/状态机/验证体系；只增加 research_graph_relation 边表。

边类型（relation_type）：
  document→stock      mentions      （研究对象提及股票）
  document→industry   belongs_to    （研究对象属于行业）
  document→event      involves      （研究对象参与事件）
  document→institution published_by （研究对象由机构发布）
  event→stock         impact        （事件影响股票）
  stock→industry      in            （股票所属行业，经 document 传递）
  event→industry      in            （事件所属行业，经 document 传递）
"""
import sqlite3, json, re
from datetime import datetime

DB = '/root/workspace/research_archive.db'

A_STOCK_RE = re.compile(r"(?<![0-9])(?:60|68|00|30)\d{4}(?![0-9])")


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def create_table(con):
    con.execute("DROP TABLE IF EXISTS research_graph_relation")
    con.execute("""
    CREATE TABLE IF NOT EXISTS research_graph_relation (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        relation_type TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id INTEGER NOT NULL,
        confidence REAL DEFAULT 0.7,
        created_at TEXT,
        UNIQUE(source_type, source_id, relation_type, target_type, target_id)
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rgr_source ON research_graph_relation(source_type, source_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rgr_target ON research_graph_relation(target_type, target_id)")
    # 机构注册表（Python hash 进程随机化不可作 ID，用自增注册表）
    con.execute("""
    CREATE TABLE IF NOT EXISTS graph_institution (
        inst_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )""")
    con.commit()


def build(con):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    con.execute("DELETE FROM research_graph_relation")
    inserted = 0

    def add(st, sid, rt, tt, tid, conf=0.7):
        nonlocal inserted
        con.execute("""INSERT OR IGNORE INTO research_graph_relation
            (source_type, source_id, relation_type, target_type, target_id, confidence, created_at)
            VALUES (?,?,?,?,?,?,?)""", (st, str(sid), rt, tt, str(tid), conf, now))
        if con.total_changes:
            inserted += 1

    def stk(c):
        """股票代码统一 int 化（'000338'→'338'，SQLite TEXT affinity 吞前导零）"""
        c = str(c)
        return str(int(c)) if c.isdigit() else c

    # ── 实体池 ──
    docs = {}
    for r in con.execute("SELECT doc_id, title_clean, stock_codes_json, message_ids_json, quality_score FROM research_document"):
        docs[r["doc_id"]] = dict(r)
    # 股票池（合法代码 → 名称）
    stock_pool = {}
    for r in con.execute("SELECT DISTINCT stock_code, stock_name FROM research_scores WHERE stock_code != ''"):
        stock_pool.setdefault(r["stock_code"], r["stock_name"] or "")
    for r in con.execute("SELECT DISTINCT stock_code, stock_name FROM event_stock_relation WHERE stock_code != ''"):
        stock_pool.setdefault(r["stock_code"], r["stock_name"] or "")
    # message → 机构
    def inst_id(name):
        if not name: return None
        con.execute("INSERT OR IGNORE INTO graph_institution (name) VALUES (?)", (name,))
        row = con.execute("SELECT inst_id FROM graph_institution WHERE name=?", (name,)).fetchone()
        return row["inst_id"] if row else None
    msg_inst = {}
    for r in con.execute("SELECT message_id, institution FROM message_classification WHERE institution IS NOT NULL AND institution != ''"):
        msg_inst.setdefault(r["message_id"], r["institution"])
    # message → 事件
    msg_ev = {}
    for r in con.execute("SELECT message_id, event_id FROM event_messages"):
        msg_ev.setdefault(r["message_id"], r["event_id"])
    # doc → 行业（v2.3.2 已物化）
    doc_ind = {}
    for r in con.execute("SELECT document_id, entity_id, confidence FROM industry_entity_relation"):
        doc_ind.setdefault(r["document_id"], []).append((r["entity_id"], r["confidence"]))

    # ── 边 1：document → stock（库内 + normalized + 正则补提）──
    norm_stock = {}
    for r in con.execute("SELECT message_id, stock_codes_json FROM normalized_messages WHERE stock_codes_json IS NOT NULL AND stock_codes_json != '[]'"):
        norm_stock[r["message_id"]] = r["stock_codes_json"]
    for did, d in docs.items():
        codes = []
        try:
            codes = [str(c) for c in json.loads(d["stock_codes_json"] or "[]") if re.fullmatch(r"(?:60|68|00|30)\d{4}", str(c)) or str(c) in stock_pool]
        except Exception: pass
        try:
            for m in json.loads(d["message_ids_json"] or "[]"):
                nj = norm_stock.get(m)
                if nj:
                    for c in json.loads(nj):
                        c = str(c)
                        if (re.fullmatch(r"(?:60|68|00|30)\d{4}", c) or c in stock_pool) and c not in codes:
                            codes.append(c)
        except Exception: pass
        for c in codes:
            add("document", did, "mentions", "stock", stk(c), 0.75)

    # ── 边 2：document → industry（v2.3.2 物化结果）──
    for did, lst in doc_ind.items():
        for eid, conf in lst:
            add("document", did, "belongs_to", "industry", eid, conf)

    # ── 边 3：document → event（经消息）──
    for did, d in docs.items():
        try:
            for m in json.loads(d["message_ids_json"] or "[]"):
                ev = msg_ev.get(m)
                if ev:
                    add("document", did, "involves", "event", ev, 0.8)
        except Exception: pass

    # ── 边 4：document → institution（经消息机构）──
    for did, d in docs.items():
        try:
            for m in json.loads(d["message_ids_json"] or "[]"):
                ins = msg_inst.get(m)
                if ins:
                    iid = inst_id(ins)
                    if iid:
                        add("document", did, "published_by", "institution", iid, 0.9)
        except Exception: pass

    # ── 边 5：event → stock（v1.x 已物化）──
    for r in con.execute("SELECT event_id, stock_code, confidence FROM event_stock_relation"):
        c = r["stock_code"]
        if re.fullmatch(r"(?:60|68|00|30)\d{4}", str(c)) or str(c) in stock_pool:
            add("event", r["event_id"], "impact", "stock", stk(c), r["confidence"] or 0.7)

    # ── 边 6：stock → industry（经 document 传递）──
    stock_inds = {}  # stock -> {industry_id: conf}
    for did, d in docs.items():
        try:
            codes = [str(c) for c in json.loads(d["stock_codes_json"] or "[]") if re.fullmatch(r"(?:60|68|00|30)\d{4}", str(c))]
        except Exception:
            codes = []
        for c in codes:
            for eid, conf in doc_ind.get(did, []):
                stock_inds.setdefault(c, {})
                stock_inds[c][eid] = max(stock_inds[c].get(eid, 0), conf)
    for c, inds in stock_inds.items():
        for eid, conf in inds.items():
            add("stock", stk(c), "in", "industry", eid, conf)

    # ── 边 7：event → industry（经 document 传递）──
    ev_inds = {}
    for did, d in docs.items():
        try:
            evs = set(msg_ev.get(m) for m in json.loads(d["message_ids_json"] or "[]") if msg_ev.get(m))
        except Exception:
            evs = set()
        for ev in evs:
            for eid, conf in doc_ind.get(did, []):
                ev_inds.setdefault(ev, {})
                ev_inds[ev][eid] = max(ev_inds[ev].get(eid, 0), conf)
    for ev, inds in ev_inds.items():
        for eid, conf in inds.items():
            add("event", ev, "in", "industry", eid, conf)

    # ── 边 8：entity → institution（经 document 一跳：event/industry/stock 的机构）──
    doc_insts = {}   # doc_id -> set(inst_id)
    for did, d in docs.items():
        try:
            for m in json.loads(d["message_ids_json"] or "[]"):
                ins = msg_inst.get(m)
                if ins:
                    iid = inst_id(ins)
                    if iid:
                        doc_insts.setdefault(did, set()).add(iid)
        except Exception: pass
    # event → institution
    ev_docs = {}     # event_id -> set(doc_id)
    for did, d in docs.items():
        try:
            for m in json.loads(d["message_ids_json"] or "[]"):
                ev = msg_ev.get(m)
                if ev:
                    ev_docs.setdefault(ev, set()).add(did)
        except Exception: pass
    for ev, ds in ev_docs.items():
        insts = set()
        for d in ds:
            insts |= doc_insts.get(d, set())
        for iid in insts:
            add("event", ev, "confirmed_by", "institution", iid, 0.6)
    # industry → institution
    ind_docs = {}
    for did, lst in doc_ind.items():
        for eid, _ in lst:
            ind_docs.setdefault(eid, set()).add(did)
    for eid, ds in ind_docs.items():
        insts = set()
        for d in ds:
            insts |= doc_insts.get(d, set())
        for iid in insts:
            add("industry", eid, "confirmed_by", "institution", iid, 0.6)
    # stock → institution（经 document mentions）
    stock_docs = {}  # stock -> set(doc_id)
    for did, d in docs.items():
        try:
            codes = [str(c) for c in json.loads(d["stock_codes_json"] or "[]") if re.fullmatch(r"(?:60|68|00|30)\d{4}", str(c))]
        except Exception:
            codes = []
        for c in codes:
            stock_docs.setdefault(c, set()).add(did)
    for c, ds in stock_docs.items():
        insts = set()
        for d in ds:
            insts |= doc_insts.get(d, set())
        for iid in insts:
            add("stock", stk(c), "followed_by", "institution", iid, 0.6)

    # ── 边 9：stock → industry（经 event 传递：stock 关联事件的行业）──
    ev_stock = {}    # event_id -> set(stock_code)
    for r in con.execute("SELECT event_id, stock_code FROM event_stock_relation"):
        c = r["stock_code"]
        if re.fullmatch(r"(?:60|68|00|30)\d{4}", str(c)):
            ev_stock.setdefault(r["event_id"], set()).add(str(c))
    for ev, ev_inds_ in ev_inds.items():
        for st in ev_stock.get(ev, set()):
            for eid, conf in ev_inds_.items():
                add("stock", stk(st), "in", "industry", eid, conf * 0.8)

    con.commit()
    n = con.execute("SELECT COUNT(*) FROM research_graph_relation").fetchone()[0]
    by_type = dict(con.execute("SELECT relation_type, COUNT(*) n FROM research_graph_relation GROUP BY 1 ORDER BY n DESC").fetchall())
    print(f"✅ 研究图谱物化: {inserted} 新边，共 {n} 条")
    for t, c in by_type.items():
        print(f"   {t}: {c}")


def main():
    con = connect()
    create_table(con)
    build(con)
    con.close()


if __name__ == "__main__":
    main()
