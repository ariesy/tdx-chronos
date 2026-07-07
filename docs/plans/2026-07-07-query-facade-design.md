# Query Facade Design · 统一查询接口 (data_dir 路径参数化)

**项目**: tdx-chronos v1.4 (Sprint 10)
**作者**: claw-cortex 🦞
**日期**: 2026-07-07 (UTC)
**关联**: 主人原话 "基于所有离线数据,封装统一 Python module 对外提供查询接口"
**主人澄清**: server-only / 不分发 / data_dir 参数化 / 避免重复复制数据

---

## 🎯 目标

**Issue**: tdx-chronos 当前 5 类数据 (K线 / 股本 / 5 指数 / 财务 / 元数据) 散落在不同子模块, 调用需要了解:
- `pd.read_parquet('data/fin/parsed/gpcw20251231.parquet')` ← 财务
- `TdxGpRecordReader.run_full_parse(...)` ← 股本
- `IndexParser.parse_all(...)` ← 指数
- `MetaDB(...).count_symbols()` ← 元数据
- 路径硬编码 / 实现细节暴露 / 没有统一错误处理

**Goal**: 提供 **单 class umbrella** `TdxChronos(data_dir)`:
- ✅ `tdx.kline("sh600000")` 一个方法拿 K线 DataFrame
- ✅ `tdx.finance("600000")` 一个方法拿财务 DataFrame
- ✅ `tdx.shareholders("600000")` 股本
- ✅ `tdx.index_klines("sh000300")` 指数
- ✅ `tdx.symbol_info("sh600000")` 元数据
- ✅ 零数据拷贝, data_dir 必传
- ✅ Jupyter / 一次性脚本友好

---

## ❌ Must NOT (non-goals)

| 项 | 不做 | 理由 |
|---|---|---|
| PyPI 分发 | `pip install tdx-chronos` | 主人明确 "先不考虑包分发" |
| HTTP / REST API | FastAPI / Flask | 主人明确 "无需使用 http 请求" |
| 缓存层 | LRU cache / Redis / disk cache | v1.4 极简 (数据已在磁盘, pandas/pyarrow 自身有 cache) |
| 写入 API | 不能 `tdx.write(...)` 修改任何数据 | facade 只 read, cron 写 |
| 修改现有 API | `Doctor / Alertor / MetaDB / TdxFinReader` 全保留 | 向后兼容 |
| Async API | 同步 pandas API 即可 | 数据量 GB 级, async 无明显收益 |

---

## 📐 设计

### 模块结构

**新增 1 个文件** (`src/tdx_chronos/client.py`, ≤ 350 行):

```
src/tdx_chronos/
├── __init__.py            # 仅 re-export public API
├── client.py              # 新增: TdxChronos facade
├── doctor.py              # 现有 (不动)
├── alertor.py             # 现有 (不动)
├── meta/db.py             # 现有 (不动)
├── fin/                   # 现有 (不动)
├── sources/               # 现有 (不动)
└── optimization/          # 现有 (不动)

tests/unit/
├── test_client.py         # 新增: TddClient × 20-30 cases
└── ... (现有不动)
```

### Public API

