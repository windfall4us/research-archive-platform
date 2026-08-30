# run_consensus_pipeline.py 设计文档 — Phase 1~4 自动化总控

> 状态：✅ 已实现并验证（commit 1f9208c + 1852ce1 + 待提交，2026-08-30）
> dry-run 全链路 GO 验证通过；真实发布验证通过（生产+测试盒 snapshot 一致、API latest_date=2026-08-29、HTML 公网 200）
> cron 已切换：22:50/23:20 由「只发布」升级为「总控运行」（旧 publisher cron 已停用，publish 保留为总控子程序）

## 目标

把「手动跑 Phase 1~4 → 发布器自动发布」升级为「Phase 1~4 自动运行 → 全链路 GO → 才调用发布器」。
最终：`run_consensus_pipeline.py` 单命令完成当日全链路，供 Hermes cron 调用。

## 职责边界（用户锁定）

```
run_consensus_pipeline.py  = 调度 + Gate + 决定是否发布
publish_consensus_daily.py = 只负责物化和发布（总控最后一步的子程序，不单独挂 cron）
```

## 编排结构（用户锁定）

```
run_consensus_pipeline.py
├─ [Phase 0] 前置审计：产物新鲜 + 目标交易日校验（该日 timeline 快照已归档 & 最新快照对齐）
├─ [Phase 1] Data Layer      — create schema → 3 ingest → acceptance → benchmark_phase1_p15
├─ [Phase 2] Market+Theme    — benchmark_phase2_p24（内嵌重算 p20b→p21→p22a→p22b→p22c→p23）
├─ [Phase 3] Stock Consensus — benchmark_phase3_p34（内嵌重算 p31→p32→p33）
├─ [Phase 4] Cross-Layer     — benchmark_phase4_p44（内嵌重算 p41→p42→p43）
├─ [Overall Gate] 4 个 benchmark 全 GO
└─ [Publish]     publish_consensus_daily.py（仅 overall GO 时调用；--force 透传）
```

## 关键发现（来自脚本审计）

- **benchmark 内嵌重算**：P3.1/P3.2/P3.3/P4.1/P4.2/P4.3 的 benchmark 都会 subprocess 调用对应主脚本先重算再验证。
  Phase 2 总 benchmark 也 subprocess 调用 p20b→p21→p22a→p22b→p22c→p23 全部重算。
  → 总控只需按序调用各阶段 benchmark，无需单独跑 pipeline 脚本（benchmark 即 pipeline+验证）。
- **Phase 1 特殊**：benchmark_phase1_p15 会重跑 3 个 ingest（幂等验证），且 Phase 1 产物是 DB（analyst_consensus.db），
  ingest 需要 timeline 快照（`data/analyst_snapshots/vip0_timeline_YYYYMMDD.json`）。
- **新鲜窗口**：publish 已用 `--max-age-hours 36` 审计 10 个 Phase1~4 JSON 产物。
- **退出码约定**：benchmark exit 0 = GO；1 = NO-GO。

## 核心原则（用户锁定）

1. 任一 Phase `NO-GO` → **停止，不发布**（不调用 publish）
2. 旧 snapshot 保持在线，不覆盖
3. 全部 GO → 才调用 publisher
4. 每阶段保留独立日志与耗时
5. 同一交易日重复运行幂等
6. 成功静默
7. 失败 Telegram 告警
8. 不因为单个展示层问题回改冻结算法

## 并发保护（2026-08-30 新增，用户锁定 4 项）

1. **同日锁**：`logs/consensus_pipeline/run.lock`（fcntl flock LOCK_EX|LOCK_NB）。
   22:50 主任务尚未结束时 23:20 撞锁 → 静默 exit 0（不并发、不抢发布）。
2. **run_id + 日期日志**：run_id=`YYYYMMDD-HHMMSS` 写入当日日志头部 + 耗时报告；
   日志目录 `logs/consensus_pipeline/YYYY-MM-DD.log`（Telegram 告警可直接引用）。
