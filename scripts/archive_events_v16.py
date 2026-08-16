#!/usr/bin/env python3
"""资讯研究档案库 v1.6 - Event→Stock 映射生成器
从 event 关联消息提取股票代码/名称，判定 relation_type + impact_score，
写入 event_stock_relation。联动 stocks.db（名称/行业/逻辑）+ 持仓标记。
2026-08-12
"""
import json, re, sqlite3, sys
from datetime import datetime

DB = "/root/workspace/research_archive.db"
STOCKS_DB = "/root/stock-kanban/backend/stocks.db"

# 受益/利空关键词 → relation_type
BENEFIT_WORDS = ['受益', '利好', '催化', '订单', '中标', '涨价', '景气', '需求', '扩产', '放量',
                 '供不应求', '份额提升', '进入', '供应链', '直接受益', '核心受益', '弹性']
RISK_WORDS = ['利空', '风险', '减持', '处罚', '立案', '停产', '下滑', '亏损', '不及预期', '制裁', '关税', '被诉']
CHAIN_WORDS = ['产业链', '上下游', '配套', '环节', '联动', '相关']


def detect_relation(text, code, name):
    """判定单股关联类型：直接受益 > 风险影响 > 产业链 > 竞争影响"""
    t = text or ""
    if name and name in t:
        # 找到该股附近的上下文（前后 60 字）
        idx = t.find(name)
        ctx = t[max(0, idx - 40): idx + len(name) + 60]
    else:
        ctx = t
    risk_hits = [w for w in RISK_WORDS if w in ctx]
    benefit_hits = [w for w in BENEFIT_WORDS if w in ctx]
    if risk_hits and not benefit_hits:
        return "风险影响", risk_hits
    if benefit_hits:
        return "直接受益", benefit_hits
    if any(w in ctx for w in CHAIN_WORDS):
        return "产业链", []
    return "产业链", []


def impact_of(ev_score, mention, n_msg, relation_type):
    """impact_score：事件评分 × 提及权重 × 关系权重"""
    base = ev_score or 50
    mention_w = min(1.2, 0.7 + mention * 0.15)
    rel_w = {"直接受益": 1.0, "风险影响": 0.9, "产业链": 0.7, "竞争影响": 0.5}.get(relation_type, 0.7)
    return min(100, int(base * mention_w * rel_w))


