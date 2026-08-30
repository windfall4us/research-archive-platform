#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_consensus_pipeline.py — 市场共识雷达 Phase 1~4 自动化总控
====================================================================================
定位：把「Phase 1~4 自动运行 → 全链路 GO → 才调用发布器」封装成单个可复用命令。
      原手动链路「手动跑 Phase1~4 → publish_consensus_daily.py 自动发布」升级为全自动。

编排结构（用户锁定 2026-08-30）：
  run_consensus_pipeline.py
  ├─ [Phase 0] 前置审计：timeline 快照 + 输入产物存在且新鲜
  ├─ [Phase 1] Data Layer      — create schema → 3 ingest → acceptance → benchmark_phase1_p15
  ├─ [Phase 2] Market+Theme    — benchmark_phase2_p24（内嵌重算 p20b→p21→p22a→p22b→p22c→p23）
  ├─ [Phase 3] Stock Consensus — benchmark_phase3_p34（内嵌重算 p31→p32→p33）
  ├─ [Phase 4] Cross-Layer     — benchmark_phase4_p44（内嵌重算 p41→p42→p43）
  ├─ [Overall Gate] 4 个 benchmark 全 GO
  └─ [Publish]     publish_consensus_daily.py（仅 overall GO 时调用）

核心原则（用户锁定）：
  1. 任一 Phase NO-GO → 停止，不发布（不调用 publish）
  2. 旧 snapshot 保持在线，不覆盖
  3. 全部 GO → 才调用 publisher
  4. 每阶段保留独立日志与耗时
  5. 同一交易日重复运行幂等
  6. 成功静默
  7. 失败 Telegram 告警
  8. 不因为单个展示层问题回改冻结算法

用法：
  python3 scripts/run_consensus_pipeline.py                 # 默认：全链路 + publish
  python3 scripts/run_consensus_pipeline.py --alert         # 补偿检测：产物/目标日未就绪也告警（23:20 用）
  python3 scripts/run_consensus_pipeline.py --target-date 2026-08-29  # 指定目标交易日（默认=北京今天）
  python3 scripts/run_consensus_pipeline.py --force                    # 透传 publish：强制发布（跳过 md5 防重复）
  python3 scripts/run_consensus_pipeline.py --dry-run       # 只跑 Phase1~4 + 各 benchmark，不 publish
  python3 scripts/run_consensus_pipeline.py --no-publish    # 同 dry-run（别名）
  python3 scripts/run_consensus_pipeline.py --no-telegram   # 禁用 Telegram 告警（仅日志）
  python3 scripts/run_consensus_pipeline.py --max-age-hours 48   # 放宽输入产物新鲜窗口

并发保护（用户锁定 2026-08-30）：
  * 同日锁：logs/consensus_pipeline/run.lock (fcntl flock) — 22:50 未结束时 23:20 撞锁直接静默退出，不并发
  * run_id：YYYYMMDD-HHMMSS，写入当日日志头部 + 耗时报告
  * 目标交易日校验：--target-date 日期的 timeline 快照必须已归档（vip0_timeline_<date>.json），
    否则视为「今日源头数据未就绪」→ exit 2（不带 --alert 静默 / 带 --alert 告警），
    绝不拿旧日完整产物通过 Gate 后误发布；旧 snapshot 保持在线不覆盖

退出码：
  0 = 全链路 GO（已 publish）/ dry-run 通过 / 撞锁静默跳过
  1 = 失败（已告警）
  2 = 产物未就绪 / 目标交易日数据未就绪（不带 --alert 时静默，主检测；带 --alert 时已告警）
