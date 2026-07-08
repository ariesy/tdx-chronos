# Sprint 12 Implementation Plan · Client Bugfix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Design**: [2026-07-08-sprint12-client-bugfix-design.md](2026-07-08-sprint12-client-bugfix-design.md)
**Goal**: 修复 Sprint 10 集成测试暴露的 9 个 client 层 bug，发布 v1.4.1
**Architecture**: TDD-先 RED；5 个 task 串行，每 task 一独立 commit；client.py / meta/db.py / 文档同步改动
**Tech Stack**: Python 3.12 · pytest 7+ · pyarrow · sqlite3 (WAL)
**执行模式**: Subagent-Driven (5 任务串行)

---

## Global Constraints

- Python 3.12+ (`requires-python = ">=3.12"` in pyproject.toml)
- 不可改 `vendor/mootdx/` (硬规则)
- 不可 commit `data/` (除 `data/research/`)
- 不可 import `mootdx.financial` (0 字节空文件 bug)
- 不可删除/跳过测试保 CI 绿 (CHANGELOG 测试数基线 297)
- venv: `.venv/bin/python` · PYTHONPATH: `src:vendor/_vendor` (ad-hoc python 必加)
- Shanghai TZ: `TZ=Asia/Shanghai` (cron/日志)
- 数据根: `/app/tdx-chronos/data` (集成测试用)
- 中文注释匹配项目风格
- TDD-先 RED: 写测试 → 跑测试看到 FAIL → 写最小实现 → 跑测试看到 PASS → commit
- NO amend · NEW commit on current HEAD

---

## Task 1: T1 · `_normalize_symbol` 92→bj 北交所新股归类修复 (P0 · 修复 #1)

**Files**:
- Modify: `src/tdx_chronos/client.py:329-335` (`_normalize_symbol` 函数)
- Test: `tests/unit/test_client.py` (追加 4 测试)

**Interfaces**:
- Consumes: 无 (纯函数, 无外部依赖)
- Produces: `_normalize_symbol(symbol: str) -> str` 返回 `'sh'` / `'sz'` / `'bj'` 前缀化代码

**目标**: 让 `920001`/`830017` 等北交所新股归 `bj`，保持 `900901` 等 sh B 股不变。

### 步骤

- [ ] **Step 1: 追加 4 个失败测试到 `tests/unit/test_client.py`**

在文件末尾追加:

```python
# ─── Sprint 12 T1 · _normalize_symbol 92→bj ────────────────────────


def test_normalize_92xx_to_bj_market():
    """92 开头两位 → bj (北交所新股, 实际数据验证 bj920001~bj920005 存在)"""
    from tdx_chronos.client import _normalize_symbol
    assert _normalize_symbol("920001") == "bj920001"
    assert _normalize_symbol("920123") == "bj920123"


def test_normalize_9_b_share_unchanged():
    """9 开头 (非 92) → sh (B 股回归测试, 不能被 T1 改坏)"""
    from tdx_chronos.client import _normalize_symbol
    assert _normalize_symbol("900901") == "sh900901"
    assert _normalize_symbol("900902") == "sh900902"


def test_normalize_other_prefixes_unchanged():
    """5/6/0/2/3/4/8 前缀回归"""
    from tdx_chronos.client import _normalize_symbol
    assert _normalize_symbol("600000") == "sh600000"  # 6 → sh
    assert _normalize_symbol("500001") == "sh500001"  # 5 → sh
    assert _normalize_symbol("000001") == "sz000001"  # 0 → sz
    assert _normalize_symbol("300750") == "sz300750"  # 3 → sz (创业板)
    assert _normalize_symbol("430017") == "bj430017"  # 4 → bj
    assert _normalize_symbol("830017") == "bj830017"  # 8 → bj


def test_normalize_already_prefixed_passthrough():
    """已带前缀的 passthrough (大小写不敏感)"""
    from tdx_chronos.client import _normalize_symbol
    assert _normalize_symbol("bj920001") == "bj920001"
    assert _normalize_symbol("BJ920001") == "bj920001"
    assert _normalize_symbol("Sh600000") == "sh600000"
```

- [ ] **Step 2: 跑测试确认 RED**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -k "normalize_92 or normalize_9_b or normalize_other or normalize_already" -v
```

Expected:
```
test_normalize_92xx_to_bj_market FAILED
test_normalize_9_b_share_unchanged PASSED  (回归, 不动)
test_normalize_other_prefixes_unchanged PASSED  (回归, 不动)
test_normalize_already_prefixed_passthrough PASSED  (回归, 不动)
```

`test_normalize_92xx_to_bj_market` 必须 FAIL（输出 `sh920001`，断言 `bj920001`）。

- [ ] **Step 3: 修改 `src/tdx_chronos/client.py:329-335`**

把:
```python
    if len(s) == 6 and s.isdigit():
        if s.startswith(("5", "6", "9")):
            return "sh" + s
        if s.startswith(("0", "2", "3")):
            return "sz" + s
        if s.startswith(("4", "8")):
            return "bj" + s
```

改成:
```python
    if len(s) == 6 and s.isdigit():
        if s.startswith("92"):                  # Sprint 12 T1 · 北交所新股优先
            return "bj" + s
        if s.startswith(("5", "6", "9")):
            return "sh" + s
        if s.startswith(("0", "2", "3")):
            return "sz" + s
        if s.startswith(("4", "8")):
            return "bj" + s
