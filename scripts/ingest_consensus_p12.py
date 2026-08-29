#!/usr/bin/env python3
"""P1.2: Event Ingest —— vip0_timeline → source_snapshots → source records →
Security Resolver → Parser v1.1 → analyst_stock_events + analyst_daily_views → ingest_runs。

设计（用户 2026-08-28 P1.2 决策）：
- Lineage：每条标准事件可无歧义追溯回快照原始记录（source_snapshot_id / source_record_id /
  logical_record_id / event_index / analyst_id / event_date / raw_target / stock_code /
  stock_name / resolve_method / raw_action / parser_version / resolver_version）
- 幂等：INSERT ... ON CONFLICT (source_record_id, event_index) DO NOTHING（禁 REPLACE，防掩盖 revision）
- ingest_runs：run_id 主键，同版本重跑留独立 run history（P1.1 schema v2）
- 只落 A 股可解析（EXACT/ALIAS，含 CONTEXT/FUZZY 预留为 0）事件进 analyst_stock_events，
  THEME/MARKET/OUT_OF_SCOPE/UNKNOWN 只统计不硬塞（既定 entity gate）
- daily_views：只落分析师每日市场观点 section（core_theme/trend/logic 原文），不反推、不混 theme
- 本步不写 position_snapshots / theme_mentions / record_revisions（P1.3 / P1.4）

用法: python3 scripts/ingest_consensus_p12.py [--json data/analyst_snapshots/vip0_timeline_20260828.json]
可重复运行（幂等）；重跑 0 new events + result_hash 不变 + ingest_runs 新增一条 run。
"""
import argparse, hashlib, json, re, sqlite3, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from action_temporal_parser_v11_p0b import parse as parse_v11

DB = ROOT / "data/analyst_consensus.db"
MASTER_DB = ROOT / "data/security_master.db"

PARSER_VERSION = "v1.1"
RESOLVER_VERSION = "exact-alias-v1"     # 0B.3 inline-code/EXACT + 0B.4 ALIAS；CONTEXT/FUZZY 关闭
SCHEMA_VERSION = "2"

BEIJING_TZ = timezone(timedelta(hours=8))
now_iso = lambda: datetime.now(BEIJING_TZ).strftime("%Y-%m-%dT%H:%M:%S%z")

# analyst 展示名 → 规范化 id（设计文档 3.1；10 位 VIP1 博主，2026-08-28 快照）
ANALYST_IDS = {
    "老樊": "laofan", "震哥本尊": "zhenge", "天赢居": "tianyingju",
    "格兰投研": "gelan", "游资混江龙": "youzi", "清北游资": "qingbei",
    "妖股刺客": "yaogu", "潘凤": "panfeng", "李梦尘": "limengchen",
    "一线天渔哥": "yixiantian",
}

# ---------- 归一化 ----------
def normalize(s):
    if not s: return ""
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

INLINE_CODE_RE = re.compile(r"\(((?:60|68|00|30|92|83|43)\d{4})\)")   # group(1)=完整6位代码
BARE_CODE_RE = re.compile(r"(?<!\d)((?:60|68|00|30|92|83|43)\d{4})(?!\d)")  # 裸代码（600103青山纸业）

# ---------- entity gate（0B.3 + 0A classify_target 合并，既定口径） ----------
NON_STOCK = {"大盘", "市场", "科技线", "科技", "半导体", "光模块", "存储", "有色", "券商",
             "农业", "AI", "AI硬件", "半导体材料", "光通信", "算力", "持仓", "手里几个科技票"}
MARKET_HINTS = ("大盘", "指数", "市场", "市场风格", "主线")
THEME_SUFFIX_RE = re.compile(r"(材料|硅片|资源|金属|折叠屏|冷液|液冷|产业链|相关$|板块|方向|概念)")
# 概念/组合词（P1.2 裁决补充，精确匹配）→ THEME（Phase 2 Theme Heat 聚合）
CONCEPTS = {"MLCC", "商业航天", "创新药CXO", "创新药高位股", "科技连板(低位)",
            "铜管持仓", "燕子家族", "特高压（2只）"}
