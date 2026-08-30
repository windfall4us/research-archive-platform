#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_trading_calendar.py — 生成 A 股交易所交易日历（替换 chinese_calendar 法定工作日历）
============================================================================================
背景（用户 2026-08-30 裁决）：chinese_calendar 判断的是「中国法定工作日/节假日」，
与「沪深北交易所交易日」存在语义差异——尤其周末调休上班日（法定工作日=YES 但 A 股不开市），
会导致总控误判为应有行情数据 → 23:20 假告警。

本脚本生成权威交易所日历：
  1) 主规则：周末永不开市（A 股周六日从不交易）+ 2026 官方休市区间
     （上交所上证公告〔2025〕45号，2025-12-22 发布；沪深北三所同一日历）
  2) 交叉验证：与同花顺金融数据 API /api/a-share/calendar/trading-days（过去一年滚动窗口）
     覆盖范围内逐日比对，零不匹配才落盘
  3) Audit：输出与 chinese_calendar 的差异报告（保留 chinese_calendar 仅作审计/fallback，
     绝不作正式 Gate）

输出：
  data/calendar/trading_days_<year>.json    —— 正式日历（含逐日 is_open）
  reports/runtime/trading_calendar_audit_<year>.md —— 审计报告

用法：python3 scripts/build_trading_calendar.py [--year 2026] [--no-api] [--out ...]
      --no-api: 跳过交易所 API 交叉验证（离线模式）
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAL_DIR = ROOT / "data" / "calendar"
AUDIT_DIR = ROOT / "reports" / "runtime"

# ---- 2026 官方休市区间（上交所上证公告〔2025〕45号，沪深北一致） ----
# 注：A 股周末永不开市（官方公告中「X月X日（星期六）为周末休市」即周末休市，无需调休上班补市）
CLOSED_RANGES = {
    2026: [
        ("2026-01-01", "2026-01-03", "元旦"),
        ("2026-02-15", "2026-02-23", "春节"),
        ("2026-04-04", "2026-04-06", "清明节"),
        ("2026-05-01", "2026-05-05", "劳动节"),
        ("2026-06-19", "2026-06-21", "端午节"),
        ("2026-09-25", "2026-09-27", "中秋节"),
        ("2026-10-01", "2026-10-07", "国庆节"),
    ],
}

EXCHANGE = "SSE"
HITHINK_BASE = "https://fuyao.aicubes.cn"
HITHINK_CAL = "/api/a-share/calendar/trading-days"


