#!/usr/bin/env python3
"""0B.6: 跨天快照 Diff + Revision 引擎（双层 ID，MODIFIED 检测）。

设计（phase0b_plan v2，用户决策 4/5）：
- logical_key = vip0:{analyst}:{date}:{section_type}:{entity}  判断"可能同一逻辑记录"
- record_id   = logical_key + :action:{NNN}                    记录指纹（同一 logical 下多条动作）
- Diff 状态：ADDED / REMOVED / UNCHANGED / MODIFIED
- MODIFIED 判定：同一 record_id（logical_key + 动作序号/文本签名）内容指纹变化
  （同一 logical_key 下不同 action 序号 = 独立记录，不算 MODIFIED 的误报来源）
- Revision 记录：revision_id / logical_record_id / snapshot_date / detected_at / revision_no /
  change_type / old_hash / new_hash / old_value / new_value / changed_fields

用法：
  python3 diff_analyst_snapshots_v2.py <before.json> <after.json>
  python3 diff_analyst_snapshots_v2.py --snap-dir data/analyst_snapshots  (自动找最新两份日终 json)
"""
import argparse, hashlib, json, re, sys
from pathlib import Path


def load_sections(path: Path) -> dict:
    """把 vip0_timeline.json 展开成 section 列表：daily_action / position_summary / analysis_item。
    返回 list of {analyst, date, section_type, entity, action_no, raw_fields}
    """
    d = json.loads(path.read_text(encoding='utf-8'))
    sections = []
    for name, b in d.get('bloggers', {}).items():
        days = b.get('days', {})
        latest = max(days.keys()) if days else None
        for day, dd in days.items():
            # 持仓汇总：最新一天的 ops 同时充当 position_summary（render_vip0 行为）
            for i, op in enumerate(dd.get('ops', [])):
                entity = re.sub(r'\([0-9]+\)', '', str(op.get('stock', ''))).strip()
                sect = 'position_summary' if day == latest else 'daily_action'
                sections.append({
                    'analyst': name, 'date': day, 'section_type': sect, 'entity': entity,
                    'action_no': i,
                    'raw_fields': {
                        'stock': op.get('stock', ''), 'logic': op.get('logic', ''),
                        'action': op.get('action', ''), 'direction': op.get('direction', ''),
                        'date': op.get('date', day),
                    },
                })
            # 观点区（analysis-item）：core_theme/trend/logic
            for label, key in (('core_theme', 'core_theme'), ('trend', 'trend'), ('logic', 'logic')):
                val = str(dd.get(key, '')).strip()
                if val and val != '今日无有效新观点':
                    sections.append({
                        'analyst': name, 'date': day, 'section_type': 'analysis_item',
                        'entity': label, 'action_no': 0,
                        'raw_fields': {'value': val},
                    })
    return sections


def logical_key(s):
    return f"vip0:{s['analyst']}:{s['date']}:{s['section_type']}:{s['entity']}"


def record_id(s, logical):
    """同一 logical 下多条 action 用【动作序号】区分（用户决策 4）。
    序号相同但内容变了 → MODIFIED（changed_fields 追踪）；序号不同 → 独立记录。
    不能用文本签名当 record_id —— 否则改文本会误判成 ADDED+REMOVED。
    """
    if s['section_type'] == 'analysis_item':
        return f"{logical}:analysis"
    return f"{logical}:action:{s['action_no']:03d}"


def fingerprint(s):
    payload = json.dumps(s['raw_fields'], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def diff(before: Path, after: Path) -> dict:
    a = {record_id(s, logical_key(s)): s for s in load_sections(before)}
    b = {record_id(s, logical_key(s)): s for s in load_sections(after)}

    result = {'added': [], 'removed': [], 'unchanged': [], 'modified': []}
    for rid, sa in a.items():
        if rid not in b:
            result['removed'].append({'record_id': rid, 'old': sa['raw_fields']})
            continue
        sb = b[rid]
        fa, fb = fingerprint(sa), fingerprint(sb)
        if fa == fb:
            result['unchanged'].append(rid)
        else:
            changed = [k for k in sa['raw_fields'] if sa['raw_fields'].get(k) != sb['raw_fields'].get(k)]
            result['modified'].append({
                'record_id': rid,
                'old_hash': fa, 'new_hash': fb,
                'old_value': {k: sa['raw_fields'].get(k) for k in changed},
                'new_value': {k: sb['raw_fields'].get(k) for k in changed},
                'changed_fields': changed,
            })
    for rid, sb in b.items():
        if rid not in a:
            result['added'].append({'record_id': rid, 'new': sb['raw_fields']})

    # 严重度：操作方向/动作变更 > 文本微调
    SEVERE = {'action', 'direction'}
    for m in result['modified']:
        m['severity'] = 'SEVERE' if SEVERE & set(m['changed_fields']) else 'TEXT'
    return result


def summarize(res: dict, before_n: int, after_n: int) -> dict:
    by_type = {}
    for m in res['modified']:
        k = f"{m['severity']}:{','.join(sorted(m['changed_fields']))}"
        by_type[k] = by_type.get(k, 0) + 1
    # 旧日期修改率（仅统计非最新日）
    return {
        'before_records': before_n, 'after_records': after_n,
        'added': len(res['added']), 'removed': len(res['removed']),
        'unchanged': len(res['unchanged']), 'modified': len(res['modified']),
        'modified_breakdown': by_type,
        'samples': {'added': res['added'][:3], 'removed': res['removed'][:3],
                    'modified': res['modified'][:3]},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('before', type=Path, nargs='?')
    ap.add_argument('after', type=Path, nargs='?')
    ap.add_argument('--snap-dir', type=Path,
                    default=Path('/home/windfall/workspace/research-archive-platform/data/analyst_snapshots'))
    ap.add_argument('--json-out', type=Path)
    args = ap.parse_args()

    if args.before and args.after:
        bf, af = args.before, args.after
    else:
        jsons = sorted(p for p in args.snap_dir.glob('vip0_timeline_20*.json')
                       if '_summary.json' not in p.name)
        if len(jsons) < 2:
            print(f'ERROR: 需要至少2份日终json快照（现有 {len(jsons)} 份）', file=sys.stderr)
            return 2
        bf, af = jsons[-2], jsons[-1]

    a = load_sections(bf); b = load_sections(af)
    res = diff(bf, af)
    summ = summarize(res, len(a), len(b))
    summ['before'] = str(bf); summ['after'] = str(af)
    print(json.dumps(summ, ensure_ascii=False, indent=2))
    if args.json_out:
        args.json_out.write_text(json.dumps(summ, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
