# [Feature] Query Facade · Implementation Plan

> **For implementer:** Use TDD throughout. Write failing test first. Watch it fail. Then implement.

**Goal:** 封 `TdxChronos(data_dir)` facade, 让 Jupyter / 一次性脚本通过 `pip install -e . && from tdx_chronos.client import TdxChronos` 即可调用 5 类离线数据 (K线 / 财务 / 股本 / 5 指数 / 元数据), 不做 HTTP / PyPI, data_dir 参数化零拷贝。

**Architecture:** 单文件 `src/tdx_chronos/client.py` 实现 facade, 用 pyarrow `filters=` predicate pushdown 在 5 个 parquet 文件中按 symbol / date 跳读, MetaDB SQLite 提供元数据查询。`__init__` 校验 5 子路径存在 + readonly mode 默认 chmod 444, lazy init MetaDB。

**Tech Stack:** Python 3.12, pyarrow (parquet), pandas, SQLite (MetaDB 已存在), pytest.

---

## Task 1: 项目骨架 + 失败测试 (scaffold)

**Files:**
- Create: `src/tdx_chronos/client.py` (空 stub)
- Create: `tests/unit/test_client.py` (空 test class)

**Step 1: Write failing test**
```python
"""Phase 1 TDD · TdxChronos facade scaffolding"""
import pytest

def test_tdx_client_can_be_imported():
    from tdx_chronos.client import TdxChronos
    assert TdxChronos is not None
```

**Step 2: Run — confirm fail**
```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit/test_client.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'tdx_chronos.client'`

**Step 3: Create stub `src/tdx_chronos/client.py`**
```python
"""Sprint 10 · Query Facade (TdxChronos)

Phase 1 骨架: 仅暴露 TdxChronos class (方法 stub 后续 task 加)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd


class TdxChronos:
    """5 类离线数据统一 facade · data_dir 必传 (零数据拷贝)

    Args:
        data_dir: 必传 · 数据根目录

    Attributes:
        data_dir: Path (resolved)
    """

    def __init__(self, data_dir: Path | str, *, readonly: bool = True) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.readonly = readonly
```

**Step 4: Run — confirm pass**
```bash
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit/test_client.py -v
```
Expected: PASS

**Step 5: Commit**
```bash
cd /app/tdx-chronos
git add src/tdx_chronos/client.py tests/unit/test_client.py
git commit -m "Sprint 10 T1 · scaffold TdxChronos class + import test"
```

---

## Task 2: `__init__` 校验 5 子路径 + lazy MetaDB

**Files:**
- Modify: `src/tdx_chronos/client.py`
- Modify: `tests/unit/test_client.py`

**Step 1: Write failing test**
```python
import pytest
from pathlib import Path


@pytest.fixture
def fake_data_dir(tmp_path):
    """伪造 5 子路径 + meta.db · 模拟完整数据目录"""
    (tmp_path / "parquet_compact").mkdir()
    (tmp_path / "fin" / "parsed").mkdir(parents=True)
    (tmp_path / "gp").mkdir()
    (tmp_path / "gp" / "records.parquet").touch()
    (tmp_path / "index").mkdir()
    (tmp_path / "index" / "indices.parquet").touch()
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "meta.db").touch()
    return tmp_path


def test_init_with_valid_data_dir(fake_data_dir):
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    assert tdx.data_dir == fake_data_dir.resolve()


def test_init_with_missing_data_dir_raises(tmp_path):
    from tdx_chronos.client import TdxChronos
    with pytest.raises(FileNotFoundError, match="data_dir 不存在"):
        TdxChronos(data_dir=tmp_path / "nonexistent", readonly=False)


def test_init_with_incomplete_data_dir_raises(tmp_path):
    """只建部分子目录 → 应报 5 子路径缺失"""
    (tmp_path / "parquet_compact").mkdir()  # 只 1 个
    from tdx_chronos.client import TdxChronos
    with pytest.raises(FileNotFoundError, match="缺失"):
        TdxChronos(data_dir=tmp_path, readonly=False)
```

**Step 2: Run — confirm fail**
Expected: `test_init_with_valid_data_dir` FAIL — 5 子路径校验未实现