"""

import argparse
import fcntl
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING_TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
LOGS_DIR = ROOT / "logs"
REPORTS_DIR = ROOT / "reports"

# Phase 1~4 各阶段 benchmark 脚本（内嵌重算主脚本 + 验证；exit 0 = GO）
PHASES = [
    {"phase": 1, "name": "Data Layer",        "benchmark": "benchmark_phase1_p15.py"},
    {"phase": 2, "name": "Market+Theme",      "benchmark": "benchmark_phase2_p24.py"},
    {"phase": 3, "name": "Stock Consensus",   "benchmark": "benchmark_phase3_p34.py"},
    {"phase": 4, "name": "Cross-Layer",       "benchmark": "benchmark_phase4_p44.py"},
]

# Phase 3 前置重算（总控显式跑，使 p3x 输出进入稳定态后再跑 benchmark_phase3 的幂等采样）：
#   benchmark_phase3 的 G8 要求「重跑后 hash == 阶段0 基线」，与 Phase 2/4 同理：
#   新数据首次进入时须先跑到稳定态，baseline 采样才捕获全量，否则 G8 误报 NO-GO。
PHASE3_INGEST = [
    "stock_consensus_factors_p31.py",
    "analyst_action_flow_p32.py",
    "stock_consensus_score_p33.py",
]

# Phase 4 前置重算（总控显式跑，使 p4x 输出进入稳定态后再跑 benchmark_phase4 的幂等采样）：
#   benchmark_phase4 的 G1 要求「重跑后 hash == 阶段0 基线」，若 p4x 尚未处理新一天数据
#   （如 2026-08-29 首次进入），阶段0 采样旧输出、重跑后新输出 → G1 误报 NO-GO。
#   总控先跑到稳定态，baseline 采样即捕获全量。
PHASE4_INGEST = [
    "cross_layer_readiness_p40.py",
    "stock_theme_linkage_p41.py",
    "consensus_divergence_p42.py",
    "cross_layer_state_p43.py",
]

# Phase 2 前置 ingest（总控显式跑，使 DB 进入稳定态后再跑 benchmark_phase2 的幂等采样）：
#   - market_view_ingest_p20b: 把 Phase1 新增 daily_views(core_theme) 生成 market 视图行
#   - theme_mention_extract_v1 --fill: 从 core_theme 提取 DIRECT theme mentions（必须 --fill 才写库）
#   - market_direction_p21: 按日聚合 market direction → all_dates.json（须在 G11 base 采样前含新日）
# 说明：benchmark_phase2 内部也会重跑这些脚本，但它的 G10/G11 幂等采样要求
#       「所有脚本已在 base 采样前处理完新数据」——否则新数据首次进入时
#       G10(行数变化)/G11(hash变化) 会误报 NO-GO。总控先跑到稳定态，base 采样即捕获全量。
PHASE2_INGEST = [
    ("market_view_ingest_p20b.py", []),
    ("theme_mention_extract_v1.py", ["--fill"]),
    ("market_direction_p21.py", []),
]

# Phase 1 前置：建 schema + 3 ingest（首次 ingest 最新快照 = 每日新增）。
# 注：不含 acceptance_p14 —— 它是 P1.4 开发期验收（期望最近一次 revision 重跑 inserted=0），
#     会因首次 ingest 新一天快照（合法新增>0）误报；Phase 1 准入判定由
#     benchmark_phase1_p15 承担（内部重跑 3 ingest 验证幂等 + G1-G7 全 gate）。
PHASE1_SETUP = [
    "create_consensus_schema_p1.py",
    "ingest_consensus_p12.py",
    "ingest_position_p13.py",
    "ingest_revision_p14.py",
]

# timeline 快照目录（Phase 1 ingest 输入）
SNAPSHOT_DIR = ROOT / "data" / "analyst_snapshots"

# 本地交易日历（用户 2026-08-30 锁定：非交易日 → NON_TRADING_DAY → silent exit 0，不制造假告警）
CALENDAR_DIR = ROOT / "data" / "calendar"


def is_trading_day(date_str: str) -> bool:
    """判断目标日是否为 A 股交易日。

    优先读本地日历 data/calendar/trading_days_<year>.json（chinese_calendar 生成，
    含国务院调休，离线确定性）；无该年日历 → 回退周一~五工作日判断（节假日可能误判但保守可容忍）。
    """
    try:
        year = date_str[:4]
        cal = json.loads((CALENDAR_DIR / f"trading_days_{year}.json").read_text(encoding="utf-8"))
        return date_str in set(cal.get("trading_days", []))
    except Exception:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.weekday() < 5

# Phase 1~4 输入产物（与 publish 一致；血缘审计用）
INPUT_FILES = [
    "reports/market_consensus/all_dates.json",
    "data/p22b/theme_daily_factors.json",
    "data/p22c/theme_heat_scores.json",
    "data/p23/theme_momentum.json",
    "data/p31/stock_consensus_factors.json",
    "data/p32/analyst_action_flow.json",
    "data/p33/stock_consensus_score.json",
    "data/p41/stock_theme_linkage.json",
    "data/p42/consensus_divergence.json",
    "data/p43/cross_layer_state.json",
]


def now() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    print(f"[{now()}] {msg}", flush=True)


# ---- 日志：全量日志 + 阶段耗时 ----
LOGFILE: Path | None = None
RUNTIME: dict = {}
RUN_ID: str = ""
LOCK_FILE: object | None = None
PIPELINE_LOG_DIR = LOGS_DIR / "consensus_pipeline"


def acquire_lock() -> bool:
    """同日锁（fcntl flock）：同一时刻只允许一个总控实例。

    22:50 主任务尚未结束时 23:20 补偿任务撞锁 → 返回 False，调用方静默退出（不并发、不抢发布）。
    """
    global LOCK_FILE
    try:
        PIPELINE_LOG_DIR.mkdir(parents=True, exist_ok=True)
        _lf = open(PIPELINE_LOG_DIR / "run.lock", "w")
        fcntl.flock(_lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        LOCK_FILE = _lf
        return True
    except OSError:
        return False


def init_logs(date_str: str):
    global LOGFILE, RUN_ID
    RUN_ID = datetime.now(BEIJING_TZ).strftime("%Y%m%d-%H%M%S")
    PIPELINE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOGFILE = PIPELINE_LOG_DIR / f"{date_str}.log"
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*70}\n[{now()}] === run_consensus_pipeline 启动 (run_id={RUN_ID}) ===\n")


def tee(msg: str):
    log(msg)
    if LOGFILE:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(f"[{now()}] {msg}\n")


def run(script: str, *args: str, timeout: int = 1800) -> tuple[int, str]:
    """执行 scripts/ 下脚本，返回 (exit_code, 尾部输出)。"""
    cmd = [sys.executable, str(SCRIPTS / script)] + list(args)
    tee(f"  ↳ 执行: {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=timeout)
        out = (r.stdout + r.stderr)[-3000:]
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return 1, f"TIMEOUT ({timeout}s)"


# ---- 告警（复用 publish_consensus_daily 的 send_telegram_alert）----
def send_telegram_alert(stage: str, detail: str, exit_code: int):
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "publish_consensus_daily", SCRIPTS / "publish_consensus_daily.py")
        if spec and spec.loader:   # spec_from_file_location 恒真，防御性检查
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)   # 顶层无副作用（main 在 if __name__ 内）
            mod.send_telegram_alert(stage, detail, exit_code)
    except Exception as e:
        tee(f"❌ 告警模块加载失败: {e}")


# ---- 前置审计 ----
def discover_timeline_snapshots() -> tuple[Path | None, Path | None]:
    """自动发现最新 timeline 快照及其前一日快照（ingest 输入）。

    返回 (latest, previous)：latest 为日期最大者，previous 为次大者。
    无快照 → (None, None)。
    """
    snaps = sorted(
        [p for p in SNAPSHOT_DIR.glob("vip0_timeline_*.json") if "summary" not in p.name],
        key=lambda p: p.name)
    if not snaps:
        return None, None
    latest = snaps[-1]
    prev = snaps[-2] if len(snaps) >= 2 else None
    return latest, prev


def write_runtime_report(date_str: str, overall: str, publish_rc: int | None = None):
    """每次自动运行生成 reports/runtime/consensus_pipeline_<date>.{json,md}。

    记录当日 eligible_market_views / events / positions / themes / fingerprint / Overall。
    用户 2026-08-30 锁定三层分离：冻结基线(phase2/3/4_benchmark*/freeze_record) immutable；
    本文件为 Rolling Runtime Expectation，每天按目标交易日数据动态记录。
    """
    RUNTIME_DIR = REPORTS_DIR / "runtime"
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = ROOT / "data" / "consensus" / "consensus_daily_snapshot.json"
    meta = {}
    try:
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        meta = snap.get("meta", {})
    except Exception:
        pass
    # eligible_market_views：直接从 DB 按口径关系算（market 行 - UNKNOWN）
    eligible_market_views = None
    try:
        import sqlite3
        con = sqlite3.connect(ROOT / "data" / "analyst_consensus.db")
        mv_total = con.execute("SELECT COUNT(*) FROM analyst_daily_views WHERE view_type='market'").fetchone()[0]
        mv_unknown = con.execute(
            "SELECT COUNT(*) FROM analyst_daily_views WHERE view_type='market' AND market_direction='UNKNOWN'").fetchone()[0]
        con.close()
        eligible_market_views = mv_total - mv_unknown
    except Exception:
        pass
    # snapshot 内容指纹（排除 generated_at，与 publish 防重复同口径）
    fingerprint = None
    try:
        import hashlib
        obj = json.loads(snap_path.read_text(encoding="utf-8"))
        obj.get("meta", {}).pop("generated_at", None)
        fingerprint = hashlib.md5(
            json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    except Exception:
        pass
    rec = {
        "date": date_str, "run_id": RUN_ID, "overall": overall, "publish_rc": publish_rc,
        "eligible_market_views": eligible_market_views,
        "events": meta.get("n_stock_events"),
        "positions": meta.get("n_positions"),
        "themes": meta.get("n_themes"),
        "theme_mentions": meta.get("n_theme_mentions"),
        "latest_date": meta.get("latest_date"),
        "fingerprint": fingerprint,
        "runtime_s": RUNTIME,
    }
    (RUNTIME_DIR / f"consensus_pipeline_{date_str}.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 市场共识雷达 · 运行时报告",
        "",
        f"**date**: {date_str} | **run_id**: {RUN_ID} | **Overall**: `{overall}`"
        + (f" | publish_rc: {publish_rc}" if publish_rc is not None else ""),
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| eligible_market_views | {eligible_market_views} |",
        f"| events (stock events) | {meta.get('n_stock_events')} |",
        f"| positions | {meta.get('n_positions')} |",
        f"| themes | {meta.get('n_themes')} |",
        f"| theme_mentions | {meta.get('n_theme_mentions')} |",
        f"| latest_date | {meta.get('latest_date')} |",
        f"| fingerprint (内容指纹, 排除 generated_at) | `{fingerprint}` |",
        f"| 阶段耗时 | {json.dumps(RUNTIME, ensure_ascii=False)} |",
        "",
        "> 冻结基线（phase2/3/4_benchmark*/freeze_record）保持 immutable；本文件为 Rolling Runtime Expectation。",
    ]
    (RUNTIME_DIR / f"consensus_pipeline_{date_str}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    tee(f"📊 运行时报告 → reports/runtime/consensus_pipeline_{date_str}.json + .md (Overall={overall})")


def snapshot_date(p: Path) -> str:
    """从 vip0_timeline_YYYYMMDD.json 提取日期 YYYY-MM-DD。"""
    import re
    m = re.search(r"(\d{4})(\d{2})(\d{2})", p.name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def audit_inputs(max_age_hours: float) -> tuple[bool, list[str]]:
    """Phase1~4 输入产物新鲜检查（同 publish 口径）。"""
    issues = []
    now_t = datetime.now(BEIJING_TZ)
    for rel in INPUT_FILES:
        p = ROOT / rel
        if not p.exists():
            issues.append(f"缺失: {rel}")
            continue
        mt = datetime.fromtimestamp(p.stat().st_mtime).astimezone(BEIJING_TZ)
        age_h = (now_t - mt).total_seconds() / 3600
        if age_h > max_age_hours:
            issues.append(f"产物过旧({age_h:.1f}h > {max_age_hours}h): {rel}")
    return (not issues), issues


# ---- 各阶段执行 ----
def run_phase(p: dict, args) -> bool:
    """执行一个 Phase：先跑 pipeline（Phase1 特殊）+ benchmark。返回 True=GO。"""
    ph = p["phase"]
    name = p["name"]
    tee(f"\n── [Phase {ph}] {name} ──")
    t0 = time.time()

    # Phase 1：显式跑前置 setup（schema + 3 ingest + acceptance）
    if ph == 1:
        latest, prev = discover_timeline_snapshots()
        if not latest:
            tee("❌ 无 timeline 快照（data/analyst_snapshots/vip0_timeline_*.json）")
            send_telegram_alert("Phase1 setup fail", "无 timeline 快照", 1)
            return False
        latest_date = snapshot_date(latest)
        tee(f"📥 Phase 1 ingest 输入: {latest.name} ({latest_date})"
            + (f" · before={prev.name}" if prev else " · 无前一日快照(revision 跳过)"))
        for sc in PHASE1_SETUP:
            extra_args: list[str] = []
            if sc == "ingest_consensus_p12.py":
                extra_args = ["--json", str(latest), "--snapshot-date", latest_date]
            elif sc == "ingest_position_p13.py":
                extra_args = ["--source-mode", "hold"]
            elif sc == "ingest_revision_p14.py":
                if not prev:
                    tee("⚠️ 无前一日快照，跳过 ingest_revision（首日运行）")
                    continue
                extra_args = ["--before", str(prev), "--after", str(latest)]
            rc, out = run(sc, *extra_args, timeout=1800)
            if rc != 0:
                tee(f"❌ [Phase 1] {sc} 失败 (exit {rc}):\n{out}")
                RUNTIME[f"p{ph}_setup"] = round(time.time() - t0, 1)
                send_telegram_alert(f"Phase{ph} setup fail", f"{sc}:\n{out}", 1)
                return False

    # Phase 2：先跑前置 ingest（p20b + p20c --fill + p21），使 DB 进入稳定态
    #   （benchmark_phase2 的 G10/G11 幂等采样要求新数据在 base 采样前已处理完）
    if ph == 2:
        for sc, extra in PHASE2_INGEST:
            rc, out = run(sc, *extra, timeout=900)
            if rc != 0:
                tee(f"❌ [Phase 2] 前置 ingest {sc} 失败 (exit {rc}):\n{out}")
                RUNTIME[f"p{ph}_ingest"] = round(time.time() - t0, 1)
                send_telegram_alert(f"Phase{ph} ingest fail", f"{sc}:\n{out}", 1)
                return False
        tee("✅ [Phase 2] 前置 ingest 完成（p20b market 视图 + p20c theme mentions --fill + p21 direction）")

    # Phase 3：先跑前置重算（p31→p33），使 p3x 输出进入稳定态
    if ph == 3:
        for sc in PHASE3_INGEST:
            rc, out = run(sc, timeout=900)
            if rc != 0:
                tee(f"❌ [Phase 3] 前置重算 {sc} 失败 (exit {rc}):\n{out}")
                RUNTIME[f"p{ph}_ingest"] = round(time.time() - t0, 1)
                send_telegram_alert(f"Phase{ph} ingest fail", f"{sc}:\n{out}", 1)
                return False
        tee("✅ [Phase 3] 前置重算完成（p31 factors + p32 action flow + p33 score）")

    # Phase 4：先跑前置重算（p40→p43），使 p4x 输出进入稳定态
    #   （benchmark_phase4 的 G1 幂等采样要求新数据在 baseline 采样前已处理完）
    if ph == 4:
        for sc in PHASE4_INGEST:
            rc, out = run(sc, timeout=900)
            if rc != 0:
                tee(f"❌ [Phase 4] 前置重算 {sc} 失败 (exit {rc}):\n{out}")
                RUNTIME[f"p{ph}_ingest"] = round(time.time() - t0, 1)
                send_telegram_alert(f"Phase{ph} ingest fail", f"{sc}:\n{out}", 1)
                return False
        tee("✅ [Phase 4] 前置重算完成（p40 readiness + p41 linkage + p42 divergence + p43 state）")

    # 跑该阶段 benchmark（内嵌重算主脚本 + 验证）
    rc, out = run(p["benchmark"], timeout=1800)
    dt = round(time.time() - t0, 1)
    RUNTIME[f"p{ph}_benchmark"] = dt
    tee(f"[Phase {ph}] benchmark 耗时 {dt}s, exit={rc}")
    if rc == 0:
        tee(f"✅ [Phase {ph}] {name} GO")
        return True
    tee(f"❌ [Phase {ph}] {name} NO-GO (exit {rc}):\n{out}")
    send_telegram_alert(f"Phase{ph} NO-GO", f"{p['benchmark']} exit={rc}:\n{out[-800:]}", 1)
    return False


def main():
    ap = argparse.ArgumentParser(description="市场共识雷达 Phase 1~4 自动化总控")
    ap.add_argument("--dry-run", action="store_true", help="只跑 Phase1~4 + 各 benchmark，不 publish")
    ap.add_argument("--no-publish", action="store_true", help="同 --dry-run（别名）")
    ap.add_argument("--no-telegram", action="store_true", help="禁用 Telegram 告警（仅日志）")
    ap.add_argument("--alert", action="store_true", help="补偿检测模式：产物/目标日未就绪也告警（23:20 用）")
    ap.add_argument("--target-date", default=datetime.now(BEIJING_TZ).strftime("%Y-%m-%d"),
                    help="目标交易日 YYYY-MM-DD（默认=北京今天；该日 timeline 快照必须已归档）")
    ap.add_argument("--force", action="store_true", help="透传 publish：跳过 md5 防重复，强制上传/发布")
    ap.add_argument("--max-age-hours", type=float, default=36.0, help="输入产物新鲜窗口（小时）")
    args = ap.parse_args()

    do_publish = not (args.dry_run or args.no_publish)
    date_str = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
    init_logs(date_str)
    tee(f"run_consensus_pipeline 启动 (run_id={RUN_ID}) · "
        f"publish={'YES' if do_publish else 'NO(dry-run)'} · "
        f"target_date={args.target_date} · 新鲜窗口={args.max_age_hours}h"
        + (" · 补偿检测(告警)" if args.alert else " · 主检测(静默)"))

    # 同日锁：撞锁 → 静默跳过（22:50 未结束时 23:20 不并发）
    if not acquire_lock():
        tee("PIPELINE_SKIPPED 另一总控实例运行中（同日锁），静默跳过")
        sys.exit(0)

    # 0a) 交易日判断：非交易日 → NON_TRADING_DAY → silent exit 0（不发布、不告警）
    #    用户 2026-08-30 锁定：真正该报警的是「应有数据的交易日到 23:20 仍未就绪」，
    #    周末/非交易日不制造假告警。日历: data/calendar/trading_days_<year>.json。
    if not is_trading_day(args.target_date):
        tee(f"NON_TRADING_DAY {args.target_date} 非交易日，静默跳过（不发布、不告警）")
        sys.exit(0)

    # 0) 前置审计：Phase1~4 输入产物新鲜
    ok, issues = audit_inputs(args.max_age_hours)
    if not ok:
        tee("前置审计不满足（Phase1~4 输入产物未就绪）:")
        for it in issues:
            tee(f"  - {it}")
        if args.alert and not args.no_telegram:
            send_telegram_alert("前置条件未满足", "; ".join(issues), 2)
        tee("PIPELINE_SKIPPED 产物未就绪" + ("（已告警）" if args.alert else "（静默，等待补偿检测）"))
        sys.exit(2)

    # 0b) 目标交易日校验：目标日 timeline 快照必须已归档 + 最新快照日期与目标对齐。
    #   防止「今日源头数据未归档，却拿旧日完整产物通过 Gate 误发布」。
    target_snap = SNAPSHOT_DIR / f"vip0_timeline_{args.target_date.replace('-', '')}.json"
    if not target_snap.exists():
        tee(f"目标交易日 {args.target_date} 快照未归档: {target_snap.name}")
        tee("→ 不运行 Phase1~4（今日源头数据未就绪），旧 snapshot 保持在线不覆盖")
        if args.alert and not args.no_telegram:
            send_telegram_alert("目标交易日数据未就绪",
                                f"{args.target_date} 快照未归档: {target_snap.name}", 2)
        tee("PIPELINE_SKIPPED 目标数据未就绪" + ("（已告警）" if args.alert else "（静默，等待补偿检测）"))
        sys.exit(2)
    latest, _prev = discover_timeline_snapshots()
    if latest and snapshot_date(latest) != args.target_date:
        tee(f"❌ 最新快照日期 {snapshot_date(latest)} ≠ 目标交易日 {args.target_date}（数据未对齐）")
        if args.alert and not args.no_telegram:
            send_telegram_alert("目标交易日数据未对齐",
                                f"latest={snapshot_date(latest)} vs target={args.target_date}", 2)
        sys.exit(2)
    tee(f"✅ 目标交易日 {args.target_date} 快照就绪（{target_snap.name}），数据对齐")

    # 1~4) 各阶段
    all_go = True
    for p in PHASES:
        if not run_phase(p, args):
            all_go = False
            break  # 任一 NO-GO → 停止，不发布

    # 写阶段耗时报告
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / f"consensus_pipeline_runtime_{date_str}.json").write_text(
            json.dumps({"date": date_str, "run_id": RUN_ID, "runtime_s": RUNTIME,
                        "overall": "GO" if all_go else "NO-GO"},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        tee(f"⚠️ 耗时报告写入失败: {e}")

    if not all_go:
        write_runtime_report(date_str, "NO-GO")
        tee("❌ Overall NO-GO：任一 Phase 未通过，不发布（旧 snapshot 保持在线）")
        sys.exit(1)

    # Overall Gate
    tee("\n✅ Overall GO：4 个 Phase benchmark 全部通过")
    if not do_publish:
        write_runtime_report(date_str, "GO")
        tee("dry-run 模式：不调用 publish（Phase1~4 已重算完成）")
        sys.exit(0)

    # 调用发布器（--force 透传：强制跳过 md5 防重复）
    tee("→ 调用 publish_consensus_daily.py 发布" + ("（--force 强制）" if args.force else ""))
    pub_args = ["--force"] if args.force else []
    rc, out = run("publish_consensus_daily.py", *pub_args, timeout=1800)
    if rc != 0:
        write_runtime_report(date_str, "GO", publish_rc=rc)
        tee(f"❌ publish 失败 (exit {rc}):\n{out}")
        # publish 已自带告警；这里补充阶段上下文
        sys.exit(1)
    write_runtime_report(date_str, "GO", publish_rc=rc)
    tee("✅ 全链路完成：Phase1~4 GO + publish OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