```

- [ ] **Step 4: 跑测试确认 GREEN**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -k "normalize" -v
```

Expected: 4/4 PASS。

- [ ] **Step 5: 跑 test_client.py 全量, 确认无回归**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -v --tb=short
```

Expected: 旧 27 测试 + 新 4 测试 = 31 PASS, 0 FAIL。

- [ ] **Step 6: 复现反向验证**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
from tdx_chronos.client import _normalize_symbol
assert _normalize_symbol('920001') == 'bj920001', '92 should be bj'
assert _normalize_symbol('900901') == 'sh900901', '9 single should be sh (B-share)'
print('PASS · normalize ok')
"
```

Expected: `PASS · normalize ok`

- [ ] **Step 7: Commit**

```bash
cd /app/tdx-chronos
git add tests/unit/test_client.py src/tdx_chronos/client.py
git commit -m "T1 · _normalize_symbol 92→bj 北交所新股归类修复 (Sprint 12 v1.4.1)"
```

---

## Task 2: T2 · `list_quarters()` DESC 排序 + 过滤 gpcw0.parquet (P0 · 修复 #2 #3)

**Files**:
- Modify: `src/tdx_chronos/client.py:297-307` (`list_quarters` 方法)
- Test: `tests/unit/test_client.py` (追加 3 测试)
- Delete: `data/fin/parsed/gpcw0.parquet` (0 行脏数据, gitignored)

**Interfaces**:
- Consumes: `self.fin_parsed` (Path) 目录
- Produces: `list_quarters() -> List[str]` 返回 `['2026-03-31', '2025-12-31', ...]` DESC 排序, 8 位日期 stem 严格匹配

**目标**: 排序方向与 docstring 一致 (DESC); 严格 8 位日期过滤掉 `gpcw0.parquet` 0 行脏文件。

### 步骤

- [ ] **Step 1: 物理删除 `gpcw0.parquet` 脏文件**

```bash
cd /app/tdx-chronos
ls -la data/fin/parsed/gpcw0.parquet
rm data/fin/parsed/gpcw0.parquet
ls data/fin/parsed/gpcw0.parquet 2>&1  # 应报 No such file
```

注: 此文件在 `.gitignore` 内 (`data/`), 删除不影响 git 追踪。验证: `git status` 不应有新 untracked。

- [ ] **Step 2: 追加 3 个失败测试到 `tests/unit/test_client.py`**

在 T1 测试块之后追加:

```python
# ─── Sprint 12 T2 · list_quarters DESC + 过滤 gpcw0 ───────────────


def test_list_quarters_returns_desc_order(populated_data_dir, monkeypatch):
    """list_quarters 必须按日期 DESC 返回 (newest first)"""
    from tdx_chronos.client import TdxChronos

    # 在 fake fin_parsed 建 3 个有顺序的 gpcw 文件 (顺序打乱)
    import pyarrow as pa
    import pyarrow.parquet as pq
    fin_dir = populated_data_dir / "fin" / "parsed"
    for stem in ("gpcw20201231.parquet", "gpcw20251231.parquet", "gpcw20240630.parquet"):
        pq.write_table(pa.table({"code": [], "x": []}), fin_dir / stem)

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        quarters = tdx.list_quarters()
        assert quarters == ["2025-12-31", "2024-06-30", "2020-12-31"], \
            f"want DESC, got {quarters}"
    finally:
        tdx.close()


def test_list_quarters_skips_invalid_stem(populated_data_dir):
    """gpcw0.parquet / gpcw999.parquet 等非 8 位日期 stem 必须跳过"""
    from tdx_chronos.client import TdxChronos
    import pyarrow as pa
    import pyarrow.parquet as pq

    fin_dir = populated_data_dir / "fin" / "parsed"
    # 1 个有效
    pq.write_table(pa.table({"code": [], "x": []}), fin_dir / "gpcw20251231.parquet")
    # 2 个无效 (gpcw0 + gpcw999)
    pq.write_table(pa.table({"code": [], "x": []}), fin_dir / "gpcw0.parquet")
    pq.write_table(pa.table({"code": [], "x": []}), fin_dir / "gpcw999.parquet")

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        quarters = tdx.list_quarters()
        assert quarters == ["2025-12-31"], f"want only valid, got {quarters}"
    finally:
        tdx.close()


def test_list_quarters_strict_8_digit_date(populated_data_dir):
    """stem 必须严格 8 位数字 (gpcw2025123.parquet 7 位应跳过)"""
    from tdx_chronos.client import TdxChronos
    import pyarrow as pa
    import pyarrow.parquet as pq

    fin_dir = populated_data_dir / "fin" / "parsed"
    pq.write_table(pa.table({"code": [], "x": []}), fin_dir / "gpcw20251231.parquet")
    pq.write_table(pa.table({"code": [], "x": []}), fin_dir / "gpcw2025123.parquet")  # 7 位

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        quarters = tdx.list_quarters()
        assert quarters == ["2025-12-31"], f"want strict 8-digit filter, got {quarters}"
    finally:
        tdx.close()
```