**Step 3: Implement `__init__` full validation**
```python
"""Sprint 10 · Query Facade (TdxChronos)
..."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd


class TdxChronos:
    """..."""

    # 5 大数据子路径
    SUBDIRS_REQUIRED = [
        "parquet_compact",
        "fin/parsed",
        "gp",          # 目录含 records.parquet
        "index",       # 目录含 indices.parquet
        "meta",        # 目录含 meta.db
    ]
    FILES_REQUIRED = [
        "gp/records.parquet",
        "index/indices.parquet",
        "meta/meta.db",
    ]

    def __init__(self, data_dir: Path | str, *, readonly: bool = True) -> None:
        self.data_dir = Path(data_dir).resolve()

        if not self.data_dir.is_dir():
            raise FileNotFoundError(f"data_dir 不存在: {self.data_dir}")

        # 必传校验: 5 子路径 + 3 file
        missing = []
        for sub in self.SUBDIRS_REQUIRED:
            if not (self.data_dir / sub).is_dir():
                missing.append(str(self.data_dir / sub))
        for f in self.FILES_REQUIRED:
            if not (self.data_dir / f).is_file():
                missing.append(str(self.data_dir / f))
        if missing:
            raise FileNotFoundError(
                f"data_dir 不完整 ({len(missing)}/8 缺失):\n  "
                + "\n  ".join(missing)
            )

        # 5 个 attribute
        self.parquet_compact = self.data_dir / "parquet_compact"
        self.fin_parsed = self.data_dir / "fin" / "parsed"
        self.gp_records = self.data_dir / "gp" / "records.parquet"
        self.index_klines = self.data_dir / "index" / "indices.parquet"
        self.meta_db_path = self.data_dir / "meta" / "meta.db"

        self.readonly = readonly
        self._db: Optional[Any] = None  # lazy MetaDB

        if readonly:
            self._lock_for_readonly()

    def _lock_for_readonly(self):
        """chmod 0444 on files · 防御 cron 写入被 facade 误改"""
        for p in [self.gp_records, self.index_klines, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR)
                except PermissionError:
                    pass  # already locked by cron, ignore

    def close(self):
        """Unlock · 让 cron 可写"""
        if not self.readonly:
            return
        for p in [self.gp_records, self.index_klines, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                except (PermissionError, FileNotFoundError):
                    pass
        if self._db is not None:
            self._db.close()
            self._db = None
```

**Step 4: Run — confirm pass**
```bash
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit/test_client.py -v
```
Expected: 3 PASS

**Step 5: Commit**
```bash
git add src/tdx_chronos/client.py tests/unit/test_client.py
git commit -m "Sprint 10 T2 · __init__ 校验 5 子路径 + readonly mode"
```

---

## Task 3: `symbol_info` + `list_symbols` (MetaDB 集成)

**Files:**
- Modify: `src/tdx_chronos/client.py`
- Modify: `tests/unit/test_client.py`

**Step 1: Write failing tests**
```python
def test_symbol_info_returns_dict(fake_data_dir):
    """先 init 一个临时 meta.db + 一行 symbol_metadata"""
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(fake_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip", "/tmp/a.parquet")
    db.close()
    
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    info = tdx.symbol_info("sh600000")
    assert info["symbol"] == "sh600000"
    assert info["market"] == "sh"


def test_symbol_info_unknown_returns_empty(fake_data_dir):
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    assert tdx.symbol_info("sh999999") == {}


def test_list_symbols_all(fake_data_dir):
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(fake_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 1, "x", "y")
    db.record_symbol("sz000001", "sz", 19910403, 1, "x", "y")
    db.record_symbol("bj838000", "bj", 20200101, 1, "x", "y")
    db.close()
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    syms = tdx.list_symbols()
    assert set(syms) == {"sh600000", "sz000001", "bj838000"}


def test_list_symbols_by_market(fake_data_dir):
    """同上 setup, 取仅 sh"""
    # ... 同样 setup
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    sh = tdx.list_symbols(market="sh")
    assert sh == ["sh600000"]
```

**Step 2: Run — confirm fail**
Expected: `symbol_info` + `list_symbols` not implemented

