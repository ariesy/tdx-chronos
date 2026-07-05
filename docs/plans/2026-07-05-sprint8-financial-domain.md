# Sprint 8 Plan · 财务领域补全 (quarter_metadata + 字段语义 + 三表勾稽 + 字段分类)

**项目**: tdx-chronos v1.2 (Sprint 7 → Sprint 8)
**日期**: 2026-07-05 (UTC)
**Design**: [sprint8-financial-domain-design.md](2026-07-05-sprint8-financial-domain-design.md)

---

## 📋 Sprint 8 现状 (决策时)

| 模块 | 状态 | Sprint 8 待办 |
|---|---|---|
| gpcw 解析器 (TdxFinReader) | ✅ Sprint 4a | - |
| 121 quarters Parquet | ✅ Sprint 4a | - |
| weekly_sync.sh 自动跑 | ✅ Sprint 5 | - |
| doctor `financial_quarters` | ✅ Sprint 5 | - |
| **meta.db `quarter_metadata`** | ❌ | **T1** |
| **585 字段语义** | ❌ (4 个 `_col582-585` 未知) | **T2** |
| **三表勾稽** | ❌ | **T3** |
| **581 字段财务报表分类** | ❌ | **T4** |

---

## 📋 任务列表 (5 tasks)

### T1: MetaDB quarter_metadata 表 + weekly_sync 接入 ⏱ 1 d

**新增** `src/tdx_chronos/meta/db.py`:
- `init_quarter_metadata_schema()` (类似 `init_gp_metadata_schema`)
- `record_quarter_metadata(report_date, file_path, ...)`
- `get_quarters(parsed_only=True)`
- `count_quarters(parse_ok=True)`

**schema**:
```sql
CREATE TABLE quarter_metadata (
    report_date INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    stock_count INTEGER,
    parquet_path TEXT,
    is_placeholder INTEGER DEFAULT 0,
    parsed_at TIMESTAMP,
    parse_ok INTEGER DEFAULT 0,
    error TEXT
)
```

**修改** `cron/weekly_sync.sh`: 解析后调 `record_quarter_metadata(...)`

**测试** 5 PASSED

### T2: 财务字段类型语义 + 4 未知字段反推 ⏱ 1 d

**新增** `src/tdx_chronos/fin/field_types.py`:
- `FIELD_CATEGORY_MAPPING: Dict[str, Tuple[str, str]]`
- Categories: per_share / profit / asset / liability / cashflow / ratio
- 4 个 `_col582-585` 摸排后命名

**摸排** `scripts/sample_unknown_fields.py`:
- 茅台 (600519) + 100 只蓝筹 2025 各 quarter 取样本
- 看 `_col582-585` 分布 · 顺序 · 与已知字段关联
- 推测命名 (如 `_col582` = 主营业务收入 etc.)

**测试** 10 PASSED

### T3: 三表勾稽 ⏱ 1 d

**新增** `src/tdx_chronos/fin/reconciliation.py`:

```python
class ReconciliationReport:
    """三表勾稽报告"""
    report_date: int
    passed: bool
    checks: list[CheckResult]
    tolerance: float = 0.001  # 0.1% 容差

def reconcile(quarter_df: pd.DataFrame) -> ReconciliationReport:
    """资产 = 负债 + 所有者权益"""
    checks = [
        BalanceSheetEquation(df),
        IncomeToRetainedEarnings(df),
        CashflowToBalanceSheet(df),
    ]
    return ReconciliationReport(checks=checks)
```

**测试** 8 PASSED

### T4: 581 字段财务报表分类 ⏱ 0.5 d

**新增** `src/tdx_chronos/fin/field_classification.py`:

```python
FIELD_CLASSIFICATION: Dict[str, str] = {
    # 利润表
    "营业收入": "income_statement",
    "营业成本": "income_statement",
    ...
    
    # 资产负债表
    "货币资金": "balance_sheet",
    "应收账款": "balance_sheet",
    ...
    
    # 现金流量表
    "经营活动产生的现金流量净额": "cashflow_statement",
    ...
    
    # 每股指标
    "基本每股收益": "per_share",
    ...
    
    # 财务比率
    "净资产收益率": "ratio",
    ...
}
```

**API**:
- `get_field_category(name) -> str`
- `get_fields_by_category(category) -> List[str]`

**测试** 5 PASSED

### T5: sprint8-report.md + git tag ⏱ 0.5 d

- 报告: 4 commits + 28 测试
- v1.2.0 tag 候选 (待主人决策)

---

## 🎯 Sprint 8 时间预算

| Task | 估算 | 累计 |
|---|---:|---:|
| T1 quarter_metadata | 6 h | 6 h |
| T2 字段语义 | 6 h | 12 h |
| T3 三表勾稽 | 6 h | 18 h |
| T4 字段分类 | 3 h | 21 h |
| T5 报告 | 3 h | 24 h |
| **总计** | **~3 d** | (估算保守 4 d) |

---

## 🦞 Sprint 8 commit 计划 (5 commits)

```
1. Sprint 8 T1 · MetaDB quarter_metadata + weekly_sync 接入 (5 测试)
2. Sprint 8 T2 · fin/field_types.py + 4 未知字段反推 (10 测试)
3. Sprint 8 T3 · fin/reconciliation.py 三表勾稽 (8 测试)
4. Sprint 8 T4 · fin/field_classification.py 581 字段分类 (5 测试)
5. Sprint 8 T5 · sprint8-report.md (v1.2 release tag 候选)
```

**v1.2 累计**: 38 + 5 = **43 commits** · 229 + 28 = **257 PASSED**

---

## 🦞 HARD GATE

**T2 实施前**: 必须基于摸排数据 (不是凭直觉)
**T3 实施前**: 必须确认三表勾稽恒等式定义 (TBD: 是否有 中间项调整?)
**T5 tag 前**: 所有测试 PASSED

---

## 🦞 Sprint 9+ 预告

- v2.0 财务领域
- type 49-255 股本语义
- 长尾 type 41-48 进一步
- 多源验证 (sina/同花顺)
- HTTP 兜底
- 在线实时推送

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>