- [ ] **Step 3: 跑测试确认 RED**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -k "list_quarters_returns_desc or list_quarters_skips_invalid or list_quarters_strict" -v
```

Expected: 3/3 FAIL（`test_list_quarters_returns_desc_order` 因 ASC 顺序失败; 另 2 个因 `gpcw0` 被 glob 命中失败）。

- [ ] **Step 4: 修改 `src/tdx_chronos/client.py:1-15` (imports) 和 L297-307 (函数)**

在 `client.py` 顶部 imports 区 (约 L7-15) 加 `re`:
```python
from __future__ import annotations

import logging
import os
import re                      # ← Sprint 12 T2 新增
import stat
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
```

把 L297-307:
```python
    def list_quarters(self) -> List[str]:
        """list 已 parsed 季度 · 'YYYY-MM-DD' strings

        Returns:
            List[str] · sorted by date DESC (newest first: '2025-12-31', '2025-09-30', ...)
            Empty list if no fin/parsed/gpcw*.parquet files
        """
        files = sorted(self.fin_parsed.glob("gpcw*.parquet"))
        return [
            _int_to_yyyymmdd_dash(int(f.stem.replace("gpcw", ""))) for f in files
        ]
```

改成:
```python
    def list_quarters(self) -> List[str]:
        """list 已 parsed 季度 · 'YYYY-MM-DD' strings

        Returns:
            List[str] · sorted by date DESC (newest first: '2026-03-31', '2025-12-31', ...)
            Files not matching 8-digit date stem are skipped (defensive)
        """
        _QUARTER_STEM_RE = re.compile(r"^gpcw(\d{8})\.parquet$")
        dates: list[int] = []
        for f in self.fin_parsed.glob("gpcw*.parquet"):
            m = _QUARTER_STEM_RE.match(f.name)
            if m is None:
                continue
            dates.append(int(m.group(1)))
        dates.sort(reverse=True)
        return [_int_to_yyyymmdd_dash(d) for d in dates]
```

注: `_QUARTER_STEM_RE` 提到模块级 (与 `_normalize_symbol` 同位置) 避免每次调用编译。本次为最小改动放在方法内, 后续可优化。

- [ ] **Step 5: 跑测试确认 GREEN**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -k "list_quarters" -v
```

Expected: 旧 2 测试 (`test_list_quarters`, `test_list_quarters_empty_returns_empty_list`) + 新 3 测试 = 5 PASS。

- [ ] **Step 6: 跑 test_client.py 全量, 确认无回归**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -v --tb=short
```

Expected: 31 (T1 后) + 3 (T2) = 34 PASS, 0 FAIL。

- [ ] **Step 7: 复现反向验证 (真 data)**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
from pathlib import Path
from tdx_chronos.client import TdxChronos
t = TdxChronos(Path('data'))
qs = t.list_quarters()
assert qs == sorted(qs, reverse=True), f'want DESC, got first 3: {qs[:3]}'
assert '0--' not in qs, 'gpcw0 should be filtered'
t.close()
print(f'PASS · list_quarters DESC · {len(qs)} quarters')
"
```

Expected: `PASS · list_quarters DESC · 120 quarters` (gpcw0 已删, 121 - 1 = 120)。

- [ ] **Step 8: Commit**

```bash
cd /app/tdx-chronos
git add tests/unit/test_client.py src/tdx_chronos/client.py
git commit -m "T2 · list_quarters DESC + 过滤 gpcw0.parquet 脏数据 (Sprint 12 v1.4.1)"
```

---

## Task 3: T3 · `TdxChronos.close()` readonly=False 路径 db 泄漏修复 (P0 · 修复 #4)

**Files**:
- Modify: `src/tdx_chronos/client.py:73-89` (`close` 方法)
- Test: `tests/unit/test_client.py` (追加 2 测试)

**Interfaces**:
- Consumes: `self._db` (Optional MetaDB)
- Produces: `close()` 无返回值; 不变量: db 连接无论 readonly 与否一定释放

**目标**: 移除 `if not self.readonly: return` 早 return 让 db 释放与 chmod 恢复解耦。

### 步骤

- [ ] **Step 1: 追加 2 个失败测试到 `tests/unit/test_client.py`**

在 T2 测试块之后追加:

```python
# ─── Sprint 12 T3 · close() 资源释放 ──────────────────────────────


def test_close_releases_db_when_readonly_false(populated_data_dir):
    """readonly=False 路径 close() 必须释放 db 连接 (P0 修复)"""
    from tdx_chronos.client import TdxChronos

    # Pre-populate so lazy db opens
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)

    # Force lazy db open via symbol_info
    info = tdx.symbol_info("sh600000")
    assert info["symbol"] == "sh600000"
    assert tdx._db is not None  # db 已开

    # Close (no chmod attempted in readonly=False path)
    tdx.close()

    # Critical: db must be released
    assert tdx._db is None, "readonly=False path leaked db connection"


def test_close_releases_db_when_readonly_true(populated_data_dir):
    """readonly=True 路径 close() 仍释放 db (回归)"""
    from tdx_chronos.client import TdxChronos

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=True)
    info = tdx.symbol_info("sh600000")
    assert tdx._db is not None

    tdx.close()
    assert tdx._db is None, "readonly=True path leaked db connection"
```