**Step 3: Implement**
```python
def _ensure_db(self):
    """Lazy init MetaDB connection"""
    if self._db is None:
        from tdx_chronos.meta.db import MetaDB
        self._db = MetaDB(self.meta_db_path)
    return self._db

def symbol_info(self, symbol: str) -> Dict[str, Any]:
    """symbol metadata · 12,256 行中一行
    
    Args:
        symbol: 'sh600000' / 'sz000001' / 'bj838000'
    
    Returns:
        dict · 含 symbol/market/first_listing_date/record_count/source_zip
        找不到返回 {} (不 raise)
    """
    db = self._ensure_db()
    conn = db._connect()
    row = conn.execute(
        "SELECT * FROM symbol_metadata WHERE symbol = ?",
        (symbol.lower(),),
    ).fetchone()
    return dict(row) if row else {}

def list_symbols(self, market: Optional[str] = None) -> List[str]:
    """list 全部 symbols (or 仅 sh/sz/bj)
    
    Args:
        market: None=all · 'sh'='sz'='bj'
    """
    db = self._ensure_db()
    conn = db._connect()
    if market:
        rows = conn.execute(
            "SELECT symbol FROM symbol_metadata WHERE market = ? ORDER BY symbol",
            (market.lower(),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT symbol FROM symbol_metadata ORDER BY symbol"
        ).fetchall()
    return [r["symbol"] for r in rows]
```

**Step 4: Run — confirm pass**
Expected: 4 PASS (2 symbol_info + 2 list)

**Step 5: Commit**
```bash
git add src/tdx_chronos/client.py tests/unit/test_client.py
git commit -m "Sprint 10 T3 · symbol_info + list_symbols (MetaDB 集成)"
```

---

## Task 4: `kline` (pyarrow predicate pushdown)

**Files:**
- Modify: `src/tdx_chronos/client.py`
- Modify: `tests/unit/test_client.py`

**Step 1: Write failing tests (用 fake parquet)**
```python
def test_kline_single_symbol(fake_data_dir):
    """建 1 行 sh.parquet 含 sh600000 几行 → 读必须返回"""
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.table({
        "symbol": ["sh600000", "sh600000", "sh600000"],
        "date": [20240102, 20240103, 20240104],
        "open": [10.0, 10.5, 11.0],
        "high": [10.5, 11.0, 11.5],
        "low": [9.8, 10.3, 10.8],
        "close": [10.3, 10.8, 11.2],
        "volume": [1000, 2000, 3000],
        "amount": [10250.0, 21600.0, 33780.0],
    })
    pq.write_table(table, str(fake_data_dir / "parquet_compact" / "sh.parquet"))
    
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.kline("sh600000")
    assert len(df) == 3
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume", "amount"]


def test_kline_with_date_range(fake_data_dir):
    """start='2024-01-02' end='2024-01-03'"""
    # ... 同 setup,但加更多 date
    table = pa.table({
        "symbol": ["sh600000"] * 5,
        "date": [20240101, 20240102, 20240103, 20240104, 20240105],
        "open": [...], "high": [...], "low": [...], "close": [...],
        "volume": [...], "amount": [...],
    })
    pq.write_table(table, str(fake_data_dir / "parquet_compact" / "sh.parquet"))
    
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.kline("sh600000", start="2024-01-02", end="2024-01-03")
    assert len(df) == 2


def test_kline_unknown_symbol_returns_empty(fake_data_dir):
    """sh999999 不存在 → 不 raise, 返回空 DataFrame"""
    # ... 同样 setup
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.kline("sh999999")
    assert df.empty
```

**Step 2: Run — confirm fail**
Expected: `kline` not defined

**Step 3: Implement `kline`**
```python
def kline(
    self,
    symbol: str,
    start: Optional[str] = None,  # 'YYYY-MM-DD' or 'YYYYMMDD'
    end: Optional[str] = None,
    columns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """K 线 · 单 symbol · pandas DataFrame (sorted by date ASC)
    
    Args:
        symbol: 'sh600000' / 'sz000001' / 'bj838000'
        start:  起始日期 (inclusive)
        end:    截止日期 (inclusive)
        columns:  子集 columns · None=全部
    
    Returns:
        DataFrame [date, open, high, low, close, volume, amount]
        找不到返回 empty DataFrame (不 raise)
    """
    import pyarrow.parquet as pq

    norm = _normalize_symbol(symbol)
    market = norm[:2]  # 'sh' / 'sz' / 'bj'
    market_file = self.parquet_compact / f"{market}.parquet"

    if not market_file.exists():
        return pd.DataFrame()  # market file 不存在(此次测试 / 部分市场) → 空

    filters = [("symbol", "=", norm)]
    if start:
        filters.append(("date", ">=", _to_yyyymmdd_int(start)))
    if end:
        filters.append(("date", "<=", _to_yyyymmdd_int(end)))

    try:
        table = pq.read_table(market_file, filters=filters, columns=columns)
    except Exception:
        return pd.DataFrame()

    df = table.to_pandas()
    return df.sort_values("date").reset_index(drop=True) if not df.empty else df


def _normalize_symbol(symbol: str) -> str:
    s = symbol.lower().strip()
    if s.startswith(("sh", "sz", "bj")):
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("5", "6", "9")):
            return "sh" + s
        if s.startswith(("0", "2", "3")):
            return "sz" + s
        if s.startswith(("4", "8")):
            return "bj" + s
    return s


def _to_yyyymmdd_int(s: str) -> int:
    """'2024-01-02' → 20240102"""
    s = s.replace("-", "").replace("/", "")
    return int(s)
```