```python
from pathlib import Path
from typing import Optional, List
import pandas as pd

class TdxChronos:
    """5 类离线数据统一 facade · data_dir 必传 (零数据拷贝)

    Args:
        data_dir: 必传 · 数据根目录 (例如 /app/tdx-chronos/data)
                  必须包含子目录:
                    parquet_compact/  K线
                    fin/parsed/       财务
                    gp/records.parquet   股本
                    index/indices.parquet  5 指数
                    meta/meta.db      元数据 SQLite

    Attributes:
        data_dir:   Path
        parquet_compact: Path = data_dir / "parquet_compact"
        fin_parsed:  Path = data_dir / "fin" / "parsed"
        gp_records:  Path = data_dir / "gp" / "records.parquet"
        index_klines: Path = data_dir / "index" / "indices.parquet"
        meta_db:     Path = data_dir / "meta" / "meta.db"

    Example:
        >>> tdx = TdxChronos(data_dir="/app/tdx-chronos/data")
        >>> df = tdx.kline("sh600000", start="2024-01-01", end="2024-12-31")
        >>> df.head()
                      date   open   high    low   close    volume       amount
        0   2024-01-02  ...    ...   ...   7.82   25378900  198478000.0
    """

    def __init__(self, data_dir: Path | str, *, readonly: bool = True) -> None:
        ...

    # ---- 5 类数据方法 ----
    def kline(
        self,
        symbol: str,             # 'sh600000' or 'sz000001' or 'bj838000'
        start: Optional[str] = None,   # 'YYYY-MM-DD'
        end: Optional[str] = None,
        columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """K 线 · 单 symbol · 返回 pandas DataFrame

        Raises:
            FileNotFoundError: data_dir 不含 parquet_compact
            ValueError:       symbol 不在 12,258 stocks 范围
        """

    def finance(
        self,
        symbol: str,             # 支持 'sh600000' 或 '600000' (兼容)
        report_date: Optional[str] = None,  # 'YYYY-MM-DD' or 'YYYYMMDD' 或 None = 最新
        ratio_only: bool = False,
    ) -> pd.DataFrame:
        """单季度财务 · 581 字段 (or 仅 ratio)"""

    def shareholders(
        self,
        symbol: str,
    ) -> pd.DataFrame:
        """股本 (1 个 symbol 1 行 · 全部字段)"""

    def index_klines(
        self,
        index_code: str,         # 'sh000001' 上证 / 'sz399001' 深证 /
                                 # 'sz399006' 创业板 / 'sh000300' 沪深300 /
                                 # 'sh000688' 科创50
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """5 指数 日线"""

    def symbol_info(self, symbol: str) -> dict:
        """symbol metadata · 12,256 行中一行"""

    # ---- list / iteration ----
    def list_symbols(self, market: Optional[str] = None) -> List[str]:
        """list 全部 symbols (or 仅 'sh'/'sz'/'bj')"""

    def list_quarters(self) -> List[str]:
        """list 已 parsed 季度 e.g. ['2025-12-31', '2025-09-30', ...]"""

    # ---- 健康检查 ----
    def doctor(self) -> DoctorReport:
        """复用现有 Doctor().run()"""

    # ---- 资源管理 ----
    def close(self) -> None:
        """关闭 meta.db connection"""
```

### 数据路径解析 (Phase 1 输入)

```python
def __init__(self, data_dir: Path | str, *, readonly: bool = True):
    self.data_dir = Path(data_dir).resolve()
    if not self.data_dir.is_dir():
        raise FileNotFoundError(f"data_dir 不存在: {self.data_dir}")

    # 5 类子路径 · 缺一个 raise (fail-fast)
    self.parquet_compact = self.data_dir / "parquet_compact"
    self.fin_parsed = self.data_dir / "fin" / "parsed"
    self.gp_records = self.data_dir / "gp" / "records.parquet"
    self.index_klines = self.data_dir / "index" / "indices.parquet"
    self.meta_db_path = self.data_dir / "meta" / "meta.db"

    missing = [p for p in [
        self.parquet_compact, self.fin_parsed,
        self.gp_records, self.index_klines, self.meta_db_path,
    ] if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"data_dir 不完整 ({len(missing)}/5 缺失):\n  " +
            "\n  ".join(str(p) for p in missing)
        )

    # readonly 校验: 启动时尝试 touch 一个 sentinel, 然后 chmod -w 校验
    # (确保 cron 写入不受 facade 影响)
    if readonly:
        self._lock_for_readonly()  # 简单: chmod 0444 on subdirs
        # ... close() 时 restore

    # lazy: 第一次实际 query 时再 init
    self._db: Optional[MetaDB] = None
```

### 各方法实现策略

#### `kline(symbol, start, end)` 

```python
def kline(self, symbol, start=None, end=None, columns=None):
    # 1. 找所在 market (sh/sz/bj)
    market = self._infer_market(symbol)  # 从 symbol 前缀推断
    market_file = self._get_market_file(market)  # parquet_compact/{market}.parquet

    # 2. 用 pyarrow + predicate pushdown 读高效子集
    import pyarrow.parquet as pq
    table = pq.read_table(
        market_file,
        filters=[
            ('symbol', '=', symbol),
            *(('date', '>=', _to_int(start)) if start else []),
            *(('date', '<=', _to_int(end)) if end else []),
        ],
        columns=columns,
    )
    return table.to_pandas().sort_values('date').reset_index(drop=True)
```

