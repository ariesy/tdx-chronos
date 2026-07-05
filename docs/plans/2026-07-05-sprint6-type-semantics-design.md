# Sprint 6 Design · 股本 type 1-48 字段语义映射 (推测版)

**项目**: tdx-chronos v1.1 第 9 修订
**作者**: claw-cortex 🦞
**日期**: 2026-07-05 (UTC)
**关联**: §四.7 type 1-48 字段语义验证 · 1.26 亿 records 摸排

---

## 🎯 目标

提供 **股本 type 1-48 → 字段语义映射表** (推测版 · 标注 confidence)，
让 Sprint 6 之后的 query 能用有名字段，不用直接读 13B records。

---

## 🦞 关键发现 (摸排真相)

### 数据现状

```
股本 records.parquet:  120,340,424 records (Sprint 6 修 bug 后 · 7,570 真股本 .dat)
type 范围:             0-255
type 1-48:            119,150,xxx records (~99%)  ← 常用股本事件段
type 49-255:          1,189,xxx records (~1%)     ← 罕见 (各 ~5000 records · 1 unique code)
type=0:               0 (gpcw 误识别修复后已为 0)
```

### 茅台 (600519) type 1-48 样本 (摸排真相)

| type | sample date | sample value_1 | sample value_2 | 推测含义 |
|---|---|---|---|---|
| 1 | 20011231 ~ 20260331 (104 季) | ~12 亿 | 0 | **季末股本快照** (总股本) |
| 3 | 各 2000 | ~12 亿 | ~12 亿 | **流通股对账** |
| 11-13 | 各 7000 | ~12 亿 | ~12 亿 | **股东户数/分红/送转相关** |
| 16 | 10.5M (~8.4%) | ~13 亿 | 0 | **总股本变动** (高频) |
| 25 | 9.2M (~7.3%) | ~12 亿 | 0 | **总股本快照** |
| 27 | 10.1M (~8.0%) | ~11 亿 | ~11 亿 | **流通股变动** |
| 38 | 8.6M (~6.9%) | 0 | 0 | **事件日期标记** (date + code only) |
| 39 | 6.5M (~5.2%) | 0 | 0 | **事件标记** |
| 40 | 5.7M (~4.6%) | 0 | ~12 亿 | **变动+存量** |
| 47 | 569K (~0.45%) | ~33 亿 | 0 | **近期每日数据** |

### type 49-255 真相

- 每种 ~4000-14000 records
- **全部 1 unique code**（= 单一文件）→ 几乎不存在，可能遗留或特殊事件
- **v1.1 暂不解释**，归类为 "rare_event"

---

## 📐 设计

### 1. `src/tdx_chronos/fin/tdxgp_types.py` 新文件

```python
# 4 大类别 (覆盖 type 1-48)
TYPE_CATEGORY_MAPPING = {
    # 类别 1: 总股本 (capital_share)
    1:  ("quarterly_snapshot_total", "high"),
    3:  ("outstanding_share_audit", "high"),
    11: ("shareholder_count_change", "medium"),
    12: ("dividend_distribution", "medium"),
    13: ("rights_offering", "medium"),
    16: ("total_share_change_event", "high"),
    25: ("total_share_snapshot", "high"),
    27: ("outstanding_share_change", "high"),
    
    # 类别 2: 流通股 (circulating_share)
    31: ("circulating_change_event", "medium"),
    36: ("circulating_snapshot", "medium"),
    
    # 类别 3: 股东结构 (shareholder_structure)
    38: ("event_date_marker", "high"),
    39: ("event_marker_only", "medium"),
    40: ("change_with_existing", "medium"),
    
    # 类别 4: 财务事件 (finance_event)
    47: ("recent_daily_record", "low"),  # 可能是近期每日数据
    
    # 类别 5: 罕见/未知 (rare)
    # type 2, 4-10, 14-15, 17-24, 26, 28-30, 32-35, 37, 41-46, 48, 49-255 → rare
}

# Convenience: 类别桶
CATEGORY_BUCKETS = {
    "capital_share": [1, 3, 11, 12, 13, 16, 25, 27],
    "circulating_share": [31, 36],
    "shareholder_structure": [38, 39, 40],
    "finance_event": [47],
    "rare_event": list(range(49, 256)),
}
```

### 2. `TdxGpRecordReader.to_categorized(category: str) -> pd.DataFrame`

按 category 返回过滤 + 重命名的 DataFrame:
- columns = `['code', 'date', 'value_1', 'value_2', 'market']`
- 自动过滤该 category 的 type

### 3. `TYPE_NAME[1..255] -> str` 反向映射

```python
TYPE_NAME = {1: "quarterly_snapshot_total", ...}
```

### 4. 测试

- 4 个 category 各自 1 个测试
- 1 个 type_name 完整性测试
- 1 个真验收 (run on real data)

---

## 🦞 已知限制

1. **type 1-48 字段语义是推测** — Sprint 6 + 后续 Sprint 7+ 可结合上市公司公告进一步验证
2. **type 49-255 暂归 rare** — 实际可能是大单交易/特殊事件，待 v2.0
3. **数据基于茅台样本** — 其他股票可能 type 分布差异，但 CATEGORY 分类应一致
4. **confidence 字段 (high/medium/low)** — 主人可调

---

## 🧪 测试矩阵

| 测试 | 验证 |
|---|---|
| `test_type_category_mapping_keys` | 48 keys 全部存在 |
| `test_category_buckets_disjoint` | 5 类不相交 |
| `test_to_categorized_capital_share` | 8 types → capital_share DataFrame |
| `test_to_categorized_real_data` | 真跑茅台 (600519) → 4 categories |
| `test_type_name_lookup` | type 1 → "quarterly_snapshot_total" |

---

## 🎯 验收标准

- [ ] tdxgp_types.py + TYPE_CATEGORY_MAPPING + CATEGORY_BUCKETS
- [ ] TdxGpRecordReader.to_categorized(category) 实现
- [ ] 5 测试 PASSED + 真跑 4 categories
- [ ] sprint6-report.md
- [ ] 27 + 2 = **29 commits**

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>