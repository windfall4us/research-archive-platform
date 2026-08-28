#!/usr/bin/env python3
"""0B.2 v2: 从 vip0_timeline.json 分层抽样 100 条 Gold Sample，用修正后的 v1.1 协议规则初标。

修正（2026-08-28 前20条复核后）：
1. 「观察/关注/跟踪/等待」≠ HOLD → 独立 WATCH（权重0），status=INTENDED
2. HOLD 仅限「持有/持股/继续拿/底仓持有」等明确持仓语义 → status=POSITION_STATE
3. temporal_type 补全：持有→CURRENT_STATE、条件句→CONDITIONAL、已执行→TODAY
4. 新增 multi-target 检测：目标含「/」多条 → 拆成多行
5. 新增 FOREIGN 检测：阿里巴巴/腾讯/美团等非A股 → entity_type=UNKNOWN + 备注
6. 「试盘/试探仓/试错」→ TRIAL（不归 HOLD）
7. 「不关注/结构偏弱/谨慎」负向观察 → WATCH + 负向备注
"""
import csv, json, random, re
from pathlib import Path

random.seed(20260828)
D = json.load(open('/home/windfall/workspace/vip0_timeline.json', encoding='utf-8'))

OPS = []
for name, b in D['bloggers'].items():
    for day, dd in b.get('days', {}).items():
        for op in dd.get('ops', []):
            OPS.append({
                'analyst': name, 'date': day,
                'stock': op.get('stock', ''), 'logic': op.get('logic', ''),
                'action': op.get('action', ''), 'direction': op.get('direction', ''),
            })

# 非A股/中概/港股 已知名单（保守，仅确认过的）
FOREIGN = ['阿里巴巴', '腾讯', '美团', '拼多多', '京东', '百度', '网易', '小米', '快手', '理想汽车', '蔚来', '小鹏汽车']

def has_code(s):
    return bool(re.search(r'(60|68|00|30)\d{4}', s))

def split_targets(o):
    """multi-target 拆行：目标含 / 或 、 拆开（保留原行 + 拆分后逐行）。"""
    raw = o['stock']
    parts = [p.strip() for p in re.split(r'[/、,，]', raw) if p.strip()]
    out = []
    for p in parts:
        row = dict(o)
        row['stock'] = p
        row['multi_from'] = raw
        out.append(row)
    return out if len(parts) > 1 else [o]

def action_type(direction, action_text):
    t = (direction or '') + ' ' + (action_text or '')
    # 清仓/走人 类（最高优先）
    if re.search(r'清仓|已走|出清|止盈离场|全部卖|落袋|彻底走人|回本离场|止损离场|割肉', t): return 'CLEAR'
    if re.search(r'止损', t): return 'STOP_LOSS'
    # 负向观察：不关注/谨慎/回避/结构偏弱 → WATCH
    if re.search(r'不关注|回避|谨慎|结构偏弱|偏弱|不建议|暂无新叙事|不碰|放弃', t): return 'WATCH'
    # 卖出/减仓
    if re.search(r'减仓|止盈|卖出|离场|减出|高抛', t):
        return 'REDUCE' if re.search(r'部分|减仓|止盈', t) else 'SELL'
    # 试盘/试探 → TRIAL
    if re.search(r'试盘|试探|试错|试探仓|试仓', t): return 'TRIAL'
    # 加仓
    if re.search(r'加仓|补仓|接回|回补', t): return 'ADD'
    # 低吸
    if re.search(r'低吸|低吃', t): return 'LOW_BUY'
    # 买入/建仓
    if re.search(r'买入|建仓|打底仓|介入|扫货|进场', t): return 'BUY'
    # 做T
    if re.search(r'做T|做t|高抛低吸|T出|网格', t): return 'DO_T'
    # 明确持仓（唯一归 HOLD 的）
    if re.search(r'持有|持股|继续拿|底仓持有|持仓', t): return 'HOLD'
    # 纯观察/关注/跟踪/等待 → WATCH
    if re.search(r'观察|关注|跟踪|等待|等|看|盯', t): return 'WATCH'
    return 'UNKNOWN'

