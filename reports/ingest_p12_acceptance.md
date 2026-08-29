# P1.2 Event Ingest 验收成绩单 — 2026-08-28

> 快照 vip0_timeline_20260828.json | parser v1.1 | resolver exact-alias-v1

## 分层（当前 resolver 视角）

- Source records: 902
- Parser total events: 1032
- A_SHARE events: 908（eligible）
- UNRESOLVED: 49（含代码 0 / 纯名称 49）
- COMPOSITE（多标的）records: 35
- THEME/MARKET/OOS events: 28/9/1

## Gate

| Gate | 结果 | 说明 |
|---|---|---|
| G1_snapshot_registered | ✅ | |
| G3_a_share_resolvable | ✅ | |
| G5_uk_unique | ✅ | |
| G4_lineage | ✅ | |
| G2_eligible_count | ✅ | |
| G6_rerun_0new | ✅ | |
| G7_rerun_hash | ✅ | |
| G8_false_exec | ✅ | |
| G0_error_zero | ✅ | |

**Overall: PASS**

## ingest_runs（同版本重跑留独立 run history）

| run_id | inserted | skipped | errors | result_hash |
|---|---|---|---|---|
| 1 | 590 | 0 | 0 | `b02264eb24861943` |
| 2 | 280 | 590 | 0 | `a6301d4ad78f3542` |
| 3 | 41 | 867 | 0 | `df425dd34e1609c9` |
| 4 | 0 | 908 | 0 | `df425dd34e1609c9` |

## UNRESOLVED（交裁决，不猜测）

- `513120`
- `513120(ETF)`
- `MLCC`
- `上海宜众`
- `两融余额`
- `中芯H`
- `亨通光D`
- `京东方`
- `京东方A`
- `创新药CXO`
- `创新药高位股`
- `华虹`
- `商业航天`
- `天博申购(新股)`
- `宇树科技`
- `安踏`
- `富祥药业`
- `杨杰科技`
- `沪深300ETF(510300)`
- `泰金科技`
- `深中华`
- `燕子家族`
- `特高压（2只）`
- `玉衡药业`
- `瑞图`
- `盛科通信`
- `矩光科技`
- `科创50ETF(588000)`
- `科技连板(低位)`
- `紫光`
- `聚和股份`
- `茂来光学`
- `药明合联`
- `药明生物`
- `贝瑞卡`
- `金建米业`
- `铜管(海亮股份)`
- `铜管持仓`
- `长鑫`
- `阿里`

## 库内历史残留（append-only，P1.4 REMOVED 处理）

- `vip0:天赢居:2026-08-28:东微半导(688261)/瑞芯微(603893):action:001` ← `东微半导(688261)/瑞芯微(603893)`（现判 COMPOSITE）
- `vip0:天赢居:2026-08-28:天齐锂业(002466)/赣锋锂业(002460):action:001` ← `天齐锂业(002466)/赣锋锂业(002460)`（现判 COMPOSITE）
- `vip0:天赢居:2026-08-28:黄河旋风(600172)/四方达(300179):action:001` ← `黄河旋风(600172)/四方达(300179)`（现判 COMPOSITE）
