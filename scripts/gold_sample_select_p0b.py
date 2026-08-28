#!/usr/bin/env python3
"""0B.1: 锁定 10 行高难度 Gold Sample 候选（覆盖矩阵 + 分散博主），输出到 CSV。"""
import csv, json, re
from pathlib import Path

D = json.load(open('/home/windfall/workspace/vip0_timeline.json', encoding='utf-8'))
OPS = []
for name, b in D['bloggers'].items():
    for day, dd in b.get('days', {}).items():
        for op in dd.get('ops', []):
            OPS.append({'analyst': name, 'date': day, 'stock': op.get('stock', ''),
                        'logic': op.get('logic', ''), 'action': op.get('action', ''),
                        'direction': op.get('direction', '')})


def T(o): return (o['action'] or '') + ' ' + (o['direction'] or '') + ' ' + (o['logic'] or '')


def pick(pred, used, prefer=None):
    for o in OPS:
        if (o['analyst'], o['stock']) in used:
            continue
        if pred(o):
            if prefer and o['analyst'] != prefer:
                continue
            used.add((o['analyst'], o['stock']))
            return o
    # 放宽：忽略 prefer
    for o in OPS:
        if (o['analyst'], o['stock']) in used:
            continue
        if pred(o):
            used.add((o['analyst'], o['stock']))
            return o
    return None


used = set()

# 1 明确买入（不同博主：游资混江龙「已介入」/格兰「想干的可以动」）
s1 = pick(lambda o: o['direction'] == '买入' and re.search(r'买入|介入|建仓|买点', T(o)), used)
# 2 明确低吸（老樊华勤：回调结束打底仓低吸）
s2 = pick(lambda o: re.search(r'低吸', o['direction']) and re.search(r'打底仓|低吸', T(o)), used)
# 3 明确加仓（老樊三环：小幅度顺势加仓）
s3 = pick(lambda o: re.search(r'加仓|补仓', o['action']) and o['direction'] != '减仓', used)
# 4 当前持仓、今天没买（老樊新洁能：继续持股策略）
s4 = pick(lambda o: o['direction'] == '持有' and re.search(r'持股|继续拿|持有', o['action']), used)
# 5 今日买入+当前仍持仓（格兰兴森：想干的可以动/买入）
s5 = pick(lambda o: o['direction'] == '买入' and re.search(r'动|买', o['action']), used, prefer='格兰投研')
# 6 减仓但未清仓（老樊利通：部分减仓止盈后接回）
s6 = pick(lambda o: o['direction'] == '减仓' and re.search(r'部分|减仓', o['action']), used)
# 7 已走/清仓（震哥宏景：清仓兑现 / 潘凤九州一轨：已全部卖出）
s7 = pick(lambda o: re.search(r'清仓兑现|已全部卖出|已清仓|彻底走人|回本离场|已走', T(o)), used, prefer='震哥本尊')
# 8 条件计划（老樊易点天下：回踩买点跟踪 / 潍柴：等回踩买点确认）
s8 = pick(lambda o: re.search(r'回踩.*(跟踪|确认)|等.*回踩|回踩.*可买|回补', T(o)) and o['direction'] in ('观察', '低吸', '买入'), used)
# 9 复合做T（天赢居晓程：反抽突破56元则T出回补部分）
s9 = pick(lambda o: re.search(r'做T|T出|高抛低吸|低吸\+做T', T(o)), used, prefer='天赢居')
# 10 非个股/无法解析（老樊大盘：卡节奏慢慢做）
s10 = pick(lambda o: re.search(r'大盘|市场|指数|板块|主线|科技线', o['stock']), used)

samples = {'1': s1, '2': s2, '3': s3, '4': s4, '5': s5, '6': s6, '7': s7, '8': s8, '9': s9, '10': s10}

# 写出 CSV
out = Path('/home/windfall/workspace/research-archive-platform/data/analyst_snapshots/gold_sample_10.csv')
out.parent.mkdir(parents=True, exist_ok=True)
fields = ['sample_id', 'analyst', 'date', 'raw_target', 'raw_text', 'direction']
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for k in sorted(samples, key=int):
        o = samples[k]
        if o is None:
            print(f'[{k}] MISSING'); continue
        w.writerow({'sample_id': k, 'analyst': o['analyst'], 'date': o['date'],
                    'raw_target': o['stock'], 'raw_text': T(o).strip(), 'direction': o['direction']})

for k in sorted(samples, key=int):
    o = samples[k]
    if o is None:
        print(f'[{k}] 无候选'); continue
    print(f'[{k}] {o["analyst"]} {o["date"]} 目标={o["stock"]} 方向={o["direction"]}')
    print(f'    建议={o["action"][:65]}')
print('\nCSV 已写出:', out)