def temporal_type(direction, action_text):
    t = (action_text or '')
    if re.search(r'若|如果|等.*(企稳|回踩|回调|确认|站上|突破)|回踩.*(可|关注|买)|逢|可.*(买|接|关注)|待|再|盘中看|看T|暂不', t): return 'CONDITIONAL'
    if re.search(r'已|完成|继续持股|继续持有|持仓跟踪|已介入|清仓|已走|持有中', t): return 'CURRENT_STATE'
    if re.search(r'现价|今日|今天', t): return 'TODAY'
    return 'UNKNOWN'

def status(direction, action_text, at):
    t = (action_text or '')
    if at == 'HOLD': return 'POSITION_STATE'
    if re.search(r'已|继续|完成', t) and not re.search(r'若|如果|等', t): return 'EXECUTED'
    if re.search(r'若|如果|等|可|暂|待|逢|回踩', t): return 'CONDITIONAL' if at != 'WATCH' else 'INTENDED'
    return 'INTENDED'

def entity_type(stock, analyst=None):
    if stock in FOREIGN: return 'UNKNOWN'  # 非A股，保守
    if re.search(r'大盘|市场|指数|板块|主线|科技线|方向', stock): return 'MARKET'
    if re.search(r'概念|产业链|板块|题材|方向|主线|三剑客|组合', stock): return 'THEME'
    return 'STOCK'

# 展开 multi-target
expanded = []
for o in OPS:
    expanded.extend(split_targets(o))
print('展开后 ops 总数:', len(expanded))

# 分层抽样
buckets = {}
for o in expanded:
    at = action_type(o['direction'], o['action'])
    buckets.setdefault(at, []).append(o)

TARGET = 100
picked = []
for at, items in buckets.items():
    share = max(1, round(TARGET * len(items) / len(expanded)))
    by_a = {}
    for o in items:
        by_a.setdefault(o['analyst'], []).append(o)
    n_per = max(1, share // len(by_a))
    for a, lst in by_a.items():
        pool = lst[:]
        random.shuffle(pool)
        picked.extend(pool[:n_per])
picked = picked[:TARGET]

out = Path('/home/windfall/workspace/research-archive-platform/data/analyst_snapshots/gold_sample_100.csv')
fields = ['sample_id', 'analyst', 'date', 'raw_target', 'raw_action', 'direction', 'raw_logic',
          'entity_type_draft', 'actions_draft', 'action_status_draft', 'temporal_type_draft',
          'has_code', 'multi_target', 'review_status', 'review_note', 'human_confirm']
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for i, o in enumerate(picked, 1):
        at = action_type(o['direction'], o['action'])
        st = status(o['direction'], o['action'], at)
        tp = temporal_type(o['direction'], o['action'])
        et = entity_type(o['stock'])
        note = ''
        if 'multi_from' in o: note += f"多目标拆分自:{o['multi_from']}; "
        if o['stock'] in FOREIGN: note += '非A股(港股/中概); '
        w.writerow({
            'sample_id': i, 'analyst': o['analyst'], 'date': o['date'],
            'raw_target': o['stock'], 'raw_action': o['action'], 'direction': o['direction'],
            'raw_logic': o['logic'],
            'entity_type_draft': et,
            'actions_draft': at,
            'action_status_draft': st,
            'temporal_type_draft': tp,
            'has_code': has_code(o['stock']),
            'multi_target': 'multi_from' in o,
            'review_status': '', 'review_note': note, 'human_confirm': '',
        })

from collections import Counter
print('博主:', Counter(p['analyst'] for p in picked))
print('动作:', Counter(p['actions_draft'] for p in picked))
print('对象:', Counter(p['entity_type_draft'] for p in picked))
print('时间:', Counter(p['temporal_type_draft'] for p in picked))
print('状态:', Counter(p['action_status_draft'] for p in picked))
print('带码:', sum(has_code(p['stock']) for p in picked), '| 多目标:', sum('multi_from' in p for p in picked))
print('CSV:', out)
