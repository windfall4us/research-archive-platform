#!/usr/bin/env python3
"""0B.6 验收辅助：从 08-28 日终累积 JSON 重建 '截至 08-27 日终' 的 before 快照。

原理：vip0_timeline.json 为增量累积（用户约束：采集/缓存必须增量，旧记录不覆盖），
保留近 15 天。将每博主 days 过滤为 <= '2026-08-27'，即得 08-27 日终时应有的内容
（若 08-28 有重写 08-27 记录，diff 阶段会如实报 MODIFIED —— 这正是 revision 引擎要检出的）。

用法: python3 reconstruct_prev_snapshot_p0b.py
输出: data/analyst_snapshots/vip0_timeline_20260827.json（派生快照，不覆盖任何原始文件）
"""
import json
from pathlib import Path

BASE = Path('/home/windfall/workspace/research-archive-platform/data/analyst_snapshots')
AFTER = BASE / 'vip0_timeline_20260828.json'
BEFORE = BASE / 'vip0_timeline_20260827.json'
CUTOFF = '2026-08-27'  # 保留 <= 该日期

d = json.loads(AFTER.read_text(encoding='utf-8'))
kept = {}
for name, b in d.get('bloggers', {}).items():
    days = {day: v for day, v in b.get('days', {}).items() if day <= CUTOFF}
    if days:
        nb = dict(b)
        nb['days'] = days
        kept[name] = nb

out = dict(d)
out['bloggers'] = kept
out['generated'] = d.get('generated', '')
out['_reconstructed'] = f'as-of {CUTOFF} 日终, from {AFTER.name} (增量重建)'

BEFORE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')

n_bloggers = len(kept)
n_days = set()
n_ops = 0
for b in kept.values():
    for day, dd in b['days'].items():
        n_days.add(day)
        n_ops += len(dd.get('ops', []))
print(f'重建 {BEFORE.name}: {n_bloggers} 博主 | {len(n_days)} 天 | {n_ops} 条操作')
print(f'日期范围: {min(n_days)} ~ {max(n_days)}')
