#!/usr/bin/env python3
"""P1.3: Position Dual-Track —— 从 vip0_timeline 提取"当前持仓"表述，
只落 analyst_position_snapshots（position_state=HOLDING / temporal=CURRENT_STATE）。

设计（用户 2026-08-29 P1.3 决策）：
- 核心定义：position_snapshots 记录"某个快照日我们确认分析师当前持有什么"，
  不是操作历史，也不能反推买入时间。
- 数据流：op（持仓表述）→ Resolver（仅 A_SHARE + 可确定标的）→
  analyst_position_snapshots → position_state = HOLDING
- 硬护栏：持仓表述 NEVER 生成 BUY/ADD/LOW_BUY/TRIAL 事件（不经过 Action Parser 推交易）；
  同一 op 在 P1.2 已落 analyst_stock_events 的交易事件（ADD/LOW_BUY/REDUCE/SELL...）照常并存 = 双轨合法。
- 观察值原则：缺失的持仓不做状态机推断/继承（08-29 缺芯原 ≠ 自动写 08-29 HOLDING 芯原）。
- 幂等：INSERT ... ON CONFLICT (analyst_id, snapshot_date, source_record_id) DO NOTHING（禁 REPLACE）
- 唯一键：(analyst_id, snapshot_date, source_record_id)——source_record_id 已天然逐股票唯一，
  每条 op 一条 HOLDING。

持仓来源判定（--source-mode）：
  hold     [默认] Parser 判定 action_status=POSITION_STATE 的 op（124 条，与 events 轨严格 1:1 双轨对照）
  direction direction=持有 的 op（201 条，采编显式标记，含操作语义杂音）
  union    hold ∪ direction（229 条）
  inter    hold ∩ direction（96 条）

用法: python3 scripts/ingest_position_p13.py [--source-mode hold]
可重复运行（幂等）；重跑 0 new + result_hash 不变 + ingest_runs 新增一条 run。
"""
import argparse, hashlib, json, sqlite3, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from action_temporal_parser_v11_p0b import parse as parse_v11
from ingest_consensus_p12 import (ANALYST_IDS, Resolver, classify_entity,
                                  collect_source_records, normalize)

DB = ROOT / "data/analyst_consensus.db"
MASTER_DB = ROOT / "data/security_master.db"

PARSER_VERSION = "v1.1"
RESOLVER_VERSION = "exact-alias-v1"
SCHEMA_VERSION = "2"
POSITION_VERSION = "p13-hold"   # 口径标识（hold/direction/union/inter）

BEIJING_TZ = timezone(timedelta(hours=8))
now_iso = lambda: datetime.now(BEIJING_TZ).strftime("%Y-%m-%dT%H:%M:%S%z")


