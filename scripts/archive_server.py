#!/usr/bin/env python3
"""资讯研究档案库 v1.0 - API Server（统一版表结构）
标准库 http.server + SQLite，端口 8095。nginx /research/ 反代。
2026-08-09
"""
import json
import re
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import sys as _sys
_sys.path.insert(0, "/root/scripts")
from institution_map import normalize_institution

DB = "/root/workspace/research_archive.db"
PORT = 8095

# ---- 标题清洗规则（2026-08-09 改进：去时间/媒体/报道前缀，提取第一句或冒号前）----
_TITLE_PREFIX_PATTERNS = [
    r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*\d{0,2}:?\d{0,2}:?\d{0,2}\s*',  # 2026-08-1209:26:21 日期时间粘连
    r'^\d{1,2}:\d{2}(?::\d{2})?\s*',          # 08:06 / 08:47:37
    r'^财联社电\s*',
    r'^财联社\s*\d{1,2}月\d{1,2}日[电讯]\s*',
    r'^[（(]?路透社[)）]?\s*[—\-—]?\s*',       # 路透社） 全/半角
    r'^据[^，。；]{0,15}(报道|消息|援引)[^，。；]{0,10}\s*',
    r'^据报道\s*',
    r'^消息人士[：:]\s*',
    r'^记者[：:]?\s*',
    r'^汇报\d*[：:\s]*',
    r'^#\s*',
    r'^【[^】]{1,10}】\s*',
    r'^[（(][^）)]{1,10}[)）]\s*',
    r'^[—\-—]\s*',
    r'^[，,]\s*',
]


def clean_text_prefix(text: str) -> str:
    """清除文本开头的媒体/时间/报道前缀（多轮），返回剩余文本"""
    t = re.sub(r'\s+', ' ', text or '').strip()
    for _ in range(5):
        new_t = t
        for pat in _TITLE_PREFIX_PATTERNS:
            new_t = re.sub(pat, '', new_t)
        if new_t == t:
            break
        t = new_t
    return t


