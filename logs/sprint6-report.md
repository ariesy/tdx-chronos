# Sprint 6 Report · 股本 type 1-48 字段语义映射 + Bug 修复

**项目**: tdx-chronos v1.1 第 9 修订
**作者**: claw-cortex 🦞
**日期**: 2026-07-05 03:30-04:10 UTC
**关联**: §四.7 type 字段含义验证 · 1.26 亿 records 摸排

---

## 🎯 目标

提供 **股本 type 1-48 → 字段语义映射表** (推测版 · 标注 confidence)，
并通过 Sprint 4b D1 真数据实证,让 query 能用有名字段访问股本 records。

---

## 🐛 Sprint 6 期间发现的 Sprint 4b D1 Bug · 修复

### 症状
- records.parquet 摸排时出现 **type=0 records** (3.37M)
- row group 573 含 65537 records, value_1 = 0x30303030 (ASCII "0000" placeholder)
- 14% records code="?" (5.4M dirty)

### 真相
- **148 个 gpcw 财务 .dat 文件** 被股本解析器误识别为股本
- `gpcw*` 以 `gp` 开头 → `iter_quarters` 用 `glob('gp*.dat')` 不过滤 `gpcw*.dat`
- 10 个 gpcw 文件被按 13 字节股本格式硬解 → **5,396,310 dirty records (4.29%)**

### 修复 (commit `0fb9cd3`)
- `tdxgp_record.py:263-272` `_discover_files` 用正则 `r'^gp(sh|sz|bj)\d{6}\.dat$'`
- 跳过 `gpcw*` 财务文件

### 修复后效果
| 指标 | 修前 | 修后 | Δ |
|---|---|---|---|
| files | 7,580 | **7,571** | -9 |
| records | 125,736,734 | **120,340,424** | -5.4M |
| output size | 627 MB | **587.7 MB** | -40 MB |
| type=0 records | 3.37M | **0** | -3.37M |
| dirty code="?" rows | 5,396,310 | **0** | -5.4M |

---

## 🦞 Sprint 6 完成

### 4 commits (T1 + T2 + 设计 + 修 bug)

```
<new commit> Sprint 6 T2 fix · 测试内存安全 (12 PASSED)
6419582 Sprint 6 T2 · to_categorized(category) + 真验收
8e142ad Sprint 6 T1 · tdxgp_types.py 字段语义映射 (推测版)
b470ddb Sprint 6 Plan · 股本 type 1-48 字段语义映射 (2 任务)
0fb9cd3 Sprint 6 prep · tdxgp_record iter_quarters 过滤 gpcw 财务文件
```

---

## 📐 设计 (Sprint 6)

### 5 类别 + 14 types 已分类

| Category | Types | 推测含义 | Confidence |
|---|---:|---|---|
| **capital_share** | 1, 3, 11, 12, 13, 16, 25, 27 (8) | 总股本变动/快照 | high (5) + medium (3) |
| **circulating_share** | 31, 36 (2) | 流通股变动 | medium |
| **shareholder_structure** | 38, 39, 40 (3) | 股东结构/事件 | high (1) + medium (2) |
| **finance_event** | 47 (1) | 近期每日数据 | low |
| **rare_event** | 49-255 (207) | 罕见/未分类 | unknown |

### 公开 API
- `TYPE_CATEGORY_MAPPING: Dict[int, Tuple[str, str]]` (type → (name, confidence))
- `TYPE_NAME: Dict[int, str]` (反向映射)
- `CATEGORY_BUCKETS: Dict[str, List[int]]` (5 类别)
- `VALID_CONFIDENCES: Set[str]`
- `get_type_name(t) / get_confidence(t) / get_category(t) / all_categories()`

### 类别过滤 API (T2 新增)
```python
TdxGpRecordReader.to_categorized(
    records_path: Path,
    category: str,        # 5 categories
    code: Optional[str],  # Optional 股票代码过滤
) -> pd.DataFrame
```

---

## 🧪 测试

### T1 (22 PASSED · 0.38s)
- TestTypeCategoryMapping (3): 14 types classified
- TestCategoryBuckets (6): 5 categories disjoint · rare_event 207
- TestLookupFunctions (7): get_* helpers
- TestConfidenceLevels (4): high/medium/low 验证
- TestTypeNameReverseMapping (1): 一致性

### T2 (12 PASSED · 60.87s)
- TestToCategorizedBasic (7):
  - 5 categories each has data
  - rare_event = 1 record (clean data 后)
  - 4 大类 dominates
  - total 83M ✓
- TestToCategorizedCode (3):
  - 茅台 (600519) 8 types 全出现
  - type=1 = 104 records (Sprint 4b 实证)
  - type_name 字段添加