# 市场数据 → MARKET
MARKET_EXTRA = {"两融余额"}


def classify_entity(raw, name_part):
    """→ (entity_type, reason)。entity_type ∈ STOCK/OUT_OF_SCOPE/THEME/MARKET/UNKNOWN。
    STOCK 只由 resolver 命中产生（resolve_status=A_SHARE），此处不做猜测。"""
    if raw in {"大盘", "市场"}:
        return "MARKET", "NON_STOCK_MARKET"
    if raw in NON_STOCK:
        return "THEME", "NON_STOCK"
    if raw in MARKET_EXTRA:
        return "MARKET", "MARKET_DATA"
    if raw in CONCEPTS:
        return "THEME", "CONCEPT"
    if any(h in name_part for h in MARKET_HINTS):
        return "MARKET", "MARKET_HINT"
    if THEME_SUFFIX_RE.search(name_part):
        return "THEME", "THEME_SUFFIX"
    return "UNKNOWN", "PENDING_RESOLVE"


# ---------- Security Resolver（0B.3/0B.4 规则） ----------
class Resolver:
    def __init__(self, master_db=MASTER_DB):
        con = sqlite3.connect(master_db)
        self.name_to_code = {r[0]: r[1] for r in con.execute("SELECT stock_name, stock_code FROM stock_master")}
        self.code_set = set(self.name_to_code.values())
        self.alias_to_code = {normalize(r[0]): r[1] for r in con.execute("SELECT alias, stock_code FROM stock_aliases")}
        self.out_of_scope = {normalize(r[0]) for r in con.execute("SELECT raw_name FROM out_of_scope")}
        con.close()

    def resolve(self, raw):
        """→ dict(entity_type, stock_code, stock_name, resolve_method, reason)
        顺序: OOS → THEME/MARKET 规则 → 复合多标的 → inline code EXACT → 裸代码 EXACT
              → 名称 EXACT → ALIAS → UNRESOLVED"""
        raw = normalize(raw)
        name_part = re.sub(INLINE_CODE_RE, "", raw).strip()   # 去括号内联代码
        norm = normalize(name_part)
        if norm in self.out_of_scope or raw in self.out_of_scope:
            return {"entity_type": "OUT_OF_SCOPE", "stock_code": None, "stock_name": None,
                    "resolve_method": "OUT_OF_SCOPE", "reason": "OOS_TABLE"}
        typ, why = classify_entity(raw, name_part)
        if typ != "UNKNOWN":
            return {"entity_type": typ, "stock_code": None, "stock_name": None,
                    "resolve_method": "OUT_OF_SCOPE", "reason": why}
        # 复合多标的（斜杠/顿号拆出 2+ 段：拓尔思/三六零、603019/000977）→ 不硬塞单股
        segments = [s for s in re.split(r"[/、,，]", raw) if len(s.strip()) >= 2]
        if len(segments) >= 2:
            return {"entity_type": "COMPOSITE", "stock_code": None, "stock_name": None,
                    "resolve_method": "OUT_OF_SCOPE", "reason": "COMPOSITE_MULTI"}
        # 代码提取：括号内 + 裸代码（去括号后的 name_part 上搜裸代码，避免双计）
        codes = [m.group(1) for m in INLINE_CODE_RE.finditer(raw)]
        codes += [m.group(1) for m in BARE_CODE_RE.finditer(name_part)]
        unique = list(dict.fromkeys(codes))
        if unique:
            known = [c for c in unique if c in self.code_set]
            if len(unique) == 1 and known:
                code = unique[0]
                nm = next((n for n, c in self.name_to_code.items() if c == code), None)
                return {"entity_type": "STOCK", "stock_code": code, "stock_name": nm,
                        "resolve_method": "EXACT", "reason": "CODE"}
            if len(unique) == 1:
                return {"entity_type": "UNKNOWN", "stock_code": None, "stock_name": None,
                        "resolve_method": "UNRESOLVED", "reason": "CODE_NOT_IN_MASTER"}
            if len(known) == len(unique):
                return {"entity_type": "COMPOSITE", "stock_code": None, "stock_name": None,
                        "resolve_method": "OUT_OF_SCOPE", "reason": "MULTI_CODE"}
            return {"entity_type": "UNKNOWN", "stock_code": None, "stock_name": None,
                    "resolve_method": "UNRESOLVED", "reason": "MULTI_CODE_PARTIAL"}
        if norm in self.name_to_code:
            return {"entity_type": "STOCK", "stock_code": self.name_to_code[norm], "stock_name": norm,
                    "resolve_method": "EXACT", "reason": "NAME"}
        if norm in self.alias_to_code:
            code = self.alias_to_code[norm]
            nm = next((n for n, c in self.name_to_code.items() if c == code), None)
            return {"entity_type": "STOCK", "stock_code": code, "stock_name": nm,
                    "resolve_method": "ALIAS", "reason": "ALIAS"}
        return {"entity_type": "UNKNOWN", "stock_code": None, "stock_name": None,
                "resolve_method": "UNRESOLVED", "reason": "NO_MATCH"}


