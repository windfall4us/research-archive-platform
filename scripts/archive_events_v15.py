#!/usr/bin/env python3
"""资讯研究档案库 v1.5 - 事件语义层
message → event_clusters（语义聚类）：实体归一 + 跨日期归并 + cluster_confidence
event_roles：事件内消息角色分层（fact/source/research/commentary/mapping/update）
事件评分：六维加权 event_score + 状态 status（emerging/heating/stable/fading/closed）
2026-08-12
"""
import json, re, sqlite3, sys
from datetime import datetime

DB = "/root/workspace/research_archive.db"

# ═══ 实体同义归一（v1.5：SK海力士/海力士/海力士半导体 → 海力士）═══
ENTITY_ALIASES = {
    "SK海力士": "海力士", "海力士半导体": "海力士", "SK Hynix": "海力士", "Hynix": "海力士",
    "NVIDIA": "英伟达", "NVDA": "英伟达", "Alunorte": "氧化铝", "J.P.摩根": "摩根大通",
    "Coreweave": "CoreWeave", "SK Hynix大连": "海力士", "大连NAND": "海力士",
    "山东天岳": "天岳先进", "天岳": "天岳先进", "中际旭创": "中际旭创", "CXMT": "长鑫存储",
}
# 主题级实体（无公司名，按主题聚类）
THEME_ENTITIES = ["HBM", "CPO", "800V", "SOFC", "固态电池", "人形机器人", "FPSO", "光模块",
                  "存储涨价", "PCB涨价", "铜箔", "DrMOS", "先进封装", "碳化硅", "AI服务器",
                  "算力租赁", "液冷", "NAND", "DRAM"]

# 事件类型关键词
EVENT_TYPE_RULES = [
    ("海外公司业绩", ['业绩', '财报', '盘后', '指引', '营收', '超预期', 'EPS', '毛利率']),
    ("公司事件", ['订单', '中标', '合同', '涨价', '扩产', '回购', '增持', '减持', '停牌', '公告',
                  '投产', '产能', '出货', '量产']),
    ("传闻求证", ['网传', '传闻', '据悉', '消息人士', '知情人士']),
    ("政策", ['政策', '监管', '补贴', '关税', '降准', '利率', '反垄断']),
    ("板块行情", ['板块', '指数', '涨停', '跌停', '北向', '成交额', '两市']),
]


def norm_entity(ent):
    """实体同义归一（v1.5）：SK海力士 → 海力士"""
    return ENTITY_ALIASES.get(ent, ent)


def extract_entities(text):
    """提取核心实体（归一后）+ 主题实体（公司实体优先）"""
    hits = []
    t = text or ""
    company_ents = [e for e in EVENT_ALIAS_KEYS if e in t]
    theme_hits = [e for e in THEME_ENTITIES if e in t]
    all_ents = company_ents + theme_hits
    for ent in sorted(all_ents, key=len, reverse=True):
        if ent in t:
            hits.append(norm_entity(ent))
    # 去重保序（公司实体在前）
    seen = set()
    out = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out[:3]


EVENT_ALIAS_KEYS = list(ENTITY_ALIASES.keys()) + [
    "CoreWeave", "Lumentum", "英伟达", "博通", "台积电", "AMD", "美光", "三星", "特斯拉", "苹果",
    "微软", "谷歌", "亚马逊", "Meta", "氧化铝", "沙特阿美", "中海油", "中际旭创", "新易盛",
    "天孚通信", "沪电股份", "胜宏科技", "生益科技", "兴森科技", "北方华创", "中芯国际", "寒武纪",
    "兆易创新", "江波龙", "佰维存储", "德明利", "药明康德", "康龙化成", "凯莱英", "天岳先进",
    "英飞凌", "永鼎股份", "聚和材料", "金海通", "深科达", "长川科技", "DeepSeek", "宇树",
    "长鑫存储", "国民技术", "爱丽家居", "欧菲光", "信通电子", "菲利华", "合锻智能", "强瑞技术",
    "耐科装备", "杰华特", "江河集团", "四川路桥", "金达威", "工业富联", "江波龙", "鹏鼎控股",
    "雅本化学", "上美股份", "欧科亿", "兴森科技", "永鼎股份",
]


def event_type_of(text):
    t = text or ""
    for etype, kws in EVENT_TYPE_RULES:
        if any(k in t for k in kws):
            return etype
    return "行业事件"


