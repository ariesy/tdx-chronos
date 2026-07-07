# tdx-chronos

> **v1.4.0 (Sprint 10 · Query Facade)** · A 股离线数据仓库 · 通达信 .day/.dat 集中下载 + Parquet 整理 + 本地统一查询接口

[![Status](https://img.shields.io/badge/status-v1.4.0-blue)]() [![Python](https://img.shields.io/badge/python-3.12-green)]() [![Tests](https://img.shields.io/badge/tests-229%20passed-brightgreen)]() [![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

**设计哲学**：Facade Pattern — 底层解析细节对调用方透明；Readonly-first — 所有写操作通过 `readonly=False` 显式授权；Real-data-tested — 每一行代码在真实数据上验证；No-network — 纯本地数据查询；TDD coverage — 229 tests passing。

## 快速开始

```python
from pathlib import Path
from tdx_chronos import TdxChronos

tdx = TdxChronos(data_dir=Path("/data/tdx"))  # 5 子路径: gp/, index/, parquet_compact/, fin/parsed/, meta/meta.db

info = tdx.symbol_info("sh600000")
klines = tdx.kline("sh600000", start="2024-01-01", end="2024-12-31")
quarters = tdx.list_quarters()  # ['20201231', '20210331', ...]
df = tdx.finance("000858", report_date="2025-12-31")
holders = tdx.shareholders("sh600000")
index_df = tdx.index_klines("sh000001", start="2024-01-01")
report = tdx.doctor()  # 健康检查

tdx.close()
```

## 数据布局

```
data_dir/
├── gp/records.parquet              # 股东信息 (7,571 .dat · 120M+ records)
├── index/indices.parquet           # 指数 K 线 (28,004 records · 5 指数)
├── parquet_compact/{market}/{symbol}.parquet   # 个股 K 线 (per-symbol 分片)
├── fin/parsed/gpcw{YYYYMMDD}.parquet           # 财报 (按季度, code 在 index 列)
└── meta/meta.db                    # SQLite · symbol_metadata 表
```

## API Reference

### `TdxChronos(data_dir, *, readonly=True)`

数据仓库入口。`data_dir` 下需包含上述 5 个数据子路径。`readonly=True` 时禁止任何写操作。

```python
tdx = TdxChronos(Path("/data/tdx"))
```

---

### `symbol_info(symbol) → dict`

返回个股基本信息（名称、市场、上市日期等），来自 SQLite `symbol_metadata` 表。

```python
info = tdx.symbol_info("sh600000")
# {'symbol': 'sh600000', 'market': 'sh', 'first_listing_date': 19991110,
#  'last_parsed_at': '...', 'record_count': 6340, ...}
```

---

### `list_symbols(market=None) → list[str]`

列出所有股票代码。可选 `market` 过滤（如 `"sh"` / `"sz"`）。

```python
codes = tdx.list_symbols()          # 所有
codes = tdx.list_symbols("sz")     # 深市
```

---

### `kline(symbol, start=None, end=None, *, columns=None) → DataFrame`

读取个股日线 K 线（来自 `parquet_compact/{market}/{symbol}.parquet`）。

```python
df = tdx.kline("sh600000", start="2024-01-01", end="2024-12-31")
# columns: date, open, high, low, close, volume, amount, ...
df = tdx.kline("sh600000", start="2024-01-01", end="2024-12-31", columns=["date", "open", "high", "low", "close"])
# 只投影需要的列 (predicate pushdown + column projection)
```

---

### `index_klines(index_code, start=None, end=None) → DataFrame`

读取指数日线 K 线（来自 `index/indices.parquet`，按 `symbol` 列过滤）。

```python
df = tdx.index_klines("sh000001", start="2024-01-01", end="2024-12-31")
# columns: date, open, high, low, close, volume, amount, symbol, market, ...
```

---

### `finance(symbol, *, report_date=None, ratio_only=False) → DataFrame`

读取个股财报数据（来自 `fin/parsed/gpcw{YYYYMMDD}.parquet`）。

```python
df = tdx.finance("000858", report_date="2025-12-31")
# columns: code, report_date, revenue, net_profit, assets, liabilities, ...
df = tdx.finance("000858", report_date="2025-12-31", ratio_only=True)
# 仅返回财务比率（roe, eps, pe, pb 等）
```

---

### `shareholders(symbol) → DataFrame`

读取个股股东数据（来自 `gp/records.parquet`，按 `code` 列过滤）。

```python
df = tdx.shareholders("sh600000")
# columns: code, type, date, value_1, value_2, market, type_name
```

---

### `list_quarters() → list[str]`

返回所有可用财报季度列表（来自 `fin/parsed/`，从文件名提取）。

```python
quarters = tdx.list_quarters()
# ['20201231', '20210331', '20210630', '20210930', ...]
```

---

### `doctor() → DoctorReport`

运行健康检查，验证数据完整性，返回结构化报告。

```python
report = tdx.doctor()
# DoctorReport(fields: total_files, missing_dirs, empty_files, corrupt_parquet, stats)
```

---

### `close()`

关闭数据库连接，释放资源。

```python
tdx.close()
```

---

## 项目状态

| Sprint | 关键变更 | 日期 | 状态 |
|---|---|---|---|
| 0 | 项目初始化 + vendoring | 2026-07-03 | ✅ |
| 1 | mootdx Vendor + 4 bug 真相 | 2026-07-03 | ✅ |
| 2 | 抽象层 + 股本元数据 SQLite | 2026-07-04 | ✅ |
| 3-4 | 解析 + Parquet 输出 + 元数据 | 2026-07-04 | ✅ |
| 5 | cron 接入 + doctor + 飞书告警 | 2026-07-05 | ✅ |
| 6 | 股本 type 字段语义 (14 types) + gpcw bug 修复 | 2026-07-05 | ✅ |
| 7 | 未分类 28 types 语义 (33 types) + zstd 实验 | 2026-07-05 | ✅ |
| 8 | gpcw 财务领域解析 (预留) | TBD | ⏳ |
| 10 | **Query Facade v1.4.0 · 9 public methods** | **2026-07-07** | **✅** |

v1.4.0 · 229 PASSED · 10 Sprint

## 文档

- **需求文档**: `requirements.md` · 唯一权威
- **Sprint 计划**: `docs/plans/`
- **Sprint 报告**: `logs/sprint{N}-report.md`
- **贡献指南**: `docs/CONTRIBUTING.md`

## License

MIT

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiren@gmail.com>
