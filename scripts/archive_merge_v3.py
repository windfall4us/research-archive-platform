#!/usr/bin/env python3
"""资讯研究档案库 v1.0 - 报告归并全链路
research 消息 → report_series（主体）/ report_versions（版本）/ report_messages（消息关联）
           / report_occurrences（重复出现）/ report_verifications（初始待验证）
2026-08-09
"""
import json, re, sqlite3, sys, hashlib
from datetime import datetime

sys.path.insert(0, "/root/scripts")
from institution_map import normalize_institution

DB = "/root/workspace/research_archive.db"

# 研报标题个股名前置（与 backfill_stock_title.py 一致）
_STOCK_NAMES = ["博迈科", "上纬新材", "兴森科技", "中际旭创", "新易盛", "天孚通信", "胜宏科技", "沪电股份",
                "生益科技", "景旺电子", "鼎泰高科", "云南锗业", "通威股份", "利欧股份", "用友网络", "岩山科技",
                "药明康德", "康龙化成", "凯莱英", "恒瑞医药", "百济神州", "兆易创新", "江波龙", "佰维存储", "德明利",
                "长川科技", "铜冠铜箔", "国际复材", "风华高科", "东山精密", "北方华创", "寒武纪", "中芯国际",
                "新易盛", "天孚通信", "方正科技", "汇绿生态", "江南新材", "锴威特", "高争民爆", "盛达资源",
                "天岳先进", "天岳", "英飞凌", "晶升股份", "天科合达", "山东天岳"]


def prepend_stock_name(title: str) -> str:
    t = (title or "").strip()
    if not t:
        return t
    for name in sorted(set(_STOCK_NAMES), key=len, reverse=True):
        if len(name) < 2:
            continue
        if name in t[:40] and not t.startswith(name):
            rest = t.replace(name, '', 1).strip(' ：:，,。.·—-_()（）【】[]')
            return f"{name}｜{rest}"
    return t


def norm_title(text):
    """提取机构 + 标题（2026-08-12：只取首行作为标题，不再吞入正文）"""
    t = text.strip()
    # 首行优先（消息首行通常是标题行）
    t = t.split('\n')[0].strip(' \u3000\t')
    t = re.sub(r'^(汇报|更新|点评|纪要|会议|快评|速评)[0-9]*[：:\s]*', '', t)
    m = re.match(r'[【\[]([^】\]]+)[】\]](.*)', t)
    inst = m.group(1).strip() if m else ""
    title = m.group(2).strip() if m else t
    norm = re.sub(r'[（(][0-9]+[)）]', '', title)
    norm = re.sub(r'[：:，,。.\s\-—_/()（）]+', '', norm)
    display = re.sub(r'[（(][0-9]+[)）]', '', title).strip()
    return inst, norm, display[:80]

def content_hash(text):
    return hashlib.md5((text or '').encode()).hexdigest()


def structure_hash(text):
    """结构哈希：去掉数字后的内容哈希（识别格式重复/版本更新的辅助）"""
    t = re.sub(r'\d+', 'N', text or '')
    return hashlib.md5(t.encode()).hexdigest()


def extract_stocks(text):
    codes = re.findall(r'ths://(\d{6})', text or "")
    if not codes:
        codes = re.findall(r'(?<!\d)(\d{6})(?!\d)', text or "")
    return list(dict.fromkeys(codes[:10]))


def extract_report_body(text):
    """2026-08-12 修复：研报正文提取（此前 core_view 恒为空导致详情抽屉空白）。
    去掉首行标题后，剩余正文按编号/冒号切分为 核心观点/推荐逻辑/催化因素/风险因素。
    """
    raw = (text or "").strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return "", "", "", ""
    body = "\n".join(lines[1:]) if len(lines) > 1 else raw  # 跳过首行标题
    if not body.strip():
        body = raw
    # 按编号分节（1. 2. 3. / 一、二、三、）
    sections = {}
    current = "core"
    for ln in body.splitlines():
        m = re.match(r'^[（(]?(\d+)[)）]?[.、．]\s*(.*)', ln)
        if m:
            n = int(m.group(1))
            current = {1: "core", 2: "logic", 3: "catalysts", 4: "risks"}.get(n, "core")
            if m.group(2).strip():
                sections.setdefault(current, []).append(m.group(2).strip())
        else:
            sections.setdefault(current, []).append(ln)
    core = "\n".join(sections.get("core", [body]))[:800]
    logic = "\n".join(sections.get("logic", []))[:600]
    catalysts = "\n".join(sections.get("catalysts", []))[:600]
    risks = "\n".join(sections.get("risks", []))[:600]
    return core, logic, catalysts, risks


