#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_consensus_daily.py — 市场共识雷达「物化 + 发布」每日管道
====================================================================================
定位：把「Phase 1~4 产物新鲜 → build snapshot → 校验 → 上传双环境 → 生成/发布 HTML」
      封装成单个可复用命令，供 Hermes cron 每日调用。成功静默，失败 Telegram 告警。

职责边界（用户锁定）：
  * 只做「物化 + 发布」，绝不修改 Phase 1~4 冻结算法/评分/状态规则
  * 前置审计：仅当最近一次 Phase 1~4 产物新鲜（mtime 在 --max-age-hours 内）才执行
  * 防重复发布：若 snapshot md5 与生产已上传一致 → 视为已是最新，跳过上传/HTML（静默）
  * 数据一致性：snapshot.meta.latest_date 必须 == all_dates 最新数据日（数据日≠运行日）
  * 幂等：同输入 → 同 snapshot md5

两级告警（用户锁定）：
  * 不带 --alert：产物未就绪 → 静默跳过（22:50 主检测）
  * 带 --alert：产物未就绪 / 任何失败 → Telegram 告警（23:20 补偿检测）
  * 防重复发布始终静默（两次检测不会重复覆盖）

用法：
  python3 scripts/publish_consensus_daily.py                    # 22:50 主检测（产物未就绪静默）
  python3 scripts/publish_consensus_daily.py --alert            # 23:20 补偿检测（未就绪/失败告警）
  python3 scripts/publish_consensus_daily.py --dry-run          # 只审计+build+校验，不上传/不发布
  python3 scripts/publish_consensus_daily.py --max-age-hours 48 # 放宽产物新鲜窗口
  python3 scripts/publish_consensus_daily.py --force            # 跳过 md5 防重复，强制发布

退出码：
  0  = 发布成功 / 静默跳过（含防重复）
  1  = 发布失败（告警）
  2  = 产物未就绪（不带 --alert 时静默；带 --alert 时已告警）
