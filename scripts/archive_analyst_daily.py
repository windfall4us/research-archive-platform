#!/usr/bin/env python3
"""日终归档：把 22:30 夜盘任务产出的 vip0_timeline.html/json 按日期复制存档 + 生成当日摘要。

纯本地复制，不重新抓取、不重新分析、不发网络请求。
职责 = 数据留存（历史 revision），与 22:30 任务的数据生产完全解耦。
"""
import json, shutil, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING_TZ = timezone(timedelta(hours=8))

SRC_HTML = Path('/home/windfall/workspace/vip0_timeline.html')
SRC_JSON = Path('/home/windfall/workspace/vip0_timeline.json')
SNAP_DIR = Path('/home/windfall/workspace/research-archive-platform/data/analyst_snapshots')


def today_str() -> str:
    return datetime.now(BEIJING_TZ).strftime('%Y%m%d')


def build_summary(json_path: Path) -> dict:
    d = json.loads(json_path.read_text(encoding='utf-8'))
    bloggers = d.get('bloggers', {})
    days = []
    for name, b in bloggers.items():
        for day in b.get('days', {}).values():
            days.append({
                'analyst': name,
                'date': day.get('date'),
                'ops': len(day.get('ops', [])),
            })
    dates = sorted({x['date'] for x in days if x['date']})
    total_ops = sum(x['ops'] for x in days)
    return {
        'archived_at': datetime.now(BEIJING_TZ).isoformat(timespec='seconds'),
        'source_generated': d.get('generated'),
        'vip': d.get('vip'),
        'title': d.get('title'),
        'analyst_count': len(bloggers),
        'day_count': len(days),
        'date_range': [dates[0], dates[-1]] if dates else [],
        'total_ops': total_ops,
        'by_analyst': {name: {'days': sum(1 for x in days if x['analyst'] == name),
                               'ops': sum(x['ops'] for x in days if x['analyst'] == name)}
                       for name in bloggers},
    }


def main() -> int:
    if not SRC_HTML.exists() or not SRC_JSON.exists():
        print(f'ERROR: 源文件缺失 html={SRC_HTML.exists()} json={SRC_JSON.exists()}', file=sys.stderr)
        return 1

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    day = today_str()
    dst_html = SNAP_DIR / f'vip0_timeline_{day}.html'
    dst_json = SNAP_DIR / f'vip0_timeline_{day}.json'
    dst_sum  = SNAP_DIR / f'vip0_timeline_{day}_summary.json'

    # 复制（若同日已存在则覆盖为最新日终版；22:30 是当日最后完整一档）
    shutil.copyfile(SRC_HTML, dst_html)
    shutil.copyfile(SRC_JSON, dst_json)

    summary = build_summary(dst_json)
    dst_sum.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps({
        'status': 'ok',
        'day': day,
        'html': str(dst_html),
        'json': str(dst_json),
        'summary': str(dst_sum),
        'html_bytes': dst_html.stat().st_size,
        'json_bytes': dst_json.stat().st_size,
        'analyst_count': summary['analyst_count'],
        'date_range': summary['date_range'],
        'total_ops': summary['total_ops'],
        'by_analyst': summary['by_analyst'],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
