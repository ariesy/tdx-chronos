# Sprint 9 Design · 财务领域扩展 (doctor 加 reconciliation + quarter_metadata + colXXX 摸排)

**项目**: tdx-chronos v1.2 (Sprint 8 → Sprint 9)
**作者**: claw-cortex 🦞
**日期**: 2026-07-05 (UTC)
**关联**: 主人原话 "现在跑" + Sprint 8 摸排真相

---

## 🎯 目标

**Sprint 8 完成后**, 财务领域 4 大模块齐备:
- ✅ quarter_metadata (Sprint 8 T1)
- ✅ field_types 585 字段语义 (Sprint 8 T2)
- ✅ reconciliation 三表勾稽 (Sprint 8 T3)
- ✅ field_classification 提取子集 (Sprint 8 T4)

**Sprint 9 目标**: 把这些模块**接入 doctor.py 健康检查**, 让每周日的 `tdx-weekly-doctor` 自动验证财务领域数据质量

---

## 📐 设计

### T1: doctor.py 加 reconciliation 健康检查 (~1.5 d)

**新增** `_check_reconciliation`:
- 跑最近 quarter (最新有效 quarter) 的 reconcile_quarter
- 检查 3 大勾稽 (BS/CF/IS) 全部 PASS
- 容差默认 0.1%
- 返回 CheckResult

**集成**: Doctor.report() 跑全套检查, reconciliation 是其中一个

### T2: doctor.py 加 quarter_metadata 健康检查 (~1 d)

**新增** `_check_quarter_metadata`:
- 用 Sprint 8 T1 的 MetaDB API
- 检查 quarter_metadata 表存在
- 检查 parsed_only quarter 数 >= 100 (Sprint 4a 验证)
- 检查 parse_ok=1 ratio >= 95%
- 返回 CheckResult

### T3: scripts/sample_unknown_fields.py colXXX 摸排 (~1 d)

**目的**: 留下 colXXX 178 + _colXXX 4 = 182 字段的真实分布数据

**实现**:
- 跑最近 4 quarters 的 colXXX 数据
- 输出:
  - 每个 colXXX 的 nonzero 率
  - mean/min/max
  - best correlation 与已知字段
  - binary 判断 (0/1)
  - 茅台 2025 样本
- 输出: `data/research/sprint9_unknown_fields.csv`

**价值**: 留 v2.0 进一步命名反推的基础

### T4: doctor.py 整合 + 飞书告警测试 (~1 d)

**目标**: 跑 `python -m tdx_chronos.doctor` 真验证:
- 8 个原有 check (Sprint 5)
- 2 个新增 check (T1 + T2)
- 总共 10 个 check
- 任一 FAIL → 通过 alertor 发送飞书告警 (DRY-RUN 默认)

### T5: sprint9-report.md (~0.5 d)

---

## 🧪 测试矩阵

### T1 (4 测试)
- `test_check_reconciliation_passes_for_latest_quarter`
- `test_check_reconciliation_handles_missing_parquet`
- `test_check_reconciliation_returns_checkresult`
- `test_check_reconciliation_tolerance_param`

### T2 (4 测试)
- `test_check_quarter_metadata_db_exists`
- `test_check_quarter_metadata_count_above_100`
- `test_check_quarter_metadata_parse_ok_ratio`
- `test_check_quarter_metadata_skips_placeholders`

### T3 (2 测试)
- `test_sample_unknown_fields_runs_without_error`
- `test_sample_unknown_fields_csv_has_182_rows`

### T4 (3 测试)
- `test_doctor_report_includes_reconciliation`
- `test_doctor_report_includes_quarter_metadata`
- `test_doctor_alertor_dryrun`

**Sprint 9 总计**: ~13 PASSED · 估算 5 d (含 weekly_doctor.sh 集成)

---

## 🦞 Sprint 9 摸排真相 (colXXX)

### `_col582-585` 真相

| 字段 | nonzero | 推测 |
|---|---:|---|
| `_col582` | 84% | 通用指标 (与营业总收入 corr=0.56) |
| `_col583-585` | 1.6-1.8% | **金融业特定** (000001 平安/000166 申万/000686 东北证券等有值) |

### colXXX 三段真相

| 区间 | 数量 | 特征 |
|---|---:|---|
| col323-400 | 78 | 通用补充字段 · col325 是 binary |
| col440-500 | 61 | **金融业特定** (corr=0.99 with 资产总计/负债合计) |
| col522-560 | 39 | 衍生指标/补充披露 |

**决策**: **不反推 colXXX 精确语义** (v2.0 工作) · Sprint 9 只留摸排数据

---

## 🦞 Sprint 9 时间预算

| Task | 估算 | 累计 |
|---|---:|---:|
| T1 reconciliation check | 1.5 d | 1.5 d |
| T2 quarter_metadata check | 1 d | 2.5 d |
| T3 colXXX 摸排脚本 | 1 d | 3.5 d |
| T4 doctor 整合 + 飞书 | 1 d | 4.5 d |
| T5 sprint9-report | 0.5 d | 5 d |
| **总计** | **~5 d** | - |

---

## 🦞 Sprint 9 计划 commit 数

| Task | T1 | T2 | T3 | T4 | T5 | Total |
|---|---:|---:|---:|---:|---:|---:|
| commits | 1 | 1 | 1 | 1 | 1 | **5** |
| tests | 4 | 4 | 2 | 3 | - | **13** |

**v1.3 累计**: 44 + 5 = **49 commits** · 243 + 13 = **256 PASSED**

---

## 🦞 Sprint 9+ 候选 (后续)

- **Sprint 10**: 多源验证 (sina/同花顺/tushare)
- **Sprint 11**: HTTP 兜底 + 在线实时推送
- **Sprint 12**: v2.0 type 49-255 股本语义
- **Sprint 13+**: 财报智能分析 (异常识别/业绩拐点)

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>