def get_api_key() -> str | None:
    import os
    env = os.environ.get("HITHINK_FINANCE_API_KEY")
    if env:
        return env
    cred = Path.home() / ".config" / "hithink-finance" / "credentials.env"
    if cred.exists():
        for line in cred.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("HITHINK_FINANCE_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return None


def fetch_exchange_calendar() -> list[str] | None:
    """拉取同花顺交易所交易日历（YYYYMMDD 列表），失败返回 None。"""
    import urllib.request
    key = get_api_key()
    if not key:
        return None
    try:
        req = urllib.request.Request(HITHINK_BASE + HITHINK_CAL, headers={"X-api-key": key})
        with urllib.request.urlopen(req, timeout=45) as resp:
            d = json.loads(resp.read().decode())
        items = d.get("data", {}).get("item", [])
        return sorted(x["date"] for x in items)
    except Exception as e:
        print(f"  ⚠ API 拉取失败（跳过交叉验证）: {e}", file=sys.stderr)
        return None


def decide(dt: date, closed_ranges) -> tuple[bool, str]:
    """返回 (is_open, reason)。周末永不开市。"""
    if dt.weekday() >= 5:
        return False, "weekend"
    ds = dt.strftime("%Y-%m-%d")
    for s, e, name in closed_ranges:
        if s <= ds <= e:
            return False, name
    return True, "trading_day"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--no-api", action="store_true", help="跳过交易所 API 交叉验证")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    year = args.year
    closed = CLOSED_RANGES.get(year)
    if closed is None:
        print(f"❌ 未配置 {year} 官方休市表", file=sys.stderr)
        return 1

    CAL_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) 周末规则 + 官方休市表 → 全年逐日
    s = date(year, 1, 1)
    e = date(year, 12, 31)
    days = []
    cur = s
    while cur <= e:
        ok, reason = decide(cur, closed)
        days.append({
            "date": cur.strftime("%Y-%m-%d"),
            "is_open": ok,
            "exchange": EXCHANGE,
            "source": "exchange_schedule_" + str(year),
            "reason": reason,
            "calendar_version": str(year),
        })
        cur += timedelta(days=1)

    trading_days = [d["date"] for d in days if d["is_open"]]
    closed_days = [d["date"] for d in days if not d["is_open"]]
    print(f"生成 {year} 全年: 交易日 {len(trading_days)} / 休市 {len(closed_days)}")

    # 2) 交易所 API 交叉验证（窗口内逐日比对）
    api_days = None
    if not args.no_api:
        api_days = fetch_exchange_calendar()
        if api_days is not None:
            api_set = set(api_days)
            # 仅验证当年且 <= 当前已知最大日（API 是过去一年滚动窗口）
            cur_max = max(api_days)
            mism = []
            for d in days:
                ymd = d["date"].replace("-", "")
                if d["date"] <= cur_max[:4] + "-" + cur_max[4:6] + "-" + cur_max[6:]:
                    api_ok = ymd in api_set
                    if api_ok != d["is_open"]:
                        mism.append((d["date"], d["reason"], d["is_open"], api_ok))
            print(f"API 交叉验证: 覆盖至 {cur_max}，不匹配 {len(mism)}")
            for m in mism[:20]:
                print("  ⚠", m)
            if mism:
                print("❌ API 交叉验证失败，拒绝落盘", file=sys.stderr)
                return 2
            # 覆盖窗口内的交易日 source 提升为 financial_api（权威确认）
            api_set_2026 = {x for x in api_set if x.startswith(str(year))}
            for d in days:
                if d["is_open"] and d["date"].replace("-", "") in api_set_2026:
                    d["source"] = "financial_api"
    else:
        print("⚠ 离线模式：跳过 API 交叉验证（source 保持 exchange_schedule）")

    # 3) chinese_calendar 审计对比（仅审计，不作 Gate）
    audit_lines = []
    try:
        import chinese_calendar as cc
        cc_workdays = set()
        cur = s
        while cur <= e:
            if cc.is_workday(cur):
                cc_workdays.add(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
        ex_set = set(trading_days)
        only_ex = sorted(ex_set - cc_workdays)   # 交易所开但 chinese 非工作日
        only_cc = sorted(cc_workdays - ex_set)   # chinese 工作日但交易所不开（含调休上班日）
        audit_lines.append(f"- chinese_calendar 工作日: {len(cc_workdays)} 天")
        audit_lines.append(f"- 交易所日历交易日: {len(ex_set)} 天")
        audit_lines.append(f"- 交易所开市但 chinese 判非工作日: {len(only_ex)} 天（{', '.join(only_ex[:12])}）")
        audit_lines.append(f"- chinese 判工作日但交易所休市（周末调休上班日等）: {len(only_cc)} 天")
        for x in only_cc:
            dt = datetime.strptime(x, "%Y-%m-%d").date()
            audit_lines.append(f"    {x} 周{'一二三四五六日'[dt.weekday()]}（法定工作日但 A 股休市 → 旧日历会误判为应有数据）")
        print(f"审计: chinese_calendar 工作日 {len(cc_workdays)} vs 交易所 {len(ex_set)}")
        print(f"  chinese 判工作日但交易所休市: {len(only_cc)} 天")
        for x in only_cc[:10]:
            print(f"    {x}")
    except ImportError:
        audit_lines.append("- chinese_calendar 不可用，跳过审计对比")

    # 4) 落盘
    out_path = Path(args.out) if args.out else CAL_DIR / f"trading_days_{year}.json"
    payload = {
        "year": year,
        "calendar_version": str(year),
        "scope": f"{s.isoformat()} ~ {e.isoformat()}",
        "exchange": EXCHANGE,
        "source": "exchange_schedule + financial_api交叉验证" if api_days else "exchange_schedule",
        "count": len(days),
        "trading_day_count": len(trading_days),
        "closed_day_count": len(closed_days),
        "days": days,
        "trading_days": trading_days,  # 兼容旧字段
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK  → {out_path} ({len(days)} 天, 交易日 {len(trading_days)})")

    # 5) 审计报告
    audit = [
        f"# 交易日历审计 {year}",
        "",
        f"- 生成: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- 正式 Gate 日历: `data/calendar/trading_days_{year}.json`（交易所日历：周末永不开市 + 官方休市区间）",
        f"- 权威来源: 沪深北交易所 {year} 休市安排（上证公告〔2025〕45号 / 2025-12-22）+ 同花顺金融数据 API 交叉验证",
        f"- API 覆盖窗口: {api_days[0] if api_days else 'N/A'} ~ {api_days[-1] if api_days else 'N/A'}（窗口内交易日 source=financial_api）",
        "",
        "## 与 chinese_calendar（法定日历）差异",
        "",
        *audit_lines,
        "",
        "> chinese_calendar 仅作审计/fallback，**绝不作为正式交易 Gate**（用户 2026-08-30 锁定）。",
        "",
    ]
    audit_path = AUDIT_DIR / f"trading_calendar_audit_{year}.md"
    audit_path.write_text("\n".join(audit), encoding="utf-8")
    print(f"OK  → {audit_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