"""

import argparse
import hashlib
import json
import os
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
     "path": "/opt/watchlist-stock-analysis/data/consensus/consensus_daily_snapshot.json",
     "api": "http://127.0.0.1:3100/api/consensus/status"},
    {"name": "TEST", "host": "192.168.50.22", "user": "admin", "password": "Qinghai123",
     "path": "/opt/watchlist-stock-analysis/data/consensus/consensus_daily_snapshot.json",
     "api": "http://127.0.0.1:3100/api/consensus/status"},
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
# Telegram 告警（~/.hermes/.env）
ENV_PATH = Path.home() / ".hermes" / ".env"

FAIL_STAGES: list[str] = []   # 失败阶段收集（用于告警摘要）
LAST_ISSUES: list[str] = []   # 前置审计问题


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


def latest_input_mtime() -> str:
    """Phase1~4 最新产物 mtime（告警字段）。"""
    try:
        ts = max(Path(ROOT / rel).stat().st_mtime for rel in INPUT_FILES if (ROOT / rel).exists())
        return datetime.fromtimestamp(ts).astimezone(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "N/A"


def audit_fresh(max_age_hours: float) -> tuple[bool, list[str]]:
    """前置审计：10 个 Phase1~4 产物 mtime 在 max_age_hours 内。"""
    global LAST_ISSUES
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
    LAST_ISSUES = issues
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


# ---------------- 远端操作 ----------------

def _connect(target: dict):
    import paramiko
    s = paramiko.SSHClient()
    s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if "password" in target:
        s.connect(target["host"], 22, target["user"], password=target["password"],
                  timeout=40, banner_timeout=30, auth_timeout=30)
    else:
        s.connect(target["host"], 22, target["user"], key_filename=target["key"],
                  timeout=40, look_for_keys=False, allow_agent=False,
                  banner_timeout=30, auth_timeout=30)
    return s


def remote_md5(target: dict) -> str | None:
    """读取远端已上传 snapshot 的 md5（不存在返回 None）。"""
    try:
        s = _connect(target)
        sftp = s.open_sftp()
        f = sftp.open(target["path"], "rb")
        data = f.read(); f.close(); sftp.close(); s.close()
        return hashlib.md5(data).hexdigest()
    except Exception:
        return None


def upload(target: dict, local: Path) -> bool:
    try:
        s = _connect(target)
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


def verify_remote_api(target: dict, expect_date: str) -> bool:
    """上传后验证生产/测试盒 API 返回正确日期。"""
    try:
        s = _connect(target)
        _, o, _ = s.exec_command(f"curl -s --max-time 20 {target['api']}", timeout=40)
        resp = o.read().decode("utf-8", "replace")
        s.close()
        data = json.loads(resp)
        ok = data.get("ok") is True and data.get("latest_date") == expect_date
        log(f"  {'✅' if ok else '❌'} API 验证 {target['name']}: {resp[:150]}")
        return ok
    except Exception as e:
        log(f"  ❌ API 验证 {target['name']} 异常: {e}")
        return False


def publish_html(date: str, local_html: Path) -> bool:
    target = TARGETS[0]  # reports 站只在生产副 VPS
    try:
        s = _connect(target)
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


# ---------------- Telegram 告警 ----------------

def _load_env() -> dict:
    cfg = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip().strip("\"'")
    return cfg


def send_telegram_alert(stage: str, detail: str, exit_code: int):
    """发送失败告警到 Telegram（内容含用户要求的字段）。"""
    import urllib.request
    env = _load_env()
    token = env.get("TELEGRAM_BOT_TOKEN") or env.get("BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log("⚠️ 未配置 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID，无法告警（请检查 ~/.hermes/.env）")
        return
    latest_data = get_latest_data_day() or "N/A"
    now = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    msg = (
        "🚨 市场共识雷达发布失败\n"
        f"\n📅 日期: {latest_data}"
        f"\n⏱ 检测时间: {now}"
        f"\n🔴 失败阶段: {stage}"
        f"\n📝 错误摘要: {detail[:500]}"
        f"\n🗂 Phase1~4 最新产物时间: {latest_input_mtime()}"
        f"\n💾 snapshot 日期: {latest_data}"
        f"\n🖥 生产环境: vip2.wmsora.vip (173.249.203.149:3100)"
        f"\n🧪 测试盒状态: 192.168.50.22:3100"
        f"\n📄 日志路径: /tmp/consensus_publish_*.log"
        f"\n🔚 退出码: {exit_code}"
    )
    payload = json.dumps({
        "chat_id": chat_id,
        "text": msg,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
            if data.get("ok"):
                log("✅ Telegram 告警已发送")
            else:
                log(f"❌ Telegram 告警发送失败: {data.get('description')}")
    except Exception as e:
        log(f"❌ Telegram 告警发送异常: {e}")


# ---------------- 主流程 ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只审计+build+校验，不上传/不发布")
    ap.add_argument("--max-age-hours", type=float, default=36.0, help="产物新鲜窗口（小时）")
    ap.add_argument("--force", action="store_true", help="跳过 md5 防重复，强制上传/发布")
    ap.add_argument("--alert", action="store_true", help="补偿检测模式：产物未就绪也告警（23:20 用）")
    ap.add_argument("--no-telegram", action="store_true", help="禁用 Telegram 告警（仅日志）")
    args = ap.parse_args()

    mode = "补偿检测(告警)" if args.alert else "主检测(静默)"
    log(f"市场共识雷达发布管道 [{mode}] · 新鲜窗口={args.max_age_hours}h")

    def fail(stage: str, detail: str):
        """统一失败出口：记录 + 日志 + Telegram + exit 1。"""
        log(f"PUBLISH_FAILED {stage}:\n{detail}")
        if not args.no_telegram:
            send_telegram_alert(stage, detail, 1)
        sys.exit(1)

    # 1) 前置审计：Phase 1~4 产物新鲜
    ok, issues = audit_fresh(args.max_age_hours)
    if not ok:
        log("前置审计不满足（Phase 1~4 当日全链路未完成）:")
        for it in issues:
            log(f"  - {it}")
        if args.alert and not args.no_telegram:
            send_telegram_alert("前置条件未满足（23:20 仍无当日产物）",
                                "; ".join(issues), 2)
        log("PUBLISH_SKIPPED 产物未就绪" + ("（已告警）" if args.alert else "（静默，等待补偿检测）"))
        sys.exit(2)
    log("✅ 前置审计通过：Phase 1~4 产物全部新鲜")

    # 2) build snapshot（幂等）
    snap_path = ROOT / SNAPSHOT_REL
    before = md5_file(snap_path) if snap_path.exists() else None
    rc, out = run("build_consensus_snapshot.py")
    if rc != 0:
        fail("builder error", f"build_consensus_snapshot 失败:\n{out}")
    after = md5_file(snap_path)
    log(f"✅ snapshot 生成: md5={after[:12]} (before={before[:12] if before else 'N/A'})")
    # snapshot hash mismatch 检查（幂等破坏告警）
    if before and before != after:
        fail("snapshot hash mismatch", f"同输入产物 md5 变化: {before[:12]} → {after[:12]}，幂等契约被破坏")

    # 3) 校验
    vok, errs = validate_snapshot()
    if not vok:
        fail("schema validation fail", "\n".join(f"  - {e}" for e in errs))
    latest_data = get_latest_data_day()
    log(f"✅ snapshot 校验通过（schema + latest_date={latest_data}）")

    if args.dry_run:
        log("PUBLISH_OK (dry-run，未上传/未发布)")
        sys.exit(0)

    # 4) 防重复发布：与生产已上传 md5 对比（始终静默）
    if not args.force:
        prod_md5 = remote_md5(TARGETS[0])
        if prod_md5 and prod_md5 == after:
            log(f"PUBLISH_SKIPPED 生产已是该版本 (md5={after[:12]})，无需重复发布")
            sys.exit(0)

    # 5) 上传双环境 + 各自 API 验证
    for t in TARGETS:
        if not upload(t, snap_path):
            fail("SSH/upload fail", f"上传失败 {t['name']} ({t['host']})")
        log(f"✅ 已上传 {t['name']} ({t['host']})")
        if not verify_remote_api(t, latest_data or ""):
            fail("production API verification fail", f"{t['name']} API 验证失败")

    # 6) 生成并发布 HTML
    date = latest_data or datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
    HTML_OUT_DIR.mkdir(parents=True, exist_ok=True)
    rc, out = run("render_consensus_snapshot_html.py", str(snap_path), str(HTML_OUT_DIR / f"{date}.html"))
    if rc != 0:
        fail("HTML render fail", f"render_consensus_snapshot_html 失败:\n{out}")
    local_html = HTML_OUT_DIR / f"{date}.html"
    if not local_html.exists():
        fail("HTML render fail", "HTML 未生成")
    if publish_html(date, local_html):
        log(f"✅ HTML 已发布 reports.wmsora.vip/consensus/{date}.html + latest.html")
    else:
        fail("HTML publish fail", "HTML 发布失败")

    log("PUBLISH_OK 全链路完成")
    sys.exit(0)


if __name__ == "__main__":
    main()
