#!/usr/bin/env python3
"""P0A name-to-code audit against a local stock master; no LLM guessing."""
import importlib.util, json, sqlite3, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('p0a_parser', ROOT/'scripts/parse_analyst_timeline_p0a.py')
mod=importlib.util.module_from_spec(spec); sys.modules['p0a_parser']=mod; spec.loader.exec_module(mod)
parse_html=mod.parse_html
HTML=sorted((ROOT/'data/analyst_snapshots').glob('vip0_timeline_*.html'))[-1]
MASTER=Path('/home/windfall/workspace/telegram_stock_bot/stocks.db')

def norm(s): return ''.join((s or '').replace('股份','').replace('有限公司','').split()).lower()
con=sqlite3.connect(MASTER); rows=con.execute('select code,stock_id,aliases from stocks').fetchall(); con.close()
name_map={}; alias_map={}
for code,name,aliases in rows:
    name_map[norm(name)]=(code,name,'EXACT')
    for a in (aliases or '').replace('，',',').split(','):
        if a.strip(): alias_map[norm(a)]=(code,name,'ALIAS')

days=parse_html(HTML.read_bytes()); actions=[a for d in days for a in d['actions']]
counts={'EXACT':0,'ALIAS':0,'CODE':0,'UNRESOLVED':0,'NON_STOCK':0}; resolved=[]; unresolved=[]
for a in actions:
    t=a['target']; raw=t['raw_target']; key=norm(raw)
    if t['entity_type'] in {'THEME','MARKET'}: counts['NON_STOCK']+=1; continue
    if t['stock_code']: counts['CODE']+=1; continue
    hit=name_map.get(key) or alias_map.get(key)
    if hit:
        counts[hit[2]]+=1; resolved.append({'source_record_id':a['source_record_id'],'raw_target':raw,'code':hit[0],'name':hit[1],'method':hit[2]})
    else:
        counts['UNRESOLVED']+=1
        if len(unresolved)<50: unresolved.append({'raw_target':raw,'action':a['raw_action_text']})
out={'html':str(HTML),'total_actions':len(actions),'master_rows':len(rows),'counts':counts,'resolved_samples':resolved[:30],'unresolved_samples':unresolved}
print(json.dumps(out,ensure_ascii=False,indent=2))
(ROOT/'data/analyst_snapshots/p0a_name_code_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