# ---------- action → event_category 映射（Phase 1 设计 3.4） ----------
CATEGORY = {
    "BUY": "TRADE", "ADD": "TRADE", "LOW_BUY": "TRADE", "TRIAL": "TRADE",
    "REDUCE": "TRADE", "SELL": "TRADE", "CLEAR": "TRADE", "STOP_LOSS": "TRADE",
    "WATCH": "OBSERVATION", "HOLD": "STATE", "DO_T": "COMPOSITE_TACTICAL",
    "UNKNOWN": "UNKNOWN",
}


def sha16(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


def collect_source_records(d):
    """展开 bloggers/days/ops → source records（带 0B.6 双层 ID）。"""
    records = []
    for bname, b in d["bloggers"].items():
        aid = ANALYST_IDS.get(bname, bname)
        for dkey in sorted(b["days"].keys()):
            day = b["days"][dkey]
            ordinals = {}
            for op in day.get("ops", []):
                entity = normalize(op.get("stock", ""))
                if not entity:
                    continue
                key = (bname, dkey, entity)
                ordinals[key] = ordinals.get(key, 0) + 1
                nnn = ordinals[key]
                logical = f"vip0:{bname}:{dkey}:{entity}"
                records.append({
                    "source_record_id": f"{logical}:action:{nnn:03d}",
                    "logical_record_id": logical,
                    "role": "daily_action",
                    "analyst_id": aid, "analyst": bname, "event_date": dkey,
                    "raw_target": op.get("stock", ""),
                    "raw_action": op.get("action", ""), "raw_logic": op.get("logic", ""),
                    "direction": op.get("direction", ""), "op_date": op.get("date", dkey),
                })
    return records


def result_hash_of(con):
    """落库后 analyst_stock_events 全表确定性 hash（幂等重跑一致性 gate）。"""
    rows = con.execute(
        "SELECT source_record_id, event_index, action_type, event_category, action_status,"
        " temporal_type, stock_code, stock_name, raw_target, resolve_method"
        " FROM analyst_stock_events ORDER BY source_record_id, event_index").fetchall()
    payload = "\n".join("|".join(str(x) for x in r) for r in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path,
                    default=ROOT / "data/analyst_snapshots/vip0_timeline_20260828.json")
    ap.add_argument("--snapshot-date", default="2026-08-28")
    args = ap.parse_args()
    if not args.json.exists():
        print(f"快照不存在: {args.json}")
        return 1

    raw = args.json.read_bytes()
    d = json.loads(raw.decode("utf-8"))
    now = now_iso()

    records = collect_source_records(d)
    resolver = Resolver()

    # ---------- 1) Resolver + 分层统计（record 级 entity） ----------
    stats = {"source_records": len(records), "parser_total_events": 0,
             "a_share": 0, "out_of_scope": 0, "theme": 0, "market": 0, "unknown": 0,
             "unresolved": 0, "eligible_stock_events": 0,
             "inserted": 0, "skipped_existing": 0, "error_count": 0}
    bucket_dist = {}

    resolved_records = []
    for r in records:
        rs = resolver.resolve(r["raw_target"])
        r["resolve"] = rs
        resolved_records.append(r)

        # parse 事件数（无论 entity 类型都计，用于分层分母）
        pr = parse_v11(r["raw_action"], r["raw_logic"])
        n_ev = len(pr["events"])
        stats["parser_total_events"] += n_ev
        bucket = rs["entity_type"]
        bucket_dist[bucket] = bucket_dist.get(bucket, 0) + n_ev
        if bucket == "STOCK":
            stats["a_share"] += n_ev
        elif bucket == "OUT_OF_SCOPE":
            stats["out_of_scope"] += n_ev
        elif bucket == "THEME":
            stats["theme"] += n_ev
        elif bucket == "MARKET":
            stats["market"] += n_ev
        elif rs["resolve_method"] == "UNRESOLVED":
            stats["unresolved"] += n_ev
        else:
            stats["unknown"] += n_ev
        if bucket == "STOCK":
            stats["eligible_stock_events"] += n_ev

    # ---------- 2) 事务落库 ----------
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    inserted = skipped = 0
    errs = []
    try:
        con.execute("BEGIN")
        # analyst_profiles（style: 源数据为自由文本描述，0B.4 未产出枚举映射，
        # 按"不猜测"原则暂落合法空串，待 Phase 2 前人工确认 10 位博主风格标签）
        for bname, b in d["bloggers"].items():
            aid = ANALYST_IDS.get(bname, bname)
            con.execute(
                "INSERT INTO analyst_profiles (analyst_id, analyst_name, style, source, topic_id, enabled, created_at, updated_at)"
                " VALUES (?,?,?,?,?,1,?,?)"
                " ON CONFLICT (analyst_id) DO NOTHING",
                (aid, bname, "", "vip0", b.get("topic_id"), now, now))
        # source_snapshots
        con.execute(
            "INSERT INTO source_snapshots (source, snapshot_date, captured_at, page_generated_at, page_sha256, raw_json_path, record_count, created_at, updated_at)"
            " VALUES ('vip0', ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (source, snapshot_date) DO NOTHING",
            (args.snapshot_date, now, d.get("generated"), hashlib.sha256(raw).hexdigest(),
             str(args.json), len(records), now, now))
        snap_id = con.execute(
            "SELECT snapshot_id FROM source_snapshots WHERE source='vip0' AND snapshot_date=?",
            (args.snapshot_date,)).fetchone()[0]

        # analyst_stock_events（只落 eligible A 股）
        for r in resolved_records:
            rs = r["resolve"]
            if rs["entity_type"] != "STOCK":
                continue
            pr = parse_v11(r["raw_action"], r["raw_logic"])
            for idx, ev in enumerate(pr["events"]):
                action = ev["action"]
                fingerprint = json.dumps(
                    {"raw_target": r["raw_target"], "raw_action": r["raw_action"],
                     "raw_logic": r["raw_logic"], "direction": r["direction"]},
                    ensure_ascii=False, sort_keys=True)
                try:
                    cur = con.execute(
                        "INSERT INTO analyst_stock_events"
                        " (source_record_id, logical_record_id, role, event_index, analyst_id, event_date,"
                        "  temporal_type, stock_code, stock_name, raw_target, action_type, event_category,"
                        "  action_status, stance, direction, raw_action, raw_logic, resolve_method,"
                        "  match_confidence, source_snapshot_id, record_hash, first_seen_at, last_seen_at,"
                        "  revision_no, created_at, updated_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)"
                        " ON CONFLICT (source_record_id, event_index) DO NOTHING",
                        (r["source_record_id"], r["logical_record_id"], r["role"], idx,
                         r["analyst_id"], r["event_date"], ev["temporal_type"],
                         rs["stock_code"], rs["stock_name"], r["raw_target"],
                         action, CATEGORY.get(action, "UNKNOWN"), ev["action_status"],
                         ev.get("stance"), r["direction"], r["raw_action"], r["raw_logic"],
                         rs["resolve_method"], None, snap_id, sha16(fingerprint),
                         now, now, now, now))
                    if cur.rowcount == 1:
                        inserted += 1
                    else:
                        skipped += 1
                except sqlite3.IntegrityError as e:
                    errs.append(f"{r['source_record_id']}[{idx}]: {e}")

        # analyst_daily_views（只落分析师每日市场观点 section 原文）
        views_ins = 0
        for bname, b in d["bloggers"].items():
            aid = ANALYST_IDS.get(bname, bname)
            for dkey in sorted(b["days"].keys()):
                day = b["days"][dkey]
                for vt in ("core_theme", "trend", "logic"):
                    content = (day.get(vt) or "").strip()
                    if not content:
                        continue
                    try:
                        cur = con.execute(
                            "INSERT INTO analyst_daily_views (analyst_id, view_date, view_type, content,"
                            " source_snapshot_id, record_hash, first_seen_at, last_seen_at, revision_no, created_at, updated_at)"
                            " VALUES (?,?,?,?,?,?,?,?,1,?,?)"
                            " ON CONFLICT (analyst_id, view_date, view_type) DO NOTHING",
                            (aid, dkey, vt, content, snap_id, sha16(content), now, now, now, now))
                        views_ins += cur.rowcount
                    except sqlite3.IntegrityError as e:
                        errs.append(f"daily_view {bname}/{dkey}/{vt}: {e}")

        # ingest_runs 记账（run_id 自增，同版本重跑独立留痕）
        h = result_hash_of(con)
        con.execute(
            "INSERT INTO ingest_runs (source_snapshot_id, parser_version, resolver_version, schema_version,"
            " started_at, finished_at, status, source_record_count, parsed_event_count,"
            " inserted_event_count, skipped_existing_count, error_count, result_hash, errors, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (snap_id, PARSER_VERSION, RESOLVER_VERSION, SCHEMA_VERSION,
             now, now, "success" if not errs else "failed",
             len(records), stats["parser_total_events"], inserted, skipped,
             len(errs), h, json.dumps(errs, ensure_ascii=False) if errs else None, now, now))
        con.commit()
        run_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    stats["inserted"] = inserted
    stats["skipped_existing"] = skipped
    stats["error_count"] = len(errs)
    stats["daily_views_created"] = views_ins
    stats["run_id"] = run_id
    stats["result_hash"] = h
    stats["bucket_dist"] = bucket_dist

    # ---------- 3) 分层报告 ----------
    print("=== P1.2 Event Ingest 分层报告 ===")
    print(f"快照: {args.json} ({args.snapshot_date})")
    print(f"Source records          : {stats['source_records']}")
    print(f"Parser total events     : {stats['parser_total_events']}")
    print(f"  A_SHARE events        : {stats['a_share']}")
    print(f"  OUT_OF_SCOPE events   : {stats['out_of_scope']}")
    print(f"  THEME events          : {stats['theme']}")
    print(f"  MARKET events         : {stats['market']}")
    print(f"  UNRESOLVED events     : {stats['unresolved']}")
    print(f"  UNKNOWN-target events : {stats['unknown']}")
    print(f"Eligible stock events   : {stats['eligible_stock_events']}")
    print(f"Inserted stock events   : {stats['inserted']}")
    print(f"Skipped existing        : {stats['skipped_existing']}")
    print(f"Daily views created     : {stats['daily_views_created']}")
    print(f"error_count             : {stats['error_count']}")
    print(f"ingest_runs run_id      : {stats['run_id']} (parser={PARSER_VERSION}, resolver={RESOLVER_VERSION})")
    print(f"result_hash             : {stats['result_hash'][:16]}")
    if errs:
        for e in errs[:10]:
            print("  ERR", e)
    print(f"bucket_dist             : {json.dumps(stats['bucket_dist'], ensure_ascii=False)}")
    return 0 if not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