def main():
    con = sqlite3.connect(DB)
    rows = con.execute("""
        SELECT r.chat_id, r.message_id, r.date, r.raw_text
        FROM message_classification c JOIN raw_messages r
          ON r.chat_id || ':' || r.message_id = c.message_id
        WHERE c.primary_category = 'research'
          AND r.chat_id || ':' || r.message_id NOT IN (SELECT message_id FROM report_messages)
        ORDER BY r.date
    """).fetchall()

    done = 0
    for chat_id, message_id, mdate, text in rows:
        mid = f"{chat_id}:{message_id}"
        inst, key, display = norm_title(text or "")
        inst = normalize_institution(inst)  # 机构标准化
        norm_key = f"{inst}:{key}" if inst else key
        if not norm_key:
            continue
        ch = content_hash(text)
        sh = structure_hash(text)
        now = mdate or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rtype = "行业研究/主题策略"
        if any(k in display for k in ['策略', '周思考', '宏观', '非农', 'CPI', '利率', '央行', '汇率', '财政', '政策']):
            rtype = "宏观策略"
        elif (any(k in display for k in ['业绩', '点评', '订单', '目标价', '盈利预测', '跟踪', '更新', '拐点'])
              and not any(k in display for k in ['板块', '行业', '非银', '银行', '证券', '保险', '估值修复', '估值有望'])):
            rtype = "公司跟踪/业绩点评"
        codes = extract_stocks(text)

        row = con.execute("SELECT series_id, current_version FROM report_series WHERE norm_key=?", (norm_key,)).fetchone()
        if not row:
            cur = con.execute("""INSERT INTO report_series
                (norm_key, title, institution, analyst, report_type, first_seen_at, last_seen_at,
                 current_version, occurrence_count, status)
                VALUES (?,?,?,?,?,?,?,1,1,?)""",
                (norm_key, prepend_stock_name(display), inst, "", rtype, now, now,
                 'active' if inst else 'candidate'))
            sid = cur.lastrowid
            core_v, logic_v, cat_v, risk_v = extract_report_body(text)
            con.execute("""INSERT INTO report_versions
                (report_id, version_no, core_view, logic, catalysts, risks, valuation,
                 stock_codes_json, industries_json, content_hash, structure_hash, changed_summary, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sid, 1, core_v, logic_v, cat_v, risk_v, '',
                 json.dumps(codes, ensure_ascii=False), "[]", ch, sh, '', now))
            con.execute("INSERT INTO report_messages (report_id, message_id, sequence_no, is_first, is_last) VALUES (?,?,1,1,1)",
                        (sid, mid))
            con.execute("INSERT INTO report_occurrences (report_id, message_id, appeared_at, is_primary, is_duplicate, duplicate_type) VALUES (?,?,?,1,0,'')",
                        (sid, mid, now))
            con.execute("INSERT INTO report_verifications (report_id, event_date, event_type, event_text, verification_status, created_at) VALUES (?,?,?,?, '待验证', ?)",
                        (sid, now, "发布", display, now))
        else:
            sid, cur_ver = row
            vrow = con.execute("SELECT version_no, content_hash, core_view FROM report_versions WHERE report_id=? ORDER BY version_no DESC LIMIT 1",
                               (sid,)).fetchone()
            if vrow and vrow[1] == ch:
                # 完全重复
                con.execute("INSERT INTO report_occurrences (report_id, message_id, appeared_at, is_primary, is_duplicate, duplicate_type) VALUES (?,?,?,0,1,'exact_duplicate')",
                            (sid, mid, now))
            else:
                # 内容更新 → 新版本
                new_ver = (vrow[0] if vrow else 0) + 1
                core_v, logic_v, cat_v, risk_v = extract_report_body(text)
                # 2026-08-12: 与上一版本正文比较，差异 <5% 判定为「同稿转发」而非「内容更新」
                import difflib as _difflib
                prev_core = (vrow[2] or "") if vrow else ""
                if prev_core and core_v:
                    ratio = _difflib.SequenceMatcher(None, prev_core, core_v).ratio()
                    changed_summary = "同稿转发" if ratio >= 0.95 else "内容更新"
                else:
                    changed_summary = "内容更新"
                con.execute("""INSERT INTO report_versions
                    (report_id, version_no, core_view, logic, catalysts, risks, valuation,
                     stock_codes_json, industries_json, content_hash, structure_hash, changed_summary, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (sid, new_ver, core_v, logic_v, cat_v, risk_v, '',
                     json.dumps(codes, ensure_ascii=False), "[]", ch, sh, changed_summary, now))
                con.execute("UPDATE report_series SET current_version=? WHERE series_id=?", (new_ver, sid))
                con.execute("INSERT INTO report_occurrences (report_id, message_id, appeared_at, is_primary, is_duplicate, duplicate_type) VALUES (?,?,?,0,1,'updated_version')",
                            (sid, mid, now))
            con.execute("INSERT INTO report_messages (report_id, message_id, sequence_no, is_first, is_last) VALUES (?,?,1,0,0)",
                        (sid, mid))
            con.execute("UPDATE report_series SET last_seen_at=?, occurrence_count=occurrence_count+1 WHERE series_id=?",
                        (now, sid))
        # 实体关联（股票代码 + 机构）
        for code in extract_stocks(text):
            con.execute("INSERT OR IGNORE INTO report_entities (report_id, entity_type, entity_id, entity_name, relation_type) VALUES (?, 'stock', ?, ?, '重点关注')",
                        (sid, code, code))
        if inst:
            con.execute("INSERT OR IGNORE INTO report_entities (report_id, entity_type, entity_id, entity_name, relation_type) VALUES (?, 'institution', ?, ?, '来源机构')",
                        (sid, inst, inst))
        done += 1
    con.commit()
    total = con.execute("SELECT count(*) FROM report_series").fetchone()[0]
    ver_n = con.execute("SELECT count(*) FROM report_versions").fetchone()[0]
    occ_n = con.execute("SELECT count(*) FROM report_occurrences").fetchone()[0]
    verif_n = con.execute("SELECT count(*) FROM report_verifications").fetchone()[0]
    print(f"✅ 归并v3: 处理 {done} | series {total} | versions {ver_n} | occurrences {occ_n} | verifications {verif_n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