def sha16(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


def collect_source_records_with_direction(d):
    """扩展 P1.2 collect_source_records：给每条 op 补 direction 字段（已在 P1.2 records 中）。
    这里直接复用 P1.2 的 records（已含 direction）。"""
    return collect_source_records(d)


def position_sources(d, mode="hold"):
    """→ 持仓来源 op 列表（每条含 source_record_id/logical_record_id/analyst_id/event_date/
    raw_target/raw_action/raw_logic/direction/analyst/op_index）。"""
    records = collect_source_records(d)
    # 源快照与 records 对齐：collect_source_records 按 bloggers/days/ops 顺序生成，
    # 我们在每 op 上重算 direction（records 已含 direction）
    hold_ops, dir_ops = [], []
    for r in records:
        # 判定：Parser 是否输出 POSITION_STATE 事件（语义=当前持仓）
        pr = parse_v11(r["raw_action"], r["raw_logic"])
        is_pos = any(ev.get("action_status") == "POSITION_STATE" for ev in pr["events"])
        is_dir = (r.get("direction") == "持有")
        if is_pos:
            hold_ops.append(r)
        if is_dir:
            dir_ops.append(r)
    if mode == "hold":
        src = hold_ops
    elif mode == "direction":
        src = dir_ops
    elif mode == "union":
        src = list({id(o): o for o in (hold_ops + dir_ops)}.values())
    elif mode == "inter":
        hs = {id(o) for o in hold_ops}
        src = [o for o in dir_ops if id(o) in hs]
    else:
        raise ValueError(f"unknown source-mode: {mode}")
    # 去重（同一 op 可能同时命中 hold+dir）
    seen, uniq = set(), []
    for r in src:
        k = r["source_record_id"]
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path,
                    default=ROOT / "data/analyst_snapshots/vip0_timeline_20260828.json")
    ap.add_argument("--snapshot-date", default="2026-08-28")
    ap.add_argument("--source-mode", default="hold",
                    choices=["hold", "direction", "union", "inter"])
    args = ap.parse_args()
    if not args.json.exists():
        print(f"快照不存在: {args.json}")
        return 1

    raw = args.json.read_bytes()
    d = json.loads(raw.decode("utf-8"))
    now = now_iso()
    resolver = Resolver()

    src = position_sources(d, args.source_mode)
    stats = {"source_mode": args.source_mode, "position_candidates": len(src),
             "a_share": 0, "out_of_scope": 0, "theme": 0, "market": 0,
             "unresolved": 0, "composite": 0, "inserted": 0,
             "skipped_existing": 0, "error_count": 0}
    bucket_dist = {}

    # ---------- 1) Resolver 分层 ----------
    resolved = []
    for r in src:
        rs = resolver.resolve(r["raw_target"])
        r["resolve"] = rs
        resolved.append(r)
        bucket_dist[rs["entity_type"]] = bucket_dist.get(rs["entity_type"], 0) + 1
        if rs["entity_type"] == "STOCK":
            stats["a_share"] += 1
        elif rs["entity_type"] == "OUT_OF_SCOPE":
            stats["out_of_scope"] += 1
        elif rs["entity_type"] == "THEME":
            stats["theme"] += 1
        elif rs["entity_type"] == "MARKET":
            stats["market"] += 1
        elif rs["entity_type"] == "COMPOSITE":
            stats["composite"] += 1
        else:
            stats["unresolved"] += 1

    # ---------- 2) 事务落库（只落 A_SHARE；position_state CHECK 约束强制 HOLDING） ----------
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    inserted = skipped = 0
    errs = []
    try:
        con.execute("BEGIN")
        snap_id = con.execute(
            "SELECT snapshot_id FROM source_snapshots WHERE source='vip0' AND snapshot_date=?",
            (args.snapshot_date,)).fetchone()[0]
        for r in resolved:
            rs = r["resolve"]
            if rs["entity_type"] != "STOCK":
                continue
            fingerprint = json.dumps(
                {"raw_target": r["raw_target"], "raw_action": r["raw_action"],
                 "raw_logic": r["raw_logic"], "direction": r.get("direction", "")},
                ensure_ascii=False, sort_keys=True)
            try:
                cur = con.execute(
                    "INSERT INTO analyst_position_snapshots"
                    " (analyst_id, snapshot_date, stock_code, stock_name, raw_target,"
                    "  position_state, raw_action, raw_logic, source_record_id, logical_record_id,"
                    "  resolve_method, source_snapshot_id, record_hash, first_seen_at, last_seen_at,"
                    "  revision_no, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)"
                    " ON CONFLICT (analyst_id, snapshot_date, source_record_id) DO NOTHING",
                    (r["analyst_id"], r["event_date"], rs["stock_code"], rs["stock_name"],
                     r["raw_target"], "HOLDING", r["raw_action"], r["raw_logic"],
                     r["source_record_id"], r["logical_record_id"], rs["resolve_method"],
                     snap_id, sha16(fingerprint), now, now, now, now))
                if cur.rowcount == 1:
                    inserted += 1
                else:
                    skipped += 1
            except sqlite3.IntegrityError as e:
                errs.append(f"{r['source_record_id']}: {e}")

        # ingest_runs 记账（复用同一表，run 口径 = position）
        h = position_hash_of(con)
        con.execute(
            "INSERT INTO ingest_runs (source_snapshot_id, parser_version, resolver_version, schema_version,"
            " started_at, finished_at, status, source_record_count, parsed_event_count,"
            " inserted_event_count, skipped_existing_count, error_count, result_hash, errors, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (snap_id, PARSER_VERSION, RESOLVER_VERSION, SCHEMA_VERSION,
             now, now, "success" if not errs else "failed",
             len(src), len(src), inserted, skipped, len(errs),
             h, json.dumps(errs, ensure_ascii=False) if errs else None, now, now))
        con.commit()
        run_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    stats.update({"inserted": inserted, "skipped_existing": skipped,
                  "error_count": len(errs), "run_id": run_id, "result_hash": h,
                  "bucket_dist": bucket_dist, "position_version": POSITION_VERSION})

    # ---------- 3) 分层报告 ----------
    print("=== P1.3 Position Dual-Track 落库报告 ===")
    print(f"快照: {args.json} ({args.snapshot_date})  source_mode={args.source_mode}")
    print(f"持仓候选 op            : {stats['position_candidates']}")
    print(f"  A_SHARE (落库)       : {stats['a_share']}")
    print(f"  OUT_OF_SCOPE         : {stats['out_of_scope']}")
    print(f"  THEME                : {stats['theme']}")
    print(f"  MARKET               : {stats['market']}")
    print(f"  COMPOSITE            : {stats['composite']}")
    print(f"  UNRESOLVED           : {stats['unresolved']}")
    print(f"Inserted HOLDING       : {stats['inserted']}")
    print(f"Skipped existing       : {stats['skipped_existing']}")
    print(f"error_count            : {stats['error_count']}")
    print(f"ingest_runs run_id     : {stats['run_id']} (parser={PARSER_VERSION}, resolver={RESOLVER_VERSION})")
    print(f"result_hash            : {stats['result_hash'][:16]}")
    if errs:
        for e in errs[:10]:
            print("  ERR", e)
    print(f"bucket_dist            : {json.dumps(stats['bucket_dist'], ensure_ascii=False)}")
    return 0 if not errs else 1


def position_hash_of(con):
    """position_snapshots 全表确定性 hash（幂等重跑一致性 gate）。"""
    rows = con.execute(
        "SELECT analyst_id, snapshot_date, stock_code, raw_target, source_record_id,"
        " position_state, resolve_method FROM analyst_position_snapshots"
        " ORDER BY analyst_id, snapshot_date, source_record_id").fetchall()
    payload = "\n".join("|".join(str(x) for x in r) for r in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
