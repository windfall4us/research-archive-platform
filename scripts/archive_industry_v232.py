#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2.3.2 行业实体化（Industry Entity）
范围：只增加 industry_entity + industry_entity_relation + 行业热度计算。
冻结期约束：不改 RS/Momentum/十模型/状态机/验证体系，不动 research_document 数据。

流程：
1. 建表 industry_entity / industry_entity_relation
2. 初始化行业树（一级 10 个 + 二级实体 + aliases 同义词，幂等 upsert）
3. 实体提取：research_document（title_clean/company/title_raw）匹配 aliases → relation（confidence）
4. 行业热度 Industry Momentum = 研究对象数 + 机构数 + 事件数 + Momentum + RS（展示层聚合）
"""
import sqlite3, json, re, sys
from datetime import datetime

DB = '/root/workspace/research_archive.db'
TZ = None  # 时区无关（本脚本不计算 age）

# ── 行业树定义（一级 10 个，二级实体，aliases 同义词）──
INDUSTRY_TREE = [
    {"name": "AI产业链", "level": 1, "category": "科技", "aliases": ["AI产业链", "人工智能", "AI应用", "AI+"]},
    {"name": "半导体", "level": 1, "category": "科技", "aliases": ["半导体", "芯片"]},
    {"name": "新能源", "level": 1, "category": "制造", "aliases": ["新能源", "碳中和", "双碳"]},
    {"name": "机器人", "level": 1, "category": "制造", "aliases": ["机器人", "具身智能"]},
    {"name": "汽车", "level": 1, "category": "制造", "aliases": ["汽车", "整车"]},
    {"name": "医药", "level": 1, "category": "医疗", "aliases": ["医药", "医疗", "生物医药"]},
    {"name": "消费", "level": 1, "category": "消费", "aliases": ["消费", "大消费", "食品饮料"]},
    {"name": "周期", "level": 1, "category": "周期", "aliases": ["周期", "大宗商品"]},
    {"name": "金融", "level": 1, "category": "金融", "aliases": ["金融", "银行", "券商"]},
    {"name": "军工", "level": 1, "category": "国防", "aliases": ["军工", "国防"]},
]

# 二级实体（parent 指向一级 name）
INDUSTRY_CHILDREN = {
    "AI产业链": [
        {"name": "AI算力", "aliases": ["AI算力", "算力", "智算", "大模型", "GPU", "AI服务", "云服务", "算力租赁", "AIDC"]},
        {"name": "AI服务器", "aliases": ["AI服务器", "服务器", "整机柜", "超节点"]},
        {"name": "液冷", "aliases": ["液冷", "服务器液冷", "冷板", "浸没式", "液冷板"]},
        {"name": "光模块/CPO", "aliases": ["光模块", "CPO", "光通信", "硅光", "1.6T", "Lumentum", "光模块/CPO"]},
        {"name": "PCB", "aliases": ["PCB", "载板", "CCL", "覆铜板", "mSAP", "BT载板", "ABF"]},
        {"name": "电源", "aliases": ["电源", "供电", "HVDC", "UPS", "电源系统", "服务器电源"]},
        {"name": "存储", "aliases": ["存储", "DRAM", "NAND", "HBM", "存储芯片", "海力士", "闪存"]},
        {"name": "AI芯片", "aliases": ["AI芯片", "ASIC", "GPU芯片", "英伟达", "寒武纪", "海光"]},
        {"name": "光芯片", "aliases": ["光芯片", "光器件", "FAU", "EML", "DFB"]},
    ],
    "半导体": [
        {"name": "晶圆制造", "aliases": ["晶圆制造", "晶圆代工", "Foundry", "中芯", "华虹"]},
        {"name": "半导体设备", "aliases": ["半导体设备", "设备", "刻蚀", "薄膜", "光刻机", "北方华创", "中微"]},
        {"name": "材料", "aliases": ["半导体材料", "硅片", "光刻胶", "靶材", "电子特气", "前驱体"]},
        {"name": "先进封装", "aliases": ["先进封装", "封装", "CoWoS", "2.5D", "3D封装", "封测"]},
        {"name": "国产替代", "aliases": ["国产替代", "自主可控", "国产化", "信创"]},
    ],
    "新能源": [
        {"name": "动力电池", "aliases": ["动力电池", "锂电", "锂电池", "电池", "宁德", "电池材料"]},
        {"name": "光伏", "aliases": ["光伏", "太阳能", "硅料", "组件", "逆变器"]},
        {"name": "储能", "aliases": ["储能", "储能系统", "大储", "户储"]},
        {"name": "充电桩", "aliases": ["充电桩", "充电", "超充"]},
    ],
    "机器人": [
        {"name": "人形机器人", "aliases": ["人形机器人", "机器人", "宇树", "特斯拉机器人", "Optimus"]},
        {"name": "减速器", "aliases": ["减速器", "谐波", "RV减速器", "丝杠"]},
        {"name": "机器视觉", "aliases": ["机器视觉", "视觉", "3D视觉"]},
    ],
    "汽车": [
        {"name": "汽车零部件", "aliases": ["汽车零部件", "零部件", "车灯", "座椅", "线束"]},
        {"name": "智能驾驶", "aliases": ["智能驾驶", "智驾", "自动驾驶", "激光雷达", "域控"]},
        {"name": "一体化压铸", "aliases": ["一体化压铸", "压铸", "压铸机"]},
    ],
    "医药": [
        {"name": "创新药", "aliases": ["创新药", "新药", "临床", "FDA", "BD授权"]},
        {"name": "CXO", "aliases": ["CXO", "CRO", "CDMO", "药明"]},
        {"name": "医疗器械", "aliases": ["医疗器械", "器械", "IVD"]},
    ],
    "消费": [
        {"name": "白酒", "aliases": ["白酒", "茅台", "五粮液", "汾酒", "酒"]},
        {"name": "食品饮料", "aliases": ["食品饮料", "乳制品", "调味品", "零食"]},
        {"name": "家电", "aliases": ["家电", "白电", "厨电", "小家电"]},
    ],
    "周期": [
        {"name": "有色", "aliases": ["有色", "铜", "铝", "锂矿", "稀土", "黄金"]},
        {"name": "煤炭", "aliases": ["煤炭", "焦煤", "动力煤"]},
        {"name": "化工", "aliases": ["化工", "石化", "炼化", "MDI", "钛白粉"]},
        {"name": "航运", "aliases": ["航运", "海运", "集运", "油运", "船舶"]},
    ],
    "金融": [
        {"name": "银行", "aliases": ["银行", "国有大行", "股份行"]},
        {"name": "券商", "aliases": ["券商", "证券", "投行", "经纪"]},
        {"name": "保险", "aliases": ["保险", "寿险", "财险"]},
    ],
    "军工": [
        {"name": "导弹", "aliases": ["导弹", "火箭弹", "精确制导"]},
        {"name": "无人机", "aliases": ["无人机", "UAV", "eVTOL"]},
        {"name": "军工电子", "aliases": ["军工电子", "雷达", "红外", "电子对抗"]},
    ],
}


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def create_tables(con):
    con.execute("""
    CREATE TABLE IF NOT EXISTS industry_entity (
        entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        parent_id INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        category TEXT DEFAULT '',
        aliases TEXT DEFAULT '[]',
        status TEXT DEFAULT 'active',
        created_at TEXT
    )""")
    con.execute("""
    CREATE TABLE IF NOT EXISTS industry_entity_relation (
        relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER NOT NULL,
        entity_id INTEGER NOT NULL,
        confidence REAL DEFAULT 0.5,
        source TEXT DEFAULT 'auto',
        created_at TEXT,
        UNIQUE(document_id, entity_id)
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ier_doc ON industry_entity_relation(document_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ier_ent ON industry_entity_relation(entity_id)")
    con.commit()


def upsert_tree(con):
    """行业树初始化（幂等：name UNIQUE，存在则更新 aliases）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    id_map = {}  # name -> entity_id
    for top in INDUSTRY_TREE:
        con.execute("""
            INSERT INTO industry_entity (name, parent_id, level, category, aliases, status, created_at)
            VALUES (?, 0, 1, ?, ?, 'active', ?)
            ON CONFLICT(name) DO UPDATE SET aliases=excluded.aliases, category=excluded.category, status='active'
        """, (top["name"], top["category"], json.dumps(top["aliases"], ensure_ascii=False), now))
    for r in con.execute("SELECT entity_id, name FROM industry_entity WHERE level=1"):
        id_map[r["name"]] = r["entity_id"]
    for parent, children in INDUSTRY_CHILDREN.items():
        pid = id_map.get(parent)
        if not pid:
            continue
        for ch in children:
            con.execute("""
                INSERT INTO industry_entity (name, parent_id, level, category, aliases, status, created_at)
                VALUES (?, ?, 2, ?, ?, 'active', ?)
                ON CONFLICT(name) DO UPDATE SET parent_id=excluded.parent_id, aliases=excluded.aliases, status='active'
            """, (ch["name"], pid, "细分", json.dumps(ch["aliases"], ensure_ascii=False), now))
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM industry_entity").fetchone()[0]
    print(f"✅ 行业树初始化: {n} 个实体（一级 {len(INDUSTRY_TREE)} + 二级 {sum(len(v) for v in INDUSTRY_CHILDREN.values())}）")
    return id_map


def extract_relations(con):
    """实体提取：research_document 标题/公司/原文 匹配 aliases → relation（confidence）"""
    entities = [dict(r) for r in con.execute(
        "SELECT entity_id, name, level, aliases FROM industry_entity WHERE status='active'")]
    alias_map = []  # (keyword, entity_id, level, name)
    for e in entities:
        kws = json.loads(e["aliases"] or "[]")
        kws.append(e["name"])
        for k in kws:
            if k and len(k) >= 2:
                alias_map.append((k, e["entity_id"], e["level"]))
    # 长词优先（避免「光模块」误中「光模块/CPO」的子串问题）
    alias_map.sort(key=lambda x: -len(x[0]))

    docs = [dict(r) for r in con.execute(
        "SELECT doc_id, title_clean, company, title_raw FROM research_document WHERE quality_score >= 30")]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rel_count = 0
    for d in docs:
        text = f"{d.get('title_clean') or ''} {d.get('company') or ''} {d.get('title_raw') or ''}"
        if not text:
            continue
        hit = {}
        for kw, eid, level in alias_map:
            if kw in text and eid not in hit:
                hit[eid] = 0.9 if level == 1 else 0.75
        if not hit:
            continue
        for eid, conf in hit.items():
            con.execute("""
                INSERT OR IGNORE INTO industry_entity_relation (document_id, entity_id, confidence, source, created_at)
                VALUES (?, ?, ?, 'auto', ?)
            """, (d["doc_id"], eid, conf, now))
            if con.total_changes:
                rel_count += 1
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM industry_entity_relation").fetchone()[0]
    ndoc = con.execute("SELECT COUNT(DISTINCT document_id) FROM industry_entity_relation").fetchone()[0]
    print(f"✅ 实体提取: {rel_count} 新关系，共 {n} 条（覆盖 {ndoc} 个文档）")


def main():
    con = connect()
    create_tables(con)
    upsert_tree(con)
    extract_relations(con)
    # 摘要
    top = [dict(r) for r in con.execute("""
        SELECT e.name, e.level, COUNT(DISTINCT r.document_id) n
        FROM industry_entity e
        LEFT JOIN industry_entity_relation r ON r.entity_id = e.entity_id
        GROUP BY e.entity_id ORDER BY n DESC, e.level LIMIT 12""")]
    for t in top:
        print(f"  L{t['level']} {t['name']}: {t['n']} 个研究对象")
    con.close()


if __name__ == "__main__":
    main()
