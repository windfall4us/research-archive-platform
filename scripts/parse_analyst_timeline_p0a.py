#!/usr/bin/env python3
"""Phase 0A parser: extract stable analyst/day/action boundaries.
No LLM, no scoring, no action normalization. Unknown is preserved.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen
from html.parser import HTMLParser

BEIJING_TZ = timezone(timedelta(hours=8))
DEFAULT_URL = "https://reports.wmsora.vip/analysts/vip0_timeline.html"
STOCK_CODE_RE = re.compile(r"(?<!\d)([0368]\d{5})(?!\d)")
STOCK_HREF_RE = re.compile(r"ths://(\d{6})")
NON_STOCK = {"大盘", "市场", "科技线", "科技", "半导体", "光模块", "存储", "有色", "券商", "农业", "AI", "AI硬件", "半导体材料", "光通信", "算力", "持仓", "手里几个科技票"}

@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    text: list = field(default_factory=list)
    @property
    def cls(self): return set((self.attrs.get("class") or "").split())
    def all_text(self):
        return unescape(" ".join(self.text + [c.all_text() for c in self.children])).strip()
    def find_all(self, cls=None, tag=None):
        out=[]
        if (cls is None or cls in self.cls) and (tag is None or self.tag == tag): out.append(self)
        for c in self.children: out.extend(c.find_all(cls, tag))
        return out

class TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.root=Node("root"); self.stack=[self.root]
    def handle_starttag(self, tag, attrs):
        n=Node(tag,dict(attrs)); self.stack[-1].children.append(n)
        if tag not in {"meta","link","img","input","br","hr"}: self.stack.append(n)
    def handle_startendtag(self, tag, attrs): self.handle_starttag(tag,attrs); self.handle_endtag(tag)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag == tag:
                self.stack=self.stack[:i]; return
    def handle_data(self,data): self.stack[-1].text.append(data.strip())

def text_clean(s): return re.sub(r"\s+", " ", unescape(s or "")).strip()
def node_text(n): return text_clean(n.all_text())
def first(n, cls):
    xs=n.find_all(cls); return xs[0] if xs else None

def classify_target(raw, href=""):
    raw=text_clean(raw)
    m=STOCK_HREF_RE.search(href or "") or STOCK_CODE_RE.search(raw)
    if m: return {"entity_type":"STOCK","raw_target":raw,"stock_code":m.group(1),"match_method":"CODE"}
    if raw in NON_STOCK or any(x in raw for x in ["大盘","指数","板块","行业","科技线","市场风格","主线"]):
        return {"entity_type":"THEME" if raw not in {"大盘","市场"} else "MARKET","raw_target":raw,"stock_code":None,"match_method":"RULE"}
    return {"entity_type":"UNKNOWN","raw_target":raw,"stock_code":None,"match_method":"UNRESOLVED"}

def parse_table(table, analyst, analysis_date, section_type):
    records=[]
    for tr in table.find_all(tag="tr"):
        tds=[c for c in tr.children if c.tag=="td"]
        if len(tds)<4: continue
        target_node=tds[0]; raw_target=node_text(target_node)
        href=""
        for a in target_node.find_all(tag="a"):
            href=a.attrs.get("href","")
        target=classify_target(raw_target,href)
        row={
            "source_record_id":f"vip0:{analyst}:{analysis_date}:{section_type}:{len(records)+1:03d}",
            "analyst":analyst,"analysis_date":analysis_date,"section_type":section_type,
            "raw_target":raw_target,"target":target,
            "raw_logic":node_text(tds[1]),"raw_action_text":node_text(tds[2]),
            "raw_direction":node_text(tds[3]),"raw_date":node_text(tds[4]) if len(tds)>4 else "",
        }
        records.append(row)
    return records

def parse_html(data):
    p=TreeParser(); p.feed(data.decode("utf-8",errors="replace")); root=p.root
    result=[]
    for card in root.find_all("blogger-card"):
        head=first(card,"card-head")
        hs=head.find_all(tag="h2") if head else []
        analyst=node_text(hs[0]) if hs else card.attrs.get("id","")
        style=node_text(first(card,"style-tip")) if first(card,"style-tip") else ""
        for day in card.find_all("day-entry"):
            badge=first(day,"date-badge")
            date=node_text(badge) if badge else ""
            analyses={}
            for item in day.find_all("analysis-item"):
                label=first(item,"label"); value=first(item,"value")
                if label and value: analyses[node_text(label)]=node_text(value)
            tables=day.find_all(tag="table")
            ops=parse_table(tables[0],analyst,date,"daily_action") if tables else []
            result.append({"analyst":analyst,"style":style,"analysis_date":date,"analyses":analyses,"actions":ops})
    return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--html",type=Path); ap.add_argument("--url",default=DEFAULT_URL); ap.add_argument("--out-dir",type=Path,default=Path("data/analyst_snapshots")); args=ap.parse_args()
    args.out_dir.mkdir(parents=True,exist_ok=True)
    if args.html: data=args.html.read_bytes(); path=args.html
    else:
        data=urlopen(Request(args.url,headers={"User-Agent":"Mozilla/5.0"}),timeout=30).read(); stamp=datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S"); path=args.out_dir/f"vip0_timeline_{stamp}.html"; path.write_bytes(data)
    days=parse_html(data); actions=[a for d in days for a in d["actions"]]
    report={"captured_at":datetime.now(BEIJING_TZ).isoformat(),"url":args.url,"snapshot_path":str(path),"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),"analyst_days":len(days),"analysts":sorted(set(d["analyst"] for d in days)),"dates":sorted(set(d["analysis_date"] for d in days)),"actions":len(actions),"entity_type_counts":{},"section_counts":{"daily_action":len(actions)},"unknown_samples":[]}
    for a in actions:
        typ=a["target"]["entity_type"]; report["entity_type_counts"][typ]=report["entity_type_counts"].get(typ,0)+1
    report["unknown_samples"]=[a for a in actions if a["target"]["entity_type"]=="UNKNOWN"][:20]
    (args.out_dir/"p0a_parsed_records.json").write_text(json.dumps({"days":days},ensure_ascii=False,indent=2)+"\n")
    (args.out_dir/"p0a_latest_audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
