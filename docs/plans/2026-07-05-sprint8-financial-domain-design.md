# Sprint 8 Design · 财务领域补全 (quarter_metadata + 字段语义 + 三表勾稽)

**项目**: tdx-chronos v1.1.0 (Sprint 7 后)
**作者**: claw-cortex 🦞
**日期**: 2026-07-05 (UTC)
**关联**: 主人最初决策 "先 A+B 然后做 C" · C 部分 = gpcw 财务领域

---

## 🎯 目标

**Sprint 8 之前 gpcw 财务领域真相**:
- ✅ TdxFinReader 解析器 (Sprint 4a)
- ✅ 121 quarters 已解析为 Parquet (`data/fin/parsed/gpcw*.parquet`)
- ✅ weekly_sync.sh 周日 02:00 自动跑 (Sprint 5)
- ✅ doctor `_check_financial_quarters` 检查 (Sprint 5)
- ❌ **meta.db 没有 quarter_metadata 表** (类似 gp_metadata)
- ❌ **4 个未知字段 `_col582-585` 没语义**
- ❌ **581 已知字段无财务报表分类** (利润表/资产负债表/现金流量表)
- ❌ **没有三表勾稽** (资产 = 负债 + 所有者权益)

**Sprint 8 主体**: 补全这 4 个 ❌ · 把财务领域从"能用"提升到"易用"

---

## 📐 设计

### T1: MetaDB 加 quarter_metadata 表 (~1 d)

**schema**:
```sql
CREATE TABLE quarter_metadata (
    report_date INTEGER PRIMARY KEY,    -- YYYYMMDD
    file_path TEXT NOT NULL,            -- 原始 gpcw{date}.zip 路径
    file_size INTEGER,                  -- bytes
    stock_count INTEGER,                -- 解析出的股票数 (~5524)
    parquet_path TEXT,                  -- 输出 parquet 路径
    is_placeholder INTEGER DEFAULT 0,   -- 164B zip 占位
    parsed_at TIMESTAMP,
    parse_ok INTEGER DEFAULT 0,
    error TEXT
);
```

**API**:
- `MetaDB.init_quarter_metadata_schema()` 类似 `init_gp_metadata_schema`
- `MetaDB.record_quarter_metadata(report_date, file_path, ...)`
- `MetaDB.get_quarters(parsed_only=True)` → List[int]
- `MetaDB.count_quarters(parse_ok=True)`

**修改 weekly_sync.sh** 接入 quarter_metadata 记录

### T2: 财务字段类型语义 (~1 d)

**问题**: 581 字段 + 4 未知 = 585 columns · 没类型分类

**方案**:
1. 摸排 581 字段中文名 + 4 未知 `_col582-585` 浮点样本
2. 创建 `fin/field_types.py` 新模块:
   - `FIELD_CATEGORY_MAPPING: Dict[str, Tuple[str, str]]`
     - key: 字段名 (e.g. "基本每股收益")
     - value: (category, sub_category) · e.g. ("per_share", "eps")
   - Categories: per_share / profit / asset / liability / cashflow / ratio
3. 给 4 个 `_col582-585` 找语义 (从公告/字段顺序反推)

**摸排数据**:
- 茅台 (600519) 2025 各 quarter 各字段值
- 看 _col582-585 分布 · 找命名规则 (顺序)

### T3: 三表勾稽 (~1 d)

**会计恒等式**:
1. **资产 = 负债 + 所有者权益**
   - 资产合计 ≈ 负债合计 + 所有者权益合计 (允许 ±0.1% 误差)
2. **利润表 → 资产负债表勾稽**
   - 净利润 ≈ 期初未分配利润 - 期末未分配利润 - 分红 (按需)
3. **现金流 → 资产负债表勾稽**
   - 现金净增加 ≈ 经营+投资+筹资净额

**实现**:
- `fin/reconciliation.py`:
  - `BalanceSheetCheck.reconcile(quarter_df) -> ReconciliationReport`
  - `IncomeStatementCheck.reconcile(...)`
  - `CashFlowCheck.reconcile(...)`

### T4: 财务报表分类 (~0.5 d)

