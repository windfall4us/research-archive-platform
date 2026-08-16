#!/usr/bin/env python3
"""资讯研究档案库 v1.0 - 入库 + 归一化
raw_messages：增量追加（chat_id+message_id 唯一，永不覆盖）
normalized_messages：清洗 + 实体识别（可重算，UPSERT）
2026-08-09
"""
import json, os, re, sqlite3, sys, hashlib
from datetime import datetime

CACHE = "/root/workspace/vip1_cache.json"
DB = "/root/workspace/research_archive.db"

INSTITUTIONS = ['国金', '天风', '国泰海通', '华鑫', '中金', '中信', '广发', '华泰', '申万', '东吴',
                '民生', '招商', '兴业', '海通', '银河', '平安', '开源', '华福', '国投', '浙商',
                '长江', '光大', '方正', '国联', '高盛', '摩根', '瑞银', '野村', '花旗', '中泰', '华西']
INDUSTRIES = {
    'AI/算力': ['算力', 'AI服务', '云服务', '大模型', 'GPU', '智算'],
    '半导体': ['半导体', '芯片', '晶圆', '封测', '存储', '光刻'],
    '光通信/CPO': ['光模块', 'CPO', '光通信', '硅光', '1.6T'],
    'PCB/载板': ['PCB', '载板', 'CCL', '覆铜板', 'mSAP'],
    '深海油气/FPSO': ['FPSO', '深海油气', '海洋工程', 'SBM'],
    '医药/CXO': ['创新药', 'CXO', '医药', 'CRO', 'CDMO', '药明'],
    '机器人': ['人形机器人', '机器人', '减速器', '丝杠', '宇树'],
    '军工': ['军工', '国防', '导弹', '军贸'],
    '新能源': ['光伏', '储能', '锂电', '风电', '硅料'],
    '消费': ['白酒', '食品', '消费'],
    '有色/稀土': ['稀土', '有色', '铜箔', '磷化铟', '金属'],
    '地产/基建': ['房地产', '地产', '基建'],
    '宏观/政策': ['央行', '利率', 'CPI', '非农', '政策', '财政'],
}


def clean_text(t):
    if not t:
        return ""
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def content_hash(t):
    return hashlib.md5((t or '').encode()).hexdigest()


def extract_institution(text):
    m = re.search(r'[【\[]([^】\]]+)[】\]]', text or "")
    if m:
        return m.group(1).strip()
    for inst in INSTITUTIONS:
        if inst in (text or ""):
            return inst
    return ""


def extract_stocks(text):
    codes = re.findall(r'ths://(\d{6})', text or "")
    if not codes:
        codes = re.findall(r'(?<!\d)(\d{6})(?!\d)', text or "")
    return list(dict.fromkeys(codes[:10]))


def extract_industries(text):
    hits = []
    for name, kws in INDUSTRIES.items():
        if any(k in (text or "") for k in kws):
            hits.append(name)
    return hits


def main():
    if not os.path.exists(CACHE):
        print("缓存不存在")
        return 0
    with open(CACHE) as f:
        items = json.load(f)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    con = sqlite3.connect(DB)
    ins_raw = 0
    ins_norm = 0
    for m in items:
        chat_id = str(m.get("chat_id") or "")
        message_id = m.get("message_id")
        if not chat_id or message_id is None:
            continue
        raw_text = m.get("content") or m.get("caption") or ""
        img_path = m.get("relative_image_path") or m.get("filepath") or ""
        # raw_messages 增量
        cur = con.execute(
            """INSERT OR IGNORE INTO raw_messages
               (chat_id, message_id, date, from_user, reply_to_message_id, source_topic,
                msg_type, raw_text, relative_image_path, raw_json, imported_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (chat_id, int(message_id), m.get("time"), m.get("from"), m.get("reply_to"),
             m.get("topic"), m.get("type"), raw_text, img_path,
             json.dumps(m, ensure_ascii=False), m.get("imported_at") or now))
        if cur.rowcount:
            ins_raw += 1
        # normalized_messages（UPSERT 可重算）
        if raw_text.strip():
            nt = clean_text(raw_text)
            title = nt[:80]
            inst = extract_institution(raw_text)
            codes = extract_stocks(raw_text)
            inds = extract_industries(raw_text)
            # 加列（幂等）
            cols = [r[1] for r in con.execute("PRAGMA table_info(normalized_messages)")]
            if "normalized_hash" not in cols:
                con.execute("ALTER TABLE normalized_messages ADD COLUMN normalized_hash TEXT")
            con.execute("""INSERT OR REPLACE INTO normalized_messages
                (message_id, normalized_text, title, source, institution, analyst,
                 stock_codes_json, stock_names_json, industries_json, topics_json, normalized_at, normalized_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"{chat_id}:{message_id}", nt, title, m.get("from") or m.get("topic"),
                 inst, "", json.dumps(codes, ensure_ascii=False), "[]",
                 json.dumps(inds, ensure_ascii=False), json.dumps([m.get("topic")], ensure_ascii=False), now,
                 content_hash(nt)))
            ins_norm += 1
    con.commit()
    total_raw = con.execute("SELECT count(*) FROM raw_messages").fetchone()[0]
    total_norm = con.execute("SELECT count(*) FROM normalized_messages").fetchone()[0]
    con.close()
    print(f"✅ 入库: raw+{ins_raw}(总{total_raw}) | normalized+{ins_norm}(总{total_norm})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