**性能考量**: parquet_compact/sh.parquet 是 1 个文件, ~700 MB, 12k stocks × N 日. pyarrow `filters` 走 row-group 跳读, 单 symbol 读 < 1s.

#### `finance(symbol, report_date)`

```python
def finance(self, symbol, report_date=None, ratio_only=False):
    # 1. 找到 stock 在每个 quarter parquet 中的行
    # strategy: 用 pyarrow multiget 或 read-all + filter (因为 258 quarters × 5524 stocks = 1.4M rows 总量)
    fin_files = sorted(self.fin_parsed.glob("gpcw*.parquet"))

    # 2. 提取 target report_dates
    target_dates = self._resolve_target_dates(report_date)  # list of int

    # 3. read & filter
    rows = []
    for f in fin_files:
        rd = int(f.stem.replace("gpcw", ""))   # 20251231
        if rd not in target_dates:
            continue
        df = pd.read_parquet(f, columns=["code", *_columns_or_all()])
        match = df[df["code"] == _normalize_symbol(symbol)]
        if not match.empty:
            rows.append(match.assign(report_date=rd))
    return pd.concat(rows).reset_index(drop=True) if rows else pd.DataFrame()
```

**性能**: 258 × 5524 行 = ~1400 行 / symbol, 全部读 in-memory ~ 600MB peak (一次性, OK).

#### `shareholders(symbol)`

```python
def shareholders(self, symbol):
    # gp/records.parquet 是 120M 行的全股本库 · 单 symbol 必 filter
    table = pq.read_table(
        self.gp_records,
        filters=[('symbol', '=', symbol)],
    )
    return table.to_pandas()
```

**性能**: predicate pushdown on 120M 行 → < 1s.

#### `index_klines(index_code, start, end)`

```python
def index_klines(self, index_code, start=None, end=None):
    table = pq.read_table(
        self.index_klines,
        filters=[
            ('index_code', '=', index_code),
            *(('date', '>=', _to_int(start)) if start else []),
            *(('date', '<=', _to_int(end)) if end else []),
        ],
    )
    return table.to_pandas().sort_values('date').reset_index(drop=True)
```

**性能**: 5 指数 × ~5000 日 = ~25k 行 · 全 file OK.

#### `symbol_info(symbol)`

```python
def symbol_info(self, symbol):
    db = self._ensure_db()
    row = db._connect().execute(
        "SELECT * FROM symbol_metadata WHERE symbol=?",
        (symbol,),
    ).fetchone()
    return dict(row) if row else {}
```

#### `list_symbols(market)` / `list_quarters()`

```python
def list_symbols(self, market=None):
    db = self._ensure_db()
    if market:
        return db.get_symbols_by_market(market)
    rows = db._connect().execute("SELECT symbol FROM symbol_metadata").fetchall()
    return [r["symbol"] for r in rows]

def list_quarters(self):
    # list fin/parsed/gpcw*.parquet
    return sorted([
        f.stem.replace("gpcw", "") for f in self.fin_parsed.glob("gpcw*.parquet")
    ])
```

### readonly 校验

```python
def _lock_for_readonly(self):
    """chmod -R a-w on 5 dirs · ensure facade 不修改数据"""
    import os, stat
    for path in [self.parquet_compact, self.fin_parsed,
                 self.gp_records, self.index_klines]:
        if path.is_dir():
            os.chmod(path, stat.S_IRUSR | stat.S_IX_USR)
    # 实际 file: chmod 444
    for p in [self.gp_records, self.index_klines, self.meta_db_path]:
        if p.is_file():
            os.chmod(p, stat.S_IRUSR)
```

注意: `close()` 时要 chmod 回 644 / 755 让 cron 能写。

### Symbol normalization 兼容

```python
def _normalize_symbol(symbol: str) -> str:
    """兼容 '600000' 和 'sh600000' 两种写法 · 内部统一"""
    s = symbol.lower().strip()
    if s.startswith(("sh", "sz", "bj")):
        return s
    if s.startswith(("5", "6", "9", "1")):  # sh (5/6/9 ...) + bj (8/4 ...)
        return "sh" + s
    if s.startswith(("0", "2", "3")):
        return "sz" + s
    return s  # 兜底
```

---

## 🧪 测试策略 (TDD 优先 — Phase 3)

### Tests (`tests/unit/test_client.py`, 25 cases)