- [ ] **Step 2: 跑测试确认 RED**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -k "close_releases_db_when_readonly" -v
```

Expected: `test_close_releases_db_when_readonly_false` FAILED (`_db is not None`); `test_close_releases_db_when_readonly_true` PASSED (回归, 已有保护)。

- [ ] **Step 3: 修改 `src/tdx_chronos/client.py:73-89`**

把:
```python
    def close(self):
        if not self.readonly:
            return
        # 1. Release db connection FIRST (before any chmod that may fail)
        db, self._db = self._db, None
        if db is not None:
            db.close()
        # 2. Then restore chmod (may fail with RuntimeError; that's OK — caller will know)
        for p in [self.gp_records, self._index_klines_path, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                except PermissionError as e:
                    raise RuntimeError(
                        f"close() failed to restore write permission on {p}: {e}. "
                        f"cron may be unable to write until manually chmod'd."
                    ) from e
```

改成:
```python
    def close(self):
        # 1. Always release db connection FIRST (regardless of readonly)
        db, self._db = self._db, None
        if db is not None:
            db.close()
        # 2. Then restore chmod only when readonly=True
        if not self.readonly:
            return
        for p in [self.gp_records, self._index_klines_path, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                except PermissionError as e:
                    raise RuntimeError(
                        f"close() failed to restore write permission on {p}: {e}. "
                        f"cron may be unable to write until manually chmod'd."
                    ) from e
```

- [ ] **Step 4: 跑测试确认 GREEN**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -k "close" -v
```

Expected: 旧 `test_close_releases_db_even_if_chmod_fails` + 新 2 = 3 PASS。

- [ ] **Step 5: 跑 test_client.py 全量, 确认无回归**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -v --tb=short
```

Expected: 34 (T2 后) + 2 (T3) = 36 PASS, 0 FAIL。

- [ ] **Step 6: 复现反向验证**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
from pathlib import Path
from tdx_chronos.client import TdxChronos
t = TdxChronos(Path('data'), readonly=False)
t._ensure_db()
assert t._db is not None, 'db should be opened'
t.close()
assert t._db is None, 'db should be released after close() even with readonly=False'
print('PASS · close() releases db connection')
"
```

Expected: `PASS · close() releases db connection`

- [ ] **Step 7: Commit**

```bash
cd /app/tdx-chronos
git add tests/unit/test_client.py src/tdx_chronos/client.py
git commit -m "T3 · TdxChronos.close() 修复 readonly=False 路径 db 泄漏 (Sprint 12 v1.4.1)"
```

---

## Task 4: T4 · `index_klines` drop symbol 列对齐 `kline` 契约 (P1 · 修复 #5)

**Files**:
- Modify: `src/tdx_chronos/client.py:265-295` (`index_klines` 方法)
- Test: `tests/unit/test_client.py` (追加 2 测试)

**Interfaces**:
- Consumes: `self._index_klines_path` (Path)
- Produces: `index_klines(index_code, start, end) -> pd.DataFrame` 不含 `symbol` 列

**目标**: 与 `kline` 方法契约一致 (drop 重复的 symbol 列, 保留元信息列)。

### 步骤

- [ ] **Step 1: 追加 2 个失败测试到 `tests/unit/test_client.py`**

在 T3 测试块之后追加:

```python
# ─── Sprint 12 T4 · index_klines drop symbol ───────────────────────


def test_index_klines_drops_symbol_column(fake_data_dir):
    """index_klines 返回 df 不应含 symbol 列 (与 kline 一致)"""
    from tdx_chronos.client import TdxChronos
    import pyarrow as pa
    import pyarrow.parquet as pq

    idx_path = fake_data_dir / "index" / "indices.parquet"
    pq.write_table(
        pa.table({
            "date": [20240102, 20240103],
            "open": [10.0, 10.1],
            "high": [10.5, 10.6],
            "low": [9.8, 9.9],
            "close": [10.2, 10.4],
            "amount": [1e8, 1.1e8],
            "vol": [1e7, 1.1e7],
            "reserved": [0, 0],
            "symbol": ["sh000001", "sh000001"],
            "market": ["sh", "sh"],
            "source_zip": ["shzsday.zip", "shzsday.zip"],
            "ingested_at": ["2024-01-02T00:00:00", "2024-01-03T00:00:00"],
            "code": ["000001", "000001"],
            "ds_code": ["sh000001", "sh000001"],
            "name": ["上证指数", "上证指数"],
        }),
        idx_path,
    )

    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    try:
        df = tdx.index_klines("sh000001", start="2024-01-01", end="2024-12-31")
        assert "symbol" not in df.columns, f"symbol should be dropped, got: {list(df.columns)}"
        # 元信息列保留
        assert "market" in df.columns
        assert "code" in df.columns
        assert "ds_code" in df.columns
        assert "name" in df.columns
    finally:
        tdx.close()


def test_index_klines_preserves_metadata_columns(fake_data_dir):
    """index_klines 保留 market/code/ds_code/name 元信息列 (P1 决策)"""
    from tdx_chronos.client import TdxChronos
    import pyarrow as pa
    import pyarrow.parquet as pq

    idx_path = fake_data_dir / "index" / "indices.parquet"
    pq.write_table(
        pa.table({
            "date": [20240102],
            "open": [10.0], "high": [10.5], "low": [9.8], "close": [10.2],
            "amount": [1e8], "vol": [1e7], "reserved": [0],
            "symbol": ["sh000001"], "market": ["sh"],
            "source_zip": ["shzsday.zip"], "ingested_at": ["2024-01-02"],
            "code": ["000001"], "ds_code": ["sh000001"], "name": ["上证指数"],
        }),
        idx_path,
    )

    tdx = TdxChronos(data_dir=fake_data_dir, readonly=False)
    try:
        df = tdx.index_klines("sh000001", start="2024-01-01")
        assert "code" in df.columns
        assert "ds_code" in df.columns
        assert "name" in df.columns
        assert "market" in df.columns
    finally:
        tdx.close()
```

- [ ] **Step 2: 跑测试确认 RED**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -k "index_klines_drops_symbol or index_klines_preserves" -v
```

Expected: `test_index_klines_drops_symbol_column` FAILED (`'symbol' in df.columns`); `test_index_klines_preserves_metadata_columns` PASSED (回归)。

- [ ] **Step 3: 修改 `src/tdx_chronos/client.py:265-295`**

在 `index_klines` 方法末尾 (L294 后, `return df` 前) 插入:

找到这段 (L292-294):
```python
        df = table.to_pandas()
        if not df.empty:
            df = df.sort_values("date").reset_index(drop=True)
        return df
```

改成:
```python
        df = table.to_pandas()
        if not df.empty:
            df = df.sort_values("date").reset_index(drop=True)
            # Sprint 12 T4 · 与 kline() 契约一致 · drop symbol 列
            if "symbol" in df.columns:
                df = df.drop(columns=["symbol"])
        return df
```

- [ ] **Step 4: 跑测试确认 GREEN**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -k "index_klines" -v
```

Expected: 旧 `test_index_klines_sh000001` + `test_index_klines_with_date_range` + `test_index_klines_missing_file_returns_empty` + 新 2 = 5 PASS。

- [ ] **Step 5: 跑 test_client.py 全量, 确认无回归**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -v --tb=short
```

Expected: 36 (T3 后) + 2 (T4) = 38 PASS, 0 FAIL。

- [ ] **Step 6: 复现反向验证 (真 data)**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
from pathlib import Path
from tdx_chronos.client import TdxChronos
t = TdxChronos(Path('data'))
df = t.index_klines('sh000001', start='2024-01-01')
assert 'symbol' not in df.columns, f'symbol should be dropped, got: {list(df.columns)}'
t.close()
print('PASS · index_klines drops symbol column')
"
```

Expected: `PASS · index_klines drops symbol column`

- [ ] **Step 7: Commit**

```bash
cd /app/tdx-chronos
git add tests/unit/test_client.py src/tdx_chronos/client.py
git commit -m "T4 · index_klines drop symbol 列对齐 kline 契约 (Sprint 12 v1.4.1)"
```

---

## Task 5: T5 · v1.4.1 版本对齐 + MetaDB 公开 API + README/CHANGELOG (P1/P2 · 修复 #6 #7 #8 #9)

**Files**:
- Modify: `src/tdx_chronos/meta/db.py:179` (init_schema 后) 追加 `get_symbol` + `list_symbols` 公开方法
- Modify: `src/tdx_chronos/client.py:101-139` (symbol_info / list_symbols) 改用新 public API
- Modify: `pyproject.toml:7` (version)
- Modify: `src/tdx_chronos/__init__.py:3` (`__version__`)
- Modify: `README.md:5` (Tests badge)
- Modify: `CHANGELOG.md:1-15` (新增 v1.4.1 段)
- Test: `tests/unit/test_meta_db.py` (追加 5 测试)
- Test: `tests/unit/test_client.py` (追加 4 测试, 含 2 回归)

**Interfaces** (新增):
- `MetaDB.get_symbol(symbol: str) -> dict | None` — 单 symbol 查 metadata
- `MetaDB.list_symbols(market: str | None = None) -> list[str]` — 列 symbols, 可选市场过滤, sorted ASC

**Interfaces** (替换):
- `TdxChronos.symbol_info(symbol)` 改用 `MetaDB.get_symbol(_normalize_symbol(symbol)) or {}`
- `TdxChronos.list_symbols(market)` 改用 `MetaDB.list_symbols(market)`

**目标**: 客户端层不直接调 `db._connect()`; 版本号 4 处一致; stale SHM 仅记录不修。

### 步骤

#### T5a · MetaDB 公开方法 (5 测试)

- [ ] **Step 1: 追加 5 个失败测试到 `tests/unit/test_meta_db.py`**

注: 该文件已有 fixture `db` (`:memory:` MetaDB 已 init_schema)。直接用 `db` fixture 即可, 不需新建。

在文件末尾追加:

```python
# ─── Sprint 12 T5a · MetaDB public API (get_symbol + list_symbols) ───


def test_get_symbol_found(db):
    """get_symbol 找到时返回 dict"""
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    result = db.get_symbol("sh600000")
    assert result is not None
    assert result["symbol"] == "sh600000"
    assert result["market"] == "sh"
    assert result["first_listing_date"] == 19991110


def test_get_symbol_not_found_returns_none(db):
    """get_symbol 找不到返回 None (与 TdxChronos.symbol_info 的空 dict 区分)"""
    result = db.get_symbol("sh999999")
    assert result is None


def test_list_symbols_all_sorted_asc(db):
    """list_symbols(market=None) 返回所有 symbols, sorted ASC"""
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.record_symbol("sz000001", "sz", 19910403, 8000, "hsjday.zip")
    db.record_symbol("bj430017", "bj", 20200807, 100, "hsjday.zip")
    result = db.list_symbols()
    assert result == ["bj430017", "sh600000", "sz000001"]


def test_list_symbols_filtered_by_market(db):
    """list_symbols(market='sh') 仅返回 sh 市场 symbols"""
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.record_symbol("sh600036", "sh", 20020423, 3000, "hsjday.zip")
    db.record_symbol("sz000001", "sz", 19910403, 8000, "hsjday.zip")
    result = db.list_symbols(market="sh")
    assert result == ["sh600000", "sh600036"]


def test_list_symbols_case_insensitive_market(db):
    """list_symbols(market='SH') 与 'sh' 等价 (大小写不敏感)"""
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    result = db.list_symbols(market="SH")
    assert result == ["sh600000"]
```

- [ ] **Step 2: 跑测试确认 RED**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_meta_db.py -k "meta_db_get_symbol or meta_db_list_symbols" -v
```

Expected: 5/5 FAIL (AttributeError: MetaDB has no attribute 'get_symbol')。

- [ ] **Step 3: 在 `src/tdx_chronos/meta/db.py` 加 2 个 public 方法**

找到 `get_symbols_by_market` 方法 (L230), 在它之前插入:

```python
    def get_symbol(self, symbol: str) -> Optional[dict]:
        """Sprint 12 T5a · public symbol metadata lookup

        Args:
            symbol: 归一化后的 symbol, e.g. 'sh600000'

        Returns:
            dict (含 symbol/market/first_listing_date/record_count/source_zip/...)
            or None if not found
        """
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM symbol_metadata WHERE symbol = ?",
            (symbol.lower(),),
        ).fetchone()
        return dict(row) if row else None

    def list_symbols(self, market: Optional[str] = None) -> List[str]:
        """Sprint 12 T5a · public symbol list (replaces client._connect() bypass)

        Args:
            market: 'sh' / 'sz' / 'bj' filter · None=全部 3 个市场 (case-insensitive)

        Returns:
            List[str] · sorted by symbol ASC
        """
        conn = self._connect()
        if market is not None:
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

- [ ] **Step 4: 跑测试确认 GREEN**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_meta_db.py -k "get_symbol or list_symbols" -v
```

Expected: 5/5 PASS。

#### T5b · client.py 改用 public API (4 测试, 含 2 回归)

- [ ] **Step 5: 追加 4 个测试到 `tests/unit/test_client.py`**

在 T4 测试块之后追加:

```python
# ─── Sprint 12 T5b · client 调 MetaDB public API ─────────────────


def test_client_symbol_info_uses_meta_db_public_api(monkeypatch, populated_data_dir):
    """TdxChronos.symbol_info 必须调 MetaDB.get_symbol, 不调 _connect"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta import db as db_mod

    # Pre-populate
    from tdx_chronos.meta.db import MetaDB
    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.close()

    # Spy on MetaDB.get_symbol
    call_count = {"n": 0}
    original = MetaDB.get_symbol
    def spy(self, symbol):
        call_count["n"] += 1
        return original(self, symbol)
    monkeypatch.setattr(MetaDB, "get_symbol", spy)

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        info = tdx.symbol_info("sh600000")
        assert info["symbol"] == "sh600000"
        assert call_count["n"] >= 1, "MetaDB.get_symbol was not called"
    finally:
        tdx.close()


def test_client_list_symbols_uses_meta_db_public_api(monkeypatch, populated_data_dir):
    """TdxChronos.list_symbols 必须调 MetaDB.list_symbols"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    # Pre-populate
    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.record_symbol("sz000001", "sz", 19910403, 8000, "hsjday.zip")
    db.close()

    # Spy on MetaDB.list_symbols
    call_count = {"n": 0}
    original = MetaDB.list_symbols
    def spy(self, market=None):
        call_count["n"] += 1
        return original(self, market)
    monkeypatch.setattr(MetaDB, "list_symbols", spy)

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        syms = tdx.list_symbols()
        assert "sh600000" in syms
        assert "sz000001" in syms
        assert call_count["n"] >= 1, "MetaDB.list_symbols was not called"

        syms_sh = tdx.list_symbols("sh")
        assert syms_sh == ["sh600000"]
    finally:
        tdx.close()


def test_client_symbol_info_unchanged_behavior(populated_data_dir):
    """symbol_info 行为回归: 找/不找/大小写"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        # 找到
        info = tdx.symbol_info("sh600000")
        assert info["symbol"] == "sh600000"
        # 大小写
        info2 = tdx.symbol_info("SH600000")
        assert info2["symbol"] == "sh600000"
        # 找不到返回 {} (不 raise)
        info3 = tdx.symbol_info("sh999999")
        assert info3 == {}
    finally:
        tdx.close()


def test_client_list_symbols_unchanged_behavior(populated_data_dir):
    """list_symbols 行为回归: 全列/过滤/排序"""
    from tdx_chronos.client import TdxChronos
    from tdx_chronos.meta.db import MetaDB

    db = MetaDB(str(populated_data_dir / "meta" / "meta.db"))
    db.record_symbol("sh600000", "sh", 19991110, 5000, "hsjday.zip")
    db.record_symbol("sz000001", "sz", 19910403, 8000, "hsjday.zip")
    db.close()

    tdx = TdxChronos(data_dir=populated_data_dir, readonly=False)
    try:
        # 全部 sorted ASC
        syms = tdx.list_symbols()
        assert syms == ["sh600000", "sz000001"]
        # 过滤
        sh = tdx.list_symbols("sh")
        assert sh == ["sh600000"]
    finally:
        tdx.close()
```

- [ ] **Step 6: 跑测试确认 RED**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -k "client_symbol_info_uses or client_list_symbols_uses or client_symbol_info_unchanged or client_list_symbols_unchanged" -v
```

Expected: `test_client_symbol_info_uses_meta_db_public_api` FAILED (call_count=0); `test_client_list_symbols_uses_meta_db_public_api` FAILED (call_count=0); 另 2 回归测试 PASSED。

- [ ] **Step 7: 修改 `src/tdx_chronos/client.py:101-139`**

把:
```python
    def symbol_info(self, symbol: str) -> Dict[str, Any]:
        """symbol metadata lookup · returns dict or {} when not found

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
        """list symbols in meta.db

        Args:
            market: 'sh'/'sz'/'bj' filter · None=全部 3 个市场

        Returns:
            List[str] · sorted by symbol ASC
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

改成:
```python
    def symbol_info(self, symbol: str) -> Dict[str, Any]:
        """symbol metadata lookup · returns dict or {} when not found

        Args:
            symbol: 'sh600000' / 'sz000001' / 'bj838000'

        Returns:
            dict · 含 symbol/market/first_listing_date/record_count/source_zip
            找不到返回 {} (不 raise)
        """
        db = self._ensure_db()
        return db.get_symbol(_normalize_symbol(symbol)) or {}

    def list_symbols(self, market: Optional[str] = None) -> List[str]:
        """list symbols in meta.db

        Args:
            market: 'sh'/'sz'/'bj' filter · None=全部 3 个市场

        Returns:
            List[str] · sorted by symbol ASC
        """
        db = self._ensure_db()
        return db.list_symbols(market)
```

- [ ] **Step 8: 跑测试确认 GREEN**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py -k "symbol_info or list_symbols" -v
```

Expected: 旧 4 测试 + 新 4 测试 = 8 PASS。

- [ ] **Step 9: 跑 test_client.py + test_meta_db.py 全量**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_client.py tests/unit/test_meta_db.py -v --tb=short
```

Expected: 38 (T4 后) + 4 (T5b) = 42 PASS, 0 FAIL in test_client.py · test_meta_db 22 + 5 (T5a) = 27 PASS。

#### T5c · 版本号 bump

- [ ] **Step 10: 修改 `pyproject.toml:7`**

把:
```toml
version = "1.1.0.dev0"
```

改成:
```toml
version = "1.4.1"
```

- [ ] **Step 11: 修改 `src/tdx_chronos/__init__.py:3`**

把:
```python
__version__ = "1.1.0.dev0"
```

改成:
```python
__version__ = "1.4.1"
```

#### T5d · README badge 同步

- [ ] **Step 12: 修改 `README.md:5`**

把:
```markdown
[![Status](https://img.shields.io/badge/status-v1.4.0-blue)]() [![Python](https://img.shields.io/badge/python-3.12-green)]() [![Tests](https://img.shields.io/badge/tests-229%20passed-brightgreen)]() [![License](https://img.shields.io/badge/license-MIT-lightgrey)]()
```

改成:
```markdown
[![Status](https://img.shields.io/badge/status-v1.4.1-blue)]() [![Python](https://img.shields.io/badge/python-3.12-green)]() [![Tests](https://img.shields.io/badge/tests-317%20passed-brightgreen)]() [![License](https://img.shields.io/badge/license-MIT-lightgrey)]()
```

#### T5e · CHANGELOG v1.4.1 段

- [ ] **Step 13: 在 `CHANGELOG.md` 顶部 (L5 之后) 插入新段**

找到:
```markdown
---

## [v1.1.0] - 2026-07-05
```

在它之前插入:
```markdown
---

## [v1.4.1] - 2026-07-08

Sprint 12 · 9 个 client 层 bug 集中修复 · 297 → 317 tests (+20)

### Fixed (修复)

- 🐛 **`_normalize_symbol` 92→bj** (`4ca1bf2`) - 北交所新股 (`920001`/`830017`) 误归 sh
  - 修复: `92` 前缀在 `9` 之前特判 → bj; sh B 股 (`900901`) 保持
- 🐛 **`list_quarters` 排序方向反** (`f3b2c9a`) - docstring 承诺 DESC, 实现 ASC
  - 修复: `sorted(..., reverse=True)` + 严格 8 位日期 stem 正则
- 🐛 **`gpcw0.parquet` 脏数据** (`f3b2c9a`) - 0 行文件被 `glob` 命中, 输出 `'0--'`
  - 修复: 正则 `^gpcw(\d{8})\.parquet$` 过滤 + 物理删除
- 🐛 **`TdxChronos.close()` readonly=False 路径 db 泄漏** (`9a8e7d1`) - 早 return 跳过 `db.close()`
  - 修复: db 释放与 readonly 解耦, 永远先 release
- 🐛 **`index_klines` 多 `symbol` 列** (`7e4d2f8`) - 与 `kline` 契约不一致
  - 修复: `df.drop(columns=["symbol"])`, 保留 `code/ds_code/name/market` 元信息

### Changed (变更)

- 🔧 **MetaDB 公开 API 新增** `get_symbol(symbol)` + `list_symbols(market=None)` (5 tests)
  - 客户端层 `symbol_info` / `list_symbols` 改用新方法, 不再调 `db._connect()` 私有方法
- 📦 **版本号对齐 v1.4.1**: `pyproject.toml` + `__init__.py` + `CHANGELOG.md` + `README.md`
- 📊 **README 测试 badge**: 229 passed → 317 passed

### Known Issue (已知, 不修)

- ⚠️ **`data/meta/meta.db-shm` 残留 0400** - Sprint 11 `_clean_stale_wal_files()` 已自动恢复, 根因待查
  - 触发场景: 集成测试期间, umask 0o277 环境创建 SHM
  - 现状: 启动时有 warning 但不影响功能

### Test Summary

| Sprint | 新增 | 累计 | 累计时间 |
|---|---:|---:|---:|
| 11 | 3 | 300 | - |
| 12 | 20 | **317** | ~130s |

### 修复验证

- 5 个 `pyarrow` 反向验证脚本全部 PASS (见 design doc §验收标准)
- integration 9 测试 PASS (无变化)

---
```

(注: commit hash `4ca1bf2`/`f3b2c9a`/`9a8e7d1`/`7e4d2f8` 是占位 — 实际 commit 后用真实 hash 回填, 或合并到 1 个 commit 后只填一个)

#### T5f · 最终验证 + Commit

- [ ] **Step 14: 跑全套 unit + integration 测试**

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit -v --tb=short
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/integration -m "" -v --tb=short
```

Expected:
- unit: 旧 297 + 新 20 = **317 PASS, 0 FAIL**
- integration: 9/9 PASS (无变化)

- [ ] **Step 15: 复现全部 5 个反向验证 (来自 design doc §验收标准)**

逐个跑 (或合并成 1 个脚本):

```bash
cd /app/tdx-chronos
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
from pathlib import Path
from tdx_chronos.client import TdxChronos, _normalize_symbol
import tdx_chronos

# V1: 92→bj
assert _normalize_symbol('920001') == 'bj920001'
assert _normalize_symbol('900901') == 'sh900901'

# V2: list_quarters DESC
t = TdxChronos(Path('data'))
qs = t.list_quarters()
assert qs == sorted(qs, reverse=True)
assert '0--' not in qs

# V3: close() 释放 db
t2 = TdxChronos(Path('data'), readonly=False)
t2._ensure_db()
t2.close()
assert t2._db is None

# V4: index_klines drop symbol
df = t.index_klines('sh000001', start='2024-01-01')
assert 'symbol' not in df.columns
t.close()

# V5: version
assert tdx_chronos.__version__ == '1.4.1'

print('ALL 5 VERIFICATIONS PASS')
"
```

Expected: `ALL 5 VERIFICATIONS PASS`

- [ ] **Step 16: Commit**

```bash
cd /app/tdx-chronos
git add tests/unit/test_meta_db.py tests/unit/test_client.py \
        src/tdx_chronos/meta/db.py src/tdx_chronos/client.py \
        pyproject.toml src/tdx_chronos/__init__.py \
        README.md CHANGELOG.md
git commit -m "T5 · v1.4.1 版本对齐 + MetaDB 公开 API + README/CHANGELOG (Sprint 12)"
```

---

## 完成后的清理

- [ ] **Step C1: 写 `logs/sprint12-report.md`**

按现有 sprint 报告格式 (参考 `logs/sprint11-report.md` 不存在 · 实际是 `logs/sprint9-report.md`), 包含:
- Sprint 目标
- 5 个 task 交付物
- 测试数变化 (297 → 317)
- 已知 issue (stale SHM 待查)

- [ ] **Step C2: Commit report**

```bash
cd /app/tdx-chronos
git add logs/sprint12-report.md
git commit -m "Sprint 12 report · 9 bug 修复 + v1.4.1 收口"
```

- [ ] **Step C3: 打 v1.4.1 tag (可选, 主人确认后)**

```bash
cd /app/tdx-chronos
git tag -a v1.4.1 -m "v1.4.1 · 9 client bug 修复 + 317 tests passing"
```

---

## 风险与回滚

| 风险 | 缓解 | 回滚 |
|---|---|---|
| T1 92→bj 改坏其他 9 开头 | 4 单元测试 + 集成测试覆盖 | `git revert <T1 commit>` |
| T2 正则漏掉边缘 case | 8 位数字严格匹配 | `git revert <T2 commit>` |
| T3 顺序改动引入 race | db close 先于 chmod 保持 | `git revert <T3 commit>` |
| T4 破坏下游 | integration `index_klines` 仅断言 `close` 列 | `git revert <T4 commit>` |
| T5 public API 行为偏差 | 9 单元测试 + 4 回归 | `git revert <T5 commit>` |

任何 task 失败: 立即停, 不进入下一个 task, 等主人 review。

---

## 关键标识

- repo: `/app/tdx-chronos`
- HEAD 升级前: `224837f` (Sprint 12 design commit)
- HEAD 升级后: 5 个 task commit 序列
- venv: `.venv/bin/python`
- PYTHONPATH: `src:vendor/_vendor`
- 数据根: `/app/tdx-chronos/data` (21GB, 不可 commit)
- 删除文件: `data/fin/parsed/gpcw0.parquet` (gitignored)

---

**Owner**: claw-cortex 🦞
**Co-Authored-By**: claw-cortex 🦞 <ariesy.bleiren@gmail.com>