3. **目标交易日校验**：`--target-date`（默认北京今天）的 timeline 快照必须已归档
   （`data/analyst_snapshots/vip0_timeline_<date>.json`）且最新快照日期与目标对齐，
   否则 exit 2 → **绝不拿旧日完整产物通过 Gate 后误发布**；旧 snapshot 保持在线不覆盖。
   未归档场景：不带 `--alert` 静默（主检测 22:50）；带 `--alert` 告警（补偿 23:20）。
4. **旧 cron 禁用而非并存**：新总控 cron 创建成功后才停用旧 publisher cron。

## CLI

```
python3 scripts/run_consensus_pipeline.py                 # 默认：全链路 + publish
python3 scripts/run_consensus_pipeline.py --alert         # 补偿检测：产物/目标日未就绪也告警（23:20 用）
python3 scripts/run_consensus_pipeline.py --target-date 2026-08-29  # 指定目标交易日（默认=北京今天）
python3 scripts/run_consensus_pipeline.py --force         # 透传 publish：强制发布（跳过 md5 防重复）
python3 scripts/run_consensus_pipeline.py --dry-run       # 只跑 Phase1~4 + 各 benchmark，不 publish
python3 scripts/run_consensus_pipeline.py --no-publish    # 同 dry-run（别名）
python3 scripts/run_consensus_pipeline.py --no-telegram   # 禁用 Telegram 告警（仅日志）
python3 scripts/run_consensus_pipeline.py --max-age-hours 48
```

退出码：0 = 全链路 GO（已 publish）/ dry-run 通过 / 撞锁静默跳过；
1 = 失败（已告警）；2 = 产物/目标交易日数据未就绪（不带 --alert 静默；带 --alert 已告警）。

## 阶段日志与耗时

- 每阶段独立日志：`logs/consensus_pipeline/<date>.log`（全量）+ 每阶段耗时表
- 耗时写入 `reports/consensus_pipeline_runtime_<date>.json`（含 run_id）

## 幂等

- Phase1~4 各脚本幂等（INSERT ON CONFLICT / DROP+CREATE+INSERT）
- snapshot 幂等 → publish 防重复用「内容指纹」：排除 `meta.generated_at`（派生自产物 mtime，
  Phase 1~4 每次重算刷新 mtime 致整文件 md5 变化）→ 跨运行内容一致即 SKIPPED，线上稳定不重复上传
- 总控整体：同交易日重复运行 → 各阶段 benchmark 幂等重算 → publish 防重复静默（SKIPPED）

## cron 切换（2026-08-30 完成）

```
原：22:50 publish_consensus_main.py         → 停用（paused）
    23:20 publish_consensus_compensate.py   → 停用（paused）
现：22:50 run_consensus_main.py    (无 --alert，静默)  → 总控主检测（job ff81b327f916）
    23:20 run_consensus_compensate.py (--alert，告警)  → 总控补偿检测（job 2cd4db162274）
```

- 22:50 主：Phase 1~4 → Overall GO → publish；上游未就绪静默 exit 2；失败告警
- 23:20 补偿：已完成同日结果 → publish 内容指纹 SKIPPED；上游此时就绪 → 完整补跑+发布；
  仍未就绪 / NO-GO → Telegram 告警

## 告警

复用 publish_consensus_daily.py 的 `send_telegram_alert`（import 复用）。失败阶段 + 错误摘要 + 时间 + 产物 mtime。
NO-GO 始终告警；产物/目标日未就绪仅 `--alert`（补偿）时告警。纯文本发送（禁 parse_mode，`*` 触发 Markdown 解析 400）。

## 依赖

- `sys.executable` 为 Hermes venv python（含 paramiko）
- 输入：`data/analyst_snapshots/vip0_timeline_*.json`（上游采集，archive_analyst_daily.py 22:40 归档）
- 输出：Phase1~4 JSON（10 个）+ snapshot + HTML