| Test class | Cases |
|---|---|
| `TestInit` | 5 paths 存在 ✓ / 不存在 raise ✓ / readonly mode ✓ |
| `TestKline` | 单 symbol ✓ / start+end filter ✓ / 不存在 symbol raise ✓ / columns subset ✓ |
| `TestFinance` | 单 quarter ✓ / 多 quarters ✓ / ratio_only ✓ / 不存在 symbol → empty ✓ |
| `TestShareholders` | 单 symbol ✓ / 不存在 → empty ✓ |
| `TestIndexKlines` | sh000001 ✓ / start+end ✓ / 5 指数全覆盖 ✓ |
| `TestSymbolInfo` | 存在 ✓ / 不存在 → empty dict ✓ |
| `TestListSymbols` | 全部 ✓ / by market ✓ |
| `TestListQuarters` | 258 季度 vs 121 parsed (实测) ✓ |
| `TestDoctor` | 9/10 DEGRADED (复现今天状态) ✓ |
| `TestReadonly` | start chmod 444 · 启动 OK · close 后 cron 能写 ✓ |
| `TestSymbolNormalize` | 'sh600000' → 'sh600000' / '600000' → 'sh600000' / '000001' → 'sz000001' ✓ |

### TDD loop (每个 method)

1. `write test_X` (red)
2. `def kline()` stub `return None` (red still)
3. 实现 (`pq.read_table(... filters=...)`)
4. re-run test (`green`)
5. refactor if needed (perf, readability)
6. commit

---

## 📊 风险与缓解

| Risk | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 3 GB parquet 整体 in-memory 爆 | 低 | 高 | pyarrow `filters=` predicate pushdown · 只读单 symbol |
| readonly chmod 误锁 cron | 中 | 高 | close() 还原 · 文档强调 "用完 close" |
| Symbol '600000' vs 'sh600000' 语义混淆 | 中 | 中 | `_normalize_symbol()` 标准化 + 单测全覆盖 |
| meta.db 慢 query on 12k rows | 低 | 低 | 已有 index on (symbol, market) |
| pyarrow 版本兼容 | 低 | 中 | lock `pyarrow>=15,<17` in pyproject.toml |

---

## ✅ 验收标准

| 标准 | 验证 |
|---|---|
| `tdx = TdxChronos(data_dir="/app/tdx-chronos/data")` 启动 ≤2s | time 命令 |
| `tdx.kline("sh600000")` 返回 ≥ 5000 行 | shape check |
| `tdx.finance("000858")` 贵州茅台 581 字段全 | column check |
| `tdx.list_symbols()` 返回 12,256 | len() check |
| `tdx.list_quarters()` 返回 258 (期望) | len() check (today: 121 due to placeholder) |
| `tdx.doctor()` 返回 9/10 (复现今日) | failed_count == 1 |
| 25/25 测试 PASSED | pytest |
| 现有 `from tdx_chronos import Doctor, MetaDB, ...` 仍工作 | smoke test |
| zero data copy (df.memory_usage 远 < 3 GB) | pandas memory check |

---

## 🚫 范围外 (Sprint 10+ 候选)

主人明确说 "先在这服务器上使用", 以下**不进 Sprint 10**:

- ⏸️ pip install / PyPI 分发
- ⏸️ HTTP / REST API
- ⏸️ 异步 API (asyncio)
- ⏸️ LRU cache / Redis cache
- ⏸️ 写入 API (tdx.write_kline 等)
- ⏸️ CLI (click/typer)
- ⏸️ 多 data_dir 合并查询

---

## 📅 Phase 拆解

| Phase | 内容 | 估算 |
|---|---|---|
| **1. Brainstorming** (本 doc) | 设计文档 + 主人拍板 | ✅ 当前 |
| **2. Writing Plans** | `docs/plans/2026-07-07-query-facade.md` 任务拆 5 task × 4h | 1d |
| **3. TDD impl** | 25 cases × 5 method × 1 hour each = ~5h | 1d |
| **4. Verification** | smoke test in Jupyter + doctor 9/10 | 0.5d |
| **5. Finish branch** | tag v1.4 + push | 0.1d |
| **总计** | | **~3 d** |

---

**Author**: claw-cortex 🦞
**Status**: Phase 1 完成 · 待主人确认设计后进 Phase 2 (writing-plans)
