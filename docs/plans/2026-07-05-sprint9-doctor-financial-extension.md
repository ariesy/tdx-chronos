# Sprint 9 Plan · 财务领域扩展 (doctor 加 reconciliation + quarter_metadata + colXXX 摸排)

**项目**: tdx-chronos v1.3 (Sprint 8 → Sprint 9)
**日期**: 2026-07-05 (UTC)
**Design**: [sprint9-doctor-financial-extension-design.md](2026-07-05-sprint9-doctor-financial-extension-design.md)

---

## 📋 Sprint 9 现状 (Sprint 8 后)

| 模块 | 状态 | Sprint 9 待办 |
|---|---|---|
| 财务领域核心 (Sprint 8 4 大模块) | ✅ | - |
| **doctor 加 reconciliation check** | ❌ | **T1** |
| **doctor 加 quarter_metadata check** | ❌ | **T2** |
| **colXXX 178 摸排脚本** | ❌ | **T3** |
| **doctor 飞书告警整合** | ❌ | **T4** |
| sprint9-report | ❌ | **T5** |

---

## 📋 任务列表 (5 tasks · 13 测试 · 5 d)

### T1: doctor.py reconciliation 健康检查 ⏱ 1.5 d

**新增** `src/tdx_chronos/doctor.py`:
```python
def _check_reconciliation(self, tolerance: float = 0.001) -> CheckResult:
    """检查: 最近 quarter 三表勾稽 PASS"""
    # 找最近 parquet
    fin_dir = self.parquet_root / "fin" / "parsed"
    files = sorted(fin_dir.glob("gpcw*.parquet"), reverse=True)
    # 跳过空 parquet
    for f in files:
        df = pd.read_parquet(f)
        if len(df) > 0 and "资产总计" in df.columns:
            from tdx_chronos.fin.reconciliation import reconcile_quarter
            report = reconcile_quarter(df, report_date=..., tolerance=tolerance)
            return CheckResult(
                name="reconciliation",
                passed=report.passed,
                actual=f"{report.failed_count}/{len(report.checks)} failed",
                threshold=f"all 3 checks pass at ±{tolerance*100:.2f}%",
                detail=f"latest: {report.report_date}",
            )
    return CheckResult(name="reconciliation", passed=False, ...)
```

**测试** 4 PASSED

### T2: doctor.py quarter_metadata 健康检查 ⏱ 1 d

**新增** `src/tdx_chronos/doctor.py`:
```python
def _check_quarter_metadata(self, db: MetaDB) -> CheckResult:
    """检查: quarter_metadata parsed_only count + parse_ok ratio"""
    parsed_count = db.count_quarters(parse_ok=True, exclude_placeholders=True)
    parsed_total = db.count_quarters(exclude_placeholders=True)
    ok_ratio = parsed_count / parsed_total if parsed_total > 0 else 0
    
    return CheckResult(
        name="quarter_metadata",
        passed=(parsed_count >= 100) and (ok_ratio >= 0.95),
        actual=f"{parsed_count}/{parsed_total} parsed ({ok_ratio*100:.1f}% ok)",
        threshold=">= 100 parsed · >= 95% ok",
    )
```

**测试** 4 PASSED

### T3: scripts/sample_unknown_fields.py colXXX 摸排脚本 ⏱ 1 d

**目的**: 留下 colXXX 178 + _colXXX 4 = 182 字段的真实分布数据

**输出**: `data/research/sprint9_unknown_fields.csv`

**列**:
- column name
- nonzero_count
- nonzero_ratio
- mean/min/max
- unique_count
- is_binary
- best_correlation_field
- best_correlation_value
- maotai_2025_value

**测试** 2 PASSED (脚本跑成功 + CSV 行数)

### T4: doctor.py 整合 + 飞书告警测试 ⏱ 1 d

**目标**: 跑 `python -m tdx_chronos.doctor` 真验证:
- 10 个 check (8 原 + 2 新)
- 任一 FAIL → alertor 飞书告警 (DRY-RUN 默认)

**测试** 3 PASSED

### T5: sprint9-report.md ⏱ 0.5 d

- 5 commits + 13 测试
- v1.3 candidate

---

## 🦞 Sprint 9 commit 计划 (5 commits)

```
1. Sprint 9 T1 · doctor reconciliation check (4 测试)
2. Sprint 9 T2 · doctor quarter_metadata check (4 测试)
3. Sprint 9 T3 · sample_unknown_fields.py 摸排脚本 (2 测试)
4. Sprint 9 T4 · doctor 整合 + 飞书告警 (3 测试)
5. Sprint 9 T5 · sprint9-report.md (v1.3 release tag 候选)
```

**v1.3 累计**: 44 + 5 = **49 commits** · 243 + 13 = **256 PASSED**

---

## 🦞 Sprint 9 HARD GATE

- T1 实施前: 先跑 reconcile_quarter 验证 gpcw20251231 真 PASS (Sprint 8 T3 已确认)
- T2 实施前: 先用 Sprint 8 T1 集成验证 (240 quarters recorded, 120 unique)
- T3 实施前: 摸排数据先看 178 colXXX 是否真有 nonzero > 0 字段
- T4 tag 前: 所有 10 个 check 跑过 PASS

---

## 🦞 Sprint 10+ 候选

- Sprint 10: 多源验证 (sina/同花顺/tushare)
- Sprint 11: HTTP 兜底 + 在线实时推送
- Sprint 12: v2.0 type 49-255 股本语义
- Sprint 13: 财报智能分析

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>