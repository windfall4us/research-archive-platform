#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_consensus_daily.py — 市场共识雷达「物化 + 发布」每日管道
====================================================================================
定位：把「Phase 1~4 产物新鲜 → build snapshot → 校验 → 上传双环境 → 生成/发布 HTML」
      封装成单个可复用命令，供 Hermes cron 每日调用。成功静默，失败退出码非 0（供 cron 告警）。

职责边界（用户锁定）：
  * 只做「物化 + 发布」，绝不修改 Phase 1~4 冻结算法/评分/状态规则
  * 前置审计：仅当最近一次 Phase 1~4 产物新鲜（mtime 在 --max-age-hours 内）才执行
  * 防重复发布：若 snapshot md5 与生产已上传一致 → 视为已是最新，跳过上传/HTML
  * 数据一致性：snapshot.meta.latest_date 必须 == all_dates 最新数据日（数据日≠运行日，Telegram 数据有滞后）
  * 幂等：同输入 → 同 snapshot md5

用法：
  python3 scripts/publish_consensus_daily.py                    # 完整执行
  python3 scripts/publish_consensus_daily.py --dry-run          # 只审计+build+校验，不上传/不发布
  python3 scripts/publish_consensus_daily.py --max-age-hours 48 # 放宽产物新鲜窗口
  python3 scripts/publish_consensus_daily.py --force            # 跳过 md5 防重复，强制发布

退出码：
  0  = 发布成功 / 静默跳过（前置不满足或已是最新），日志含 PUBLISH_OK / PUBLISH_SKIPPED
  1  = 发布失败（日志含 PUBLISH_FAILED + 原因）
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING_TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# ---- 双环境部署目标（生产副 VPS + 测试盒 fnOS）----
TARGETS = [
    {"name": "PROD", "host": "173.249.203.149", "user": "root", "key": "/home/windfall/.ssh/id_ed25519",
     "path": "/opt/watchlist-stock-analysis/data/consensus/consensus_daily_snapshot.json"},
    {"name": "TEST", "host": "192.168.50.22", "user": "admin", "password": "Qinghai123",
     "path": "/opt/watchlist-stock-analysis/data/consensus/consensus_daily_snapshot.json"},
]

# Phase 1~4 输入产物（血缘审计）
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

SNAPSHOT_REL = "data/consensus/consensus_daily_snapshot.json"
HTML_OUT_DIR = ROOT / "reports/consensus"
# reports.wmsora.vip 站点根（副 VPS python http.server :8080，根=/root/vip1_reports）
REPORTS_ROOT = "/root/vip1_reports/consensus"


