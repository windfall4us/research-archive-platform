#!/usr/bin/env python3
"""Compare two vip0 timeline HTML snapshots by stable analyst/day/action records."""
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('p0a_parser', ROOT/'scripts/parse_analyst_timeline_p0a.py')
mod=importlib.util.module_from_spec(spec); sys.modules['p0a_parser']=mod; spec.loader.exec_module(mod)

def records(path):
    days=mod.parse_html(path.read_bytes()); out={}
    for day in days:
        for action in day['actions']:
            # stable content identity; row position is retained as an audit hint only
            identity=(day['analyst'],day['analysis_date'],action['raw_target'],action['raw_logic'],action['raw_action_text'],action['raw_direction'],action['raw_date'])
            key=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()[:20]
            out[key]=dict(action,record_hash=key)
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('before',type=Path); ap.add_argument('after',type=Path); args=ap.parse_args()
    a=records(args.before); b=records(args.after)
    added=sorted(set(b)-set(a)); removed=sorted(set(a)-set(b)); unchanged=sorted(set(a)&set(b))
    print(json.dumps({'before':str(args.before),'after':str(args.after),'before_actions':len(a),'after_actions':len(b),'added':len(added),'removed':len(removed),'unchanged':len(unchanged),'added_samples':[b[k] for k in added[:10]],'removed_samples':[a[k] for k in removed[:10]]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
