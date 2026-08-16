# 资讯研究档案库 版本说明（VERSION.md）

| 字段 | 值 |
|---|---|
| **生产版本** | v2.2 |
| **运行阶段** | v2.2.1 Stability Observation（稳定观察期） |
| **代码状态** | 冻结（Frozen） |
| **数据状态** | 持续积累 |
| **验证机制** | 每日自动（cron 全链路） |
| **观察周期** | 2-4 周（约 20 个交易日） |

## 版本演进

```
v1.3  资讯分类库
v1.4  研究档案库（8 主类型互斥）
v1.4.2 来源可信库（message_role）
v1.5  事件驱动研究系统（语义事件 75 + 传播链）
v1.6  事件-个股智能联动（event_stock_relation 829）
v1.7  Event Momentum（六维热度 + 触发点）
v1.8  Event Watch Pool（52 候选 + 状态机）
v1.8.1 Stock Event Catalyst（个股事件催化）
v1.9  Research Score（事件30+模型35+技术20+资金15）
v1.9.1 Research Evolution（历史快照 + score_change + research_state）
v2.0  Event Driven Research Terminal（今日驾驶舱 + Research Summary）
v2.1  Research Validation（T+1/T+3/T+5 后验验证）
v2.2  Hermes Research Agent（每日 09:00 研究简报）
v2.2.1 Stability Observation（当前：观察期，参数冻结）
```

## 核心参数版本（观察期冻结）

| 模块 | 版本 | 说明 |
|---|---|---|
| 分类 | classify v1.4 | 8 主类型互斥 + message_role |
| 事件 | events v1.5 | 语义聚类 + cluster_confidence |
| 动量 | momentum v1.7 | 六维加权 + 触发点 |
| 候选 | watchpool v1.8 | EVENT_FOUND→RESEARCH→WATCH→MODEL_CHECK→TRIAL_READY |
| 评分 | research_score v1.9 | 事件30% + 十模型35% + 技术20% + 资金15% |
| 结论 | summary v2.0 | Research Summary 自动生成 |
| 验证 | validation v2.1 | T+1/T+3/T+5 + 命中率 |
| 简报 | brief v2.2 | 每日 09:00 Telegram |

**冻结声明**：观察期内不修改上述任何参数/权重/算法，保证数据可比性。
