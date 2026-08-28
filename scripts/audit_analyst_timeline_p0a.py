#!/usr/bin/env python3
"""Phase 0A audit for vip0_timeline.html.
Only audits boundaries and snapshots; it does not score or normalize actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

BEIJING_TZ = timezone(timedelta(hours=8))
DEFAULT_URL = "https://reports.wmsora.vip/analysts/vip0_timeline.html"

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = Counter()
        self.ids = Counter()
        self.classes = Counter()
        self.text_chunks = []
        self.table_rows = 0
        self.in_script = False
        self.in_style = False
    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids[attrs["id"]] += 1
        for c in (attrs.get("class") or "").split():
            self.classes[c] += 1
        if tag == "tr": self.table_rows += 1
        if tag == "script": self.in_script = True
        if tag == "style": self.in_style = True
    def handle_endtag(self, tag):
        if tag == "script": self.in_script = False
        if tag == "style": self.in_style = False
    def handle_data(self, data):
        if data.strip() and not self.in_script and not self.in_style:
            self.text_chunks.append(data.strip())


def fetch(url: str, out_dir: Path) -> tuple[Path, bytes]:
    data = urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()
    stamp = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"vip0_timeline_{stamp}.html"
    path.write_bytes(data)
    return path, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--html", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("data/analyst_snapshots"))
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.html:
        data = args.html.read_bytes(); path = args.html
    else:
        path, data = fetch(args.url, args.out_dir)
    text = data.decode("utf-8", errors="replace")
    p = Parser(); p.feed(text)
    visible = " ".join(p.text_chunks)
    visible = re.sub(r"\s+", " ", visible)
    dates = sorted(set(re.findall(r"20\d{2}-\d{2}-\d{2}", visible)))
    counts = {}
    for label, pat in {
        "analyst": r"覆盖\s*(\d+)\s*位博主",
        "daily_analysis": r"(\d+)\s*次日分析",
        "stock_actions": r"(\d+)\s*个股操作",
        "date_range": r"(20\d{2}-\d{2}-\d{2})\s*~\s*(20\d{2}-\d{2}-\d{2})",
    }.items():
        m = re.search(pat, visible)
        counts[label] = m.groups() if m else None
    headers = re.findall(r"[^<>]{1,30}(?:个股|逻辑|操作建议|方向|日期|核心主线|趋势分析|推荐逻辑|最新持仓)[^<>]{0,30}", visible)
    report = {
        "snapshot_path": str(path),
        "captured_at": datetime.now(BEIJING_TZ).isoformat(),
        "url": args.url,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "html": {"tags": p.tags.most_common(20), "table_rows": p.table_rows, "class_counts": p.classes.most_common(40)},
        "summary_matches": counts,
        "date_literals": dates,
        "boundary_markers": sorted(set(headers))[:80],
        "visible_text_chars": len(visible),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    (args.out_dir / "p0a_latest_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

if __name__ == "__main__":
    main()