def main():
    con = sqlite3.connect(DB)
    # 股票名 → 代码 映射（stocks.db 268 只 + 内置常见）
    name2code = {}
    try:
        scon = sqlite3.connect(STOCKS_DB)
        for sym, name in scon.execute("SELECT symbol, name FROM stocks WHERE name IS NOT NULL").fetchall():
            name2code[name] = str(sym)
        scon.close()
    except Exception as e:
        print("stocks.db 读取失败:", e)

    # 清空旧映射（重建）
    con.execute("DELETE FROM event_stock_relation")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    events = con.execute("""
        SELECT e.event_id, e.event_title, e.event_type, e.event_score, e.themes_json,
               e.stock_codes_json, e.occurred_date, e.update_count
        FROM event_clusters e WHERE e.merge_status != 'manual_merged'
    """).fetchall()

    created = 0
    for eid, title, etype, ev_score, themes_json, codes_json, odate, n_msg in events:
        # 1) 事件已聚合的股票代码
        codes = []
        try:
            codes = json.loads(codes_json or "[]")
        except Exception:
            codes = []
        # 2) 从事件消息里再扫股票名（stocks.db 名匹配）
        #    排除 digest/market 类消息：隔夜要闻/昨日热点/盘面综述/概念股罗列/连板结构
        #    的股票名是「昨日涨停板块汇总」，不代表与事件真实关联（如 北京文化←英伟达事件 误关联）
        msgs = con.execute("""
            SELECT r.raw_text, COALESCE(c.content_type, '') FROM event_messages em
            JOIN raw_messages r ON r.chat_id||':'||r.message_id = em.message_id
            LEFT JOIN message_classification c ON c.message_id = em.message_id
            WHERE em.event_id=?""", (eid,)).fetchall()
        # 只保留非 digest/market 的消息用于股票扫描；
        # 另排除含罗列特征词的 news（概念股汇总/相关公司/连板/昨日热点编号罗列 等）
        # 编号罗列模式：『1、xxx』『8、电影：…』——多主题快讯的板块/热点罗列
        ROSTER_PAT = re.compile(
            r'(概念股|概念谷|相关公司|连板|昨日热点|盘面|板块汇总|标的：|相关标的'
            r'|(?:^|\n)\s*\d{1,2}[、\.．]\s*[\u4e00-\u9fa5A-Za-z]{2,12}[：:])')
        texts = []
        for m in msgs:
            ct = m[1]
            txt = m[0] or ""
            if ct in ("digest", "market"):
                continue
            if ROSTER_PAT.search(txt):
                continue
            texts.append(txt)
        all_text = "\n".join(texts)
        # 名字 → 代码（过滤非真实股票：6位数字需符合 A股代码规则）
        valid_codes = set(name2code.values())
        def is_astock_code(c):
            # 6开头(沪A/科创688) / 0开头(深A) / 3开头(创业板)
            return re.fullmatch(r'(6\d{5}|0\d{5}|3\d{5})', c or "") is not None
        # 从消息文本扫 stocks.db 股票名 → 补代码
        for name, code in name2code.items():
            if code in codes or len(name) < 2:
                continue
            if name in all_text:
                codes.append(code)
        filtered = []
        for c in codes:
            if c in valid_codes or is_astock_code(c):
                filtered.append(c)
        codes = list(dict.fromkeys(filtered))
        if not codes:
            continue
        # 每只股票统计提及次数 + 逻辑
        for code in codes:
            name = next((n for n, c in name2code.items() if c == code), "")
            mention = all_text.count(name) if name else all_text.count(code)
            if name:
                mention += all_text.count(code)
            mention = max(1, mention)
            relation_type, hits = detect_relation(all_text, code, name)
            impact = impact_of(ev_score or 50, mention, n_msg or 1, relation_type)
            # 逻辑：提及该股的句子（截取含股票名的句子）
            logic = ""
            if name:
                for line in all_text.split("\n"):
                    if name in line:
                        logic = re.sub(r'\s+', ' ', line).strip()[:120]
                        break
            if not logic and hits:
                logic = f"事件文本含关键词：{'/'.join(hits[:4])}"
            con.execute("""INSERT OR REPLACE INTO event_stock_relation
                (event_id, stock_code, stock_name, relation_type, source, confidence,
                 impact_score, logic, mention_count, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (eid, code, name, relation_type, "auto", 0.7, impact, logic, mention, now))
            created += 1
    con.commit()
    print(f"✅ v1.6 事件→股票映射: {created} 条关系")
    # 分布
    print("  relation_type:", dict(con.execute("SELECT relation_type, COUNT(*) FROM event_stock_relation GROUP BY 1").fetchall()))
    # 有映射的事件数
    print("  覆盖事件:", con.execute("SELECT COUNT(DISTINCT event_id) FROM event_stock_relation").fetchone()[0],
          "/", con.execute("SELECT COUNT(*) FROM event_clusters").fetchone()[0])
    # 样本
    print("  高 impact 样本:")
    for r in con.execute("""SELECT e.event_title, r.stock_code, r.stock_name, r.relation_type, r.impact_score, r.logic
        FROM event_stock_relation r JOIN event_clusters e ON e.event_id=r.event_id
        ORDER BY r.impact_score DESC LIMIT 8""").fetchall():
        print(f"    [{r[4]}分|{r[3]}] {r[1]} {r[2]} ← {r[0][:28]}")
        print(f"       {r[5][:60] if r[5] else ''}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
