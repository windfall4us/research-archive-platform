# 📚 资讯研究档案库 · Research Archive Platform

> **事件驱动型 A 股研究决策辅助平台**
> 从 Telegram 六源资讯自动构建「事件 → 个股 → 研究排序 → 人工决策」完整闭环。

![version](https://img.shields.io/badge/version-v2.2.1-blue)
![status](https://img.shields.io/badge/status-stability_observation-green)

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
# 依序执行迁移（建表 + 加列，幂等）
python3 archive_v14_migrate.py   # 分类维度列 + event 表
python3 archive_v15_migrate.py   # 事件评分/状态列
python3 archive_v16_migrate.py   # 事件-股票关系表
python3 archive_v17_migrate.py   # 动量表 + 触发点列
python3 archive_v18_migrate.py   # 研究队列表
python3 archive_v19_migrate.py   # 研究评分表
python3 archive_v20_migrate.py   # 研究结论表
python3 archive_v21_migrate.py   # 验证表
```

生成 `research_archive.db`（19 张表）。

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
├── scripts/                       # 数据管线 21 个脚本
│   ├── archive_ingest_v2.py
│   ├── archive_classify_v14.py
│   ├── archive_merge_v3.py
│   ├── archive_events_v15.py
│   ├── archive_events_v16.py
│   ├── archive_momentum_v17.py
│   ├── archive_watchpool_v18.py
│   ├── archive_researchscore_v19.py
│   ├── archive_summary_v20.py
│   ├── archive_validate_v21.py
│   ├── archive_backtest_v21b.py
│   ├── archive_server.py           # REST API
│   ├── institution_map.py          # 机构名标准化
│   └── archive_v{14..21}_migrate.py # 迁移脚本
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
| [docs/系统说明书.md](docs/系统说明书.md) | 完整使用说明书（17 章） |
| [docs/数据流设计图.md](docs/数据流设计图.md) | 数据管线全图（8 阶段） |
| [docs/数据清洗阶段.md](docs/数据清洗阶段.md) | 清洗阶段详解 |
| [docs/VERSION.md](docs/VERSION.md) | 版本与参数冻结 |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | 版本演进记录 |

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
| v2.2.1 | **稳定观察期（当前）** |

---

## ⚠️ 免责声明

本项目为**研究辅助工具**，所有输出不构成任何投资建议。股市有风险，决策需谨慎。交易决策请基于独立判断。
