#!/usr/bin/env python3
"""v2.3.0 数据治理层：研究文档归并 + 质量评分
核心目标：把"同一研究对象的多个转发/摘要"聚合成一个 research_document，
解决 同一条资讯被多个身份展示、content_type 分类混乱、标题质量差、消息与摘要未分离 问题。

分层保留：
  raw_messages          保留全部（不动）
  normalized_messages   保留（不动）
  message_classification 保留（不动）
  research_document     新增（研究对象层）
"""
import json
import re
import sqlite3
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

DB = "/root/workspace/research_archive.db"
TZ = ZoneInfo("Asia/Shanghai")

# 内容性质 → 一级分类（第一行展示）
NATURE_MAP = {
    "research_report": "研报", "research_activity": "调研", "institution_view": "观点",
    "news": "新闻", "announcement": "公告", "market": "行情", "digest": "汇总",
    "attachment": "图片", "empty_invalid": "无效",
}

# 标题规范化：删除日期/URL/群名/来源前缀/编号
_TITLE_NOISE = [
    (r"https?://\S+", ""),            # URL
    (r"\d{8}", ""),                    # 20260814
    (r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", ""),  # 2026-08-14
    (r"^\d{1,2}:\d{2}(?::\d{2})?\s*", ""),  # 08:06
    (r"^【[^】]{0,10}】\s*", ""),       # 【天风电新】
    (r"^#\S*#?\s*", ""),               # #标签#
    (r"^[（(]?[^）)]{0,12}[)）]?\s*[-—]\s*", ""),  # （机构）-
    (r"^财联社\d{1,2}月\d{1,2}日[电讯]\s*", ""),
    (r"^[—\-\s]+", ""),
]


def clean_title(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    for pat, rep in _TITLE_NOISE:
        t = re.sub(pat, rep, t)
    return t.strip()[:80]


def norm_key(title: str) -> str:
    """标题归一化键：去标点/空白，用于相似度比较"""
    return re.sub(r"[\W_]+", "", title or "").lower()


def extract_company(text: str) -> str:
    """从消息中提取公司名（股票名优先）"""
    m = re.search(r"([\u4e00-\u9fa5]{2,6})(?:\(|（)(\d{6})[)）]", text or "")
    if m:
        return m.group(1)
    return ""


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    # 建表（幂等）
    con.execute("""CREATE TABLE IF NOT EXISTS research_document (
        doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
        title_clean TEXT,
        title_raw TEXT,
        company TEXT,
        institution TEXT,
        research_type TEXT,          -- 公司点评/行业观点/调研纪要...
        content_nature TEXT,         -- 研报/调研/观点/新闻...
        stock_codes_json TEXT,
        industries_json TEXT,
        message_ids_json TEXT,       -- 归并的原始消息
        source_count INTEGER,
        institution_count INTEGER,
        quality_score INTEGER,
        first_seen_at TEXT,
        last_seen_at TEXT,
        created_at TEXT,
        updated_at TEXT
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rd_title ON research_document(title_clean)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rd_company ON research_document(company)")

    # 重新生成（幂等重建）
    con.execute("DELETE FROM research_document")

    # 取所有已分类的研究类消息（content_type 非 news/announcement/market/图片/无效）
    rows = con.execute("""
        SELECT c.message_id, c.content_type, c.content_subtype, c.institution,
               c.message_role, c.entities_json, c.themes_json, c.research_value,
               r.raw_text, r.date, r.chat_id, r.message_id AS raw_mid
        FROM message_classification c
        JOIN raw_messages r ON r.chat_id||':'||r.message_id = c.message_id
        WHERE c.content_type IN ('research_report', 'research_activity', 'institution_view')
        ORDER BY r.date
    """).fetchall()
    print(f"研究类消息: {len(rows)}")

    docs = []  # 已建 doc 列表
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    merged = 0
    created = 0

    for r in rows:
        d = dict(r)
        text = d["raw_text"] or ""
        title = clean_title(text)
        nk = norm_key(title)
        if not nk:
            continue
        # 机构/公司/股票
        inst = d["institution"] or ""
        company = extract_company(text)
        try:
            ent = json.loads(d["entities_json"] or "{}")
            codes = [str(c) for c in ent.get("stocks", [])]
        except Exception:
            codes = []
        # 研究类型（第二行）
        rtype = d["content_subtype"] or d["content_type"] or ""
        nature = NATURE_MAP.get(d["content_type"], d["content_type"] or "")

        # 归并判定：找已有 doc 中标题相似>90% 且 同股票 且 24h 内的
        matched_doc = None
        for doc in docs:
            if doc["_age"] <= 24 and SequenceMatcher(None, nk, doc["_nk"]).ratio() >= 0.90:
                # 股票相同（任一非空交集）或都为空
                doc_codes = set(doc["_codes"])
                if (doc_codes and codes and doc_codes & set(codes)) or (not doc_codes and not codes):
                    matched_doc = doc
                    break
        if matched_doc:
            # 归并
            matched_doc["_msg_ids"].append(d["message_id"])
            if inst and inst not in matched_doc["_insts"]:
                matched_doc["_insts"].append(inst)
            if codes:
                matched_doc["_codes"] = sorted(set(matched_doc["_codes"]) | set(codes))
            matched_doc["_age"] = 0  # 重置年龄（以最新消息时间）
            matched_doc["last_seen_at"] = d["date"] or now
            merged += 1
        else:
            # 新 doc
            doc = {
                "title_clean": title, "title_raw": (text or "")[:120],
                "company": company, "institution": inst, "research_type": rtype,
                "content_nature": nature,
                "stock_codes_json": json.dumps(codes, ensure_ascii=False),
                "industries_json": d["themes_json"] or "[]",
                "message_ids_json": json.dumps([d["message_id"]], ensure_ascii=False),
                "source_count": 1, "institution_count": 1 if inst else 0,
                "first_seen_at": d["date"] or now, "last_seen_at": d["date"] or now,
                "created_at": now, "updated_at": now,
                "_nk": nk, "_codes": list(codes), "_msg_ids": [d["message_id"]],
                "_insts": [inst] if inst else [], "_age": 0,
            }
            docs.append(doc)
            created += 1

    # 质量评分 + 写库
    for doc in docs:
        score = 30 if doc["institution"] else 0          # 机构 +30
        if doc["content_nature"] in ("研报", "调研"):
            score += 20                                    # 原始研报/调研 +20
        if doc["_codes"]:
            score += 20                                    # 股票明确 +20
        if doc["content_nature"] in ("观点", "研报", "调研"):
            score += 15                                    # 摘要/观点完整 +15
        if len(doc["_msg_ids"]) > 3:
            score -= 20                                    # 重复转发 -20
        if not doc["institution"] and not doc["_codes"]:
            score -= 30                                    # 无来源无股票 -30
        doc["quality_score"] = max(0, min(100, score))
        doc["source_count"] = len(set(doc["_msg_ids"]))
        doc["institution_count"] = len(doc["_insts"])
        doc["message_ids_json"] = json.dumps(doc["_msg_ids"], ensure_ascii=False)
        doc["stock_codes_json"] = json.dumps(doc["_codes"], ensure_ascii=False)
        con.execute("""INSERT INTO research_document
            (title_clean, title_raw, company, institution, research_type, content_nature,
             stock_codes_json, industries_json, message_ids_json,
             source_count, institution_count, quality_score,
             first_seen_at, last_seen_at, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (doc["title_clean"], doc["title_raw"], doc["company"], doc["institution"],
             doc["research_type"], doc["content_nature"],
             doc["stock_codes_json"], doc["industries_json"], doc["message_ids_json"],
             doc["source_count"], doc["institution_count"], doc["quality_score"],
             doc["first_seen_at"], doc["last_seen_at"], doc["created_at"], doc["updated_at"]))

    con.commit()
    total = con.execute("SELECT COUNT(*) FROM research_document").fetchone()[0]
    q50 = con.execute("SELECT COUNT(*) FROM research_document WHERE quality_score >= 50").fetchone()[0]
    con.close()
    print(f"✅ v2.3.0 研究文档归并: 消息 {len(rows)} → 文档 {total}（合并 {merged}，新建 {created}）")
    print(f"   质量≥50（可进重点研究）: {q50}")


if __name__ == "__main__":
    main()