**Step 4: Run — confirm pass**
Expected: 3 PASS

**Step 5: Commit**
```bash
git add src/tdx_chronos/client.py tests/unit/test_client.py
git commit -m "Sprint 10 T4 · kline (pyarrow predicate pushdown)"
```

---

## Task 5: `finance` + `shareholders` + `index_klines` + `list_quarters` + `doctor`

**Files:**
- Modify: `src/tdx_chronos/client.py`
- Modify: `tests/unit/test_client.py`

**Step 1: Write failing tests**
```python
def test_finance_single_quarter(fake_data_dir):
    """建 1 季度 parquet 含 600000 一行"""
    import pyarrow as pa, pyarrow.parquet as pq
    table = pa.table({
        "code": ["sh600000"],
        "report_date": [20251231],
        "资产总计": [1000.0],
        "负债合计": [400.0],
        "所有者权益合计": [600.0],
        "净利润": [50.0],
        # ... 用最少 column 因为 ratio_only 测试只关心 columns 数
    })
    pq.write_table(table, str(fake_data_dir / "fin" / "parsed" / "gpcw20251231.parquet"))
    
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.finance("sh600000", report_date="2025-12-31")
    assert len(df) == 1
    assert "资产总计" in df.columns


def test_finance_all_quarters(fake_data_dir):
    """report_date=None → 最新季度 (or 最近 1)"""
    # ... 建 2 季度 parquet
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.finance("sh600000")  # 默认行为: 全部 available quarters
    assert isinstance(df, pd.DataFrame)


def test_shareholders_single_symbol(fake_data_dir):
    import pyarrow as pa, pyarrow.parquet as pq
    table = pa.table({"symbol": ["sh600000"], "name": ["ABC"], "share": [1000.0]})
    pq.write_table(table, str(fake_data_dir / "gp" / "records.parquet"))
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.shareholders("sh600000")
    assert len(df) == 1


def test_index_klines_sh000001(fake_data_dir):
    import pyarrow as pa, pyarrow.parquet as pq
    table = pa.table({
        "index_code": ["sh000001"] * 3,
        "date": [20240101, 20240102, 20240103],
        "open": [3000.0, 3010.0, 3020.0],
        "high": [3010.0, 3020.0, 3030.0],
        "low": [2990.0, 3000.0, 3010.0],
        "close": [3005.0, 3015.0, 3025.0],
        "volume": [100, 200, 300],
    })
    pq.write_table(table, str(fake_data_dir / "index" / "indices.parquet"))
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    df = tdx.index_klines("sh000001")
    assert len(df) == 3


def test_list_quarters(fake_data_dir):
    """fin/parsed 下 2 个 parquet → 2 个 quarter string"""
    import pyarrow as pa, pyarrow.parquet as pq
    table = pa.table({"code": [], "report_date": []})  # empty
    pq.write_table(table, str(fake_data_dir / "fin" / "parsed" / "gpcw20251231.parquet"))
    pq.write_table(table, str(fake_data_dir / "fin" / "parsed" / "gpcw20250930.parquet"))
    from tdx_chronos.client import TdxChronos
    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    quarters = tdx.list_quarters()
    assert "2025-12-31" in quarters
    assert "2025-09-30" in quarters
```

**Step 2: Run — confirm fail**

