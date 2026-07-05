# Sprint 7 Plan · 未分类 28 types 语义补全 + v1.1 release

**项目**: tdx-chronos v1.1 第 9 修订
**日期**: 2026-07-05 (UTC)
**Design**: [sprint7-uncategorized-types-design.md](2026-07-05-sprint7-uncategorized-types-design.md)

---

## 📋 任务列表 (6 tasks)

### T1: 摸排脚本 + 样本 csv 输出 ⏱ 2 h

**目标**: 用代码 + 真数据看每个未分类 type 的样本

**文件**: `scripts/sample_uncategorized_types.py`

```python
"""Sprint 7 T1 · 摸排未分类 28 types 的样本

输出: data/type_samples.csv
列: code, type, sample_date, sample_value_1, sample_value_2, sample_market, ...
"""
import pyarrow.parquet as pq
from pathlib import Path

RECORDS = Path('/app/tdx-chronos/data/gp/records.parquet')
SAMPLES = Path('/app/tdx-chronos/data/type_samples.csv')

UNCATEGORIZED = [2, 4, 5, 6, 7, 8, 9, 10, 14, 15, 17, 18, 19, 20,
                 21, 22, 23, 24, 26, 28, 29, 30, 32, 33, 34, 35, 37,
                 41, 42, 43, 44, 45, 46, 48]

SAMPLE_CODES = ['600519', '601318', '600036', '600028', '600030']  # 茅台/平安/招行/石化/中信

# 对每个 type: 取 5 个样本股票各 5 条
# 输出 CSV
```

**验收**: CSV 含 28 × 25 = 700 sample records

### T2: TYPE_CATEGORY_MAPPING 扩展 + CATEGORY_BUCKETS 重定义 ⏱ 1 h

**文件**: `src/tdx_chronos/fin/tdxgp_types.py` (修改)

**变更**:
1. 扩展 TYPE_CATEGORY_MAPPING 加 11 个 top 未分类 types (基于 T1 摸排)
2. 重定义 CATEGORY_BUCKETS
3. TYPE_NAME 自动从 MAPPING 生成
4. 加新 helper `get_types_by_confidence(level)`

### T3: 测试 + 真验收 ⏱ 1 h

**文件**: `tests/unit/test_tdxgp_uncategorized.py` (新建)

**测试**:
- `test_top11_uncategorized_classified` (11 类型都有 mapping)
- `test_categorized_coverage_above_90pct` (覆盖率 ≥ 90%)
- `test_sample_maotai_type21` (sample 验证)
- `test_sample_pingan_type6` (sample 验证)
- `test_legacy_types_in_rare_event` (长尾归 rare_event)
- + 20 more = **25 PASSED**

**真验收**: 跑 `to_categorized('capital_share')` 看 records 数 ≥ 70M

### T4: Parquet zstd 压缩实验 ⏱ 2 h

**文件**: `scripts/recompress_zstd.py` (新建) + `tests/unit/test_parquet_compression.py`

**步骤**:
1. 用 zstd 重写 records.parquet
2. 对比 size (snappy 587.7 MB → zstd 期望 ~400-450 MB)
3. 验证 records 数一致
4. 验证 to_categorized 性能不退化
5. 决定是否切换 (Sprint 7b)

**commit**: `bench` (不切换 default, 只实验 + 报告)

### T5: README + CHANGELOG ⏱ 1 h

**文件**: 
- `README.md` (新建)
- `CHANGELOG.md` (新建)

**README** 含:
- 项目简介 (tdx-chronos: TDX 通达信数据 → Parquet)
- 数据规模 (1.26 亿股本 records · 12,256 symbols · 121 quarters)
- 5 大模块 (kline / financial / gp / index / cron)
- 安装 (venv + pyproject)
- 使用示例
- 测试 (pytest)

**CHANGELOG v1.1.0**:
- Sprint 1: 项目初始化 + vendoring
- Sprint 2: 抽象层 + 股本元数据
- Sprint 3: K线抽象 + Parquet 输出
- Sprint 4: 财务/股本/指数 + 索引 + 元数据
- Sprint 5: cron 接入 + doctor + 告警
- Sprint 6: type 字段语义 + bug 修复 (gpcw)
- Sprint 7: 未分类 types 语义 + zstd 优化

### T6: git tag v1.1.0 ⏱ 0.5 h

**步骤**:
1. `git tag -a v1.1.0 -m "..."`
2. `git push origin v1.1.0`
3. 验证: `git tag --list` 含 v1.1.0

---

## 🎯 Sprint 7 总时间预算

| 任务 | 估算 | 累计 |
|---|---:|---:|
| T1 摸排 | 2 h | 2 h |
| T2 扩展 | 1 h | 3 h |
| T3 测试 | 1 h | 4 h |
| T4 zstd | 2 h | 6 h |
| T5 文档 | 1 h | 7 h |
| T6 tag | 0.5 h | **7.5 h (~1 d)** |

加上 commit/push/报告等:**Sprint 7 ≈ 2 d**

---

## 🦞 Sprint 7 commit 计划 (6 commits)

```
1. Sprint 7 T1 · 摸排脚本 + type_samples.csv 输出
2. Sprint 7 T2 · TYPE_CATEGORY_MAPPING 扩展 11 types
3. Sprint 7 T3 · test_tdxgp_uncategorized.py (25 PASSED)
4. Sprint 7 T4 · Parquet zstd 压缩实验 (bench)
5. Sprint 7 T5 · README.md + CHANGELOG.md
6. Sprint 7 T6 · git tag v1.1.0 + sprint7-report.md
```

**v1.1 累计**: 32 + 6 = **38 commits** · 201 + 25 = **226 PASSED**

---

## 🦞 Sprint 8 预告 (C 部分 · gpcw 财务)

待 Sprint 7 完成后启动:
- T1: gpcw 解析器 (~3 d)
- T2: gpcw type 字段语义 (~2 d)
- **估算**: 5 d

---

## 🦞 HARD GATE

**T2 实施前**: 必须基于 T1 摸排数据, 不允许"凭直觉"猜测 28 types 语义
**T4 实施前**: 必须确认 zstd 压缩率 ≥ 25%, 否则保留 snappy
**T6 实施前**: 所有测试 PASSED

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>