def log(msg: str):
    print(f"[{datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def md5_file(p: Path) -> str:
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get_latest_data_day() -> str | None:
    """从 all_dates.json 取最新数据日（days 为 dict，key=日期）。"""
    try:
        ad = json.loads((ROOT / "reports/market_consensus/all_dates.json").read_text(encoding="utf-8"))
        days = ad.get("days", {})
        if isinstance(days, dict) and days:
            return sorted(days.keys())[-1]
    except Exception:
        pass
    return None


def audit_fresh(max_age_hours: int) -> tuple[bool, list[str]]:
    """前置审计：10 个 Phase1~4 产物 mtime 在 max_age_hours 内。"""
    issues = []
    now = datetime.now(BEIJING_TZ)
    for rel in INPUT_FILES:
        p = ROOT / rel
        if not p.exists():
            issues.append(f"缺失: {rel}")
            continue
        mt = datetime.fromtimestamp(p.stat().st_mtime).astimezone(BEIJING_TZ)
        age_h = (now - mt).total_seconds() / 3600
        if age_h > max_age_hours:
            issues.append(f"产物过旧({age_h:.1f}h > {max_age_hours}h): {rel}")
    return (not issues), issues


def run(script: str, *args: str) -> tuple[int, str]:
    cmd = [sys.executable, str(SCRIPTS / script)] + list(args)
    log(f"  ↳ 执行: {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=1200)
        return r.returncode, (r.stdout + r.stderr)[-3000:]
    except subprocess.TimeoutExpired:
        return 1, "TIMEOUT"


def validate_snapshot() -> tuple[bool, list[str]]:
    """校验 snapshot：schema 字段 + 数据一致性（latest_date == all_dates 最新数据日）。"""
    errs = []
    snap_path = ROOT / SNAPSHOT_REL
    if not snap_path.exists():
        errs.append("snapshot 未生成")
        return False, errs
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    for key in ["meta", "overview", "themes", "stocks", "divergence", "analysts"]:
        if key not in snap:
            errs.append(f"缺少 key: {key}")
    snap_date = snap.get("meta", {}).get("latest_date")
    latest_data = get_latest_data_day()
    if snap_date and latest_data and snap_date != latest_data:
        errs.append(f"数据不一致: snapshot.latest_date={snap_date} ≠ all_dates 最新={latest_data}")
    return (not errs), errs


def remote_md5(target: dict) -> str | None:
    """读取远端已上传 snapshot 的 md5（不存在返回 None）。"""
    import paramiko
    try:
        s = paramiko.SSHClient()
        s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if "password" in target:
            s.connect(target["host"], 22, target["user"], password=target["password"],
                      timeout=40, banner_timeout=30, auth_timeout=30)
        else:
            s.connect(target["host"], 22, target["user"], key_filename=target["key"],
                      timeout=40, look_for_keys=False, allow_agent=False,
                      banner_timeout=30, auth_timeout=30)
        sftp = s.open_sftp()
        f = sftp.open(target["path"], "rb")
        data = f.read(); f.close(); sftp.close(); s.close()
        return hashlib.md5(data).hexdigest()
    except Exception:
        return None


def upload(target: dict, local: Path) -> bool:
    import paramiko
    try:
        s = paramiko.SSHClient()
        s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if "password" in target:
            s.connect(target["host"], 22, target["user"], password=target["password"],
                      timeout=40, banner_timeout=30, auth_timeout=30)
        else:
            s.connect(target["host"], 22, target["user"], key_filename=target["key"],
                      timeout=40, look_for_keys=False, allow_agent=False,
                      banner_timeout=30, auth_timeout=30)
        s.exec_command(f"mkdir -p {Path(target['path']).parent}")
        import time; time.sleep(0.5)
        sftp = s.open_sftp()
        sftp.put(str(local), target["path"])
        rsize = sftp.stat(target["path"]).st_size
        sftp.close(); s.close()
        return rsize == local.stat().st_size
    except Exception as e:
        log(f"  ❌ 上传失败 {target['name']}: {e}")
        return False


def publish_html(date: str, local_html: Path) -> bool:
    import paramiko
    try:
        s = paramiko.SSHClient()
        s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        s.connect("173.249.203.149", 22, "root", key_filename="/home/windfall/.ssh/id_ed25519",
                  timeout=40, look_for_keys=False, allow_agent=False, banner_timeout=30, auth_timeout=30)
        s.exec_command(f"mkdir -p {REPORTS_ROOT}")
        import time; time.sleep(0.5)
        sftp = s.open_sftp()
        for name in [f"{date}.html", "latest.html"]:
            sftp.put(str(local_html), f"{REPORTS_ROOT}/{name}")
        sftp.close(); s.close()
        return True
    except Exception as e:
        log(f"  ❌ HTML 发布失败: {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只审计+build+校验，不上传/不发布")
    ap.add_argument("--max-age-hours", type=float, default=36.0, help="产物新鲜窗口（小时）")
    ap.add_argument("--force", action="store_true", help="跳过 md5 防重复，强制上传/发布")
    args = ap.parse_args()

    log(f"市场共识雷达发布管道 · 最大产物新鲜窗口={args.max_age_hours}h")

    # 1) 前置审计：Phase 1~4 产物新鲜
    ok, issues = audit_fresh(args.max_age_hours)
    if not ok:
        log("PUBLISH_SKIPPED 前置审计不满足（Phase 1~4 当日全链路未完成）:")
        for it in issues:
            log(f"  - {it}")
        sys.exit(0)
    log("✅ 前置审计通过：Phase 1~4 产物全部新鲜")

    # 2) build snapshot（幂等）
    snap_path = ROOT / SNAPSHOT_REL
    before = md5_file(snap_path) if snap_path.exists() else None
    rc, out = run("build_consensus_snapshot.py")
    if rc != 0:
        log(f"PUBLISH_FAILED build_consensus_snapshot 失败:\n{out}")
        sys.exit(1)
    after = md5_file(snap_path)
    log(f"✅ snapshot 生成: md5={after[:12]} (before={before[:12] if before else 'N/A'})")

    # 3) 校验
    vok, errs = validate_snapshot()
    if not vok:
        log("PUBLISH_FAILED snapshot 校验失败:\n" + "\n".join(f"  - {e}" for e in errs))
        sys.exit(1)
    latest_data = get_latest_data_day()
    log(f"✅ snapshot 校验通过（schema + latest_date={latest_data}）")

    if args.dry_run:
        log("PUBLISH_OK (dry-run，未上传/未发布)")
        sys.exit(0)

    # 4) 防重复发布：与生产已上传 md5 对比
    if not args.force:
        prod_md5 = remote_md5(TARGETS[0])
        if prod_md5 and prod_md5 == after:
            log(f"PUBLISH_SKIPPED 生产已是该版本 (md5={after[:12]})，无需重复发布")
            sys.exit(0)

    # 5) 上传双环境
    for t in TARGETS:
        if upload(t, snap_path):
            log(f"✅ 已上传 {t['name']} ({t['host']})")
        else:
            log(f"PUBLISH_FAILED 上传失败 {t['name']}")
            sys.exit(1)

    # 6) 生成并发布 HTML
    date = latest_data or datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
    HTML_OUT_DIR.mkdir(parents=True, exist_ok=True)
    rc, out = run("render_consensus_snapshot_html.py", str(snap_path), str(HTML_OUT_DIR / f"{date}.html"))
    if rc != 0:
        log(f"PUBLISH_FAILED render HTML 失败:\n{out}")
        sys.exit(1)
    local_html = HTML_OUT_DIR / f"{date}.html"
    if not local_html.exists():
        log("PUBLISH_FAILED HTML 未生成")
        sys.exit(1)
    if publish_html(date, local_html):
        log(f"✅ HTML 已发布 reports.wmsora.vip/consensus/{date}.html + latest.html")
    else:
        log("PUBLISH_FAILED HTML 发布失败")
        sys.exit(1)

    log("PUBLISH_OK 全链路完成")
    sys.exit(0)


if __name__ == "__main__":
    main()