def title_clean(text):
    """标题归一（v1.5）：去时间戳/机构前缀/编号/特殊字符"""
    t = re.split(r'[\n\r]', (text or "").strip())[0]
    t = re.sub(r'^\s*\d{1,2}:\d{2}\s*[　 ]*', '', t)
    t = re.sub(r'^[【\[]([^】\]]{0,10})[】\]]\s*', '', t)
    t = re.sub(r'^(汇报|快报|简报|速递|摘要|更新)\s*\d*\s*', '', t)
    t = re.sub(r'[（(]\d+[)）]', '', t)
    t = re.sub(r'[\s\u3000]+', '', t)
    return t.strip()[:50]


def detect_event_role(ct, role, mtype, text):
    """事件内消息角色（v1.5）：
    fact=事实快讯 | source=原始来源/公告 | research=机构观点 | commentary=二次解读
    mapping=A股映射 | update=后续更新（默认）"""
    if mtype == "image":
        return "attachment"
    t = text or ""
    # 概念股/映射：含 概念股/标的/受益/A股映射 等词
    if re.search(r'(概念股|标的股|映射|受益股|A股受益|相关A股|概念股汇总)', t):
        return "mapping"
    if ct == "news":
        return "fact" if role != "commentary" else "commentary"
    if ct in ("research_report", "research_activity"):
        return "research"
    if ct == "institution_view":
        return "research" if role == "original" else "commentary"
    if ct == "announcement":
        return "source"
    if ct == "digest":
        return "summary"
    return "update"


def event_status(dates, now):
    """事件状态（v1.5）：按更新频率 + 时间跨度
    emerging=新出现（首次<24h 且 消息<=3）
    heating=升温（更新>=4 且 时间跨度<48h）
    stable=持续（跨度>=48h）
    fading=降温（跨度>=72h 且 更新少）
    closed=结束（跨度>=7天 无更新）"""
    if not dates:
        return "stable"
    first = min(dates)
    last = max(dates)
    try:
        f = datetime.strptime(first[:19], "%Y-%m-%d %H:%M:%S")
        l = datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return "stable"
    span_h = (l - f).total_seconds() / 3600
    n = len(dates)
    # 距现在多久无更新
    try:
        now_dt = datetime.strptime(now[:19], "%Y-%m-%d %H:%M:%S")
        idle_h = (now_dt - l).total_seconds() / 3600
    except Exception:
        idle_h = 0
    if span_h >= 168 or idle_h >= 120:
        return "closed"
    if span_h >= 72 and n <= 3:
        return "fading"
    if span_h >= 48:
        return "stable"
    if n >= 4:
        return "heating"
    return "emerging"


