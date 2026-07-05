# Sprint 7 Design · 未分类 28 types 语义补全 + v1.1 release

**项目**: tdx-chronos v1.1 第 9 修订
**作者**: claw-cortex 🦞
**日期**: 2026-07-05 (UTC)
**关联**: Sprint 6 v2.0 TODO + v1.1 release tag

---

## 🎯 目标

1. **A 部分**: 补全 type 1-48 未分类 28 types 的语义映射 (Sprint 6 v2.0 TODO · 占 records 31%)
2. **B 部分**: v1.1 release tag + Parquet 压缩优化 (zstd vs snappy) + CHANGELOG

---

## 🦞 关键摸排真相 (2026-07-05 05:28 UTC)

### Sprint 6 后未分类 types (1-48) 实证

| Type | Records | % of total | 已知名 |
|---:|---:|---:|---|
| **21** | 6,549,131 | 5.4% | ❌ 最大未分类 |
| **6** | 5,819,310 | 4.8% | ❌ 第二大 |
| **19** | 2,931,050 | 2.4% | ❌ 第三 |
| 15 | 2,247,565 | 1.9% | ❌ |
| 5 | 2,160,619 | 1.8% | ❌ |
| 17 | 2,054,841 | 1.7% | ❌ |
| 8 | 2,030,817 | 1.7% | ❌ |
| 9 | 1,995,792 | 1.7% | ❌ |
| 7 | 1,981,803 | 1.6% | ❌ |
| 10 | 1,948,030 | 1.6% | ❌ |
| 18 | 1,879,783 | 1.6% | ❌ |
| 14 | 1,803,468 | 1.5% | ❌ |
| 20 | 1,094,916 | 0.9% | ❌ |
| 32 | 861,482 | 0.7% | ❌ |
| 22 | 380,590 | 0.3% | ❌ |
| 45 | 309,635 | 0.3% | ❌ |
| ... | < 300K each | < 0.3% each | ❌ |

**已分类 14 types 共 83.1M (69%)** · **未分类 28+ types 共 37.2M (31%)**

### 当前 CATEGORY_BUCKETS 5 类别 (Sprint 6)
- `capital_share` (8 types) · `circulating_share` (2) · `shareholder_structure` (3) · `finance_event` (1) · `rare_event` (49-255)

---

## 📐 设计

### A 部分 · 未分类 28 types 语义补全

#### 步骤 1: 摸排 (T1)

抽样 茅台 (600519) + 3-5 只大蓝筹 (中国平安 / 招商银行 / 中国石化 / 中信证券) 看每只 type 的样本 records:

```
对每只样本股票:
  对每个未分类 type (top 11 + 17 长尾):
    取 sample date + value_1 + value_2
    看 date 模式 (历史 vs 近期) 
    看 value_1 分布 (12 亿附近 = 总股本 / 11 亿 = 流通股 / 其他)
    看 value_2 分布 (类似比对)
```

输出: `data/type_samples.csv` (master 样本)

#### 步骤 2: 推测映射 (T2)

基于摸排 + 已公开股本变动公告语义:

| Type | Records | 推测语义 (待 T1 验证) |
|---:|---:|---|
| 21 | 6.5M | **总股本变动 - 含 value_2 字段** (可能 = 流通股变化) |
| 6 | 5.8M | **总股本历史快照 - 长期持有** (类似 type 25) |
| 19 | 2.9M | **股东户数变动** (类似 type 11) |
| 5/7/8/9/10 | ~2M each | **高频变动事件** (总股本 / 流通股 / 股东结构 共用) |
| 15/17 | ~2M | **股东结构相关** (类似 type 38) |
| 14/18/20 | ~1-2M | **历史事件标记** (类似 type 39) |
| ... | < 1M | **长尾·暂归 rare_event** |

#### 步骤 3: 重新分类 (T3)

更新 `TYPE_CATEGORY_MAPPING` 字典 + `CATEGORY_BUCKETS`:

```python
TYPE_CATEGORY_MAPPING = {
    # Sprint 6 已分类 (14 types)
    1: ("quarterly_snapshot_total", "high"),
    3: ("outstanding_share_audit", "high"),
    ...
    
    # Sprint 7 新增 (top 11 ~ 28 types · 基于摸排)
    21: ("total_share_change_extended", "medium"),  # 含 value_2 字段
    6: ("total_share_historical_snapshot", "medium"),
    19: ("shareholder_count_extended", "medium"),
    5: ("total_share_change_event_legacy", "low"),
    7: ("outstanding_share_change_legacy", "low"),
    ...
}

# 新 category? 视摸排结果定
CATEGORY_BUCKETS = {
    "capital_share": [...],  # 扩展 ~ 14-18 types
    "circulating_share": [...],  # 扩展 ~ 4-6 types
    "shareholder_structure": [...],  # 扩展 ~ 6-10 types
    "finance_event": [...],  # 1-2 types
    "rare_event": list(range(?)),  # 缩小到 ~150-180 types
}
```