**Step 3: Implement remaining methods**
```python
def finance(
    self,
    symbol: str,
    report_date: Optional[str] = None,  # 'YYYY-MM-DD' or 'YYYYMMDD' or None
    ratio_only: bool = False,
) -> pd.DataFrame:
    """单 symbol 财务 · 多 quarter 默认
    
    Args:
        symbol: 'sh600000' 或 '600000'
        report_date: 单 quarter · None=全部 available
        ratio_only: True=仅 ratio 类型 columns (Sprint 8 T2 logic 简化版)
    
    Returns:
        DataFrame 每行 = 1 个 (symbol, quarter) · 含 581 or ratio columns
        找不到返回 empty DataFrame
    """
    import pyarrow.parquet as pq
    norm = _normalize_symbol(symbol)
    bare = norm[2:] if norm.startswith(("sh", "sz", "bj")) else norm

    files = sorted(self.fin_parsed.glob("gpcw*.parquet"))
    if not files:
        return pd.DataFrame()

    # filter by report_date if specified
    if report_date:
        target_yyyymmdd = _to_yyyymmdd_int(report_date)
        files = [f for f in files if f.stem.replace("gpcw", "") == str(target_yyyymmdd)]
        if not files:
            return pd.DataFrame()

    rows = []
    for f in files:
        df = pq.read_table(f).to_pandas()
        match = df[df["code"] == bare]
        if not match.empty:
            rd = int(f.stem.replace("gpcw", ""))
            match = match.assign(report_date=rd)
            if ratio_only:
                # 简化: 保留 ratio 列(field_types F_ALL_RATIO 标志为 'rate' 类型)
                # v1.4: 仅过滤 column 名含 '_ratio' 或 'ratio_' 或 '率'
                ratio_cols = [c for c in match.columns 
                              if "ratio" in c.lower() or "率" in c]
                match = match[["code", "report_date"] + ratio_cols]
            rows.append(match)
    return pd.concat(rows).reset_index(drop=True) if rows else pd.DataFrame()


def shareholders(self, symbol: str) -> pd.DataFrame:
    """股本 1 行 (per symbol in real data, but 数据可能是 row per snapshot)
    
    Args:
        symbol: 'sh600000'
    """
    import pyarrow.parquet as pq
    norm = _normalize_symbol(symbol)
    table = pq.read_table(self.gp_records, filters=[("symbol", "=", norm)])
    return table.to_pandas()


def index_klines(
    self,
    index_code: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """5 指数 日线 · pandas DataFrame"""
    import pyarrow.parquet as pq
    code = index_code.lower()
    filters = [("index_code", "=", code)]
    if start:
        filters.append(("date", ">=", _to_yyyymmdd_int(start)))
    if end:
        filters.append(("date", "<=", _to_yyyymmdd_int(end)))
    table = pq.read_table(self.index_klines, filters=filters)
    df = table.to_pandas()
    return df.sort_values("date").reset_index(drop=True) if not df.empty else df


def list_quarters(self) -> List[str]:
    """list 已 parsed 季度 · ['2025-12-31', '2025-09-30', ...]"""
    files = sorted(self.fin_parsed.glob("gpcw*.parquet"))
    return [_int_to_yyyymmdd_dash(int(f.stem.replace("gpcw", ""))) for f in files]


def doctor(self):
    """复用现有 Doctor().run()"""
    from tdx_chronos.doctor import Doctor
    return Doctor(meta_db_path=self.meta_db_path, parquet_root=self.data_dir).run()


def _int_to_yyyymmdd_dash(n: int) -> str:
    s = str(n)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
```

**Step 4: Run all tests — confirm pass**
```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit/test_client.py -v
```
Expected: **20/20 PASSED** (1 + 3 + 4 + 3 + 9 新加)

**Step 5: Commit**
```bash
git add src/tdx_chronos/client.py tests/unit/test_client.py
git commit -m "Sprint 10 T5 · finance / shareholders / index_klines / list_quarters / doctor (完整 facade)"
```

---

## Task 6: 集成测试 (真数据!)

**Files:**
- Create: `tests/integration/test_client_integration.py`

**Step 1: Write integration test**
```python
"""Sprint 10 · Integration · 用真 /app/tdx-chronos/data"""

import pytest
from pathlib import Path

DATA_DIR = Path("/app/tdx-chronos/data")


@pytest.mark.skipif(not DATA_DIR.exists(), reason="prod data not available")
class TestRealIntegration:
    def test_init_real(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            assert tdx.data_dir == DATA_DIR
        finally:
            tdx.close()

    def test_kline_sh600000(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            df = tdx.kline("sh600000")
            assert len(df) >= 5000
            assert "close" in df.columns
        finally:
            tdx.close()

    def test_finance_000858(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            df = tdx.finance("000858")  # 贵州茅台
            assert len(df) > 0
        finally:
            tdx.close()

    def test_list_symbols_count(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            syms = tdx.list_symbols()
            assert len(syms) == 12256
        finally:
            tdx.close()

    def test_list_quarters_count(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            quarters = tdx.list_quarters()
            # 实测 today: 121 parsed (也有可能 258 if 全跑过)
            assert len(quarters) >= 120
        finally:
            tdx.close()

    def test_doctor_returns_degraded(self):
        from tdx_chronos.client import TdxChronos
        tdx = TdxChronos(data_dir=DATA_DIR)
        try:
            report = tdx.doctor()
            # 9/10 DEGRADED (主人接受现状)
            assert report.failed_count == 1
            assert report.level == "degraded"
        finally:
            tdx.close()
```

