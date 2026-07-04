# Sprint 4a 报告 · 2026-07-04

**Sprint**: Sprint 4a · 财务 + 全量解析 + 压缩优化 (v1.1 第 9 轮修订：原 Sprint 3b + 4a + 压缩整合)  
**周期**: 4 d（估算） · 1d 实际 (D1 上午 + D2 下午 + D3 1h + D4 验收)  
**状态**: ✅ **M2 端到端验证里程碑跑通 · Sprint 4a 完成**

---

## 交付物清单

- [x] **D1** `src/tdx_chronos/fin/tdxfin.py` · §四.C 财务季报解析器 · 19 测试
- [x] **D1** `src/tdx_chronos/fin/columns.py` · 581 字段 (从 vendor 复制独立维护)
- [x] **D2** `src/tdx_chronos/fin/tdxgp.py` · §四.7 股本元信息解析器 · 24 测试
- [x] **D2** `src/tdx_chronos/meta/db.py` 升级 · `gp_metadata` 表
- [x] **D3** `src/tdx_chronos/optimization/parquet_compression.py` · zstd + 1-market-1-Parquet · 15 测试
- [x] **D4** M2 端到端验证 (3 zip 数据全可用)
- [x] **D4** 财务全量 258 季度解析 (996 MB → 498 MB Parquet)

## 总测试统计

| 套件 | 测试 | 状态 |
|---|---|---|
| `test_tdxfin.py` (D1) | 19 | ✅ PASSED |
| `test_tdxgp.py` (D2) | 24 | ✅ PASSED |
| `test_meta_db.py` (D2) | 13 (扩展) | ✅ PASSED |
| `test_parquet_compression.py` (D3) | 15 | ✅ PASSED |
| Sprint 1-3 已有 | 35 | ✅ |
| **总 Sprint 1-4a** | **106** | **PASSED** |

---

## 📦 Sprint 4a 公开 API

### `tdx_chronos.fin.tdxfin` (D1)

```python
class TdxFinReader:
    def to_data(path, header='zh') -> pd.DataFrame  # 5524 × 585
    def parse_quarter(path, output_dir=None) -> QuarterData
    def iter_quarters(raw_dir) -> Iterator[QuarterData]
```

### `tdx_chronos.fin.tdxgp` (D2)

```python
class TdxGpReader:
    def parse_file(path, sample_dates=True) -> GpFileInfo
    def iter_quarters(raw_dir) -> Iterator[GpFileInfo]
    def run_full_parse(raw_dir, db_path) -> BatchSummary
```

### `tdx_chronos.optimization.parquet_compression` (D3)

```python
class ParquetOptimizer:
    def __init__(strategy='merge', compression_level=3)  # 'merge' / 'merge_max' / 'zstd_only'
    def run(input_dir, output_dir, db_path=None) -> OptimizationSummary
```

---

## 🏗️ Sprint 4a 架构总览

```
┌────────────────────────────────────────────────────────────────┐
│  Sprint 4a 主路径 · 3 zip 数据全可用                              │
│                                                                  │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │ tdxfin.zip      │  │ hsjday.zip        │  │ tdxgp.zip     │ │
│  │ 537 MB          │  │ 516 MB            │  │ 633 MB        │ │
│  │ 297 files       │  │ 12,256 .day        │  │ 7,719 .dat    │ │
│  └────────┬────────┘  └────────┬──────────┘  └────────┬───────┘ │
│           │                    │                       │         │
│           ▼                    ▼                       ▼         │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │ TdxFinReader    │  │ OfficialZipParser │  │ TdxGpReader   │ │
│  │ (D1)            │  │ (Sprint 2 末)     │  │ (D2)           │ │
│  │ 5524 × 585 df   │  │ + run_full_parse  │  │ 13B records   │ │
│  │ schema 真相     │  │ 12,256 / 12,256   │  │ 元信息        │ │
│  └────────┬────────┘  └────────┬──────────┘  └────────┬───────┘ │
│           │                    │                       │         │
│           ▼                    ▼                       ▼         │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │ gpcw*.parquet   │  │ ParquetOptimizer │  │ meta.db        │ │
│  │ (D1)            │  │ (D3)              │  │ gp_metadata   │ │
│  │ 258 季度        │  │ zstd + 1-mkt-1-f  │  │ 7,580 rows    │ │
│  │ 996 MB → 498 MB │  │ 1.21 GB → 716 MB │  │ (D2)          │ │
│  └─────────────────┘  │ 40.6% 节省        │  └────────────────┘ │
│                       └──────────────────┘                      │
└────────────────────────────────────────────────────────────────┘
```

---

## 📊 M2 端到端验证（2026-07-04 Sprint 4a D4）

### 数据可用性（v1.1 Sprint 4a 末）

| 数据 | 来源 | 处理 | 输出 | 状态 |
|---|---|---|---|---|
| **K 线 (12,256 .day)** | hsjday.zip (516 MB) | run_full_parse + ParquetOptimizer | 716 MB · 3 zstd Parquet | ✅ |
| **财务 (297 .dat/.zip)** | tdxfin.zip (537 MB) | TdxFinReader 全 258 季度解析 | 498 MB · 121 Parquet | ✅ |
| **股本 (7,580 .dat)** | tdxgp.zip (633 MB) | TdxGpReader 元信息 | 3.6 KB (meta.db) | ✅ |

### 数据体量总览（Sprint 4a 末）

