#!/usr/bin/env python3
"""0B.3 步骤②: 从同花顺 API /api/meta/tickers/list 全量拉取 A 股 → staging。

链路: API → raw_a_share_full.json → staging(校验前) → (后续脚本校验) → stock_master
只拉 asset_type=a-share；ETF/指数/港股保留在 staging 不进入 STOCK EXACT 基准。
"""
import json, os, time, urllib.request, urllib.error
from pathlib import Path

BASE = "https://fuyao.aicubes.cn"
OUT = Path("/home/windfall/workspace/research-archive-platform/data/security_staging/raw_a_share_full.json")
OUT.parent.mkdir(parents=True, exist_ok=True)


def get_key():
    env = os.environ.get("HITHINK_FINANCE_API_KEY")
    if env: return env
    cred = os.path.expanduser("~/.config/hithink-finance/credentials.env")
    if os.path.exists(cred):
        for line in open(cred):
            line = line.strip()
            if not line: continue
            if line.startswith("HITHINK_FINANCE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
            return line
    return None


KEY = get_key()
HEADERS = {"X-api-key": KEY, "User-Agent": "Mozilla/5.0"}


def api_get(path, retries=4):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(BASE + path, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 4001, 5001, 5002, 5003) and attempt < retries - 1:
                time.sleep(6 * (attempt + 1)); continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < retries - 1:
                time.sleep(6 * (attempt + 1)); continue
            raise


def main():
    all_rows = []
    limit, offset = 1000, 0
    while True:
        r = api_get(f"/api/meta/tickers/list?asset_type=a-share&limit={limit}&offset={offset}")
        code = r.get("code")
        if code != 0:
            print(f"error code={code} msg={r.get('message')}", flush=True)
            break
        data = r.get("data") or {}
        rows = data.get("item") or data.get("items") or data.get("list") or []
        all_rows.extend(rows)
        print(f"offset={offset} 累计={len(all_rows)} (本批 {len(rows)})", flush=True)
        if len(rows) < limit:
            break
        offset += limit
        time.sleep(0.3)

    OUT.write_text(json.dumps(all_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n完成: 共 {len(all_rows)} 条 → {OUT}")
    if all_rows:
        print("字段:", list(all_rows[0].keys()))
        print("样例:", json.dumps(all_rows[0], ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