def main():
    con = sqlite3.connect(DB)
    # 自选股（评分维度）
    watch = set()
    try:
        scon = sqlite3.connect("/root/stock-kanban/backend/stocks.db")
        watch = {str(r[0]) for r in scon.execute("SELECT symbol FROM stocks")}
        scon.close()
    except Exception:
        pass

    rows = con.execute("""
        SELECT c.message_id, r.date, r.raw_text, c.content_type, c.research_value,
               c.institution, c.themes_json, c.message_role
        FROM message_classification c JOIN raw_messages r
          ON r.chat_id || ':' || r.message_id = c.message_id
        WHERE c.content_type != 'empty_invalid' AND c.content_type != 'attachment'
    """).fetchall()

    con.execute("DELETE FROM event_messages")
    con.execute("DELETE FROM event_clusters")

    # 第一步：实体 + 日期 初步分组（实体已归一）
    events = {}
    for mid, mdate, text, ct, value, inst, themes_json, role in rows:
        if not text:
            continue
        day = (mdate or "")[:10]
        # 汇总类消息（下周提醒/大事记/一周展望/财经日历）不创建事件，只贡献已有事件
        if re.search(r'(下周.*(提醒|展望|大事|关注|数据)|一周.*(展望|回顾|前瞻)|财经日历|本周关注|本月关注)', text):
            continue
        ents = extract_entities(text)
        if not ents:
            continue
        for ent in ents:
            key = f"{ent}|{day}"
            ev = events.setdefault(key, {
                "entities": [], "message_ids": [], "dates": [],
                "title": "", "best_val": -1, "types": [], "insts": set(),
                "themes": set(), "theme_cnt": {}, "value_sum": 0,
                "roles": [], "sources": set(), "from_users": set(), "has_stock": False,
                "fact_titles": [], "view_titles": [], "is_digest_only": True,
            })
            if ent not in ev["entities"]:
                ev["entities"].append(ent)
            ev["message_ids"].append(mid)
            ev["dates"].append(mdate)
            ev["insts"].add(inst or "社群")
            ev["sources"].add(inst or "社群")
            ev["value_sum"] += value or 0
            if ct != "digest":
                ev["is_digest_only"] = False
            try:
                th = json.loads(themes_json) if themes_json else []
            except Exception:
                th = []
            for th_ in th:
                ev["themes"].add(th_)
                ev["theme_cnt"][th_] = ev["theme_cnt"].get(th_, 0) + 1
            if value and value > ev["best_val"] and ct != "digest":
                ev["best_val"] = value
                ev["title"] = title_clean(text)
            ev["types"].append(event_type_of(text))
            ev["roles"].append(detect_event_role(ct, role or "", "text", text))
            # 标题候选：优先 fact/news 类（标题干净），其次 research
            cand = title_clean(text)
            if ct in ("news", "announcement", "market") and len(cand) >= 6:
                ev.setdefault("fact_titles", []).append((value or 0, cand))
            else:
                ev.setdefault("view_titles", []).append((value or 0, cand))
            # 股票映射检测
            nm = con.execute("SELECT stock_codes_json FROM normalized_messages WHERE message_id=?", (mid,)).fetchone()
            if nm and nm[0]:
                try:
                    if json.loads(nm[0]):
                        ev["has_stock"] = True
                except Exception:
                    pass

    # 第二步：跨日期归并（v1.5：相邻日期同一实体合并，cluster_confidence 降级）
    # 同一实体出现在 连续 2 天内 → 合并为一个事件（如 08-11/08-12 海力士）
    # key=(ent, first_day)，days 集合存在 value 里（set 不可哈希，不能当 key）
    merged = {}
    for key, ev in events.items():
        ent, day = key.split("|")
        placed = False
        for mkey in list(merged.keys()):
            ment = mkey[0]
            if ment == ent:
                target_days = merged[mkey]["days"]
                if any(abs((datetime.strptime(day, "%Y-%m-%d") - datetime.strptime(d, "%Y-%m-%d")).days) <= 2 for d in target_days):
                    # 并入
                    target_days.add(day)
                    target = merged[mkey]
                    target["message_ids"].extend(ev["message_ids"])
                    target["dates"].extend(ev["dates"])
                    target["insts"].update(ev["insts"])
                    target["sources"].update(ev["sources"])
                    target["value_sum"] += ev["value_sum"]
                    target["roles"].extend(ev["roles"])
                    target["types"].extend(ev["types"])
                    for th_, c in ev["theme_cnt"].items():
                        target["themes"].add(th_)
                        target["theme_cnt"][th_] = target["theme_cnt"].get(th_, 0) + c
                    if ev["best_val"] > target["best_val"]:
                        target["best_val"] = ev["best_val"]
                        target["title"] = ev["title"]
                    if ev["has_stock"]:
                        target["has_stock"] = True
                    for e in ev["entities"]:
                        if e not in target["entities"]:
                            target["entities"].append(e)
                    placed = True
                    break
        if not placed:
            ev["days"] = {day}
            merged[(ent, day)] = ev

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created = 0
    for (ent, first_day), ev in merged.items():
        if len(ev["message_ids"]) < 1:
            continue
        # digest 单独命中（无实质内容消息）→ 不建事件（汇总类消息只贡献到已有事件）
        if ev.get("is_digest_only"):
            continue
        days_set = ev["days"]
        day = sorted(days_set)[0]
        # 事件类型：多数投票
        etype = max(set(ev["types"]), key=ev["types"].count) if ev["types"] else "行业事件"
        # 事件标题：优先 fact 类干净标题（news/公告），其次机构观点标题
        # 只取【包含本实体】的消息标题（避免 凯莱英 事件被 药明康德 标题污染）
        fact_titles = sorted([x for x in ev.get("fact_titles", []) if ent in x[1] or ent in (ev.get("title") or "")], key=lambda x: -x[0])
        view_titles = sorted([x for x in ev.get("view_titles", []) if ent in x[1] or ent in (ev.get("title") or "")], key=lambda x: -x[0])
        if not fact_titles:
            fact_titles = sorted(ev.get("fact_titles", []), key=lambda x: -x[0])
        if not view_titles:
            view_titles = sorted(ev.get("view_titles", []), key=lambda x: -x[0])
        if fact_titles and len(fact_titles[0][1]) >= 6:
            title = fact_titles[0][1]
        elif view_titles and len(view_titles[0][1]) >= 6:
            title = view_titles[0][1]
        elif ev.get("title"):
            title = ev["title"]
        else:
            title = f"{ent}事件"
        # 若标题仍不含本实体（被同消息的其他实体标题污染，如 凯莱英←药明康德），
        # 且存在未过滤的标题候选 → 取其中能体现本实体的第一句
        if ent not in title and (ev.get("fact_titles") or ev.get("view_titles")):
            for pool in (ev.get("fact_titles", []), ev.get("view_titles", [])):
                for _, cand in sorted(pool, key=lambda x: -x[0]):
                    if ent in cand:
                        title = cand
                        break
                if ent in title:
                    break
        # 去标题尾部噪音（残留时间戳/编号）
        title = re.sub(r'[：:]\s*\d{1,2}:\d{2}$', '', title)
        full_title = title if (title and ent in title) else (f"{ent}｜{title}" if title else f"{ent}事件")
        # 股票代码聚合
        stock_codes = []
        for mid in ev["message_ids"][:25]:
            nm = con.execute("SELECT stock_codes_json FROM normalized_messages WHERE message_id=?", (mid,)).fetchone()
            if nm and nm[0]:
                try:
                    stock_codes.extend(json.loads(nm[0]))
                except Exception:
                    pass
        stock_codes = list(dict.fromkeys(stock_codes))[:20]
        # 主题 top3
        top_themes = [t_ for t_, _ in sorted(ev["theme_cnt"].items(), key=lambda x: -x[1])][:3]
        if not top_themes:
            top_themes = sorted(ev["themes"])[:3]
        # 独立来源数 = 去重后的机构+社群（同源不重复计）
        n_src = len(ev["sources"])
        n_inst = len([s for s in ev["sources"] if s != "社群"])
        n_msg = len(ev["message_ids"])
        # ── 事件评分（v1.5 六维加权）──
        # 重要性 30%（research_value 归一）
        imp = min(30, int((ev["best_val"] if ev["best_val"] > 0 else 50) * 30 / 100))
        # 研究价值 20%（有机构观点的消息占比）
        n_research = sum(1 for r in ev["roles"] if r in ("research", "commentary"))
        research_pct = n_research / n_msg if n_msg else 0
        rv = int(20 * research_pct)
        # 机构数量 15%（>=3 家满分）
        nv = int(15 * min(1.0, n_inst / 3))
        # 独立来源 15%（>=5 来源满分）
        sv = int(15 * min(1.0, n_src / 5))
        # 自选股关联 10%
        wv = 10 if any(c in watch for c in stock_codes) else 0
        # 时效性 10%（最近 12h 内更新满分，24h 减半）
        try:
            last_dt = datetime.strptime(max(ev["dates"])[:19], "%Y-%m-%d %H:%M:%S")
            now_dt = datetime.strptime(now[:19], "%Y-%m-%d %H:%M:%S")
            age_h = (now_dt - last_dt).total_seconds() / 3600
        except Exception:
            age_h = 99
        tv = int(10 * (1 if age_h <= 12 else (0.5 if age_h <= 24 else 0.2)))
        event_score = imp + rv + nv + sv + wv + tv
        # ── 状态 ──
        status = event_status(ev["dates"], now)
        # ── 聚类置信度：同日同实体=0.9，跨日合并=0.7 ──
        cluster_conf = 0.9 if len(days_set) == 1 else 0.7

        cur = con.execute("""INSERT INTO event_clusters
            (event_title, event_type, industry, themes_json, occurred_date, stock_codes_json,
             source_count, institution_count, importance_score, first_seen_at, last_seen_at,
             entity_key, created_at, event_score, status, cluster_confidence, update_count, merge_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (full_title, etype, "", json.dumps(top_themes, ensure_ascii=False), day,
             json.dumps(stock_codes, ensure_ascii=False),
             n_src, n_inst, ev["best_val"] if ev["best_val"] > 0 else 50,
             min(ev["dates"]) if ev["dates"] else now, max(ev["dates"]) if ev["dates"] else now,
             f"{ent}|{day}", now, event_score, status, cluster_conf, n_msg, "auto"))
        eid = cur.lastrowid
        # 角色分层写入 event_messages
        for mid, role in zip(ev["message_ids"], ev["roles"]):
            con.execute("INSERT OR IGNORE INTO event_messages (event_id, message_id, message_role) VALUES (?,?,?)",
                        (eid, mid, role))
        created += 1
    con.commit()

    print(f"✅ v1.5 语义事件: {created} 个事件")
    top = con.execute("""SELECT event_id, event_title, event_type, event_score, status,
                                source_count, institution_count, update_count, cluster_confidence
                         FROM event_clusters ORDER BY event_score DESC LIMIT 10""").fetchall()
    for r in top:
        print(f"   [{r[3]}分|{r[4]}] {r[1][:34]} | {r[2]} | {r[5]}来源 {r[6]}机构 {r[7]}更新 conf={r[8]}")
    # 状态分布
    print("  状态分布:", dict(con.execute("SELECT status, COUNT(*) FROM event_clusters GROUP BY 1").fetchall()))
    # 角色分布
    print("  角色分布:", dict(con.execute("SELECT message_role, COUNT(*) FROM event_messages GROUP BY 1").fetchall()))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
