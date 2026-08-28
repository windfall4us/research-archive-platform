# 0B.3: Security/Stock Master 设计（2026-08-28）

> 目标：统一 Security Master，供 Consensus Engine / 十大模型 / 问股 / RS 共用同一标准库。
> 原则：避免两套股票表（一个认 688521 一个不认）；Precision 优先；B3 先不上 FUZZY。

## 一、统一架构

```
Security Master (stock_master)
        │
        ├── 供 Consensus Engine
        ├── 供 十大模型
        ├── 供 问股
        └── 供 RS / Research Graph
```

任何子系统不建自己的股票表，只引用 Security Master。

## 二、数据源优先级（用户决策 D）

1. **第一优先：现有金融数据 API / 平台股票基础库**（hithink-finance，与现有平台同源）
2. **第二优先：同花顺标的检索**（symbol search 消歧）
3. **第三优先：人工 alias 表**（补充社区别名）

避免：Consensus 一套表、十大模型另一套、问股再一套 → 名称/退市状态/代码后缀/ETF 混入。

## 三、表结构 v1

### stock_master（主表）
```sql
CREATE TABLE stock_master (
    stock_code       TEXT PRIMARY KEY,      -- 6位 如 688521
    stock_name       TEXT NOT NULL,          -- 标准简称 如 芯原股份
    exchange         TEXT NOT NULL,          -- SSE / SZSE / BSE
    full_code        TEXT NOT NULL UNIQUE,   -- 688521.SH / 000001.SZ
    short_name       TEXT,                   -- 更短简称 如 芯原
    security_type    TEXT NOT NULL DEFAULT 'STOCK',  -- STOCK/ETF/INDEX/BOND/FUND/OTHER
    list_status      TEXT DEFAULT 'LISTED',  -- LISTED/DELISTED/SUSPENDED/UNKNOWN
    aliases_json     TEXT,                   -- 冗余索引（主数据存 stock_aliases）
    source           TEXT NOT NULL,          -- hithink/tushare/manual
    source_updated_at TEXT,
    created_at       TEXT,
    updated_at       TEXT
);
-- 全市场约 5000+ 行
```

### stock_aliases（别名表，独立存储而非塞主表）
```sql
CREATE TABLE stock_aliases (
    alias          TEXT PRIMARY KEY,
    stock_code     TEXT NOT NULL REFERENCES stock_master(stock_code),
    alias_type     TEXT NOT NULL,   -- SHORT_NAME / MANUAL_ALIAS / COMMUNITY_ALIAS / PREV_NAME / ABBR
    confidence     REAL DEFAULT 0.8,
    source         TEXT,            -- manual / community / auto_candidate
    review_status  TEXT DEFAULT 'PENDING',  -- PENDING/APPROVED/REJECTED
    created_at     TEXT,
    updated_at     TEXT
);
-- 例：芯原 → 688521 SHORT_NAME / 中芯 → 688981 MANUAL_ALIAS / 小寒武纪 → 688256 COMMUNITY_ALIAS
```

## 四、对象分类（entity_type）与代码解析分层

### entity_type（0B.4，先定枚举）
```
STOCK / ETF / INDEX / THEME / MARKET / UNKNOWN
（security_type 预留，避免遇到"大盘ETF/科创50"重构）
```

### 匹配方法（Precision 优先，用户决策 E）
```
EXACT       自动通过   芯原股份 → 688521
ALIAS       自动通过   芯原 → 芯原股份（必须人工维护/审核，不放任模糊）
CONTEXT     高置信通过 结合核心主线/逻辑上下文消歧重名
FUZZY       默认 review 绝不直接判 STOCK
UNRESOLVED  不计算     保留原文，进人工队列
```

### 判定阈值（第一版保守）
```
EXACT    命中 → 直接通过
ALIAS    命中且 confidence≥0.9 → 通过；否则 review
CONTEXT  高置信才通过
FUZZY    一律 review
UNKNOWN  不计算
```

## 五、Gold Sample 中的 STOCK 样本（B3 首测基准）

gold_sample_100.csv 中：
- entity_type_draft=STOCK：97 条
- 其中带代码（has_code=True）：11 条
- 其余 86 条需名称解析（EXACT/ALIAS 目标）

健康首测结果期望：
```
Gold STOCK 样本：97
EXACT 命中：~70
ALIAS 命中：~15
未解析：~10
误解析：0
→ Recall ≈ 88%，Precision = 100%
```

宁可 `Recall 89% / Precision 100%`，不要 `Recall 99% / Precision 94%`。
（共识引擎是 Precision 优先系统：漏 1 条 = 少信号；把 A 认成 B = 制造错误共识。）

## 六、实施顺序（B3.1 → B3.2 → B3.3 → 首测）

```
B3.1  建表 stock_master + stock_aliases（SQL，本项目库 or 独立 db）
B3.2  实现 EXACT 匹配（名称 → 代码）
B3.3  实现 ALIAS 匹配（别名 → 代码，人工 alias 表驱动）
B3.4  用 Gold Sample 97 条 STOCK 跑第一次测试 → Recall/Precision
```

## 七、待确认（下一步需要你拍板）

1. **库位置**：新建独立 `security_master.db`，还是并入现有 stocks.db / 研究档案库？
2. **全量导入**：是否现在跑一次 hithink `symbol list` 全量导出（5000+ 行）入库？
3. **alias 来源**：第一版人工 alias 表我出初稿（从 Gold Sample 未解析名称开始），你审核？