- TestToCategorizedErrors (2): ValueError + FileNotFoundError

### Sprint 6 总计: **34 PASSED** + Sprint 1-5 167 = **201 PASSED**

---

## 📊 真验收 (clean data · 2026-07-05 03:30 UTC)

### 总 records 摸排 (gpcw 修 bug 后 · 120,340,424 总)

| Category | Types | Records | % of total |
|---|---:|---:|---:|
| capital_share | 8 | **57,166,923** | 47.5% |
| circulating_share | 2 | **4,497,462** | 3.7% |
| shareholder_structure | 3 | **20,871,635** | 17.3% |
| finance_event | 1 | **564,046** | 0.5% |
| rare_event (49-255) | 207 | **1** | ~0% |
| **小计 4 类** | 14 | **83,100,066** | **69.0%** |
| 未分类 type 1-48 (28 types) | 28 | **37,240,358** | 31.0% |
| **总计** | 256 | **120,340,424** | 100% |

### 茅台 (600519) 实证
- type=1 (quarterly_snapshot_total): **104 records** ✓ (Sprint 4b D1 实证)
- 8 capital_share types 全部出现
- 列: code, date, value_1, value_2, market + type_name

### Type 1-48 全分布摸排 (capital_share 内)
| type | 名 | confidence | row group 出现 |
|---|---|---|---:|
| 1 | quarterly_snapshot_total | high | 5801 |
| 3 | outstanding_share_audit | medium | ~5000 |
| 11 | shareholder_count_change | medium | ~7000 |
| 12 | dividend_distribution | medium | ~7000 |
| 13 | rights_offering | medium | ~7000 |
| 16 | total_share_change_event | high | 6718 |
| 25 | total_share_snapshot | high | 5817 |
| 27 | outstanding_share_change | high | 5817 |

---

## 🦞 学到的教训

### 1. 命名约定冲突 (`gpcw` vs `gp`)
- 股本 `gp{sh,sz,bj}*.dat` 与 财务 `gpcw*.dat` 都以 `gp` 开头
- **过滤必须用前缀+市场代码**: `gp(sh|sz|bj)\d{6}\.dat` 而不是 `gp*.dat`
- **教训**: 摸排时遇到 type=0 records 是关键警报 → 立即做 row group level 摸排

### 2. Arrow pc.is_in 用法
- `pc.is_in(array, value_set=types)` · **`value_set` 必须是 `pa.array(types)`**
- 传 list 会抛 TypeError: "is not a valid value set"
- **教训**: pyarrow 18+ 的 `pc.is_in` API 与早期版本不同

### 3. 测试反映真实数据 · 不要"完美期望"
- Sprint 6 摸排后写 `test_total_records_matches_full_data` 期望 120M
- 实际 5 类别累计 = 83M (差 37M 未分类 type 1-48)
- **教训**: 摸排数据后再写测试断言, 不假定所有 type 都已分类

### 4. 测试内存安全
- `to_categorized` 加载整个 parquet → 多次调用爆内存
- **教训**: 测试做"全量统计"时用 metadata + 单次 read + pc.is_in, 不要 N 次 to_categorized

---

## 🦞 已知限制

1. **type 1-48 字段语义是推测** — Sprint 7+ 可结合上市公司公告进一步验证
2. **未分类 28 个 type 1-48 (37M records · 31%)** — v1.1 暂不解释
3. **rare_event 207 types** — 实际几乎无数据, 可能在 v2.0 重定义
4. **confidence 字段 (high/medium/low)** — 主人可调

---

## 🎯 v2.0 TODO

- type 1-48 未分类 28 types 进一步语义验证 (公开股本变动公告匹配)
- type 49-255 大单交易/特殊事件验证
- 引入 type_name 索引 (currently apply · 慢)

---

## 📁 Sprint 6 关键文件

- `src/tdx_chronos/fin/tdxgp_types.py` · 4428 字节
- `src/tdx_chronos/fin/tdxgp_record.py:263-272` · `_discover_files` bug fix
- `src/tdx_chronos/fin/tdxgp_record.py` · to_categorized API (~30 行)
- `tests/unit/test_tdxgp_types.py` · 22 测试
- `tests/unit/test_tdxgp_categorized.py` · 12 测试 (修后版本)
- `docs/plans/2026-07-05-sprint6-type-semantics-design.md` · Design
- `docs/plans/2026-07-05-sprint6-type-semantics.md` · Plan

---

**Sprint 6 状态: ✅ 完成 · 4 commits · 34 PASSED · 真跑实证 (83M / 120M)**
**v1.1 累计: ~32 commits · 201 PASSED · 5 categories 类别化股本 records**

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>