**581 字段分类**:
- 利润表 (~50 fields): 营业收入/营业成本/净利润/...
- 资产负债表 (~250 fields): 资产/负债/权益各项
- 现金流量表 (~80 fields): 经营/投资/筹资各类
- 每股指标 (~20 fields): 每股净资产/每股EPS/...
- 财务比率 (~50 fields): 毛利率/ROE/资产负债率/...
- 衍生/其他 (~130 fields): 衍生品/分部信息/...

**模块**: `fin/field_classification.py`:
```python
FIELD_CLASSIFICATION: Dict[str, str] = {
    "基本每股收益": "per_share",
    "营业收入": "income_statement",
    "货币资金": "balance_sheet",
    ...
}
```

**API**:
- `get_field_category(field_name) -> str`
- `get_fields_by_category(category) -> List[str]`
- `IncomeStatement.get(quarter_df)` → 提取所有利润表字段

---

## 🧪 测试矩阵

### T1 (5 测试)
- `test_quarter_metadata_schema_init`
- `test_record_quarter_metadata_basic`
- `test_get_quarters_parsed_only`
- `test_quarter_count_parsed`
- `test_weekly_sync_records_metadata` (集成)

### T2 (10 测试)
- `test_field_types_module_imports`
- `test_per_share_fields_classified` (15+)
- `test_balance_sheet_fields_classified` (50+)
- `test_income_statement_fields_classified` (20+)
- `test_cashflow_fields_classified` (15+)
- `test_ratio_fields_classified` (10+)
- `test_unknown_fields_have_meaning` (4 个 _col582-585)
- `test_field_category_lookup`
- `test_field_category_coverage_above_85pct`
- `test_maotai_2025q1_field_samples`

### T3 (8 测试)
- `test_balance_sheet_equation_holds`
- `test_income_to_retained_earnings` (茅台)
- `test_cashflow_to_balance_sheet`
- `test_placeholder_quarter_skipped`
- `test_reconciliation_tolerance`
- `test_reconciliation_report_passed`
- `test_reconciliation_report_failed_breakdown`
- `test_maotai_2025q1_reconciliation`

### T4 (5 测试)
- `test_field_classification_imports`
- `test_income_statement_fields_subset` (30+)
- `test_balance_sheet_fields_subset` (200+)
- `test_cashflow_fields_subset` (50+)
- `test_per_share_fields_subset` (15+)

**Sprint 8 总计**: ~28 PASSED · 估算 5 d

---

## 🎯 Sprint 8 验收标准

- [ ] T1: quarter_metadata 表 + 5 测试 · weekly_sync 接入
- [ ] T2: 581 + 4 = 585 字段语义 · 10 测试
- [ ] T3: 三表勾稽 · 8 测试
- [ ] T4: 581 字段分类 · 5 测试
- [ ] sprint8-report.md
- [ ] **~38 commits → ~44 commits** · **229 PASSED → ~257 PASSED**

---

## 🦞 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| `_col582-585` 无法反推语义 | 中 | 中 | 标记 unknown · 留 v2.0 解决 |
| 三表勾稽误差大 (财务报表差异) | 中 | 中 | 容差 +0.1% · 标记异常 |
| 581 字段分类过粗 | 高 | 低 | 后续 Sprint 9+ 细化 |
| weekly_sync 接入破坏现有 cron | 低 | 高 | 保留旧路径 · 只追加 quarter_metadata 记录 |

---

## 🦞 Sprint 8 时间预算

| Task | 估算 | 累计 |
|---|---:|---:|
| T1 quarter_metadata | 1 d | 1 d |
| T2 字段类型语义 | 1 d | 2 d |
| T3 三表勾稽 | 1 d | 3 d |
| T4 财务报表分类 | 0.5 d | 3.5 d |
| Sprint 8 report + tag | 0.5 d | 4 d |
| **总计** | **4 d** | - |

---

## 🦞 Sprint 8 计划 commit 数

| Task | T1 | T2 | T3 | T4 | T5 | Total |
|---|---:|---:|---:|---:|---:|---:|
| commits | 1 | 1 | 1 | 1 | 1 | **5** |
| tests | 5 | 10 | 8 | 5 | - | **28** |

**v1.2 累计**: 38 + 5 = **43 commits** · 229 + 28 = **257 PASSED**

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>