#### 步骤 4: 测试 (T4)

- 22 PASSED (T1 Sprint 6) + 新增 ~20-30 PASSED (新类型)
- to_categorized 真跑实证 (覆盖率达到 ~90%+)

### B 部分 · v1.1 Release

#### 步骤 5: Parquet 压缩优化 (T5)

- 当前: snappy 压缩率 39.4% (587.7 MB from 1.49 GB raw)
- 目标: zstd 压缩率 ~25-30% (预计 400-450 MB)
- 测试: 重写 records.parquet + verify records 数一致 + 性能对比

```python
# tdxgp_record.py write 时加 compression="zstd"
table.to_parquet(path, compression="zstd", compression_level=3)
```

#### 步骤 6: README + CHANGELOG (T6)

- `README.md` 新增: 功能介绍 + 安装 + 使用 + 数据规模
- `CHANGELOG.md`: v1.1.0 条目 (Sprint 1-7 全部要点)

#### 步骤 7: git tag v1.1.0 (T7)

- tag 触发 GitHub release (可选)
- tag commit 验证通过所有测试

---

## 🧪 测试矩阵

### A 部分
| 测试 | 验证 |
|---|---|
| `test_top11_uncategorized_classified` | top 11 types (21/6/19/15/5/17/8/9/7/10/18) 全部有 type_name + confidence |
| `test_categorized_coverage_above_90pct` | 4 大类累计 records ≥ 90% |
| `test_sample_maotai_type21` | 茅台 type=21 sample 验证 |
| `test_sample_pingan_type6` | 中国平安 type=6 sample 验证 |
| `test_legacy_types_in_rare_event` | 长尾 (< 1M) types 仍归 rare_event |

### B 部分
| 测试 | 验证 |
|---|---|
| `test_zstd_compression_smaller` | zstd 后 records.parquet < snappy 旧大小 |
| `test_zstd_read_compatible` | zstd parquet 可读 + records 数一致 |
| `test_readme_exists` | README.md 含功能/安装/使用 |
| `test_changelog_v110` | CHANGELOG.md 含 v1.1.0 条目 |
| `test_git_tag_v110` | git tag v1.1.0 存在 |

---

## 🎯 验收标准

### A 部分
- [ ] T1: 摸排脚本 (`sample_types.py`) + 样本 csv 输出
- [ ] T2: TYPE_CATEGORY_MAPPING 扩展 + CATEGORY_BUCKETS 重定义
- [ ] T3: 22 (旧) + 25 (新) = **47 PASSED** · 4 大类覆盖 ≥ 90%
- [ ] sprint7-uncategorized-report.md

### B 部分
- [ ] T4: Parquet 改 zstd 压缩 (可选 Sprint 7b 验证)
- [ ] T5: README.md + CHANGELOG.md
- [ ] T6: git tag v1.1.0
- [ ] sprint7-release-report.md

**总计**: 32 (Sprint 6) + ~6 (Sprint 7) = **~38 commits** + tag

---

## 🦞 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| top 11 types 推测全错 | 中 | 高 | 摸排 T1 验证后再 commit T2 (不开绿灯不写代码) |
| zstd 压缩率不及预期 | 低 | 中 | 留 fallback · sprint 7b 单独实验 |
| 重新分类破坏 Sprint 5-6 兼容 | 低 | 中 | TYPE_CATEGORY_MAPPING 后向兼容 (旧 API 不变) |
| 28 types 中长尾不能归类 | 高 | 低 | 长尾归 rare_event · 与 Sprint 6 设计一致 |

---

## 🦞 Sprint 7 时间预算

- **A 部分 (T1-T3)**: 3-4 d
- **B 部分 (T4-T6)**: 1-2 d
- **总计**: 4-6 d (匹配 v1.0 → v1.1 节奏)

### Sprint 8 (C 部分 · gpcw 财务领域)
- T1: gpcw 解析器实现 (~3 d)
- T2: gpcw type 字段语义映射 (~2 d)
- **总计**: 3-5 d

---

## 🦞 Sprint 7 计划 commit 数

| Sprint | T1 | T2 | T3 | T4 | T5 | T6 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sprint 7 commits | 1 | 1 | 1 | 1 | 1 | 1 | **6** |
| Sprint 7 测试 | - | - | 25 | - | - | - | **25** |

**v1.1 累计**: 32 + 6 = **~38 commits** · 201 + 25 = **~226 PASSED**

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>