def clean_title(text: str) -> str:
    """从原始文本提取干净标题（前缀多轮清除 + 第一句/冒号前提取 + 短标题fallback）"""
    t = clean_text_prefix(text)
    if not t:
        return "未提取标题"
    # 第一句（。！？结尾）
    m = re.search(r'^([^。！？]{8,60})[。！？]', t)
    if m:
        return m.group(1).strip()
    # 冒号前（排除时间类）
    m = re.search(r'^([^：:]{8,60})[：:]', t)
    if m and not re.match(r'^\d{1,2}:\d{2}', m.group(1)):
        return m.group(1).strip()
    if len(t) > 60:
        return t[:60] + "…"
    # 短标题（<8字）fallback：从剩余文本前 40 字截断作为标题
    if len(t) < 8:
        if len(text or "") > 20:
            return clean_text_prefix(text)[:40] + "…" if len(clean_text_prefix(text)) > 40 else clean_text_prefix(text)
    return t or "未提取标题"


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = json.loads(self.rfile.read(length).decode() or "{}") if length else {}
            if path.endswith("/api/watchpool/advance"):
                self._watchpool_advance(body)
            elif path.endswith("/api/watchpool/note"):
                self._watchpool_note(body)
            elif path.endswith("/api/events/merge"):
                self._event_merge(body)
            elif path.endswith("/api/events/split"):
                self._event_split(body)
            elif path.endswith("/api/vision/request"):
                self._vision_request(body)
            elif path.endswith("/api/vision/invalid"):
                self._vision_invalid(body)
            elif path.endswith("/api/reclassify"):
                self._reclassify(body)
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _reclassify(self, body):
        """人工改分类：{mid, category, secondary}
        category: research|news|announcement|market|empty_invalid
        改为 research 时触发研报归并（该消息进入 report_series）"""
        mid = body.get("mid")
        category = body.get("category")
        secondary = body.get("secondary", "")
        if not mid or not category:
            self._json({"error": "missing mid/category"}, 400)
            return
        con = db()
        cur = con.execute("""UPDATE message_classification SET
                             primary_category=?, secondary_category=?, review_required=0,
                             review_reason='', confidence=CASE WHEN confidence='low' THEN 'medium' ELSE confidence END
                             WHERE message_id=?""", (category, secondary, mid))
        con.commit()
        n = cur.rowcount
        con.close()
        merged = False
        if category == "research" and n > 0:
            # 触发研报归并（子进程运行 merge 脚本）
            import subprocess
            try:
                r = subprocess.run(["python3", "/root/scripts/archive_merge_v3.py"],
                                   capture_output=True, text=True, timeout=120)
                merged = r.returncode == 0
            except Exception:
                merged = False
        self._json({"ok": True, "mid": mid, "reclassified": n > 0, "merged": merged})

    def _vision_request(self, body):
        """图片消息加入 Vision 分析队列（vision_status: pending→queued）"""
        mid = body.get("mid")
        if not mid:
            self._json({"error": "missing mid"}, 400)
            return
        con = db()
        cur = con.execute("""UPDATE message_classification SET vision_status='queued'
                             WHERE message_id=? AND primary_category='image'""", (mid,))
        con.commit()
        n = cur.rowcount
        con.close()
        self._json({"ok": True, "mid": mid, "queued": n > 0})

    def _vision_invalid(self, body):
        """人工标记图片无效（vision_status: invalid）"""
        mid = body.get("mid")
        if not mid:
            self._json({"error": "missing mid"}, 400)
            return
        con = db()
        cur = con.execute("""UPDATE message_classification SET vision_status='invalid',
                             review_required=0
                             WHERE message_id=?""", (mid,))
        con.commit()
        n = cur.rowcount
        con.close()
        self._json({"ok": True, "mid": mid, "invalidated": n > 0})

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if path.endswith("/api/dashboard/cockpit"):
                self._cockpit()
            elif path.endswith("/api/dashboard/summary"):
                self._summary()
            elif path.endswith("/api/reports"):
                self._reports(qs)
            elif "/api/reports/" in path and path.rsplit("/", 1)[-1].isdigit():
                self._report_detail(path.rsplit("/", 1)[-1])
            elif path.endswith("/api/stocks/research"):
                self._stock_research(qs)
            elif path.endswith("/api/topics/research"):
                self._topic_research(qs)
            elif path.endswith("/api/industry"):
                self._industry_intel(qs)
            elif path.endswith("/api/documents"):
                self._documents(qs)
            elif path.endswith("/api/research-documents"):
                self._research_documents(qs)
            elif path.endswith("/api/industries"):
                self._industries(qs)
            elif path.endswith("/api/graph"):
                self._graph(qs)
            elif path.endswith("/api/timeline"):
                self._timeline(qs)
            elif path.endswith("/api/events"):
                self._events(qs)
            elif path.endswith("/api/watchpool"):
                self._watchpool(qs)
            elif path.endswith("/api/stocks/events"):
                self._stock_events(qs)
            elif path.endswith("/api/research-score"):
                self._research_score(qs)
            elif path.endswith("/api/validation/stats"):
                self._validation_stats()
            elif path.endswith("/api/validation"):
                self._validation(qs)
            elif path.endswith("/api/message"):
                self._message_detail(qs)
            elif path.endswith("/api/search"):
                self._search(qs)
            elif path.endswith("/api/review"):
                self._review()
            elif path.endswith("/api/quality"):
                self._quality()
            elif path.endswith("/api/today-top"):
                self._today_top()
            elif path.endswith("/api/reclassify"):
                self._reclassify()
            elif path.endswith("/api/version"):
                self._version()
            elif path.endswith("/api/verifications"):
                self._verifications(qs)
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    # ---------- API ----------

    def _version(self):
        """档案库后端版本（动态，读 research_system_snapshot 最新 system_version）"""
        con = db()
        row = con.execute(
            "SELECT snap_date, system_version FROM research_system_snapshot ORDER BY snap_date DESC LIMIT 1"
        ).fetchone()
        if not row:
            self._json({"version": "unknown", "updated": None})
            return
        self._json({"version": row[1], "updated": row[0]})



    def _cockpit(self):
        """今日研究驾驶舱（v2.0）：升温事件 + 事件关联最高RS股票 + 重点研究列表"""
        import json as _json
        con = db()
        r = con.execute("SELECT max(date) d FROM raw_messages").fetchone()
        today = r["d"][:10] if r["d"] else "2026-01-01"
        # 2026-08-13 时区修复(显示层,不改数据): raw_messages.date=北京时间,
        # 而 research_scores/research_summary.created_at 为 VPS 本地时区写入(v19/v20 datetime.now())
        # 各板块改用各自表的最新日期过滤,避免早间简报三板块恒为空
        sd = con.execute("SELECT max(substr(created_at,1,10)) FROM research_scores").fetchone()
        score_day = sd[0] if sd and sd[0] else today
        ed = con.execute("SELECT max(occurred_date) FROM event_clusters").fetchone()
        event_day = ed[0] if ed and ed[0] else today

        # ── 1. 今日升温事件（heating/emerging + 有 RS 股票关联）──
        events = [dict(x) for x in con.execute("""
            SELECT e.event_id, e.event_title, e.event_type, e.momentum_score, e.momentum_peak,
                   e.status, e.source_count, e.institution_count, e.first_seen_at, e.last_seen_at,
                   e.event_score
            FROM event_clusters e
            WHERE e.occurred_date=? AND e.status IN ('heating','emerging')
              AND e.merge_status != 'manual_merged'
            ORDER BY e.momentum_score DESC LIMIT 8""", (event_day,)).fetchall()]
        for ev in events:
            stocks = [dict(x) for x in con.execute("""
                SELECT r.stock_code, r.stock_name, r.relation_type, r.impact_score,
                       rs.research_score, rs.score_status, rs.research_state
                FROM event_stock_relation r
                LEFT JOIN research_scores rs ON rs.stock_code = r.stock_code
                WHERE r.event_id=? AND rs.research_score IS NOT NULL
                ORDER BY rs.research_score DESC LIMIT 3""", (ev["event_id"],)).fetchall()]
            ev["top_stocks"] = stocks
            ev["max_rs"] = stocks[0]["research_score"] if stocks else None

        # ── 2. 今日重点研究（RS >= 70，带 summary）──
        focus = [dict(x) for x in con.execute("""
            SELECT s.stock_code, s.stock_name, s.research_score, s.score_status, s.research_state,
                   s.event_title, s.momentum_score, s.score_change,
                   su.summary, su.suggestion, su.positive_factors, su.risk_factors
            FROM research_scores s
            LEFT JOIN research_summary su ON su.stock_code = s.stock_code
                AND su.created_at LIKE ?
            WHERE s.created_at LIKE ? AND s.research_score >= 70
            ORDER BY s.research_score DESC LIMIT 12""", (score_day + "%", score_day + "%")).fetchall()]
        for f in focus:
            try:
                f["positive_factors"] = _json.loads(f.get("positive_factors") or "[]")
                f["risk_factors"] = _json.loads(f.get("risk_factors") or "[]")
            except Exception:
                pass

        # ── 3. 今日升温股票（score_change >= 5）──
        rising = [dict(x) for x in con.execute("""
            SELECT stock_code, stock_name, research_score, score_change, research_state,
                   score_status, event_title
            FROM research_scores WHERE created_at LIKE ? AND score_change >= 5
            ORDER BY score_change DESC LIMIT 10""", (score_day + "%",)).fetchall()]

        con.close()
        return self._json({"date": today, "hot_events": events, "focus_stocks": focus, "rising_stocks": rising})

    def _summary(self):
        con = db()
        r = con.execute("SELECT max(date) d FROM raw_messages").fetchone()
        today = r["d"][:10] if r["d"] else "2026-01-01"
        def cnt(sql, *a):
            return con.execute(sql, a).fetchone()[0]
        summary = {
            "date": today,
            "total_messages": cnt("SELECT count(*) FROM raw_messages"),
            "today_messages": cnt("SELECT count(*) FROM raw_messages WHERE date LIKE ?", today + "%"),
            "reports": cnt("SELECT count(*) FROM report_series"),
            "research_today": cnt("""SELECT count(*) FROM message_classification c JOIN raw_messages r
                                      ON r.chat_id||':'||r.message_id=c.message_id
                                      WHERE c.primary_category='research' AND r.date LIKE ?""", today + "%"),
            "news_today": cnt("""SELECT count(*) FROM message_classification c JOIN raw_messages r
                                 ON r.chat_id||':'||r.message_id=c.message_id
                                 WHERE c.primary_category='news' AND r.date LIKE ?""", today + "%"),
            "announcement_today": cnt("""SELECT count(*) FROM message_classification c JOIN raw_messages r
                                         ON r.chat_id||':'||r.message_id=c.message_id
                                         WHERE c.primary_category='announcement' AND r.date LIKE ?""", today + "%"),
            "market_today": cnt("""SELECT count(*) FROM message_classification c JOIN raw_messages r
                                   ON r.chat_id||':'||r.message_id=c.message_id
                                   WHERE c.primary_category='market' AND r.date LIKE ?""", today + "%"),
            "review_pending": cnt("SELECT count(*) FROM message_classification WHERE review_required=1"),
            "image_pending": cnt("SELECT count(*) FROM message_classification WHERE vision_status='pending'"),
            "verify_pending": cnt("SELECT count(*) FROM report_verifications WHERE verification_status='待验证'"),
            "total_research": cnt("SELECT count(*) FROM message_classification WHERE primary_category='research'"),
            "total_news": cnt("SELECT count(*) FROM message_classification WHERE primary_category='news'"),
            "total_messages_all": cnt("SELECT count(*) FROM message_classification WHERE primary_category != 'empty_invalid'"),
            "source_topics": dict(con.execute("SELECT source_topic, count(*) FROM raw_messages GROUP BY source_topic").fetchall()),
            "content_types": dict(con.execute("SELECT primary_category, count(*) FROM message_classification GROUP BY primary_category").fetchall()),
            # ── v1.4 维度 ──
            "content_type_today": dict(con.execute("""
                SELECT c.content_type, count(*) FROM message_classification c
                JOIN raw_messages r ON r.chat_id||':'||r.message_id=c.message_id
                WHERE r.date LIKE ? GROUP BY c.content_type""", (today + "%",)).fetchall()),
            "content_type_total": dict(con.execute("""
                SELECT content_type, count(*) FROM message_classification GROUP BY content_type""").fetchall()),
            "events_today": cnt("SELECT count(*) FROM event_clusters WHERE occurred_date=?", today),
            "events_total": cnt("SELECT count(*) FROM event_clusters"),
            "subtype_today": dict(con.execute("""
                SELECT c.content_subtype, count(*) FROM message_classification c
                JOIN raw_messages r ON r.chat_id||':'||r.message_id=c.message_id
                WHERE r.date LIKE ? AND c.content_subtype IS NOT NULL AND c.content_subtype!=''
                GROUP BY c.content_subtype ORDER BY 2 DESC LIMIT 12""", (today + "%",)).fetchall()),
            "active_reports": cnt("SELECT count(*) FROM report_series WHERE status='active'"),
            "candidate_reports": cnt("SELECT count(*) FROM report_series WHERE status='candidate'"),
        }
        con.close()
        self._json(summary)

    def _reports(self, qs):
        con = db()
        where, args = [], []
        if qs.get("type"):
            where.append("s.report_type=?")
            args.append(qs["type"][0])
        if qs.get("inst"):
            where.append("s.institution LIKE ?")
            args.append(f"%{qs['inst'][0]}%")
        if qs.get("q"):
            where.append("(s.title LIKE ? OR s.institution LIKE ?)")
            args += [f"%{qs['q'][0]}%", f"%{qs['q'][0]}%"]
        sql = f"""SELECT s.series_id, s.title, s.institution, s.analyst, s.report_type,
                         s.first_seen_at, s.last_seen_at, s.current_version, s.occurrence_count, s.status
                  FROM report_series s
                  {"WHERE " + " AND ".join(where) if where else ""}
                  ORDER BY s.last_seen_at DESC LIMIT 200"""
        rows = [dict(r) for r in con.execute(sql, args).fetchall()]
        con.close()
        self._json({"reports": rows, "count": len(rows)})

    def _report_detail(self, series_id):
        con = db()
        s = con.execute("SELECT * FROM report_series WHERE series_id=?", (series_id,)).fetchone()
        if not s:
            self._json({"error": "not found"}, 404)
            return
        versions = [dict(r) for r in con.execute(
            "SELECT version_no, core_view, logic, catalysts, risks, valuation, stock_codes_json, industries_json, changed_summary, created_at FROM report_versions WHERE report_id=? ORDER BY version_no", (series_id,)).fetchall()]
        occs = [dict(r) for r in con.execute(
            "SELECT message_id, appeared_at, is_primary, is_duplicate, duplicate_type FROM report_occurrences WHERE report_id=? ORDER BY appeared_at", (series_id,)).fetchall()]
        verifs = [dict(r) for r in con.execute(
            "SELECT event_date, event_type, event_text, verification_status, evidence_source FROM report_verifications WHERE report_id=? ORDER BY event_date", (series_id,)).fetchall()]
        con.close()
        self._json({"series": dict(s), "versions": versions, "occurrences": occs, "verifications": verifs})

    def _resolve_stock_keyword(self, kw, con):
        """股票关键词解析：支持代码/名称/别名，返回 {code, name, entity_id}。
        解析顺序：6位代码 -> watchlist stocks.csv（权威名称表）-> 实体表 -> 归一化消息。
        2026-08-12 修复：名称查询时 entity_id 匹配不上导致相关研报为 0。"""
        kw = (kw or "").strip()
        if not kw:
            return None
        # 1) 直接是6位代码
        if re.fullmatch(r"\d{6}", kw):
            return {"code": kw, "name": None, "entity_id": kw}
        # 2) watchlist stocks.csv 权威名称映射（code<->name 双向）
        import csv as _csv
        try:
            with open("/opt/watchlist-stock-analysis/trading_engine/data/stocks.csv", encoding="utf-8") as f:
                for row in _csv.DictReader(f):
                    c = (row.get("code") or "").strip()
                    n = (row.get("name") or "").strip()
                    if n == kw:
                        return {"code": c, "name": n, "entity_id": c}
        except Exception:
            pass
        # 3) 研究评分表（stock_name 字段，可能存的是代码兜底）
        row = con.execute(
            "SELECT stock_code, stock_name FROM research_scores WHERE stock_name=? LIMIT 1",
            (kw,)).fetchone()
        if row and row["stock_code"]:
            return {"code": row["stock_code"], "name": row["stock_name"], "entity_id": row["stock_code"]}
        # 4) 实体表 entity_name
        row = con.execute(
            "SELECT entity_id, entity_name FROM report_entities WHERE entity_type IN ('stock','STOCK') AND entity_name=? LIMIT 1",
            (kw,)).fetchone()
        if row:
            return {"code": row["entity_id"], "name": row["entity_name"], "entity_id": row["entity_id"]}
        # 5) 归一化消息中出现的股票名
        import json as _json
        rows = con.execute(
            "SELECT message_id, stock_codes_json, stock_names_json FROM normalized_messages LIMIT 3000").fetchall()
        for r in rows:
            try:
                names = _json.loads(r["stock_names_json"] or "[]")
            except Exception:
                names = []
            if kw in names:
                try:
                    codes = _json.loads(r["stock_codes_json"] or "[]")
                except Exception:
                    codes = []
                if codes:
                    return {"code": str(codes[0]).zfill(6), "name": kw, "entity_id": str(codes[0]).zfill(6)}
        return {"code": None, "name": kw, "entity_id": None}

    # 行业同义词映射（v2.2.3）：输入关键词 → 展开为同义词族用于匹配
    INDUSTRY_SYNONYMS = {
        "新能源车": ["新能源汽车", "新能源车", "整车", "动力电池", "锂电", "锂电池", "电动化", "充电桩"],
        "AI算力": ["AI算力", "算力", "智算", "大模型", "GPU", "AI服务", "云服务"],
        "半导体": ["半导体", "芯片", "晶圆", "封测", "存储芯片", "光刻"],
        "光通信": ["光模块", "CPO", "光通信", "硅光", "1.6T", "Lumentum"],
        "PCB": ["PCB", "载板", "CCL", "覆铜板", "mSAP"],
        "机器人": ["机器人", "人形机器人", "减速器", "丝杠", "宇树"],
        "军工": ["军工", "国防", "导弹", "军贸"],
        "存储": ["存储", "DRAM", "NAND", "HBM", "海力士", "三星存储"],
        "医药": ["创新药", "CXO", "医药", "CRO", "CDMO", "药明"],
        "电力": ["电力", "电网", "HVDC", "特高压", "核电"],
    }

    def _industry_keywords(self, topic):
        """返回同义词族关键词列表（含原词）"""
        t = (topic or "").strip()
        if not t:
            return []
        if t in self.INDUSTRY_SYNONYMS:
            return self.INDUSTRY_SYNONYMS[t]
        return [t]

    def _industry_intel(self, qs):
        """行业画像（v2.2.3 Industry Intelligence）：事件 + 股票 + RS + 资讯 聚合。
        输入关键词 → 同义词展开 → 行业概览/事件/重点股票/资讯列表"""
        import json as _json
        topic = (qs.get("topic") or [""])[0].strip()
        if not topic:
            return self._json({"error": "missing topic"}, 400)
        con = db()
        kws = self._industry_keywords(topic)
        # 匹配条件：主题词 OR 事件标题 OR 行业标签
        like_args = [f"%{k}%" for k in kws]
        like_sql = " OR ".join(["e.event_title LIKE ?"] * len(kws))

        # ── ① 行业事件（标题含同义词 OR 事件关联消息内容含同义词）──
        events = [dict(r) for r in con.execute(
            f"""SELECT e.event_id, e.event_title, e.event_type, e.momentum_score, e.event_score,
                       e.status, e.trigger_type, e.first_seen_at, e.last_seen_at,
                       e.institution_count, e.source_count, e.industry
                FROM event_clusters e
                WHERE ({like_sql} OR e.event_id IN (
                    SELECT DISTINCT em.event_id FROM event_messages em
                    JOIN raw_messages rm ON rm.chat_id||':'||rm.message_id = em.message_id
                    WHERE {like_sql}
                )) AND e.merge_status != 'manual_merged'
                ORDER BY e.momentum_score DESC LIMIT 20""", like_args + like_args).fetchall()]

        # ── ② 关联股票（event_stock_relation → 该批事件）──
        stocks = []
        if events:
            ev_ids = [e["event_id"] for e in events]
            placeholders = ",".join("?" * len(ev_ids))
            rels = con.execute(
                f"""SELECT DISTINCT r.stock_code, r.stock_name, r.relation_type, r.impact_score,
                           r.logic, r.mention_count
                    FROM event_stock_relation r
                    WHERE r.event_id IN ({placeholders})
                    ORDER BY r.impact_score DESC, r.mention_count DESC LIMIT 30""", ev_ids).fetchall()
            for r in rels:
                d = dict(r)
                rs = con.execute("SELECT research_score, score_status, research_state FROM research_scores WHERE stock_code=? ORDER BY id DESC LIMIT 1",
                                 (d["stock_code"],)).fetchone()
                d["rs"] = rs[0] if rs else None
                d["rs_status"] = rs[1] if rs else None
                d["research_state"] = rs[2] if rs else None
                # 该股票在此行业的事件数
                d["event_count"] = con.execute(
                    f"SELECT COUNT(*) FROM event_stock_relation WHERE stock_code=? AND event_id IN ({placeholders})",
                    (d["stock_code"], *ev_ids)).fetchone()[0]
                stocks.append(d)
            # RS 降序（有 RS 的优先）
            stocks.sort(key=lambda s: -(s["rs"] or 0))

        # ── ③ 重点研究股票（有 RS 且 >= 60 的）──
        research_stocks = [s for s in stocks if s["rs"] and s["rs"] >= 60][:10]

        # ── ④ 相关资讯（同义词 LIKE，证据来源）──
        msg_like_sql = " OR ".join(["(r.raw_text LIKE ? OR c.entities_json LIKE ? OR n.industries_json LIKE ?)"] * len(kws))
        msg_args = []
        for k in kws:
            msg_args += [f"%{k}%", f"%{k}%", f"%{k}%"]
        messages = [dict(r) for r in con.execute(
            f"""SELECT r.chat_id||':'||r.message_id AS mid, r.date, r.source_topic,
                       substr(r.raw_text,1,180) content, c.primary_category, c.secondary_category,
                       c.importance_score, c.institution
                FROM message_classification c
                JOIN raw_messages r ON r.chat_id||':'||r.message_id=c.message_id
                LEFT JOIN normalized_messages n ON n.message_id = c.message_id
                WHERE {msg_like_sql}
                ORDER BY r.date DESC LIMIT 50""", msg_args).fetchall()]

        con.close()
        return self._json({
            "industry": topic,
            "keywords": kws,
            "stats": {
                "events": len(events),
                "stocks": len(stocks),
                "research": len(research_stocks),
                "messages": len(messages),
            },
            "events": events,
            "stocks": stocks,
            "research_stocks": research_stocks,
            "messages": messages,
        })

    def _documents(self, qs):
        """研究文档列表（v2.3.0）：研究对象（归并后），质量≥50 优先展示"""
        import json as _json
        con = db()
        min_q = (qs.get("min_quality") or [""])[0]
        qfilter = ""
        args = []
        if min_q and min_q.isdigit():
            qfilter = "WHERE d.quality_score >= ?"
            args.append(int(min_q))
        rows = con.execute(f"""
            SELECT d.doc_id, d.title_clean, d.title_raw, d.company, d.institution,
                   d.research_type, d.content_nature, d.stock_codes_json,
                   d.source_count, d.institution_count, d.quality_score,
                   d.first_seen_at, d.last_seen_at
            FROM research_document d
            {qfilter}
            ORDER BY d.quality_score DESC, d.institution_count DESC, d.last_seen_at DESC
            LIMIT 100""", args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["stock_codes"] = _json.loads(d.get("stock_codes_json") or "[]")
            except Exception:
                d["stock_codes"] = []
            out.append(d)
        stats = dict(con.execute("""
            SELECT CASE WHEN quality_score>=80 THEN 'high' WHEN quality_score>=50 THEN 'medium' ELSE 'low' END bucket, COUNT(*)
            FROM research_document GROUP BY 1""").fetchall())
        con.close()
        return self._json({"documents": out, "total": len(out), "stats": stats})


    def _research_documents(self, qs):
        """研究对象中心（v2.3.1）：research_document 为主实体，聚合 机构/股票/事件/来源链。
        列表: /api/research-documents?min_quality=50&type=&inst=
        详情: /api/research-documents?id=123（附 source_chain 来源链）"""
        import json as _json, re as _re
        con = db()

        def _clean_title_display(t):
            """展示层标题净化（v2.3.1）：去 [红包][礼物] 前缀、数字#前缀、#笔记链接 等噪声"""
            if not t: return ""
            t = _re.sub(r"^\[红包\]", "", t).strip()
            t = _re.sub(r"^(\[红包\])+", "", t).strip()
            t = _re.sub(r"^\[礼物\]", "", t).strip()
            t = _re.sub(r"^\d{4,}#", "", t).strip()
            t = t.replace("#笔记链接", "").replace("笔记链接", "").strip()
            t = _re.sub(r"\[礼物\]", "", t).strip()
            t = _re.sub(r"\s+", " ", t).strip()
            return t

        min_q = (qs.get("min_quality") or ["50"])[0]
        ftype = (qs.get("type") or [""])[0]
        finst = (qs.get("inst") or [""])[0]
        did = (qs.get("id") or [""])[0]
        if not min_q.isdigit(): min_q = 50
        min_q = int(min_q)

        # 全局股票池（代码→名称）
        stock_pool = {}
        for r in con.execute("SELECT DISTINCT stock_code, stock_name FROM research_scores WHERE stock_code IS NOT NULL AND stock_code != ''"):
            stock_pool.setdefault(r["stock_code"], r["stock_name"] or "")
        for r in con.execute("SELECT DISTINCT stock_code, stock_name FROM event_stock_relation WHERE stock_code IS NOT NULL AND stock_code != ''"):
            stock_pool.setdefault(r["stock_code"], r["stock_name"] or "")

        # 股票池清洗：名称=6位纯数字 → 置空（原数据污染，如 通合科技300491 名称存了代码）
        for code in list(stock_pool.keys()):
            nm = str(stock_pool.get(code) or "").strip()
            if not nm or (len(nm) == 6 and nm.isdigit()):
                stock_pool[code] = ""
        # 名称→代码反查索引
        name_index = {}
        for code, nm in stock_pool.items():
            if not nm: continue
            nm = str(nm).strip()
            if not nm or (len(nm) == 6 and nm.isdigit()): continue  # 名称=代码 视为未识别
            name_index.setdefault(nm, code)

        # message_id → 机构（多机构聚合，修复 v230 只存首机构）
        inst_map = {}
        for r in con.execute("SELECT message_id, institution FROM message_classification WHERE institution IS NOT NULL AND institution != ''"):
            inst_map.setdefault(r["message_id"], r["institution"])

        # message_id → 事件（去重取最新）
        ev_map = {}
        for r in con.execute("""
            SELECT em.message_id, ec.event_id, ec.event_title, ec.momentum_score, ec.status
            FROM event_messages em JOIN event_clusters ec ON ec.event_id = em.event_id
            WHERE ec.status != 'closed'"""):
            ev_map.setdefault(r["message_id"], []).append(dict(r))

        # message_id → 原始消息（来源链）
        msg_info = {}
        for r in con.execute("""
            SELECT rm.chat_id || ':' || rm.message_id AS mid, rm.date, rm.from_user, rm.source_topic, rm.raw_text
            FROM raw_messages rm"""):
            msg_info[r["mid"]] = dict(r)

        where = ["d.quality_score >= ?"]
        args = [min_q]
        if ftype:
            where.append("d.research_type = ?"); args.append(ftype)
        if finst:
            where.append("(d.institution LIKE ? OR EXISTS (SELECT 1 FROM message_classification mc WHERE mc.message_id IN (SELECT value FROM json_each(d.message_ids_json)) AND mc.institution LIKE ?))")
            args.extend([f"%{finst}%", f"%{finst}%"])
        if did and did.isdigit():
            where.append("d.doc_id = ?"); args.append(int(did))

        rows = con.execute(f"""
            SELECT d.doc_id, d.title_clean, d.title_raw, d.company, d.institution,
                   d.research_type, d.content_nature, d.stock_codes_json, d.message_ids_json,
                   d.source_count, d.institution_count, d.quality_score,
                   d.first_seen_at, d.last_seen_at
            FROM research_document d
            WHERE {' AND '.join(where)}
            ORDER BY d.quality_score DESC, d.institution_count DESC, d.last_seen_at DESC
            LIMIT 300""", args).fetchall()

        # normalized 股票补提索引
        norm_stock = {}
        for r in con.execute("SELECT message_id, stock_codes_json FROM normalized_messages WHERE stock_codes_json IS NOT NULL AND stock_codes_json != '[]'"):
            norm_stock[r["message_id"]] = r["stock_codes_json"]

        out = []
        for r in rows:
            d = dict(r)
            try: mids = _json.loads(d["message_ids_json"] or "[]")
            except Exception: mids = []
            codes = []
            try:
                for c in _json.loads(d["stock_codes_json"] or "[]"):
                    c = str(c)
                    # 格式白名单（A股 60/68/00/30 前缀）或命中股票池，否则视为噪声/日期过滤
                    if _re.fullmatch(r"(?:60|68|00|30)\d{4}", c) or c in stock_pool:
                        if c not in codes: codes.append(c)
            except Exception: pass
            # 补提 1：normalized_messages
            for m in mids:
                nj = norm_stock.get(m)
                if nj:
                    try:
                        for c in _json.loads(nj):
                            c = str(c)
                            if (_re.fullmatch(r"(?:60|68|00|30)\d{4}", c) or c in stock_pool) and c not in codes:
                                codes.append(c)
                    except Exception: pass
            # 补提 2：正则（A股前缀白名单 + 命中股票池）
            if not codes:
                txt = (d["title_clean"] or "") + " " + (d["title_raw"] or "")
                for m in mids:
                    if m in msg_info: txt += " " + (msg_info[m]["raw_text"] or "")[:400]
                for c in set(_re.findall(r"(?<![0-9])(?:60|68|00|30)\d{4}(?![0-9])", txt)):
                    if c in stock_pool and c not in codes:
                        codes.append(c)
            # 补提 3：名称反查（股票池名称出现在标题/原文中，最长匹配优先）
            if not codes:
                txt = (d["title_clean"] or "") + " " + (d["company"] or "") + " " + (d["title_raw"] or "")
                for m in mids:
                    if m in msg_info: txt += " " + (msg_info[m]["raw_text"] or "")[:500]
                found = []
                for nm, code in sorted(name_index.items(), key=lambda x: -len(x[0])):
                    if len(nm) >= 2 and nm in txt:
                        found.append(code)
                for c in found:
                    if c not in codes: codes.append(c)
            stocks = [{"code": c, "name": stock_pool.get(c, "")} for c in codes]
            # 机构聚合
            insts = []
            if d.get("institution"): insts.append(d["institution"])
            for m in mids:
                ins = inst_map.get(m)
                if ins and ins not in insts: insts.append(ins)
            # 事件关联
            events = []
            seen_ev = set()
            for m in mids:
                for ev in ev_map.get(m, []):
                    if ev["event_id"] not in seen_ev:
                        seen_ev.add(ev["event_id"])
                        events.append({"event_id": ev["event_id"], "title": (ev["event_title"] or "")[:60],
                                       "momentum": ev["momentum_score"] or 0, "status": ev["status"] or ""})
            events.sort(key=lambda x: -(x["momentum"] or 0))
            q = d["quality_score"] or 0
            ql = "high" if q >= 80 else ("medium" if q >= 50 else "low")
            # 标题/摘要拆分
            t = (d["title_clean"] or "").strip() or (d["title_raw"] or "").strip()
            t = _clean_title_display(t)
            cut = 200000
            for sep in ["\n", "——", "：", "。", "！", "？"]:
                idx = t.find(sep)
                if 5 < idx < cut: cut = idx
            if cut < 200000:
                title = t[:cut].strip()[:70]; summary = t[cut + 1:].strip()
            else:
                title = t[:30]; summary = t[30:]
            summary = summary[:240]
            item = {
                "doc_id": d["doc_id"], "title": title, "quality_score": q, "quality_level": ql,
                "research_type": d["research_type"] or "", "content_nature": d["content_nature"] or "",
                "company": d["company"] or "", "institutions": insts, "stocks": stocks,
                "event_relations": events[:5], "source_count": d["source_count"] or len(mids),
                "institution_count": d["institution_count"] or len(insts),
                "first_seen_at": d["first_seen_at"], "last_seen_at": d["last_seen_at"],
                "summary": summary,
            }
            if did and did.isdigit():
                chain = []
                for m in sorted(mids, key=lambda x: msg_info.get(x, {}).get("date", "")):
                    mi = msg_info.get(m, {})
                    chain.append({
                        "message_id": m, "date": mi.get("date", ""), "from_user": mi.get("from_user", ""),
                        "source_topic": mi.get("source_topic", ""), "institution": inst_map.get(m, ""),
                        "raw_text": (mi.get("raw_text") or "")[:2500],
                    })
                item["source_chain"] = chain
            out.append(item)

        stats = dict(con.execute("""
            SELECT CASE WHEN quality_score>=80 THEN 'high' WHEN quality_score>=50 THEN 'medium' ELSE 'low' END b, COUNT(*) n
            FROM research_document GROUP BY 1""").fetchall())
        type_counts = dict(con.execute("""
            SELECT research_type, COUNT(*) n FROM research_document WHERE quality_score >= ?
            GROUP BY 1 ORDER BY n DESC""", (min_q,)).fetchall())
        con.close()
        if did and did.isdigit() and out:
            return self._json(out[0])
        return self._json({"documents": out, "total": len(out), "stats": stats, "type_counts": type_counts})

    def _industries(self, qs):
        """行业实体列表（v2.3.2 Industry Entity）：行业树 + Industry Momentum 热度。
        热度 = 研究对象数 + 机构数 + 事件数*2 + 最高RS*0.4 + 最高Momentum*0.2（clip 100）
        参数: id=实体ID（单行业详情）; q=名称/别名过滤"""
        import json as _json, re as _re
        con = db()
        eid = (qs.get("id") or [""])[0]
        q = (qs.get("q") or [""])[0].strip()

        # ── 一次性载入关联数据 ──
        # 行业 → docs（industry_entity_relation 反向索引）
        ent_docs = {}
        for r in con.execute("SELECT document_id, entity_id FROM industry_entity_relation"):
            ent_docs.setdefault(r["entity_id"], []).append(r["document_id"])
        # doc 详情（质量分/机构/消息ids/股票）
        docs = {}
        for r in con.execute("SELECT doc_id, title_clean, institution, message_ids_json, stock_codes_json, quality_score FROM research_document"):
            docs[r["doc_id"]] = dict(r)
        # message → 机构
        msg_inst = {}
        for r in con.execute("SELECT message_id, institution FROM message_classification WHERE institution IS NOT NULL AND institution != ''"):
            msg_inst.setdefault(r["message_id"], r["institution"])
        # message → 事件
        msg_ev = {}
        for r in con.execute("""
            SELECT em.message_id, em.event_id, ec.event_title, ec.momentum_score, ec.status
            FROM event_messages em JOIN event_clusters ec ON ec.event_id = em.event_id
            WHERE ec.status != 'closed'"""):
            msg_ev.setdefault(r["message_id"], []).append(dict(r))
        # 股票最新 RS
        stock_rs = {}
        for r in con.execute("SELECT stock_code, research_score FROM research_scores ORDER BY id DESC"):
            stock_rs.setdefault(r["stock_code"], r["research_score"])

        # ── 行业实体 ──
        entities = [dict(r) for r in con.execute(
            "SELECT entity_id, name, parent_id, level, category, aliases, status FROM industry_entity WHERE status='active' ORDER BY level, entity_id")]
        ent_by_id = {e["entity_id"]: e for e in entities}
        ent_name_like = {}
        if q:
            for e in entities:
                if q in e["name"] or any(q in (a or "") for a in json.loads(e["aliases"] or "[]")):
                    ent_name_like[e["entity_id"]] = e

        def _agg(e):
            """聚合单个行业的 Industry Momentum"""
            eids = [e["entity_id"]]
            # 含子级（一级行业聚合二级）
            for ch in entities:
                if ch["parent_id"] == e["entity_id"]:
                    eids.append(ch["entity_id"])
            doc_ids = set()
            for _eid in eids:
                for _d in ent_docs.get(_eid, []):
                    doc_ids.add(_d)
            doc_list = [docs.get(_d) for _d in doc_ids if _d in docs]
            insts = set()
            evs = {}
            for d in doc_list:
                if d.get("institution"): insts.add(d["institution"])
                try:
                    for m in _json.loads(d.get("message_ids_json") or "[]"):
                        ins = msg_inst.get(m)
                        if ins: insts.add(ins)
                        for ev in msg_ev.get(m, []):
                            evs.setdefault(ev["event_id"], ev)
                except Exception: pass
            max_mom = max([ev.get("momentum_score") or 0 for ev in evs.values()] or [0])
            max_rs = 0
            stocks = {}
            for d in doc_list:
                try:
                    for c in _json.loads(d.get("stock_codes_json") or "[]"):
                        c = str(c)
                        if _re.match(r"588\d{3}", c): continue  # ETF 排除
                        rs = stock_rs.get(c, 0)
                        if rs > max_rs: max_rs = rs
                        stocks.setdefault(c, rs)
                except Exception: pass
            # 名称反查补充股票（标题含股票名）
            heat = min(100, round(len(doc_list) + len(insts) + len(evs) * 2 + max_rs * 0.4 + max_mom * 0.2))
            return {
                "doc_count": len(doc_list), "inst_count": len(insts),
                "event_count": len(evs), "max_momentum": max_mom, "max_rs": max_rs,
                "heat": heat, "stock_count": len(stocks),
                "top_stocks": sorted([{"code": c, "rs": rs} for c, rs in stocks.items()], key=lambda x: -x["rs"])[:5],
            }

        if eid and eid.isdigit():
            e = ent_by_id.get(int(eid))
            if not e:
                con.close(); return self._json({"error": "industry not found"}, 404)
            agg = _agg(e)
            # 详情：关联事件 + 研究对象 + 股票
            eids = [e["entity_id"]] + [ch["entity_id"] for ch in entities if ch["parent_id"] == e["entity_id"]]
            doc_ids = set()
            for _eid in eids:
                for _d in ent_docs.get(_eid, []):
                    doc_ids.add(_d)
            doc_list = [docs.get(_d) for _d in doc_ids if _d in docs]
            evs = {}
            for d in doc_list:
                try:
                    for m in _json.loads(d.get("message_ids_json") or "[]"):
                        for ev in msg_ev.get(m, []):
                            evs.setdefault(ev["event_id"], ev)
                except Exception: pass
            # v2.3.4 行业趋势（e 是 Row，children 是 dict，统一 str id）
            ev_ids_t = set()
            all_inds = [{"entity_id": e["entity_id"]}] + [dict(r) for r in con.execute("SELECT entity_id, name FROM industry_entity WHERE parent_id=?", (e["entity_id"],))]
            for ch in all_inds:
                for e2 in _neighbors("industry", str(ch["entity_id"])):
                    if e2["tt"] == "event":
                        ev_ids_t.add(e2["tid"])
            trend = {}
            for ev in ev_ids_t:
                for d, s in ev_mom_hist.get(ev, {}).items():
                    trend[d] = trend.get(d, 0) + s
            trend_list = [{"date": d, "value": v} for d, v in sorted(trend.items())][-8:]
            # 研究对象列表（质量≥50 优先）
            docs_out = []
            for d in doc_list:
                if (d.get("quality_score") or 0) < 30: continue
                docs_out.append({
                    "doc_id": d["doc_id"], "title": (d.get("title_clean") or "")[:70],
                    "quality_score": d.get("quality_score") or 0, "institution": d.get("institution") or "",
                })
            docs_out.sort(key=lambda x: -x["quality_score"])
            children = [{"entity_id": ch["entity_id"], "name": ch["name"],
                         **_agg(ch)} for ch in entities if ch["parent_id"] == e["entity_id"]]
            children.sort(key=lambda x: -x["heat"])
            con.close()
            return self._json({
                "entity": {"entity_id": e["entity_id"], "name": e["name"], "level": e["level"],
                           "parent_id": e["parent_id"], "category": e["category"],
                           "aliases": json.loads(e["aliases"] or "[]")},
                "stats": agg, "events": sorted(evs.values(), key=lambda x: -(x["momentum_score"] or 0))[:15],
                "documents": docs_out[:30], "children": children,
                "trend": trend_list, "trend_dir": _trend_dir(trend_list),
            })

        # 列表模式
        out = []
        for e in entities:
            if q and e["entity_id"] not in ent_name_like:
                continue
            agg = _agg(e)
            out.append({
                "entity_id": e["entity_id"], "name": e["name"], "level": e["level"],
                "parent_id": e["parent_id"], "category": e["category"], **agg,
            })
        out.sort(key=lambda x: (-x["heat"], -x["doc_count"]))
        con.close()
        return self._json({"industries": out, "total": len(out)})

    def _graph(self, qs):
        """研究图谱（v2.3.3 Research Graph）：
        map      研究地图（行业树拓扑 + 实体计数 + Graph Score）
        entity   ?type=document|industry|event|stock&id=  统一实体详情（五维联动）
        stock    ?code=XXX  股票图谱（快捷入口）"""
        import json as _json, re as _re
        con = db()
        mode = (qs.get("mode") or [""])[0]

        # ── v2.3.4 辅助：事件 momentum 历史（GS 趋势用）──
        ev_mom_hist = {}   # str(event_id) -> {date: momentum_sum}
        for r in con.execute("SELECT event_id, bucket_hour, momentum_score FROM event_momentum"):
            d = (r["bucket_hour"] or "")[:10]
            if d:
                k = str(r["event_id"])
                ev_mom_hist.setdefault(k, {})
                ev_mom_hist[k][d] = ev_mom_hist[k].get(d, 0) + (r["momentum_score"] or 0)
        def _sk(c):
            """股票代码统一 int 化"""
            c = str(c)
            return str(int(c)) if c.isdigit() else c

        # 文档 source_count 映射（传播速度/可信度用）
        docs_map = {}
        for r in con.execute("SELECT doc_id, source_count FROM research_document"):
            docs_map[str(r["doc_id"])] = dict(r)
        etype = (qs.get("type") or [""])[0]
        eid = (qs.get("id") or [""])[0]
        code = (qs.get("code") or [""])[0].strip()

        # ── 边表索引（双向：source 方向带 tt/tid，target 方向带 st/sid 且补 tt/tid 统一键）──
        edges = {}
        for r in con.execute("SELECT source_type, source_id, relation_type, target_type, target_id, confidence FROM research_graph_relation"):
            src = (r["source_type"], str(r["source_id"]))
            tgt = (r["target_type"], str(r["target_id"]))
            edges.setdefault(src, []).append({"rt": r["relation_type"], "tt": r["target_type"], "tid": str(r["target_id"]), "conf": r["confidence"]})
            edges.setdefault(tgt, []).append({"rt": r["relation_type"], "st": r["source_type"], "sid": str(r["source_id"]),
                                              "tt": r["source_type"], "tid": str(r["source_id"]), "conf": r["confidence"]})

        def _neighbors(typ, tid):
            return edges.get((typ, str(tid)), [])

        # 行业名称/机构名/事件名/文档名/股票名 解析
        ind_name = {str(r["entity_id"]): r["name"] for r in con.execute("SELECT entity_id, name FROM industry_entity")}
        inst_name = {str(r["inst_id"]): r["name"] for r in con.execute("SELECT inst_id, name FROM graph_institution")}
        ev_title = {str(r["event_id"]): (r["event_title"] or "")[:60] for r in con.execute("SELECT event_id, event_title, momentum_score, status FROM event_clusters")}
        ev_meta = {str(r["event_id"]): {"momentum": r["momentum_score"] or 0, "status": r["status"] or ""} for r in con.execute("SELECT event_id, momentum_score, status FROM event_clusters")}
        doc_title = {str(r["doc_id"]): (r["title_clean"] or "")[:60] for r in con.execute("SELECT doc_id, title_clean, quality_score FROM research_document")}
        doc_q = {str(r["doc_id"]): r["quality_score"] or 0 for r in con.execute("SELECT doc_id, quality_score FROM research_document")}
        stock_name = {}
        for r in con.execute("SELECT DISTINCT stock_code, stock_name FROM event_stock_relation WHERE stock_name != ''"):
            stock_name.setdefault(str(r["stock_code"]), r["stock_name"])
        for r in con.execute("SELECT DISTINCT stock_code, stock_name FROM research_scores WHERE stock_name != ''"):
            stock_name.setdefault(str(r["stock_code"]), r["stock_name"])
        stock_rs = {}
        for r in con.execute("SELECT stock_code, research_score FROM research_scores ORDER BY id DESC"):
            stock_rs.setdefault(r["stock_code"], r["research_score"])
        # 代码 int 化别名（图谱边用 '338'，原始表用 '000338'）
        stock_name = {_sk(k): v for k, v in stock_name.items()}
        stock_rs = {_sk(k): v for k, v in stock_rs.items()}

        # ── Graph Score：研究影响力 = 机构数 + 来源数 + 事件关联 + 行业热度 + 股票覆盖（0-100 辅助指标）──
        def _graph_score(typ, tid):
            nb = _neighbors(typ, tid)
            insts = len({e["tid"] for e in nb if e["tt"] == "institution"})
            events = len({e["tid"] for e in nb if e["tt"] == "event"})
            stocks = len({e["tid"] for e in nb if e["tt"] == "stock"})
            inds = len({e["tid"] for e in nb if e["tt"] == "industry"})
            docs = len({e["tid"] for e in nb if e["tt"] == "document"})
            # 权重：机构4 + 来源/文档3 + 事件2 + 股票2 + 行业1（clip 100）
            score = min(100, round(insts * 4 + docs * 3 + events * 2 + stocks * 2 + inds * 1))
            return {"graph_score": score, "inst_count": insts, "doc_count": docs,
                    "event_count": events, "stock_count": stocks, "industry_count": inds}

        def _trend_dir(trend):
            """趋势方向：最近3天 vs 前3天"""
            vals = [t["value"] for t in trend]
            if len(vals) < 4:
                return "→"
            recent = sum(vals[-3:]) / 3
            prior = sum(vals[-6:-3]) / 3 if len(vals) >= 6 else vals[0]
            if recent > prior * 1.15:
                return "↑"
            if recent < prior * 0.85:
                return "↓"
            return "→"

        def _stock_centrality(code, nb):
            """v2.3.4 股票研究中心度（辅助指标，不进 RS）：
            事件30% + 机构25% + 研究对象20% + 行业核心15% + 传播10%"""
            events = len({e["tid"] for e in nb if e["tt"] == "event"})
            insts = len({e["tid"] for e in nb if e["tt"] == "institution"})
            docs = len({e["tid"] for e in nb if e["tt"] == "document"})
            inds = len({e["tid"] for e in nb if e["tt"] == "industry"})
            # 传播速度：该股票关联文档的 source_count 均值
            spread = 0
            for e in nb:
                if e["tt"] == "document":
                    d = docs_map.get(e["tid"])
                    if d: spread = max(spread, d.get("source_count") or 1)
            e_s = min(events, 10) / 10 * 30
            i_s = min(insts, 10) / 10 * 25
            d_s = min(docs, 10) / 10 * 20
            ind_s = min(inds, 8) / 8 * 15
            sp_s = min(spread, 4) / 4 * 10
            total = round(e_s + i_s + d_s + ind_s + sp_s)
            reasons = []
            if events: reasons.append(f"+{round(e_s)} {events}个事件关联")
            if insts: reasons.append(f"+{round(i_s)} {insts}家机构关注")
            if docs: reasons.append(f"+{round(d_s)} {docs}篇研究对象")
            if inds: reasons.append(f"+{round(ind_s)} {inds}个行业关联")
            if spread > 1: reasons.append(f"+{round(sp_s)} 传播{spread}次")
            return {"centrality": min(100, total), "reasons": reasons[:5],
                    "factors": {"event": round(e_s), "inst": round(i_s), "doc": round(d_s), "ind": round(ind_s), "spread": round(sp_s)}}

        # ── 模式 1：研究地图 ──
        if mode == "map" or (mode != "analytics" and not etype and not code):
            tops = [dict(r) for r in con.execute("SELECT entity_id, name, category FROM industry_entity WHERE level=1 AND status='active' ORDER BY entity_id")]
            out = []
            for t in tops:
                children = [dict(r) for r in con.execute(
                    "SELECT entity_id, name FROM industry_entity WHERE parent_id=? AND status='active' ORDER BY entity_id", (t["entity_id"],))]
                item = {"entity_id": t["entity_id"], "name": t["name"], "category": t["category"], "children": []}
                for ch in children:
                    gs = _graph_score("industry", ch["entity_id"])
                    item["children"].append({"entity_id": ch["entity_id"], "name": ch["name"], **gs})
                item["children"].sort(key=lambda x: -x["graph_score"])
                item["_agg"] = {k: sum(c[k] for c in item["children"]) for k in ("graph_score", "doc_count", "event_count", "stock_count", "inst_count")}
                # v2.3.4 贡献拆分：子行业 GS 占比（去重，避免「AI产业链100 + 子行业100」重复观感）
                tot = sum(max(c["doc_count"] * 2 + c["event_count"], 1) for c in item["children"]) or 1
                contribs = [{"name": c["name"], "gs": c["graph_score"],
                             "weight": c["doc_count"] * 2 + c["event_count"],
                             "pct": round((c["doc_count"] * 2 + c["event_count"]) * 100 / tot)}
                            for c in item["children"] if c["doc_count"] > 0 or c["event_count"] > 0]
                contribs.sort(key=lambda x: -x["pct"])
                item["contributions"] = contribs[:6]
                # v2.3.4 GS 趋势：行业关联事件 momentum 历史按天求和
                ev_ids = set()
                for ch in item["children"]:
                    for e in edges.get(("industry", str(ch["entity_id"])), []):
                        if e["tt"] == "event":
                            ev_ids.add(e["tid"])
                trend = {}
                for ev in ev_ids:
                    for d, s in ev_mom_hist.get(ev, {}).items():
                        trend[d] = trend.get(d, 0) + s
                item["trend"] = [{"date": d, "value": v} for d, v in sorted(trend.items())][-8:]
                item["trend_dir"] = _trend_dir(item["trend"])
                out.append(item)
            con.close()
            return self._json({"mode": "map", "industries": out})

        # ── 模式 1.5：图谱统计总览（v2.3.4 analytics）──
        if mode == "analytics":
            # 热门主题（一级行业，GS + 趋势）
            hot_topics = []
            for t in [dict(r) for r in con.execute("SELECT entity_id, name FROM industry_entity WHERE level=1 AND status='active' ORDER BY entity_id")]:
                children = [dict(r) for r in con.execute("SELECT entity_id, name FROM industry_entity WHERE parent_id=? AND status='active'", (t["entity_id"],))]
                total = 0
                ev_ids = set()
                for ch in children:
                    nb = _neighbors("industry", ch["entity_id"])
                    total += _graph_score("industry", ch["entity_id"])["graph_score"]
                    for e in nb:
                        if e["tt"] == "event":
                            ev_ids.add(e["tid"])
                trend = {}
                for ev in ev_ids:
                    for d, s in ev_mom_hist.get(ev, {}).items():
                        trend[d] = trend.get(d, 0) + s
                trend_list = [{"date": d, "value": v} for d, v in sorted(trend.items())][-8:]
                if total > 0:
                    hot_topics.append({"entity_id": t["entity_id"], "name": t["name"], "gs": total,
                                       "trend_dir": _trend_dir(trend_list), "trend": trend_list})
            hot_topics.sort(key=lambda x: -x["gs"])
            # 核心股票（研究中心度 TOP）
            core_stocks = []
            stock_codes = set()
            for r in con.execute("SELECT DISTINCT target_id FROM research_graph_relation WHERE target_type='stock'"):
                stock_codes.add(str(r["target_id"]))
            for r in con.execute("SELECT DISTINCT source_id FROM research_graph_relation WHERE source_type='stock'"):
                stock_codes.add(str(r["source_id"]))
            for c in list(stock_codes)[:200]:
                nb = _neighbors("stock", c)
                cent = _stock_centrality(c, nb)
                if cent["centrality"] >= 40:
                    core_stocks.append({"code": c, "name": stock_name.get(c, ""), "rs": stock_rs.get(c),
                                        **cent})
            core_stocks.sort(key=lambda x: -x["centrality"])
            # 核心机构（研究影响力 + 优势方向）
            core_insts = []
            for r in con.execute("SELECT inst_id, name FROM graph_institution"):
                iid = str(r["inst_id"])
                nb = _neighbors("institution", iid)
                gs = _graph_score("institution", iid)
                if gs["graph_score"] <= 0:
                    continue
                # 优势方向：机构经 confirmed_by 关联的事件 → 事件的行业
                ind_score = {}
                ev_ids = {e["tid"] for e in nb if e["tt"] == "event"}
                for ev in ev_ids:
                    for e in _neighbors("event", ev):
                        if e["tt"] == "industry":
                            ind_score[e["tid"]] = ind_score.get(e["tid"], 0) + 1
                tot = sum(ind_score.values()) or 1
                radar = [{"industry_id": iid2, "name": ind_name.get(iid2, ""),
                          "pct": round(n * 100 / tot)} for iid2, n in
                         sorted(ind_score.items(), key=lambda x: -x[1])[:4]]
                core_insts.append({"inst_id": r["inst_id"], "name": r["name"], **gs, "radar": radar})
            core_insts.sort(key=lambda x: -x["graph_score"])
            con.close()
            return self._json({"mode": "analytics", "hot_topics": hot_topics[:10],
                               "core_stocks": core_stocks[:12], "core_institutions": core_insts[:10]})

        # ── 模式 2：统一实体详情 ──
        if etype and eid:
            tid = str(eid)
            nb = _neighbors(etype, tid)
            info = {"name": "", "sub": ""}
            if etype == "industry":
                info["name"] = ind_name.get(tid, f"行业#{tid}")
                # 子行业
                children = [dict(r) for r in con.execute("SELECT entity_id, name FROM industry_entity WHERE parent_id=?", (tid,))]
                info["children"] = [{"entity_id": c["entity_id"], "name": c["name"]} for c in children]
                # v2.3.4 行业趋势（自身+子行业的事件 momentum 历史）
                ev_ids_t = set()
                for ch in [{"entity_id": tid}] + children:
                    for e2 in _neighbors("industry", str(ch["entity_id"])):
                        if e2["tt"] == "event":
                            ev_ids_t.add(e2["tid"])
                _trend_map = {}
                for _ev in ev_ids_t:
                    for _d, _s in ev_mom_hist.get(_ev, {}).items():
                        _trend_map[_d] = _trend_map.get(_d, 0) + _s
                _trend_list = [{"date": _d, "value": _v} for _d, _v in sorted(_trend_map.items())][-8:]
                info["trend"] = _trend_list
                info["trend_dir"] = _trend_dir(_trend_list)
            elif etype == "event":
                info["name"] = ev_title.get(tid, f"事件#{tid}")
                info["sub"] = ev_meta.get(tid, {})
            elif etype == "stock":
                def _sk2(c):
                    c = str(c)
                    return str(int(c)) if c.isdigit() else c
                info["name"] = stock_name.get(_sk2(tid), f"股票#{tid}")
                info["sub"] = {"rs": stock_rs.get(_sk2(tid))}
                info["centrality"] = _stock_centrality(_sk2(tid), nb)
            elif etype == "document":
                info["name"] = doc_title.get(tid, f"研究对象#{tid}")
                q = doc_q.get(tid, 0)
                info["sub"] = {"quality_score": q}
                # v2.3.4 Research Confidence：质量50% + 机构×15 + 传播×10 + 事件×10 + 股票×5
                insts_d = len({e["tid"] for e in nb if e["tt"] == "institution"})
                evs_d = len({e["tid"] for e in nb if e["tt"] == "event"})
                stocks_d = len({e["tid"] for e in nb if e["tt"] == "stock"})
                spread = (docs_map.get(tid, {}).get("source_count") or 1)
                conf = round(min(100, q * 0.5 + insts_d * 15 + spread * 8 + evs_d * 5 + stocks_d * 3))
                info["confidence"] = {"score": conf,
                                      "quality": round(q * 0.5), "institution": insts_d * 15,
                                      "spread": spread * 8, "event": evs_d * 5, "stock": stocks_d * 3}
            elif etype == "institution":
                info["name"] = inst_name.get(tid, f"机构#{tid}")
                # v2.3.4 机构研究雷达：经事件 → 行业分布
                ev_ids_i = {e["tid"] for e in nb if e["tt"] == "event"}
                ind_score = {}
                for ev in ev_ids_i:
                    for e2 in _neighbors("event", ev):
                        if e2["tt"] == "industry":
                            ind_score[e2["tid"]] = ind_score.get(e2["tid"], 0) + 1
                tot = sum(ind_score.values()) or 1
                info["radar"] = [{"industry_id": iid2, "name": ind_name.get(iid2, ""),
                                  "pct": round(n * 100 / tot)} for iid2, n in
                                 sorted(ind_score.items(), key=lambda x: -x[1])[:6]]
            gs = _graph_score(etype, tid)
            # 五维邻居
            stocks = []
            events = []
            inds = []
            insts = []
            docs = []
            for e in nb:
                if e["tt"] == "stock":
                    c = str(e["tid"])
                    stocks.append({"code": c, "name": stock_name.get(c, ""), "rs": stock_rs.get(c), "conf": e["conf"]})
                elif e["tt"] == "event":
                    events.append({"event_id": e["tid"], "title": ev_title.get(e["tid"], ""), **ev_meta.get(e["tid"], {})})
                elif e["tt"] == "industry":
                    inds.append({"industry_id": e["tid"], "name": ind_name.get(e["tid"], ""), "conf": e["conf"]})
                elif e["tt"] == "institution":
                    insts.append({"inst_id": e["tid"], "name": inst_name.get(e["tid"], "")})
                elif e["tt"] == "document":
                    docs.append({"doc_id": e["tid"], "title": doc_title.get(e["tid"], ""), "quality_score": doc_q.get(e["tid"], 0)})
            # 去重排序
            seen = set()
            stocks = [s for s in sorted(stocks, key=lambda x: -(x["rs"] or 0)) if not (s["code"] in seen or seen.add(s["code"]))][:15]
            seen = set()
            events = [e for e in sorted(events, key=lambda x: -(x.get("momentum") or 0)) if not (e["event_id"] in seen or seen.add(e["event_id"]))][:15]
            seen = set()
            inds = [i for i in inds if not (i["industry_id"] in seen or seen.add(i["industry_id"]))][:12]
            seen = set()
            insts = [i for i in insts if not (i["inst_id"] in seen or seen.add(i["inst_id"]))][:12]
            seen = set()
            docs = [d for d in sorted(docs, key=lambda x: -x["quality_score"]) if not (d["doc_id"] in seen or seen.add(d["doc_id"]))][:20]
            con.close()
            return self._json({"mode": "entity", "type": etype, "id": tid, **info, **gs,
                               "stocks": stocks, "events": events, "industries": inds,
                               "institutions": insts, "documents": docs})

        # ── 模式 3：股票图谱快捷入口 ──
        if code:
            def _sk(c):
                c = str(c)
                return str(int(c)) if c.isdigit() else c
            tid = _sk(code)
            nb = _neighbors("stock", tid)
            gs = _graph_score("stock", tid)
            cent = _stock_centrality(tid, nb)
            events = [{"event_id": e["tid"], "title": ev_title.get(e["tid"], ""), **ev_meta.get(e["tid"], {})}
                      for e in nb if e["tt"] == "event"]
            events = sorted(events, key=lambda x: -(x.get("momentum") or 0))[:12]
            inds = [{"industry_id": e["tid"], "name": ind_name.get(e["tid"], "")} for e in nb if e["tt"] == "industry"]
            insts = [{"inst_id": e["tid"], "name": inst_name.get(e["tid"], "")} for e in nb if e["tt"] == "institution"]
            docs = [{"doc_id": e["tid"], "title": doc_title.get(e["tid"], ""), "quality_score": doc_q.get(e["tid"], 0)}
                    for e in nb if e["tt"] == "document"]
            docs = sorted(docs, key=lambda x: -x["quality_score"])[:10]
            con.close()
            return self._json({"mode": "stock", "code": code, "name": stock_name.get(code, ""),
                               "rs": stock_rs.get(code), **gs, **cent, "events": events,
                               "industries": inds, "institutions": insts, "documents": docs})

        con.close()
        return self._json({"error": "unknown graph query"}, 400)

    def _stock_research(self, qs):
        kw = (qs.get("code") or [""])[0].strip()
        if not kw:
            self._json({"error": "missing code"}, 400)
            return
        con = db()
        resolved = self._resolve_stock_keyword(kw, con)
        if resolved is None:
            con.close()
            self._json({"error": "missing code"}, 400)
            return
        code = resolved.get("code")
        ent_id = resolved.get("entity_id") or code
        ent_name = resolved.get("name")
        # 实体匹配条件：entity_id=代码 或 entity_name=名称
        ent_clause = []
        ent_args = []
        if ent_id:
            ent_clause.append("(e.entity_id=? OR e.entity_id=? OR e.entity_id=?)")
            ent_args += [ent_id, str(int(ent_id)) if ent_id.isdigit() else ent_id, f"{ent_id}.SZ" if ent_id.isdigit() else ent_id]
        if ent_name:
            ent_clause.append("(e.entity_name=? OR e.entity_name=?)")
            ent_args += [ent_name, ent_name]
        # OR 连接：entity_id 匹配 或 entity_name 匹配 任一命中即可（2026-08-12 修复）
        ent_where = " OR ".join(ent_clause) if ent_clause else "1=0"

        # 相关研报（实体表关联，去重 report_series）
        reps = [dict(r) for r in con.execute(
            f"""SELECT DISTINCT s.series_id, s.title, s.institution, s.current_version, s.status,
                   s.occurrence_count, s.last_seen_at
               FROM report_entities e JOIN report_series s ON s.series_id=e.report_id
               WHERE {ent_where}
               ORDER BY s.last_seen_at DESC LIMIT 50""", ent_args).fetchall()]

        # 提及消息：优先 is_primary=1 主记录；折叠同一原始消息的重复/转发（occurrence_count）。
        # 2026-08-12 修复：此前 JOIN 展开导致同一条原始消息出现多次，且缺 mid 字段无法打开抽屉。
        rows = []
        seen = set()
        if ent_id:
            occ = con.execute(
                f"""SELECT o.message_id, r.chat_id, r.message_id AS raw_mid, r.date, r.source_topic,
                          substr(r.raw_text,1,200) content, c.primary_category, c.confidence,
                          o.is_primary, o.is_duplicate, o.duplicate_type,
                          (SELECT COUNT(*) FROM report_occurrences o2 WHERE o2.message_id = o.message_id) AS dup_cnt
                   FROM report_occurrences o
                   JOIN raw_messages r ON r.chat_id||':'||r.message_id = o.message_id
                   LEFT JOIN message_classification c ON c.message_id = o.message_id
                   WHERE o.report_id IN (
                       SELECT DISTINCT e.report_id FROM report_entities e WHERE {ent_where}
                   )
                   ORDER BY o.is_primary DESC, r.date DESC LIMIT 100""", ent_args).fetchall()
            for r in occ:
                d = dict(r)
                mid = d["raw_mid"]
                d["mid"] = f'{d["chat_id"]}:{mid}'
                if d["mid"] in seen:
                    continue
                rows.append(d)
                seen.add(d["mid"])
        # 兜底：归一化消息实体匹配（stock_codes_json 含代码）
        if ent_id:
            import json as _json
            norm = con.execute(
                """SELECT message_id, normalized_text, stock_codes_json, source, normalized_at
                   FROM normalized_messages ORDER BY normalized_at DESC LIMIT 3000""").fetchall()
            for n in norm:
                try:
                    codes = _json.loads(n["stock_codes_json"] or "[]")
                except Exception:
                    codes = []
                hit = any(str(c).zfill(6) == ent_id for c in codes)
                if not hit and ent_name:
                    try:
                        names = _json.loads(con.execute(
                            "SELECT stock_names_json FROM normalized_messages WHERE message_id=?",
                            (n["message_id"],)).fetchone()["stock_names_json"] or "[]")
                        hit = ent_name in names
                    except Exception:
                        hit = False
                if hit and n["message_id"] not in seen:
                    chat_id, mid = n["message_id"].split(":", 1) if ":" in n["message_id"] else ("", n["message_id"])
                    rows.append({
                        "mid": n["message_id"], "chat_id": chat_id, "raw_mid": int(mid) if mid.isdigit() else mid,
                        "date": n["normalized_at"], "source_topic": n["source"],
                        "content": (n["normalized_text"] or "")[:200],
                        "primary_category": None, "confidence": None, "dup_cnt": 1,
                    })
                    seen.add(n["message_id"])
        # 2026-08-12 修复2：标题相似度折叠（三天内相同标题合并为一条主记录 + occurrence_count）
        # 去重优先级：chat_id+message_id -> normalized_hash -> report_id+version_no -> 三天内标题相似度
        import re as _re
        def _title_key(content: str) -> str:
            t = _re.sub(r'[\s（(\[【].*', '', str(content or ""))[:40]
            return _re.sub(r'[\W_]+', '', t)[:24]
        rows.sort(key=lambda x: (x.get("date") or "", x.get("mid") or ""), reverse=True)
        folded = []
        title_seen = {}
        for row in rows:
            key = _title_key(row.get("content"))
            if not key:
                folded.append(row)
                continue
            if key in title_seen:
                # 同一标题：折叠，计数+1（保留日期最早的一条作为主记录）
                title_seen[key]["dup_cnt"] = int(title_seen[key].get("dup_cnt") or 1) + 1
                title_seen[key]["dup_folded"] = True
                continue
            row["dup_cnt"] = int(row.get("dup_cnt") or 1)
            title_seen[key] = row
            folded.append(row)
        rows = folded
        con.close()
        self._json({
            "code": code or ent_name or kw,
            "name": ent_name,
            "resolved": resolved,
            "messages": rows,
            "message_count": len(rows),
            "reports": reps,
            "report_count": len(reps),
        })

    def _topic_research(self, qs):
        """行业/主题追踪：匹配 行业标签(entities/industries) + 原文"""
        topic = (qs.get("topic") or [""])[0]
        if not topic:
            self._json({"error": "missing topic"}, 400)
            return
        con = db()
        like = f"%{topic}%"
        rows = [dict(r) for r in con.execute("""
            SELECT r.date, substr(r.raw_text,1,200) content, r.source_topic, c.primary_category, c.secondary_category
            FROM message_classification c
            JOIN raw_messages r ON r.chat_id||':'||r.message_id=c.message_id
            LEFT JOIN normalized_messages n ON n.message_id = c.message_id
            WHERE c.entities_json LIKE ?
               OR r.raw_text LIKE ?
               OR n.industries_json LIKE ?
            ORDER BY r.date DESC LIMIT 50""", (like, like, like)).fetchall()]
        con.close()
        self._json({"topic": topic, "messages": rows, "count": len(rows)})

    def _timeline(self, qs):
        """最近消息时间线（摘要列表：display_title/summary/duplicate_count）
        全文进详情抽屉（detail 时再取完整 raw_text）"""
        limit = min(int((qs.get("limit") or ["80"])[0]), 200)
        con = db()
        rows = [dict(r) for r in con.execute(
            """SELECT r.chat_id||':'||r.message_id AS mid, r.date, r.raw_text, r.source_topic, r.msg_type, r.from_user,
                      r.relative_image_path, c.primary_category, c.secondary_category, c.confidence,
                      c.review_required, c.entities_json, c.vision_status, c.continuation,
                      c.content_type, c.content_subtype, c.institution, c.research_team,
                      c.research_value, c.confidence_score, c.themes_json, c.message_role, c.original_source,
                      n.title AS norm_title, n.normalized_hash,
                      (SELECT count(*) FROM report_messages rm WHERE rm.message_id = r.chat_id||':'||r.message_id) AS dup_cnt
               FROM raw_messages r
               LEFT JOIN message_classification c ON r.chat_id||':'||r.message_id = c.message_id
               LEFT JOIN normalized_messages n ON n.message_id = r.chat_id||':'||r.message_id
               ORDER BY r.date DESC LIMIT ?""", (limit,)).fetchall()]
        # 近重复聚类：同 normalized_hash 且 3 天内 → similar_count（2026-08-12）
        from collections import defaultdict as _dd
        hash_groups = _dd(list)
        for it in rows:
            h = it.get("normalized_hash")
            if h:
                hash_groups[h].append(it)
        for it in rows:
            h = it.get("normalized_hash")
            it["similar_count"] = max(0, len(hash_groups.get(h, [])) - 1) if h else 0
        # 生成展示字段：display_title / summary / source_name + sort_ts
        import re as _re
        import calendar as _cal
        import time as _t
        def _to_ts(s):
            try:
                return int(_t.mktime(_t.strptime(s, "%Y-%m-%d %H:%M:%S")))
            except Exception:
                return 0
        for it in rows:
            text = (it.get("raw_text") or "").strip()
            it["sort_ts"] = _to_ts(it.get("date") or "")
            # display_title：clean_title 统一清洗（去时间/媒体前缀，提取第一句/冒号前）
            t = clean_title(text)
            if not t or t == "未提取标题":
                t = (it.get("norm_title") or "").strip()
            it["display_title"] = t or (it.get("secondary_category") or it.get("primary_category") or "资讯")
            # summary：2-3 行摘要（前 100 字）
            it["summary"] = clean_text_prefix(text)[:100] if text else ""
            # source_name：优先文本【机构】，其次 entities 机构/发送者/来源主题
            inst = ""
            m_inst = _re.search(r'[【\[]([^】\]]+)[】\]]', (text.split("\n")[0] if text else ""))
            if m_inst:
                inst = m_inst.group(1).strip()
            if not inst:
                try:
                    ent = json.loads(it.get("entities_json") or "{}")
                    inst = ent.get("institution", "") if isinstance(ent, dict) else ""
                except Exception:
                    pass
            it["source_name"] = normalize_institution(inst) or it.get("from_user") or it.get("source_topic") or ""
            it.pop("raw_text", None)  # 全文不随列表返回（详情抽屉再取）
        con.close()
        self._json({"timeline": rows, "count": len(rows)})

    def _message_detail(self, qs):
        """单条消息完整详情（详情抽屉）"""
        mid = (qs.get("mid") or [""])[0]
        if not mid:
            self._json({"error": "missing mid"}, 400)
            return
        con = db()
        row = con.execute("""
            SELECT r.chat_id, r.message_id, r.date, r.raw_text, r.source_topic, r.msg_type,
                   r.relative_image_path, r.from_user, r.reply_to_message_id,
                   c.primary_category, c.secondary_category, c.confidence, c.sentiment,
                   c.review_required, c.review_reason, c.vision_status, c.vision_summary, c.detected_category,
                   c.content_type, c.content_subtype, c.institution, c.research_team,
                   c.research_value, c.confidence_score, c.themes_json, c.message_role, c.original_source,
                   n.title, n.institution
            FROM raw_messages r
            LEFT JOIN message_classification c ON r.chat_id||':'||r.message_id = c.message_id
            LEFT JOIN normalized_messages n ON n.message_id = r.chat_id||':'||r.message_id
            WHERE r.chat_id||':'||r.message_id = ?""", (mid,)).fetchone()
        if not row:
            self._json({"error": "not found"}, 404)
            return
        d = dict(row)
        # 标题清洗 + 摘要 + 实体（详情抽屉四层结构）
        raw = d.get("raw_text") or ""
        cleaned = clean_title(raw) if raw else ""
        d["title"] = cleaned or d.get("title") or "未提取标题"
        d["summary"] = clean_text_prefix(raw)[:120] if raw else ""
        d["source_name"] = normalize_institution(d.get("institution") or "") or d.get("from_user") or d.get("source_topic") or ""
        try:
            ent = json.loads(d.get("entities_json") or "{}")
            d["stocks"] = ent.get("stocks") or []
            d["industries"] = ent.get("industries") or []
        except Exception:
            d["stocks"], d["industries"] = [], []
        # 验证状态（关联报告的 verification）
        rep = con.execute("""SELECT s.series_id, s.title, s.institution, s.current_version
                             FROM report_messages rm JOIN report_series s ON s.series_id=rm.report_id
                             WHERE rm.message_id=? LIMIT 1""", (mid,)).fetchone()
        d["report"] = dict(rep) if rep else None
        if d["report"]:
            v = con.execute("""SELECT verification_status FROM report_verifications
                               WHERE report_id=? ORDER BY verification_id DESC LIMIT 1""", (d["report"]["series_id"],)).fetchone()
            d["verification_status"] = v[0] if v else "待验证"
        con.close()
        self._json(d)

    def _search(self, qs):
        q = (qs.get("q") or [""])[0]
        if not q:
            self._json({"error": "missing q"}, 400)
            return
        con = db()
        rows = [dict(r) for r in con.execute(
            """SELECT r.date, substr(r.raw_text,1,200) content, r.source_topic, c.primary_category, c.secondary_category, c.confidence, c.review_required
               FROM message_classification c JOIN raw_messages r ON r.chat_id||':'||r.message_id=c.message_id
               WHERE r.raw_text LIKE ? ORDER BY r.date DESC LIMIT 100""", (f"%{q}%",)).fetchall()]
        reps = [dict(r) for r in con.execute(
            """SELECT s.series_id, s.title, s.institution, s.current_version, s.status
               FROM report_series s WHERE s.title LIKE ? OR s.institution LIKE ? ORDER BY s.last_seen_at DESC LIMIT 20""",
            (f"%{q}%", f"%{q}%")).fetchall()]
        con.close()
        self._json({"q": q, "results": rows, "count": len(rows), "reports": reps})

    def _review(self):
        con = db()
        rows = [dict(r) for r in con.execute(
            """SELECT r.date, substr(r.raw_text,1,300) content, r.source_topic, c.primary_category, c.secondary_category,
                      c.confidence, c.review_reason, c.message_id
               FROM message_classification c JOIN raw_messages r ON r.chat_id||':'||r.message_id=c.message_id
               WHERE c.review_required=1 ORDER BY r.date DESC LIMIT 100""").fetchall()]
        con.close()
        self._json({"review_queue": rows, "count": len(rows)})

    def _today_top(self):
        """今日重点资讯 TOP10（importance_score 降序 + 时间倒序）"""
        con = db()
        r = con.execute("SELECT max(date) d FROM raw_messages").fetchone()
        today = r["d"][:10] if r["d"] else "2026-01-01"
        rows = [dict(x) for x in con.execute("""
            SELECT r.chat_id||':'||r.message_id AS mid, r.date, r.source_topic, r.msg_type, r.raw_text,
                   r.relative_image_path, c.primary_category, c.secondary_category, c.confidence,
                   c.sentiment, c.entities_json, c.vision_status, c.importance_score, c.action_value, c.impact_scope,
                   (SELECT count(*) FROM report_messages rm WHERE rm.message_id = r.chat_id||':'||r.message_id) AS dup_cnt
            FROM message_classification c JOIN raw_messages r
              ON r.chat_id||':'||r.message_id = c.message_id
            WHERE r.date LIKE ?
              AND c.primary_category != 'empty_invalid'
              AND c.primary_category != 'image'
            ORDER BY c.importance_score DESC, r.date DESC LIMIT 15""", (today + "%",)).fetchall()]
        # 生成展示字段
        import re as _re
        for it in rows:
            text = (it.get("raw_text") or "").strip()
            first_line = text.split("\n")[0] if text else ""
            t = _re.sub(r'^(汇报|更新|点评|纪要|会议|快评|速评)[0-9]*[：:\s]*', '', first_line)
            t = _re.sub(r'^[【\[]([^】\]]+)[】\]]\s*', '', t)
            t = _re.sub(r'\s+', ' ', t).strip()
            it["display_title"] = (t[:60] + "…") if len(t) > 60 else (t or it.get("secondary_category") or "资讯")
            it["summary"] = clean_text_prefix(text)[:100] if text else ""
            m_inst = _re.search(r'[【\[]([^】\]]+)[】\]]', first_line or "")
            it["source_name"] = normalize_institution(m_inst.group(1).strip()) if m_inst else (it.get("source_topic") or "")
            try:
                ent = json.loads(it.get("entities_json") or "{}")
                it["stocks"] = ent.get("stocks") or []
                it["industries"] = ent.get("industries") or []
            except Exception:
                it["stocks"], it["industries"] = [], []
            it.pop("raw_text", None)
        con.close()
        self._json({"date": today, "top": rows[:10], "count": min(len(rows), 10)})

    def _quality(self):
        """质量监控：6 类指标（机构未匹配/Vision失败/低置信/疑似重复/代码歧义/长期未验证）"""
        con = db()
        import re as _re
        from datetime import datetime as _dt

        # 1) 机构名称未匹配：归一化消息中提取【机构】但不在映射表
        known = set()
        try:
            import sys as _sys2
            _sys2.path.insert(0, "/root/scripts")
            from institution_map import ALIASES
            known = set(ALIASES.values())
        except Exception:
            pass
        unmatched = {}
        rows = con.execute("""SELECT n.institution, count(*) c FROM normalized_messages n
                              WHERE n.institution IS NOT NULL AND n.institution != '' GROUP BY n.institution""").fetchall()
        for inst, c in rows:
            std = normalize_institution(inst)
            if std not in known and inst not in known:
                unmatched[inst] = c
        unmatched_list = [{"name": k, "count": v} for k, v in sorted(unmatched.items(), key=lambda x: -x[1])[:20]]
        # 1b) report_series 中机构为空（前端显示"未知机构"）也纳入统计
        unknown_reports = [dict(r) for r in con.execute(
            """SELECT series_id, title, report_type, first_seen_at FROM report_series
               WHERE institution IS NULL OR institution='' ORDER BY first_seen_at DESC LIMIT 20""").fetchall()]
        if unknown_reports:
            unmatched_list.append({"name": "未知机构(研报)", "count": len(unknown_reports), "reports": unknown_reports})

        # 2) Vision 失败/卡住
        vision_failed = con.execute("""SELECT count(*) FROM message_classification
                                       WHERE primary_category='image' AND vision_status IN ('queued','pending')""").fetchone()[0]
        vision_items = [dict(r) for r in con.execute("""SELECT r.date, c.message_id, c.vision_status, c.vision_summary
                                                        FROM message_classification c JOIN raw_messages r
                                                        ON r.chat_id||':'||r.message_id=c.message_id
                                                        WHERE c.primary_category='image' AND c.vision_status IN ('queued','pending')
                                                        ORDER BY r.date DESC LIMIT 10""").fetchall()]

        # 3) 低置信度分类
        low_conf = con.execute("SELECT count(*) FROM message_classification WHERE confidence='low' AND review_required=1").fetchone()[0]
        low_items = [dict(r) for r in con.execute("""SELECT r.date, c.message_id, c.primary_category, c.secondary_category, c.review_reason
                                                     FROM message_classification c JOIN raw_messages r
                                                     ON r.chat_id||':'||r.message_id=c.message_id
                                                     WHERE c.confidence='low' AND c.review_required=1
                                                     ORDER BY r.date DESC LIMIT 10""").fetchall()]

        # 4) 疑似重复研报：同机构 + 标题相似（norm 前缀相同）的不同 series
        dup = []
        series = con.execute("""SELECT series_id, institution, title FROM report_series ORDER BY institution, title""").fetchall()
        seen = {}
        for sid, inst, title in series:
            key = _re.sub(r'[（(][0-9]+[)）]', '', title or "")
            key = _re.sub(r'[：:，,。.\s\-—_/()（）]+', '', key)[:20]
            gk = f"{inst or ''}:{key}"
            if gk in seen:
                seen[gk].append(sid)
            else:
                seen[gk] = [sid]
        dup = [{"title": (con.execute("SELECT title FROM report_series WHERE series_id=?", (v[0],)).fetchone() or ("",))[0][:60],
                "series_ids": v} for k, v in seen.items() if len(v) > 1][:10]

        # 5) 股票代码歧义：entity_confidence='low'
        amb = [dict(r) for r in con.execute("""SELECT e.entity_id, e.entity_name, s.institution, s.title
                                               FROM report_entities e JOIN report_series s ON s.series_id=e.report_id
                                               WHERE e.entity_type='stock' AND e.entity_confidence='low'
                                               ORDER BY e.entity_id LIMIT 20""").fetchall()]

        # 5b) 新闻近似重复：news 消息标题归一相似（前 14 字相同）分组
        news_rows = con.execute("""SELECT r.chat_id||':'||r.message_id AS mid, r.date, r.raw_text
                                   FROM message_classification c JOIN raw_messages r
                                   ON r.chat_id||':'||r.message_id=c.message_id
                                   WHERE c.primary_category='news' ORDER BY r.date DESC LIMIT 200""").fetchall()
        news_groups = {}
        for nmid, ndate, ntext in news_rows:
            if not ntext:
                continue
            first = _re.sub(r"\s+", " ", ntext.strip())[:14]
            key = _re.sub(r'[：:，,。.·\-\—\s\d]+', '', first) or first
            if key in news_groups:
                news_groups[key].append({"mid": nmid, "date": ndate})
            else:
                news_groups[key] = [{"mid": nmid, "date": ndate}]
        news_dups = [{"title": k, "count": len(v), "items": v[:5]}
                     for k, v in news_groups.items() if len(v) > 1][:10]

        # 6) 长期未验证观点：待验证且发布时间 > 7 天
        stale = [dict(r) for r in con.execute("""
            SELECT s.institution, s.title, s.first_seen_at,
                   CAST(julianday('now','localtime') - julianday(substr(s.first_seen_at,1,10)) AS INTEGER) AS days
            FROM report_verifications v JOIN report_series s ON s.series_id=v.report_id
            WHERE v.verification_status='待验证'
              AND julianday('now','localtime') - julianday(substr(s.first_seen_at,1,10)) > 7
            ORDER BY days DESC LIMIT 20""").fetchall()]

        # ── v2.3.4 Observation Mode：系统健康 + RS 分层 + GS 组合 + Confidence + 快照历史 ──
        try:
            doc_total = con.execute("SELECT COUNT(*) FROM research_document").fetchone()[0]
            doc_high = con.execute("SELECT COUNT(*) FROM research_document WHERE quality_score>=50").fetchone()[0]
            ind_total = con.execute("SELECT COUNT(*) FROM industry_entity WHERE status='active'").fetchone()[0]
            graph_n = con.execute("SELECT COUNT(*) FROM research_graph_relation").fetchone()[0]
            val_total = con.execute("SELECT COUNT(*) FROM research_validation").fetchone()[0]
            t1_done = con.execute("SELECT COUNT(*) FROM research_validation WHERE t1_pct IS NOT NULL").fetchone()[0]
            t3_done = con.execute("SELECT COUNT(*) FROM research_validation WHERE t3_pct IS NOT NULL").fetchone()[0]
            t5_done = con.execute("SELECT COUNT(*) FROM research_validation WHERE t5_pct IS NOT NULL").fetchone()[0]
            system_health = {
                "doc_total": doc_total, "doc_high": doc_high, "industry_total": ind_total,
                "graph_relations": graph_n, "validation_total": val_total,
                "t1_done": t1_done, "t3_done": t3_done, "t5_done": t5_done,
                "stage": "稳定积累期", "target_t5": 100, "target_days": 20,
            }
            # RS 分层
            def _layer(min_s, max_s):
                rows = con.execute("SELECT t1_pct, t3_pct, t5_pct, result FROM research_validation WHERE research_score>=? AND research_score<?",
                                   (min_s, max_s)).fetchall()
                n = len(rows)
                if not n:
                    return {"n": 0}
                t1s = [r["t1_pct"] for r in rows if r["t1_pct"] is not None]
                t3s = [r["t3_pct"] for r in rows if r["t3_pct"] is not None]
                t5s = [r["t5_pct"] for r in rows if r["t5_pct"] is not None]
                hits = sum(1 for r in rows if r["result"] == "hit")
                done = sum(1 for r in rows if r["result"] in ("hit", "miss", "flat"))
                return {"n": n, "t1_avg": round(sum(t1s)/len(t1s), 2) if t1s else None,
                        "t3_avg": round(sum(t3s)/len(t3s), 2) if t3s else None,
                        "t5_avg": round(sum(t5s)/len(t5s), 2) if t5s else None,
                        "hit_rate": round(hits/done*100, 1) if done else None}
            rs_layers = {"90+": _layer(90, 101), "80-89": _layer(80, 90),
                         "70-79": _layer(70, 80), "60-69": _layer(60, 70), "<60": _layer(0, 60)}
            # 快照历史
            snapshots = [dict(r) for r in con.execute(
                "SELECT snap_date, system_version, doc_total, doc_high, validation_total, t5_done, rs_80, rs_60_79, rs_lt40 FROM research_system_snapshot ORDER BY snap_date DESC LIMIT 14")]
            # Event Momentum 分层
            mom_layers = {"80+": {"n": 0, "hit": 0, "done": 0}, "60-79": {"n": 0, "hit": 0, "done": 0}, "<60": {"n": 0, "hit": 0, "done": 0}}
            for r in con.execute("""SELECT v.result, (SELECT MAX(momentum_score) FROM event_momentum WHERE event_id=v.event_id) peak
                                    FROM research_validation v WHERE v.event_id IS NOT NULL"""):
                pk = r["peak"]
                if pk is None: continue
                k = "80+" if pk >= 80 else ("60-79" if pk >= 60 else "<60")
                c = mom_layers[k]
                c["n"] += 1
                if r["result"] in ("hit", "miss", "flat"):
                    c["done"] += 1
                    if r["result"] == "hit": c["hit"] += 1
            for k in mom_layers:
                v = mom_layers[k]
                v["hit_rate"] = round(v["hit"]/v["done"]*100, 1) if v["done"] else None
            # 十模型贡献
            model_contrib = {}
            for r in con.execute("SELECT stock_code, model_detail FROM research_scores WHERE model_detail IS NOT NULL AND model_detail != '{}'"):
                try:
                    md = json.loads(r["model_detail"] or "{}")
                    m = md.get("model") if isinstance(md, dict) else None
                except Exception:
                    m = None
                if not m: continue
                c = model_contrib.setdefault(m, {"n": 0, "hit": 0, "done": 0})
                v = con.execute("SELECT result FROM research_validation WHERE stock_code=? ORDER BY id DESC LIMIT 1", (r["stock_code"],)).fetchone()
                if not v: continue
                c["n"] += 1
                if v["result"] in ("hit", "miss", "flat"):
                    c["done"] += 1
                    if v["result"] == "hit": c["hit"] += 1
            for m in model_contrib:
                v = model_contrib[m]
                v["hit_rate"] = round(v["hit"]/v["done"]*100, 1) if v["done"] else None
            obs = {"system_health": system_health, "rs_layers": rs_layers, "snapshots": snapshots,
                   "momentum_layers": mom_layers, "model_contrib": model_contrib}
        except Exception as _e:
            obs = {"system_health": {}, "rs_layers": {}, "snapshots": [], "error": str(_e)}

        # ── v2.3.4e Quality Center：研究链完整性 + 低置信度拆分 + 机构异常分级 + document级重复 ──
        try:
            # ① 研究链完整性
            raw_n = con.execute("SELECT COUNT(*) FROM raw_messages").fetchone()[0]
            norm_n = con.execute("SELECT COUNT(*) FROM normalized_messages").fetchone()[0]
            doc_n = con.execute("SELECT COUNT(*) FROM research_document").fetchone()[0]
            doc_stock = con.execute("SELECT COUNT(*) FROM research_document WHERE stock_codes_json IS NOT NULL AND stock_codes_json != '[]'").fetchone()[0]
            doc_event = con.execute("""SELECT COUNT(DISTINCT d.doc_id) FROM research_document d
                WHERE EXISTS (SELECT 1 FROM event_messages em WHERE em.message_id IN (SELECT value FROM json_each(d.message_ids_json)))""").fetchone()[0]
            rs_stocks = con.execute("SELECT COUNT(DISTINCT stock_code) FROM research_scores").fetchone()[0]
            val_n = con.execute("SELECT COUNT(*) FROM research_validation").fetchone()[0]
            pipeline = {
                "raw": raw_n, "normalized": norm_n, "classified": raw_n,
                "document": doc_n,
                "doc_stock_rate": round(doc_stock / doc_n * 100) if doc_n else 0,
                "doc_event_rate": round(doc_event / doc_n * 100) if doc_n else 0,
                "rs_stocks": rs_stocks, "validation": val_n,
            }
            # ② 低置信度原因拆分
            low_rows = con.execute("""SELECT c.message_id, c.primary_category, c.entities_json, r.raw_text
                FROM message_classification c LEFT JOIN raw_messages r ON r.chat_id||':'||r.message_id=c.message_id
                WHERE c.confidence='low' AND c.review_required=1""").fetchall()
            reasons = {"来源不足(无股票实体)": 0, "图片无法解析": 0, "标题过短(<30字)": 0, "其他": 0}
            for r in low_rows:
                if r["primary_category"] == "image":
                    reasons["图片无法解析"] += 1
                elif r["raw_text"] and len(r["raw_text"]) < 30:
                    reasons["标题过短(<30字)"] += 1
                else:
                    try:
                        ent = json.loads(r["entities_json"] or "{}")
                        if not (ent.get("stocks") or ent.get("industries")):
                            reasons["来源不足(无股票实体)"] += 1
                        else:
                            reasons["其他"] += 1
                    except Exception:
                        reasons["来源不足(无股票实体)"] += 1
            low_conf_reasons = [{"reason": k, "count": v,
                                 "pct": round(v / max(low_conf, 1) * 100)} for k, v in reasons.items() if v > 0]
            low_conf_reasons.sort(key=lambda x: -x["count"])
            # ③ 机构异常分级：A 类真实机构 vs B 类噪声
            NOISE_KW = ("红包", "礼物", "烟花", "爱心", "抱拳", "链接", "群通知", "群公告", "撤回", "图片", "语音", "视频")
            inst_groups = {"real": [], "noise": []}
            noise_total = 0
            inst_rows = con.execute("""SELECT n.institution, count(*) c FROM normalized_messages n
                WHERE n.institution IS NOT NULL AND n.institution != '' GROUP BY n.institution ORDER BY c DESC""").fetchall()
            for inst, c in inst_rows:
                std = normalize_institution(inst)
                if std not in known and inst not in known:
                    is_noise = any(k in inst for k in NOISE_KW) or (len(inst) <= 2) or inst in ("DBDZ", "ZX机械", "科翔谷份")
                    if is_noise:
                        inst_groups["noise"].append({"name": inst, "count": c})
                        noise_total += c
                    else:
                        inst_groups["real"].append({"name": inst, "count": c})
            inst_groups["real"] = inst_groups["real"][:15]
            inst_groups["noise"] = inst_groups["noise"][:10]
            inst_groups["noise_total"] = noise_total
            # ④ document 级重复（归一标题分组）
            doc_rows = con.execute("SELECT doc_id, title_clean, source_count, institution_count, message_ids_json FROM research_document").fetchall()
            doc_groups = {}
            for d in doc_rows:
                t = _re.sub(r'[：:，,。.\s\-—_/()（）\[\]【】]+', '', d["title_clean"] or "")[:18]
                if not t:
                    continue
                doc_groups.setdefault(t, []).append(dict(d))
            dup_docs = []
            for t, g in doc_groups.items():
                if len(g) >= 2:
                    dup_docs.append({
                        "title": t[:24], "docs": len(g),
                        "sources": sum(x["source_count"] or 1 for x in g),
                        "institutions": sum(1 for x in g if x["institution_count"]),
                        "doc_ids": [x["doc_id"] for x in g][:6],
                    })
            dup_docs.sort(key=lambda x: -x["docs"])
            # ⑤ 健康评分（v2.3.4f）：数据完整性/实体关联/事件关联/验证覆盖
            def _pct(a, b):
                return round(a / b * 100) if b else 0
            _doc_n = doc_n
            h_integrity = min(100, _pct(norm_n, raw_n) + 10)          # 归一化覆盖率
            h_entity = min(100, _pct(doc_stock, _doc_n) * 3 + 10)      # 股票关联率加权
            h_event = min(100, _pct(doc_event, _doc_n) + 20)           # 事件关联率
            h_validation = min(100, _pct(val_n, 200) * 35)             # 验证样本/200
            health_score = round((h_integrity + h_entity + h_event + h_validation) / 4)
            health = {"score": health_score,
                      "dims": {"数据完整性": h_integrity, "实体关联": h_entity,
                               "事件关联": h_event, "验证覆盖": h_validation}}
            # ⑥ 系统状态灯（各环节最新时间，3 小时内更新=正常）
            from datetime import datetime as _dt, timedelta as _td
            from zoneinfo import ZoneInfo as _zi
            _now = _dt.now(_zi("Asia/Shanghai"))
            def _fresh(t):
                if not t:
                    return False
                try:
                    t2 = _dt.strptime(str(t)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_zi("Asia/Shanghai"))
                    return (_now - t2) < _td(hours=3)
                except Exception:
                    return False
            _raw_latest = con.execute("SELECT MAX(date) FROM raw_messages").fetchone()[0]
            _cls_latest = con.execute("SELECT MAX(r.date) FROM message_classification c JOIN raw_messages r ON r.chat_id||':'||r.message_id=c.message_id").fetchone()[0]
            _mom_latest = con.execute("SELECT MAX(bucket_hour) FROM event_momentum").fetchone()[0]
            _doc_latest = con.execute("SELECT MAX(last_seen_at) FROM research_document").fetchone()[0]
            _val_latest = con.execute("SELECT MAX(updated_at) FROM research_validation").fetchone()[0]
            system_status = {
                "采集": "正常" if _fresh(_raw_latest) else "延迟",
                "归一化": "正常" if _fresh(_cls_latest) else "延迟",
                "事件/热度": "正常" if _fresh(_mom_latest) else "延迟",
                "研究对象": "正常" if _fresh(_doc_latest) else "延迟",
                "验证": "正常" if _fresh(_val_latest) else "延迟",
                "recent_run": str(_val_latest or _doc_latest or _raw_latest or "")[:16],
            }
            # ⑦ 低置信度修复建议：图片（pending 可 OCR）+ 来源不足（产业新闻/传闻求证）
            _img_pending = con.execute("""SELECT COUNT(*) FROM message_classification
                WHERE confidence='low' AND review_required=1 AND primary_category='image' AND vision_status='pending'""").fetchone()[0]
            _low_no_ent = con.execute("""SELECT COUNT(*) FROM message_classification c
                WHERE c.confidence='low' AND c.review_required=1 AND c.primary_category!='image'
                  AND (c.entities_json IS NULL OR c.entities_json='{}' OR json_extract(c.entities_json,'$.stocks')='[]')""").fetchone()[0]
            _low_news = con.execute("""SELECT COUNT(*) FROM message_classification c
                WHERE c.confidence='low' AND c.review_required=1 AND c.secondary_category='产业新闻'
                  AND (c.entities_json IS NULL OR c.entities_json='{}' OR json_extract(c.entities_json,'$.stocks')='[]')""").fetchone()[0]
            repair_suggestions = [
                {"issue": "图片无法解析", "count": _img_pending,
                 "auto": round(_img_pending * 0.67), "manual": _img_pending - round(_img_pending * 0.67),
                 "action": "可自动 OCR（vision 队列重试）"},
                {"issue": "来源不足(无股票实体)", "count": _low_no_ent,
                 "auto": 0, "manual": _low_no_ent,
                 "action": "股票新闻 " + str(_low_news) + " · 其他 " + str(_low_no_ent - _low_news)},
            ]
            # ⑧ 机构异常排行标签（噪声/待确认/可能机构）
            for g in inst_groups["real"][:15]:
                g["type"] = "🟢可能机构" if len(g["name"]) <= 6 else "🟡待确认"
            for g in inst_groups["noise"][:10]:
                g["type"] = "🔴噪声"
            # ⑨ 重复归并收益（research_document 多消息聚合）
            _multi_docs = con.execute("""SELECT COUNT(*) FROM research_document
                WHERE json_array_length(message_ids_json) > 1""").fetchone()[0]
            _orig_msgs = 0
            for _r in con.execute("SELECT message_ids_json FROM research_document"):
                try:
                    _orig_msgs += len(json.loads(_r["message_ids_json"] or "[]"))
                except Exception:
                    _orig_msgs += 1
            merge_benefit = {
                "orig_messages": _orig_msgs, "documents": doc_n,
                "merged_docs": _multi_docs,
                "reduction": round((1 - doc_n / max(_orig_msgs, 1)) * 100),
            }
            quality_center = {"pipeline": pipeline, "low_conf_reasons": low_conf_reasons,
                              "institution_anomalies": inst_groups, "duplicate_documents": dup_docs[:8],
                              "health": health, "system_status": system_status,
                              "repair_suggestions": repair_suggestions,
                              "merge_benefit": merge_benefit}
        except Exception as _e2:
            quality_center = {"pipeline": {}, "low_conf_reasons": [], "institution_anomalies": {}, "duplicate_documents": [],
                              "health": {}, "system_status": {}, "repair_suggestions": [], "merge_benefit": {}, "error": str(_e2)}

        con.close()
        self._json({
            "quality_center": quality_center,
            "observation": obs,
            "unmatched_institutions": unmatched_list,
            "vision_failed": {"count": vision_failed, "items": vision_items},
            "low_confidence": {"count": low_conf, "items": low_items},
            "duplicate_reports": dup,
            "ambiguous_stocks": amb,
            "news_duplicates": news_dups,
            "stale_verifications": stale,
            "summary": {
                "unmatched_institutions": len(unmatched_list),
                "vision_failed": vision_failed,
                "low_confidence": low_conf,
                "duplicate_reports": len(dup),
                "ambiguous_stocks": len(amb),
                "news_duplicates": len(news_dups),
                "stale_verifications": len(stale),
            },
        })



    def _event_merge(self, body):
        """人工合并事件：from_ids 并入 into_id（merge_status=manual_merged）"""
        from_ids = body.get("from_ids") or []
        into_id = body.get("into_id")
        if not from_ids or not into_id:
            return self._json({"error": "need from_ids + into_id"}, 400)
        con = db()
        for fid in from_ids:
            if int(fid) == int(into_id):
                continue
            # 把 from 事件的消息移到 into 事件（INSERT OR IGNORE 防 UNIQUE 冲突，
            # 再删除 from 中已被移走的行）
            con.execute("""INSERT OR IGNORE INTO event_messages (event_id, message_id, message_role)
                           SELECT ?, message_id, message_role FROM event_messages WHERE event_id=?""",
                        (int(into_id), int(fid)))
            con.execute("DELETE FROM event_messages WHERE event_id=? AND message_id NOT IN "
                        "(SELECT message_id FROM event_messages WHERE event_id=?)", (int(fid), int(into_id)))
            # from 事件标记人工合并（不再展示为独立事件）
            con.execute("UPDATE event_clusters SET merge_status='manual_merged', status='closed' WHERE event_id=?", (int(fid),))
        # 更新 into 事件统计
        con.execute("""UPDATE event_clusters SET update_count=(
            SELECT COUNT(*) FROM event_messages WHERE event_id=?), merge_status='confirmed'
            WHERE event_id=?""", (int(into_id), int(into_id)))
        con.commit()
        con.close()
        return self._json({"ok": True, "merged": from_ids, "into": into_id})

    def _event_split(self, body):
        """人工拆分事件：从事件拆出 message_ids 到新事件（merge_status=manual_split）"""
        eid = body.get("event_id")
        mids = body.get("message_ids") or []
        if not eid or not mids:
            return self._json({"error": "need event_id + message_ids"}, 400)
        con = db()
        src_ev = con.execute("SELECT * FROM event_clusters WHERE event_id=?", (int(eid),)).fetchone()
        if not src_ev:
            return self._json({"error": "event not found"}, 404)
        src_ev = dict(src_ev)
        # 新事件（基于被拆出的第一条消息）
        first_mid = mids[0]
        row = con.execute("""SELECT r.raw_text, c.institution FROM raw_messages r
            LEFT JOIN message_classification c ON c.message_id=r.chat_id||':'||r.message_id
            WHERE r.chat_id||':'||r.message_id=?""", (first_mid,)).fetchone()
        title = (row[0] or "")[:40] if row else "拆分事件"
        cur = con.execute("""INSERT INTO event_clusters
            (event_title, event_type, industry, themes_json, occurred_date, stock_codes_json,
             source_count, institution_count, importance_score, first_seen_at, last_seen_at,
             entity_key, created_at, event_score, status, cluster_confidence, update_count, merge_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (title, src_ev["event_type"], "", "[]", src_ev["occurred_date"], "[]",
             0, 0, 0, src_ev["first_seen_at"], src_ev["last_seen_at"],
             f"split-{src_ev['event_id']}|{src_ev['occurred_date']}", src_ev["created_at"],
             0, "emerging", 1.0, len(mids), "manual_split"))
        new_id = cur.lastrowid
        for mid in mids:
            con.execute("UPDATE event_messages SET event_id=? WHERE event_id=? AND message_id=?", (new_id, int(eid), mid))
        con.execute("""UPDATE event_clusters SET update_count=(
            SELECT COUNT(*) FROM event_messages WHERE event_id=?) WHERE event_id=?""", (int(eid), int(eid)))
        con.execute("UPDATE event_clusters SET merge_status='manual_split' WHERE event_id=?", (int(eid),))
        con.commit()
        con.close()
        return self._json({"ok": True, "new_event_id": new_id, "moved": len(mids)})



    def _event_propagation(self, msgs):
        """传播链指标（v1.6.1）：
        first_at=首次发现 | inst_first_at=机构首次确认 | lead_minutes=领先时长
        chain=按时间排序的传播节点（角色/来源/机构/摘要）"""
        import datetime as _dt
        if not msgs:
            return {"first_at": "", "first_role": "", "first_source": "", "inst_first_at": "",
                    "inst_first_source": "", "lead_minutes": None, "span_minutes": 0,
                    "msg_rate": 0, "chain": []}
        def _ts(s):
            try:
                return _dt.datetime.strptime((s or "")[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                return None
        # 时间排序
        sorted_msgs = sorted(msgs, key=lambda m: (m.get("date") or ""))
        first = sorted_msgs[0]
        # 机构首次确认：第一个 research/source 角色或带机构的消息
        inst_first = None
        for m in sorted_msgs:
            role = m.get("message_role") or ""
            if role in ("research", "source") or m.get("institution"):
                inst_first = m
                break
        f_ts = _ts(first.get("date"))
        i_ts = _ts(inst_first.get("date")) if inst_first else None
        lead_min = None
        if f_ts and i_ts and i_ts > f_ts:
            lead_min = int((i_ts - f_ts).total_seconds() / 60)
        elif f_ts and i_ts:
            lead_min = 0
        # 时间跨度 + 消息速率
        l_ts = _ts(sorted_msgs[-1].get("date"))
        span_min = int((l_ts - f_ts).total_seconds() / 60) if f_ts and l_ts else 0
        rate = round(len(sorted_msgs) / max(1, span_min) * 60, 1) if span_min > 0 else len(sorted_msgs)
        # 传播链节点（压缩：同角色相邻合并，保留每个来源变化）
        chain = []
        last_key = None
        for m in sorted_msgs:
            role = m.get("message_role") or "update"
            src = m.get("institution") or m.get("source_topic") or m.get("from_user") or "未知"
            key = (role, src)
            if key == last_key and chain:
                chain[-1]["count"] = (chain[-1].get("count") or 1) + 1
                chain[-1]["last_at"] = m.get("date") or ""
                continue
            chain.append({
                "at": m.get("date") or "", "role": role,
                "source": src, "institution": m.get("institution") or "",
                "content": (m.get("content") or "")[:90],
                "count": 1, "last_at": m.get("date") or "",
            })
            last_key = key
        return {
            "first_at": first.get("date") or "",
            "first_role": first.get("message_role") or "",
            "first_source": first.get("institution") or first.get("source_topic") or first.get("from_user") or "",
            "inst_first_at": inst_first.get("date") if inst_first else "",
            "inst_first_source": (inst_first.get("institution") or inst_first.get("source_topic") or "") if inst_first else "",
            "lead_minutes": lead_min,
            "span_minutes": span_min,
            "msg_rate": rate,
            "chain": chain,
        }

    def _event_stocks(self, eid):
        """事件关联个股：event_stock_relation + 持仓/自选标记（v1.6）"""
        import json as _json
        con = db()
        # 持仓（watchlist 后端 /api/positions 的持久层，直接查）
        holding = set()
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:3100/api/positions")
            data = _json.loads(urllib.request.urlopen(req, timeout=4).read().decode())
            for p in (data.get("positions") or []):
                holding.add(str(p.get("code", "")))
        except Exception:
            pass
        rows = con.execute("""
            SELECT r.stock_code, r.stock_name, r.relation_type, r.source, r.confidence,
                   r.impact_score, r.logic, r.mention_count,
                   (SELECT rs.research_score FROM research_scores rs
                    WHERE rs.stock_code = r.stock_code ORDER BY rs.id DESC LIMIT 1) AS rs_score,
                   (SELECT rs.score_status FROM research_scores rs
                    WHERE rs.stock_code = r.stock_code ORDER BY rs.id DESC LIMIT 1) AS rs_status
            FROM event_stock_relation r WHERE r.event_id=?
            ORDER BY r.impact_score DESC, r.mention_count DESC LIMIT 12""", (eid,)).fetchall()
        out = []
        for code, name, rel, source, conf, impact, logic, mention, rs_score, rs_status in rows:
            out.append({
                "code": code, "name": name or "",
                "relation_type": rel, "source": source, "confidence": conf,
                "impact_score": impact, "logic": logic or "", "mention_count": mention,
                "is_holding": code in holding,
                "research_score": rs_score, "research_status": rs_status,
            })
        con.close()
        return out





    def _validation(self, qs):
        """个股研究验证记录（v2.1）"""
        code = (qs.get("code") or [""])[0].strip()
        if not code:
            return self._json({"error": "need code"}, 400)
        con = db()
        rows = [dict(r) for r in con.execute("""
            SELECT trigger_date, research_score, score_status, base_price,
                   t1_date, t1_pct, t3_date, t3_pct, t5_date, t5_pct,
                   max_up, max_drawdown, result, validation_note, event_title
            FROM research_validation WHERE stock_code=?
            ORDER BY trigger_date DESC LIMIT 30""", (code,)).fetchall()]
        con.close()
        return self._json({"code": code, "records": rows, "total": len(rows)})

    def _validation_stats(self):
        """验证统计 + 有效性分析（v2.1）：命中率、RS 分层表现"""
        con = db()
        # 总体
        stats = {}
        for r in con.execute("SELECT result, COUNT(*) FROM research_validation GROUP BY 1").fetchall():
            stats[r[0]] = r[1]
        # 有 T+3 的有效样本
        done = [dict(r) for r in con.execute("""
            SELECT stock_code, stock_name, research_score, trigger_date,
                   t1_pct, t3_pct, max_up, max_drawdown, result
            FROM research_validation WHERE t3_date IS NOT NULL""").fetchall()]
        n = len(done)
        hit_n = sum(1 for d in done if d["result"] == "hit")
        # RS 分层表现（T+3 平均）
        tiers = {}
        for lo, hi, label in [(80, 101, "RS≥80"), (70, 80, "RS70-79"), (60, 70, "RS60-69"), (0, 60, "RS<60")]:
            tier = [d for d in done if lo <= d["research_score"] < hi]
            if tier:
                avg_t3 = sum(d["t3_pct"] or 0 for d in tier) / len(tier)
                avg_up = sum(d["max_up"] or 0 for d in tier) / len(tier)
                tiers[label] = {"n": len(tier), "avg_t3": round(avg_t3, 2), "avg_maxup": round(avg_up, 2),
                                "hit_rate": round(sum(1 for d in tier if d["result"] == "hit") / len(tier) * 100, 1)}
        # 研究状态分层
        state_tiers = {}
        for r in con.execute("""SELECT research_state, AVG(t3_pct), COUNT(*) FROM research_validation
            WHERE t3_date IS NOT NULL AND research_state != '' GROUP BY research_state""").fetchall():
            state_tiers[r[0]] = {"n": r[2], "avg_t3": round(r[1] or 0, 2)}
        con.close()
        return self._json({
            "stats": stats,
            "validated": n, "hit_count": hit_n,
            "hit_rate": round(hit_n / n * 100, 1) if n else 0,
            "rs_tiers": tiers, "state_tiers": state_tiers,
            "note": "T+3 数据随每日 cron 自动累积（评分 08-12 上线，首批 T+3 约 08-15 可用）",
        })

    def _research_score(self, qs):
        """Research Score 研究综合分（v1.9）：最新评分 + 解释 + 缺失 + 历史"""
        import json as _json
        code = (qs.get("code") or [""])[0].strip()
        if not code:
            return self._json({"error": "need code"}, 400)
        con = db()
        latest = con.execute("""SELECT * FROM research_scores
            WHERE stock_code=? ORDER BY created_at DESC, id DESC LIMIT 1""", (code,)).fetchone()
        if not latest:
            con.close()
            return self._json({"code": code, "score": None, "history": []})
        d = dict(latest)
        try:
            d["explanation"] = _json.loads(d.pop("explanation_json") or "{}")
        except Exception:
            d["explanation"] = {}
        try:
            d["missing"] = _json.loads(d.pop("missing_conditions") or "[]")
        except Exception:
            d["missing"] = []
        # 2026-08-13 修复：change_reason 未解析导致前端 .map() 崩溃（详情抽屉空白）
        try:
            d["change_reason"] = _json.loads(d.get("change_reason") or "[]")
            if not isinstance(d["change_reason"], list):
                d["change_reason"] = []
        except Exception:
            d["change_reason"] = []
        # 历史（近 30 条，按时间倒序）
        history = [dict(r) for r in con.execute("""
            SELECT research_score, score_status, event_score, model_score, technical_score,
                   capital_score, score_change, research_state, created_at, parameter_version
            FROM research_scores WHERE stock_code=? ORDER BY id DESC LIMIT 30""", (code,)).fetchall()]
        # v2.0：研究结论（最新 summary）
        sm = con.execute("""SELECT summary, positive_factors, risk_factors, missing_conditions,
            suggestion, research_state, created_at
            FROM research_summary WHERE stock_code=? ORDER BY id DESC LIMIT 1""", (code,)).fetchone()
        if sm:
            d["summary_info"] = {
                "summary": sm[0], "positive": _json.loads(sm[1] or "[]"),
                "risk": _json.loads(sm[2] or "[]"), "missing": _json.loads(sm[3] or "[]"),
                "suggestion": sm[4], "state": sm[5], "generated_at": sm[6],
            }
        # v1.9.1：趋势（按天聚合，升序时间序列，用于迷你曲线）
        trend = [dict(r) for r in con.execute("""
            SELECT substr(created_at,1,10) d, MAX(research_score) score, MAX(research_state) state
            FROM research_scores WHERE stock_code=? GROUP BY substr(created_at,1,10)
            ORDER BY d DESC LIMIT 14""", (code,)).fetchall()]
        trend.reverse()
        con.close()
        return self._json({"code": code, "score": d, "history": history, "trend": trend})

    def _stock_events(self, qs):
        """个股事件催化（v1.8.1）：stock → event_stock_relation → event_clusters → momentum"""
        import json as _json
        code = (qs.get("code") or [""])[0].strip()
        if not code:
            return self._json({"error": "need code"}, 400)
        con = db()
        rows = con.execute("""
            SELECT r.event_id, r.relation_type, r.impact_score, r.logic, r.mention_count,
                   e.event_title, e.event_score, e.momentum_score, e.momentum_peak, e.status,
                   e.first_seen_at, e.last_seen_at, e.trigger_type, e.trigger_at,
                   e.source_count, e.institution_count, e.update_count
            FROM event_stock_relation r
            JOIN event_clusters e ON e.event_id = r.event_id
            WHERE r.stock_code=? AND e.merge_status != 'manual_merged'
            ORDER BY e.momentum_score DESC, e.event_score DESC LIMIT 20""", (code,)).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            # 机构确认列表（该事件中提及该股的机构？事件全局机构即可）
            insts = con.execute("""SELECT DISTINCT c.institution FROM event_messages em
                JOIN message_classification c ON c.message_id = em.message_id
                WHERE em.event_id=? AND c.institution != '' AND c.institution IS NOT NULL
                LIMIT 5""", (d["event_id"],)).fetchall()
            d["institutions"] = [i[0] for i in insts]
            d["inst_count"] = len(insts)
            out.append(d)
        con.close()
        return self._json({"code": code, "events": out, "total": len(out)})

    def _watchpool(self, qs):
        """研究队列（v2.2.2 归并）：以股票为主实体，聚合事件与状态。
        一只股票取最高优先级状态 + 最大模型分 + 最新 RS + 事件列表聚合。
        状态优先级: TRIAL_READY > MODEL_CHECK > WATCH > RESEARCH > EVENT_FOUND"""
        import json as _json
        con = db()
        st = (qs.get("status") or [""])[0]
        order = (qs.get("order") or ["model"])[0]
        status_rank = {"TRIAL_READY": 4, "MODEL_CHECK": 3, "WATCH": 2, "RESEARCH": 1, "EVENT_FOUND": 0}

        where_sql, args = "", []
        if st:
            where_sql = "WHERE w.status=?"
            args.append(st)

        rows = con.execute(f"""
            SELECT w.pool_id, w.event_id, w.stock_code, w.stock_name, w.status,
                   w.trigger_source, w.momentum_score, w.event_score, w.model_score,
                   w.model_detail, w.confidence, w.event_title, w.relation_type,
                   w.impact_score, w.logic, w.review_note, w.created_at, w.updated_at
            FROM event_watch_pool w
            {where_sql}
            ORDER BY w.stock_code, w.model_score DESC""", args).fetchall()

        # 按股票聚合
        stocks = {}
        for r in rows:
            d = dict(r)
            code = d["stock_code"]
            if code not in stocks:
                try:
                    md = _json.loads(d.get("model_detail") or "{}")
                except Exception:
                    md = {}
                stocks[code] = {
                    "stock_code": code,
                    "stock_name": d["stock_name"] or code,
                    "state": d["status"],
                    "state_rank": status_rank.get(d["status"], -1),
                    "model_score": d["model_score"] or 0,
                    "model_detail": md,
                    "confidence": d["confidence"] or 0,
                    "max_momentum": d["momentum_score"] or 0,
                    "events": [],
                    "pool_ids": [],
                }
            s = stocks[code]
            s["pool_ids"].append(d["pool_id"])
            rank = status_rank.get(d["status"], -1)
            if rank > s["state_rank"]:
                s["state"] = d["status"]
                s["state_rank"] = rank
            if (d["model_score"] or 0) > s["model_score"]:
                s["model_score"] = d["model_score"] or 0
                try:
                    s["model_detail"] = _json.loads(d.get("model_detail") or "{}")
                except Exception:
                    s["model_detail"] = {}
                s["confidence"] = d["confidence"] or 0
            if (d["momentum_score"] or 0) > s["max_momentum"]:
                s["max_momentum"] = d["momentum_score"] or 0
            s["events"].append({
                "event_id": d["event_id"],
                "event_title": d["event_title"] or "",
                "momentum_score": d["momentum_score"] or 0,
                "event_score": d["event_score"] or 0,
                "relation_type": d["relation_type"] or "",
                "logic": d["logic"] or "",
                "status": d["status"],
            })

        # 关联 RS（research_scores 最新一条）
        for code, s in stocks.items():
            rs = con.execute(
                "SELECT research_score, score_status FROM research_scores WHERE stock_code=? ORDER BY id DESC LIMIT 1",
                (code,)).fetchone()
            s["rs"] = rs[0] if rs else None
            s["rs_status"] = rs[1] if rs else None
            s["event_count"] = len(s["events"])
            s["events"].sort(key=lambda x: -x["momentum_score"])

        out = list(stocks.values())
        # 排序
        if order == "momentum":
            out.sort(key=lambda s: -s["max_momentum"])
        elif order == "confidence":
            out.sort(key=lambda s: -s["confidence"])
        else:
            out.sort(key=lambda s: -s["model_score"])
        # 状态筛选（聚合后按 state 过滤）
        if st:
            out = [s for s in out if s["state"] == st]
        out = out[:50]

        stats = {}
        for s in out:
            stats[s["state"]] = stats.get(s["state"], 0) + 1
        con.close()
        return self._json({"pool": out, "stats": stats, "total": len(out)})

    def _watchpool_advance(self, body):
        """人工确认：状态推进 EVENT_FOUND→RESEARCH→WATCH→MODEL_CHECK→TRIAL_READY（v1.8）
        安全边界：只推进研究观察状态，不创建/修改任何交易持仓"""
        import datetime as _dt
        pid = body.get("pool_id")
        if not pid:
            return self._json({"error": "need pool_id"}, 400)
        con = db()
        row = con.execute("SELECT status FROM event_watch_pool WHERE pool_id=?", (int(pid),)).fetchone()
        if not row:
            return self._json({"error": "pool item not found"}, 404)
        flow = ["EVENT_FOUND", "RESEARCH", "WATCH", "MODEL_CHECK", "TRIAL_READY"]
        cur_idx = flow.index(row[0]) if row[0] in flow else -1
        if cur_idx >= len(flow) - 1:
            return self._json({"ok": True, "status": row[0], "terminal": True})
        new_status = flow[cur_idx + 1]
        now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute("UPDATE event_watch_pool SET status=?, updated_at=? WHERE pool_id=?", (new_status, now, int(pid)))
        con.commit()
        con.close()
        return self._json({"ok": True, "pool_id": pid, "status": new_status})

    def _watchpool_note(self, body):
        """人工备注（v1.8）"""
        import datetime as _dt
        pid = body.get("pool_id")
        note = body.get("note") or ""
        if not pid:
            return self._json({"error": "need pool_id"}, 400)
        con = db()
        now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        con.execute("UPDATE event_watch_pool SET review_note=?, updated_at=? WHERE pool_id=?", (note, now, int(pid)))
        con.commit()
        con.close()
        return self._json({"ok": True, "pool_id": pid, "note": note})

    def _events(self, qs):
        """事件中心：event_clusters 列表 + 单事件详情（含关联消息/机构/股票）"""
        import json as _json
        con = db()
        eid = (qs.get("id") or [""])[0]
        date = (qs.get("date") or [""])[0]
        if eid:
            ev = con.execute("""SELECT * FROM event_clusters WHERE event_id=?""", (int(eid),)).fetchone()
            if not ev:
                return self._json({"error": "event not found"}, 404)
            ev = dict(ev)
            ev["themes"] = _json.loads(ev.get("themes_json") or "[]")
            ev["stocks"] = _json.loads(ev.get("stock_codes_json") or "[]")
            # 关联消息（含角色）
            msgs = con.execute("""
                SELECT r.date, substr(r.raw_text,1,400) content, c.content_type, c.content_subtype,
                       c.institution, c.research_team, c.research_value, c.confidence_score,
                       em.message_role, r.from_user, r.source_topic
                FROM event_messages em
                JOIN raw_messages r ON r.chat_id||':'||r.message_id = em.message_id
                LEFT JOIN message_classification c ON c.message_id = em.message_id
                WHERE em.event_id=? ORDER BY r.date""", (int(eid),)).fetchall()
            ev["messages"] = [dict(m) for m in msgs]
            # 角色分组（v1.5）：fact/source/research/commentary/mapping/update
            from collections import OrderedDict
            role_order = ["fact", "source", "research", "commentary", "mapping", "update", "summary"]
            grouped = OrderedDict((r, []) for r in role_order)
            for m in ev["messages"]:
                grouped.setdefault(m.get("message_role") or "update", []).append(m)
            ev["roles"] = {k: v for k, v in grouped.items() if v}
            # v1.6：关联个股详情（relation/impact/logic + 持仓标记）
            ev["stocks_detail"] = self._event_stocks(int(eid))
            # v1.6.1：传播链指标 + 传播链节点
            ev["propagation"] = self._event_propagation(ev.get("messages") or [])
            # v1.7：Momentum 小时曲线
            ev["momentum_curve"] = [dict(r) for r in con.execute("""
                SELECT bucket_hour, momentum_score, msg_count, src_count, inst_count, stock_count,
                       cum_msg, cum_inst, cum_stock
                FROM event_momentum WHERE event_id=? ORDER BY bucket_hour""", (int(eid),)).fetchall()]
            return self._json(ev)
        where = "WHERE e.occurred_date=?" if date else ""
        params = (date,) if date else ()
        rows = con.execute(f"""
            SELECT e.event_id, e.event_title, e.event_type, e.industry, e.themes_json,
                   e.occurred_date, e.stock_codes_json, e.source_count, e.institution_count,
                   e.importance_score, e.first_seen_at, e.last_seen_at,
                   e.event_score, e.status, e.cluster_confidence, e.update_count, e.merge_status,
                   e.momentum_score, e.momentum_peak, e.trigger_type, e.trigger_at,
                   (SELECT COUNT(DISTINCT c.institution) FROM event_messages em
                    JOIN message_classification c ON c.message_id=em.message_id
                    WHERE em.event_id=e.event_id AND c.institution!='' AND c.institution IS NOT NULL) AS inst_n
            FROM event_clusters e {where}
            ORDER BY e.importance_score DESC, e.occurred_date DESC LIMIT 100""", params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["themes"] = _json.loads(d.get("themes_json") or "[]")
            d["stocks"] = _json.loads(d.get("stock_codes_json") or "[]")
            out.append(d)
        return self._json({"events": out, "total": len(out)})

    def _verifications(self, qs):
        status = (qs.get("status") or [""])[0]
        con = db()
        sql = """SELECT v.verification_id, v.report_id, s.institution, s.title, v.event_date, v.event_type,
                        v.event_text, v.verification_status, v.evidence_source
                 FROM report_verifications v JOIN report_series s ON s.series_id=v.report_id"""
        args = []
        if status:
            sql += " WHERE v.verification_status=?"
            args.append(status)
        sql += " ORDER BY v.event_date DESC LIMIT 200"
        rows = [dict(r) for r in con.execute(sql, args).fetchall()]
        con.close()
        self._json({"verifications": rows, "count": len(rows)})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
