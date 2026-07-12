# tdx-chronos

> **v1.4.3 (Sprint 13 · ETF 显式化 + list_etfs)** · A 股离线数据仓库 · 通达信 .day/.dat 集中下载 + Parquet 整理 + 本地统一查询接口

[![Status](https://img.shields.io/badge/status-v1.4.3-blue)]() [![Python](https://img.shields.io/badge/python-3.12-green)]() [![Tests](https://img.shields.io/badge/tests-330%20passed-brightgreen)]() [![License](https://img.shields.io/badge/license-MIT-lightgrey)]()

**设计哲学**：Facade Pattern — 底层解析细节对调用方透明；Readonly-first — 所有写操作通过 `readonly=False` 显式授权；Real-data-tested — 每一行代码在真实数据上验证；No-network — 纯本地数据查询；TDD coverage — 330 tests passing。

## 快速开始

```python
from pathlib import Path
from tdx_chronos import TdxChronos

tdx = TdxChronos(data_dir=Path("/data/tdx"))  # 5 子路径: gp/, index/, parquet_compact/, fin/parsed/, meta/meta.db

# ── A 股 ──
info = tdx.symbol_info("sh600000")
klines = tdx.kline("sh600000", start="2024-01-01", end="2024-12-31")
quarters = tdx.list_quarters()  # ['20260331', '20251231', ...] DESC
df = tdx.finance("000858", report_date="2025-12-31")
holders = tdx.shareholders("sh600000")
index_df = tdx.index_klines("sh000001", start="2024-01-01")
report = tdx.doctor()  # 健康检查
df = tdx.shareholders_history("sh600000", types=[1,2,3,4], since_date="2024-01-01", limit=10)

# ── ETF / 场内基金 (Sprint 13 显式化) ──
etfs = tdx.list_etfs()                       # 全部 ETF/LOF/REITs/可转债
sh_etfs = tdx.list_etfs(market="sh")         # 仅沪市 (50ETF/510300/588200/...)
sz_etfs = tdx.list_etfs(market="sz")         # 仅深市 (159915 创业板ETF/180101 REITs/...)
df = tdx.kline("sh510050", start="2024-01-01")             # 50ETF 日线
df = tdx.kline("sz159915", start="2024-01-01")             # 创业板ETF 日线
df = tdx.shareholders("sh510050")                          # ETF 股本变动 (有数据)
df = tdx.finance("sh510050")                               # → 空 DataFrame (tdxfin.zip 不含基金)

tdx.close()
```

> 📌 **覆盖范围速查** (12,279 symbols)
> - A 股 (主板/创业板/科创板/北交所): 日 K + 财务 + 股本
> - **场内基金** (ETF + LOF + 封闭基金 + REITs): 日 K + 股本 (**财务不可用**)
> - **可转债** (沪 110-113 / 深 123/127/128): 日 K + 股本 (**财务不可用**)
> - 主要指数 (sh000xxx/sz399xxx): 日 K

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

> 含 A 股 + 场内基金 (含 ETF) + 可转债 + REITs + 指数。要仅取 ETF/基金，用 `list_etfs()`。

---

### `list_etfs(market=None) → list[str]`  · **v1.4.3 新增**

列出场内基金 / ETF / LOF / REITs / 可转债代码。按通达信 / SSE / SZSE 公开代码段规则过滤。

```python
etfs = tdx.list_etfs()                  # 全部 ETF/LOF/REITs/可转债
etfs = tdx.list_etfs(market="sh")       # 仅沪市 (50ETF/510300/588200/...)
etfs = tdx.list_etfs(market="sz")       # 仅深市 (159915 创业板ETF/180101 REITs/...)
```

| 代码段 | 类型 | 例子 |
|---|---|---|
| `sh500xxx` | 沪市老封闭式基金 | sh500001 基金金泰 |
| `sh510xxx` ~ `sh518xxx` | 沪市 ETF (跨/单/跨境/主题) | sh510050 50ETF, sh510300 沪深300ETF |
| `sh511xxx` | 国债 / 黄金 / 货币 ETF | sh511010 国债ETF |
| `sh512xxx` | 沪市行业 ETF | sh512760 芯片ETF |
| `sh513xxx` | 跨境 / QDII ETF | sh513500 标普500ETF |
| `sh56xxxx` | 沪市 LOF | — |
| `sh588xxx` | 科创板 ETF | sh588200 科创50ETF |
| `sh11xxxx` | 沪市可转债 | — |
| `sz159xxx` | **深市 ETF** | sz159915 创业板ETF |
| `sz16xxxx` | 深市 LOF | — |
| `sz18xxxx` | **深市公募 REITs** | sz180101 |
| `sz12xxxx` | 深市可转债 | — |

数据可用性：**日 K 线 ✅ 股本 ✅ 财务 ❌** (tdxfin.zip 不含基金 — 见 `finance()` 文档)

---

### `kline(symbol, start=None, end=None, *, columns=None) → DataFrame`

读取个股日线 K 线（来自 `parquet_compact/{market}/{symbol}.parquet`）。

**同样适用于场内基金 (含 ETF) / 可转债 / 指数** — API 一致，hsjday.zip 全覆盖。

```python
df = tdx.kline("sh600000", start="2024-01-01", end="2024-12-31")
# columns: date, open, high, low, close, volume, amount, ...
df = tdx.kline("sh600000", start="2024-01-01", end="2024-12-31", columns=["date", "open", "high", "low", "close"])
# 只投影需要的列 (predicate pushdown + column projection)

# ETF 同 API
df = tdx.kline("sh510050", start="2024-01-01")   # 50ETF
df = tdx.kline("sz159915", start="2024-01-01")   # 创业板ETF
df = tdx.kline("sh588200", start="2024-01-01")   # 科创50ETF
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

> ⚠️ **ETF / 场内基金 / 可转债 不在 `tdxfin.zip` 范围内**。对 `sh510050` / `sz159915` 等代码调用本方法会直接返回**空 DataFrame**（非错误）。基金财务数据需走 tushare `fund_basic` 或类似第三方源。

---

### `shareholders(symbol) → DataFrame`

读取个股股东数据（来自 `gp/records.parquet`，按 `code` 列过滤）。

```python
df = tdx.shareholders("sh600000")
# columns: code, type, date, value_1, value_2, market, type_name
```

> **同样支持场内基金 (含 ETF) / 可转债**（来自 tdxgp.zip，包含 sh5/sz1 等代码段）。实测 sh510050 有 ~2000 行股本变动 records。

---

### `shareholders_history(symbol, types=None, since_date=None, until_date=None, limit=None) → DataFrame`

股本历史（带 filter 条件）。来自 `gp/records.parquet`，按 date DESC 排序。

```python
df = tdx.shareholders_history("sh600000", types=[1, 2, 3, 4], since_date="2024-01-01", limit=10)
# columns: type, date, value_1, value_2, market, code, symbol
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
| 11 | Incremental Finance + `shareholders_history()` | 2026-07-08 | ✅ |
| 12 | 9 个 client 层 bug 集中修复 | 2026-07-08 | ✅ |
| 13 | **ETF 显式化 · `list_etfs()` + 文档更新** | **2026-07-10** | **✅** |

v1.4.3 · 330 PASSED · 13 Sprint

## 文档

- **需求文档**: `requirements.md` · 唯一权威
- **Sprint 计划**: `docs/plans/`
- **Sprint 报告**: `logs/sprint{N}-report.md`
- **贡献指南**: `docs/CONTRIBUTING.md`

## License

MIT

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiren@gmail.com>
