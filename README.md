# 📚 资讯研究档案库 · Research Archive Platform

> **事件驱动型 A 股研究决策辅助平台**
> 从 Telegram 六源资讯自动构建「事件 → 个股 → 研究排序 → 人工决策」完整闭环。

![version](https://img.shields.io/badge/version-v2.3.4e-blue)
![status](https://img.shields.io/badge/status-observation_lock-green)

---

## ✨ 系统定位

不是简单的新闻阅读工具，而是面向 A 股研究与交易决策辅助的**事件驱动研究系统**：

```
资讯采集 → 分类 → 事件 → 来源可信 → 传播链 → Momentum
→ 股票映射 → 事件催化 → 十大模型 → Research Score → Research Summary
→ 每日简报 → T+验证反馈 → 人工决策
```

**核心能力**：
- 资讯自动分类归档（8 主类型互斥）
- 事件语义聚类 + 传播链溯源
- 事件热度（Momentum）实时监测
- 事件→个股映射 + 持仓联动
- 十大模型融合的 Research Score 研究排序
- **研究对象中心（v2.3.0）**：多来源研报归并为研究文档
- **行业实体化（v2.3.2）**：三级行业树，解决「关键词命中≠行业关系」
- **研究图谱（v2.3.3）**：5 实体（文档/股票/事件/行业/机构）互连 + Graph Score
- **观察仪表盘（v2.3.4）**：市场环境判定 + 系统快照 + 每日观察日报
- 每日研究简报自动推送（Hermes Skill）
- T+1/T+3/T+5 研究后验验证

---

## 🚀 快速开始（复刻步骤）

### 前置环境

| 组件 | 版本/说明 |
|---|---|
| 服务器 | Linux VPS（Debian 12 实测） |
| Python | 3.11+（sqlite3 内置） |
| Hermes Agent | 用于 cron 调度 + 每日简报 Skill |
| 数据源 | Telegram 六源导出（vip1_cache.json 格式） |
| 前端 | Node.js + npm（构建 ArchivePage） |

### 第 1 步：拉取代码

```bash
git clone https://github.com/<your>/research-archive-platform.git
cd research-archive-platform
```

### 第 2 步：准备数据源

将 Telegram 六源导出放入 `/root/workspace/vip1_cache.json`：

```json
[
  {
    "chat_id": "-1001234567890",
    "message_id": 123,
    "content": "【天风通信】永鼎股份涨停点评：...",
    "time": "2026-08-12 12:58:45",
    "type": "text",
    "topic": "热点发现",
    "from": "fs2tg"
  }
]
```

> 字段：`chat_id` / `message_id` / `content`（文本或图片 caption）/ `time` / `type`（text|image）/ `topic` / `from`

### 第 3 步：初始化数据库

```bash
cd scripts
# ① 完整建库（18 张表，幂等）
python3 archive_schema_init.py

# ② 依序执行版本迁移（加列，幂等）
python3 archive_v14_migrate.py   # 分类维度列 + event 表
python3 archive_v15_migrate.py   # 事件评分/状态列
python3 archive_v16_migrate.py   # 事件-股票关系表
python3 archive_v17_migrate.py   # 动量表 + 触发点列
python3 archive_v18_migrate.py   # 研究队列表
python3 archive_v19_migrate.py   # 研究评分表
python3 archive_v20_migrate.py   # 研究结论表
python3 archive_v21_migrate.py   # 验证表
```

生成 `research_archive.db`（18+ 张表）。

> **外部依赖说明**：v16/v18/v19 阶段依赖两个可选数据源——
> ① 备选股池 `stocks.db`（股票名→代码映射，无则跳过股票扫描）
> ② 十大模型 API（`http://127.0.0.1:3100/api/models`，无则模型维度为 0）
> 两者缺失不影响主链路运行，仅对应维度为空。

### 第 4 步：跑数据管线

```bash
# 首次全量（顺序执行）
python3 archive_ingest_v2.py          # 入库+清洗
python3 archive_classify_v14.py       # 8类互斥分类
python3 archive_merge_v3.py           # 研报归并
python3 archive_events_v15.py         # 事件语义聚类
python3 archive_events_v16.py         # 事件→股票映射
python3 archive_momentum_v17.py       # 事件热度
python3 archive_watchpool_v18.py      # 研究队列
python3 archive_researchscore_v19.py  # Research Score
python3 archive_summary_v20.py        # 研究结论
python3 archive_validate_v21.py       # T+验证
python3 archive_backtest_v21b.py      # 历史回填验证

# v2.3 链尾三脚本（研究对象/行业/图谱）
python3 archive_doc_v230.py           # 研究对象归并
python3 archive_industry_v232.py      # 行业实体化
python3 archive_graph_v233.py         # 研究图谱 + Graph Score
```

### 第 4b 步：观察期每日任务

```bash
# 每日（cron）
30 21 * * * python3 /root/scripts/archive_quality_check_v223.py      # 质量检查
40 21 * * * python3 /root/scripts/archive_validation_snapshot_v234c.py # 验证快照
45 21 * * * python3 /root/scripts/archive_obs_report_v234d.py          # 观察日报
# 及 archive_obs_v234.py（观察模式统计）
```

### 第 5 步：启动 API 服务

```bash
# 方式 A：systemd（推荐）
cp deploy/research-archive.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now research-archive

# 方式 B：手动
python3 archive_server.py   # :8095
```

验证：`curl http://127.0.0.1:8095/research/api/dashboard/summary`

### 第 6 步：部署前端

```bash
# 将 frontend/ArchivePage.tsx 放入你的 Next.js/Vinext 项目 components/
# 参考 deploy/ 下的 nginx 配置
```

### 第 7 步：配置 cron

```bash
crontab -e
# 每 30 分钟跑数据管线（8:00-23:00）
*/30 8-23 * * * cd /root/workspace && \
  python3 /root/scripts/archive_ingest_v2.py && \
  python3 /root/scripts/archive_classify_v14.py && \
  python3 /root/scripts/archive_merge_v3.py && \
  python3 /root/scripts/archive_events_v15.py && \
  python3 /root/scripts/archive_events_v16.py && \
  python3 /root/scripts/archive_momentum_v17.py && \
  python3 /root/scripts/archive_watchpool_v18.py && \
  python3 /root/scripts/archive_researchscore_v19.py && \
  python3 /root/scripts/archive_summary_v20.py && \
  python3 /root/scripts/archive_validate_v21.py && \
  python3 /root/scripts/archive_backtest_v21b.py >> /var/log/research-archive.log 2>&1
```

### 第 8 步：Hermes 每日简报

```bash
# 安装 Skill
cp -r skill/research-daily-brief ~/.hermes/skills/research/

# 创建 cron（Hermes 内）
cronjob create \
  --name research-daily-brief \
  --schedule "0 9 * * *" \
  --skill research-daily-brief \
  --deliver telegram:<your_chat_id>
```

---

## 🏗️ 架构总览

```
Telegram 6源 → vip1_cache.json
        ↓
╔══════════════════════════════════════════╗
║ 数据管线（cron 每30min）                  ║
║ ① ingest_v2    入库+清洗                  ║
║ ② classify_v14 8类互斥分类                ║
║ ③ merge_v3     研报归并                  ║
║ ④ events_v15   事件语义聚类              ║
║ ⑤ events_v16   事件→股票映射             ║
║ ⑥ momentum_v17 事件热度                  ║
║ ⑦ watchpool_v18 研究队列                 ║
║ ⑧ score_v19    Research Score           ║
║ ⑨ summary_v20  研究结论                  ║
║ ⑩ validate_v21 T+验证                   ║
╚══════════════════════════════════════════╝
        ↓
archive_server.py (:8095) — 24 个 REST API
        ↓ nginx /archive/ → 8095
ArchivePage.tsx — 资讯研究终端（9 Tab）
        ↓
Hermes Skill — 每日简报 → Telegram
        ↓
人工研究决策（交易状态机保持人工）
```

---

## 📦 目录结构

```
research-archive-platform/
├── README.md                      # 本文件
├── LICENSE
├── docs/
│   ├── 系统说明书.md               # 完整使用说明书
│   ├── 数据流设计图.md             # 数据管线全图
│   ├── 数据清洗阶段.md             # 清洗阶段说明
│   ├── VERSION.md                  # 版本与参数冻结
│   ├── CHANGELOG.md                # 版本演进
│   └── v2.2.1_观察期说明.md        # 观察期定义
├── scripts/                       # 数据管线 30+ 个脚本
│   ├── archive_schema_init.py     # 完整建库（第一步，24 表）
│   ├── archive_init_v1.py         # 初始建库（兼容旧版）
│   ├── archive_ingest_v2.py       # 入库+清洗
│   ├── archive_classify_v14.py    # 8类分类
│   ├── archive_merge_v3.py        # 研报归并
│   ├── archive_events_v15.py      # 事件聚类
│   ├── archive_events_v16.py      # 事件→股票映射
│   ├── archive_momentum_v17.py    # 事件热度
│   ├── archive_watchpool_v18.py   # 研究队列
│   ├── archive_researchscore_v19.py # Research Score
│   ├── archive_summary_v20.py     # 研究结论
│   ├── archive_validate_v21.py    # T+验证
│   ├── archive_backtest_v21b.py   # 历史回填验证
│   ├── archive_quality_check_v223.py # 质量检查（观察期）
│   ├── archive_doc_v230.py        # 研究对象归并
│   ├── archive_industry_v232.py   # 行业实体化
│   ├── archive_graph_v233.py      # 研究图谱 + Graph Score
│   ├── archive_obs_v234.py        # 观察模式统计
│   ├── archive_validation_snapshot_v234c.py # 验证快照
│   ├── archive_obs_report_v234d.py # 观察日报
│   ├── archive_server.py          # REST API（29 端点）
│   ├── institution_map.py         # 机构名标准化
│   └── archive_v{14..21}_migrate.py # 版本迁移脚本
├── frontend/
│   └── ArchivePage.tsx            # 资讯研究终端组件
├── skill/
│   └── research-daily-brief/      # Hermes 每日简报 Skill
│       ├── SKILL.md
│       ├── scripts/generate_brief.py
│       └── references/brief_sample.md
├── deploy/
│   ├── research-archive.service   # systemd 单元
│   ├── nginx-archive.conf         # nginx 反代
│   └── crontab.example            # cron 配置示例
└── requirements.txt               # Python 依赖（stdlib only）
```

---

## 🧠 核心概念

### 8 主类型（content_type 互斥）
`research_report`（正式研报）· `institution_view`（券商观点）· `research_activity`（调研纪要）· `news`（新闻）· `announcement`（正式公告）· `market`（行情）· `digest`（汇总复盘）· `attachment`（图片）

### 消息角色（message_role）
`original`（原始）· `forward`（转发）· `summary`（汇总）· `commentary`（解读）· `attachment`（附件）

### 事件系统
- **语义聚类**：实体归一（SK海力士→海力士）+ 跨日归并
- **传播链**：首发→机构确认→扩散→A股映射（lead_time 机构领先分钟数）
- **Momentum**：消息速度25% + 新来源20% + 新机构20% + 股票映射15% + 机构响应10% + 时长衰减10%
- **触发点**：FIRST_INSTITUTION / STOCK_EXPANSION / CONSENSUS_BUILD / HEAT_BREAKOUT

### Research Score（研究综合分，100 分制）
```
事件强度 30 + 十大模型 35 + 技术状态 20 + 资金状态 15
状态：重点研究(90+) / 优先跟踪(80+) / 观察(70+) / 普通(60+) / 忽略(<60)
研究状态（独立于交易）：cold→warming→focused→confirmed→fading
```

### 研究队列状态机
```
EVENT_FOUND → RESEARCH → WATCH → MODEL_CHECK → TRIAL_READY
```

### 研究对象（v2.3.0）
多来源研报按「标题相似>90% + 同股票 + 24h 内」归并为研究文档，质量评分：
```
机构 +30 / 研报调研 +20 / 股票明确 +20 / 摘要完整 +15
重复转发>3 条 -20 / 无来源无股票 -30（<50 不进重点研究）
```

### 行业实体化（v2.3.2）
三级行业树（industry_entity），文档↔行业通过实体关系关联（非关键词命中），
Industry Momentum = 行业关联文档的事件热度聚合。

### 研究图谱（v2.3.3）
5 实体互连：`Research Document ↔ Stock / Event / Industry / Institution`
7 类边：in / belongs_to / impact / confirmed_by / involves / published_by / mentions
```
Graph Score（研究影响力，辅助指标不进 RS）：
GS = min(100, 机构×4 + 文档×3 + 事件×2 + 股票×2 + 行业×1)
```

### 图谱统计优化（v2.3.4）
① 行业贡献拆分（热度去重）② 股票中心度 ③ 机构研究雷达 ④ 研究对象可信度 ⑤ GS 时间趋势

### 研究验证
- T+1 / T+3 / T+5 表现 + 最大涨幅/回撤
- 结果：hit / miss / flat / pending
- RS 分层有效性分析（数据反馈优化 v2.3 的基础）

---

## 🔒 安全边界

```
✅ 自动采集  ✅ 自动分类  ✅ 自动分析  ✅ 自动排序  ✅ 自动简报
❌ 自动买入  ❌ 自动卖出  ❌ 自动改持仓  ❌ 自动交易
```

- Research Score 回答「值不值得重点研究」，不是「是否买入」
- 交易状态机 `WATCH→TRIAL→ADD_1→ADD_2→HOLD` 始终人工确认
- 所有输出带「研究辅助 · 非投资建议」

---

## 📖 文档索引

| 文档 | 说明 |
|---|---|
| [docs/系统说明书.md](docs/系统说明书.md) | 完整使用说明书（20 章，v2.3.4e） |
| [docs/数据流设计图.md](docs/数据流设计图.md) | 数据管线全图（8 阶段） |
| [docs/数据清洗阶段.md](docs/数据清洗阶段.md) | 清洗阶段详解 |
| [docs/VERSION.md](docs/VERSION.md) | 版本与参数冻结 |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | 版本演进记录（至 v2.3.4e） |

---

## 🛠️ 运维

```bash
# API 服务
systemctl restart research-archive

# 前端构建（vinext）
cd /opt/watchlist-stock-analysis
rm -rf .vinext && npm run build
systemctl restart watchlist-stock-analysis

# 数据库备份
cp /root/workspace/research_archive.db /backup/research_archive_$(date +%Y%m%d).db
```

---

## 📝 版本

| 版本 | 里程碑 |
|---|---|
| v1.3-v1.4 | 资讯分类库 / 研究档案库 |
| v1.5-v1.6 | 事件驱动 / 个股联动 |
| v1.7-v1.8 | Momentum / 研究队列 |
| v1.9-v2.0 | Research Score / 研究终端 |
| v2.1-v2.2 | 验证体系 / 每日简报 |
| v2.2.2 | 研究队列股票级聚合 |
| v2.3.0 | 研究对象归并（数据治理层） |
| v2.3.1 | 机构研究 Tab → 研究对象中心 |
| v2.3.2 | 行业实体化（三级行业树） |
| v2.3.3 | 研究图谱融合 + Graph Score |
| v2.3.4 | 图谱统计优化 + 观察模式 |
| v2.3.4c | 验证快照完整化（可解释层） |
| v2.3.4d | 每日观察日报 |
| v2.3.4e | Quality Center + 市场环境判定 |
| v4.3.0 | 问股 Strategy Engine |
| **v2.3.4e** | **Observation Lock（当前）** |

---

## ⚠️ 免责声明

本项目为**研究辅助工具**，所有输出不构成任何投资建议。股市有风险，决策需谨慎。交易决策请基于独立判断。
