# run_consensus_pipeline.py 设计文档 — Phase 1~4 自动化总控

## 目标

把「手动跑 Phase 1~4 → 发布器自动发布」升级为「Phase 1~4 自动运行 → 全链路 GO → 才调用发布器」。
最终：`run_consensus_pipeline.py` 单命令完成当日全链路，供 Hermes cron 调用。

## 编排结构（用户锁定）

```
run_consensus_pipeline.py
├─ [Phase 0] 前置审计：Phase1~4 输入产物（timeline 快照等）存在且新鲜
├─ [Phase 1] Data Layer      — create schema → 3 ingest → acceptance → benchmark_phase1_p15
├─ [Phase 2] Market+Theme    — benchmark_phase2_p24（内嵌重算 p20b→p21→p22a→p22b→p22c→p23）
├─ [Phase 3] Stock Consensus — benchmark_phase3_p34（内嵌重算 p31→p32→p33）
├─ [Phase 4] Cross-Layer     — benchmark_phase4_p44（内嵌重算 p41→p42→p43）
├─ [Overall Gate] 4 个 benchmark 全 GO
└─ [Publish]     publish_consensus_daily.py（仅 overall GO 时调用）
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

## CLI

```
python3 scripts/run_consensus_pipeline.py                 # 默认：全链路 + publish
python3 scripts/run_consensus_pipeline.py --dry-run       # 只跑 Phase1~4 + 各 benchmark，不 publish
python3 scripts/run_consensus_pipeline.py --no-publish    # 同 dry-run（别名）
python3 scripts/run_consensus_pipeline.py --no-telegram   # 禁用 Telegram 告警（仅日志）
python3 scripts/run_consensus_pipeline.py --max-age-hours 48
```

退出码：0 = 全链路 GO（已 publish）；2 = 产物未就绪静默（主检测）；1 = 失败（已告警）。

## 阶段日志与耗时

- 每阶段独立日志：`logs/consensus_pipeline_<date>.log`（全量）+ 每阶段耗时表
- 耗时写入 `reports/consensus_pipeline_runtime_<date>.json`

## 幂等

- Phase1~4 各脚本幂等（INSERT ON CONFLICT / DROP+CREATE+INSERT）
- snapshot 幂等（md5 契约）→ publish 防重复（生产 md5 一致 → 静默 SKIP）
- 总控整体：同交易日重复运行 → 各阶段 benchmark 幂等重算 → publish 防重复静默

## 告警

复用 publish_consensus_daily.py 的 `send_telegram_alert`（import 复用）。失败阶段 + 错误摘要 + 时间 + 产物 mtime。

## 依赖

- `sys.executable` 为 Hermes venv python（含 paramiko）
- 输入：`data/analyst_snapshots/vip0_timeline_*.json`（上游采集）
- 输出：Phase1~4 JSON（10 个）+ snapshot + HTML