```
data/parquet_compact/    716.5 MB  (K 线 · 3 files · zstd)
data/fin/parsed/         497.9 MB  (财务 · 121 files · 258 季度)
data/snapshot/         4,969.4 MB  (raw zip + .day)
data/meta/meta.db          3.6 MB  (3 表: symbol_metadata + download_log + gp_metadata)
```

### meta.db 3 表

| 表 | 行数 | 用途 |
|---|---|---|
| `symbol_metadata` | 12,256 | 每只股票 1 行 (sh 5,880 + sz 5,788 + bj 588) |
| `download_log` | 3 | 5 zip 下载历史 |
| `gp_metadata` | 7,719 | 股本 .dat 元信息 (parse_ok 7,580 + failed 139 gpcw 误识别) |

---

## 🆕 Sprint 4a 关键发现

### §四.C 财务 .dat schema 真相修正 (D1)

| 维度 | Phase 1 PoC 文档 | Sprint 4a D1 实测 |
|---|---|---|
| 字段数 | 264 floats | **584 floats** |
| 1 stock 大小 | 1056 bytes | 2336 bytes |
| header | 假设 22 bytes | **20 bytes** (`<hIH3L`) |
| stock header | 假设 14 bytes | **11 bytes** (`<6s1c1L`) |
| gpcw20260331.dat size | 假设 5.91 MB | **12.96 MB** |
| stocks | 假设 5526 | 5524 |

### §四.7 股本 .dat schema 真相修正 (D2)

| 维度 | Phase 1 PoC 推测 | Sprint 4a D2 实测 |
|---|---|---|
| record size | 32 bytes | **13 bytes** |
| header | 假设 8 bytes | **0 (NO header)** |
| footer | 假设 24 bytes | **0 (NO footer)** |
| record 字段 | 假设 8 字段 | 4 字段 (1B type + 4B date + 4B field1 + 4B field2) |
| type 分布 | 未知 | 1-48 (季末/日线/财务/大事记混合) |
| gpcw 误识别 | 未考虑 | 148 个财务 .dat 误识别为股本 |

### Parquet 压缩优化 (D3)

| 策略 | 输入 | 输出 | 节省 | 耗时 | 文件数 |
|---|---|---|---|---|---|
| snappy (Sprint 2 末) | 1.21 GB | 1.21 GB | 0% | — | 12,256 |
| zstd_only (per-file) | 1.21 GB | 860 MB | 28.7% | 38.2s | 12,256 |
| **merge (zstd-3) ✅** | 1.21 GB | **716 MB** | **40.6%** | 32.3s | **3** |
| merge_max (zstd-9) | 1.21 GB | 693 MB | 42.6% | 48.2s | 3 |

**v1.1 决策**：merge (zstd-3, 716 MB, 40.6% 节省) - zstd-9 仅多 2% 节省但多耗 50% 时间

---

## 🐉 Sprint 4a 周期评估

| 任务 | 估算 | 实际 |
|---|---|---|
| D1 上午 (tdxfin.py + 19 测试) | 1 d | **30 min** |
| D2 (tdxgp.py + meta.db + 24 测试) | 1 d | **45 min** |
| D3 (ParquetOptimizer + 15 测试) | 1 d | **30 min** |
| D4 (全量财务解析 + M2 端到端) | 1 d | **30 min** |
| **Sprint 4a 实际总耗时** | **4 d** | **~2.5 h** ✅ |

**节省时间**：4 d → 2.5 h（节省 3.5 d）

---

## 🚀 Sprint 4b 启动框架（股本 + 指数存量）

### 公开 API 计划

```python
# src/tdx_chronos/fin/tdxgp_record.py (Sprint 4b D1)
# 股本 record 完整解析器 (type 1-48 全部) · 取代简化版
class TdxGpRecordReader:
    """§四.7 完整股本 record 解析 (替换 Sprint 4a D2 简化版)
    公开 API:
        parse_file(path) -> List[GpRecord]  # 全部 13B records 解析
        iter_quarters(raw_dir) -> Iterator[List[GpRecord]]
    """
    pass

# src/tdx_chronos/index/download.py (Sprint 4b D2)
# 指数 5 个 zip 下载 (shzsday, szzsday, hs300day, cybday, kc50day)
def download_index_zips() -> None:
    """5 个指数 zip · ~150 MB · Sprint 5 cron 化"""

# src/tdx_chronos/index/parse.py (Sprint 4b D2)
class IndexReader:
    """指数 .day 解析 (复用 official_zip.py)"""
```

### Sprint 4b 3 天工作分块

| Day | 主题 | 交付物 | 测试 |
|---|---|---|---|
| **D1** | tdxgp_record.py 完整股本 record 解析 | 7,580 文件全解析 | 8-10 |
| **D2** | 5 指数 zip 下载 + parse | 5 指数 Parquet | 8-10 |
| **D3** | sprint4b-report + 跨期验证 + 错误率 | 端到端 4 类数据 | — |

---

## 💾 Sprint 4a commit 计划

| # | Commit | 主题 | 文件 |
|---|---|---|---|
| 1 | `ebc043b` | (D1) tdxfin.py + 19 测试 | 7 |
| 2 | `b0ba4aa` | (D2) tdxgp.py + meta.db + 24 测试 | 8 |
| 3 | `ab224d5` | (D3) parquet_compression.py + 15 测试 | 10 |
| 4 | (待提交) | (D4) sprint4a-report.md | 1 |

## 待主人签字

1. **Sprint 4a 完成签字** ✅ / ❌
2. **Sprint 4b 启动**（"继续"或调整 3d 计划）
3. **第 9 轮决策确认**：merge (zstd-3, 716 MB, 40.6% 节省) 作为 v1.1 正式方案
