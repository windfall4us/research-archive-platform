# P1.2 Event Ingest 验收成绩单 — 2026-08-28

> 快照 vip0_timeline_20260828.json | parser v1.1 | resolver exact-alias-v1

## 分层（当前 resolver 视角）

- Source records: 902
- Parser total events: 1032
- A_SHARE events: 934（eligible）
- UNRESOLVED: 5（含代码 0 / 纯名称 5）
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
| 5 | 26 | 908 | 0 | `478a7c4f712b8bce` |
| 6 | 0 | 934 | 0 | `478a7c4f712b8bce` |

## UNRESOLVED（交裁决，不猜测）

- `上海宜众`
- `泰金科技`
- `玉衡药业`
- `瑞图`
- `紫光`

## 库内历史残留（append-only，P1.4 REMOVED 处理）

- `vip0:天赢居:2026-08-28:东微半导(688261)/瑞芯微(603893):action:001` ← `东微半导(688261)/瑞芯微(603893)`（现判 COMPOSITE）
- `vip0:天赢居:2026-08-28:天齐锂业(002466)/赣锋锂业(002460):action:001` ← `天齐锂业(002466)/赣锋锂业(002460)`（现判 COMPOSITE）
- `vip0:天赢居:2026-08-28:黄河旋风(600172)/四方达(300179):action:001` ← `黄河旋风(600172)/四方达(300179)`（现判 COMPOSITE）