**Step 2: Run — confirm pass**

**Step 3: N/A (no impl needed)**

**Step 4: Run — confirm pass**
```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/integration/test_client_integration.py -v -m ""  # 取消 skip
```
Expected: **6/6 PASSED** against real data

**Step 5: Commit**
```bash
git add tests/integration/test_client_integration.py
git commit -m "Sprint 10 T6 · integration test 真数据 6 cases"
```

---

## Task 7: README + 完成

**Files:**
- Create: `src/tdx_chronos/CLIENT_README.md`

**Step 1: Write README**
```markdown
# TdxChronos Client · Query Facade Usage

5 类离线数据一个 class 拿完。

## 安装
\`\`\`bash
cd /app/tdx-chronos
pip install -e .  # 或 PYTHONPATH=src:vendor/_vendor 直接 import
\`\`\`

## 用法
\`\`\`python
from tdx_chronos.client import TdxChronos
from pathlib import Path

tdx = TdxChronos(data_dir=Path("/app/tdx-chronos/data"))

# 1. K线
df = tdx.kline("sh600000", start="2024-01-01", end="2024-12-31")

# 2. 财务 581 字段 (or ratio_only=True 仅 ratio 列)
df = tdx.finance("000858", report_date="2025-12-31")

# 3. 股本
df = tdx.shareholders("600000")

# 4. 5 指数
df = tdx.index_klines("sh000300")

# 5. 元数据
info = tdx.symbol_info("sh600000")

# 6. 健康检查
report = tdx.doctor()

# 7. list
syms = tdx.list_symbols(market="sh")  # ['sh600000', 'sh600001', ...]
quarters = tdx.list_quarters()          # ['2025-12-31', '2025-09-30', ...]

tdx.close()
\`\`\`
```

**Step 2-5: commit 完整**
```bash
git add src/tdx_chronos/CLIENT_README.md
git commit -m "Sprint 10 · finalize · client.py + 26 tests + README"
git tag v1.4.0
git push origin main --tags
```

---

## 🎯 Sprint 10 全景 · 周期 ~3 d

| Task | 内容 | 估算 |
|---|---|---|
| T1 | scaffold + import test | 0.5 h |
| T2 | __init__ 校验 | 1 h |
| T3 | symbol_info + list_symbols | 1.5 h |
| T4 | kline (pyarrow predicate) | 2 h |
| T5 | finance / shareholders / index_klines / list_quarters / doctor | 3 h |
| T6 | integration 真数据 | 1 h |
| T7 | README + tag v1.4.0 | 0.5 h |
| **总** | | **~9 h ≈ 2 d** |

---

## YAGNI / DRY / TDD 三原则执行点

| 原则 | 体现 |
|---|---|
| YAGNI | 不写 cache / async / write API (主人明确不在 v1.4) |
| DRY | `_normalize_symbol` + `_to_yyyymmdd_int` 复用 5 处 |
| TDD | 25 cases (test) → 7 task → 每个先 test 后 impl, 每 task commit |
| Frequent commits | T1-T5 5 个中间 commit, 不一次性 push |

---

## Sprint 11+ 候选 (Phase 5+)

- ⏸️ 把 `TdxChronos` 暴露到 PyPI
- ⏸️ HTTP / REST wrapper (FastAPI)
- ⏸️ 异步 API (asyncio)
- ⏸️ LRU cache / Redis cache
- ⏸️ `tdx write_*` 写入 API (cron 也能调,而不只是 cron shell)
- ⏸️ Reconciliation 集成: `tdx.reconcile("sh600000")` 一行跑 BS/CF/IS
- ⏸️ 修 reconciliation 1/3 fail (688779 边界)

---

**Author**: claw-cortex 🦞
**Phase**: 2 (writing-plans) 完整, 待主人选 Subagent-driven vs Manual
