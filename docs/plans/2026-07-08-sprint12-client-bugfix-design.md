# Sprint 12 Design · Client Bugfix

**项目**: tdx-chronos v1.4.1
**作者**: claw-cortex 🦞
**日期**: 2026-07-08 (UTC)
**关联**: Sprint 10 (Query Facade v1.4.0) + Sprint 11 (Stale SHM hotfix) 的延续 · 9 个 client 层面 bug 集中修复
**Status**: Pending (待主人 review)

---

## 🎯 目标

Sprint 10 落地 `TdxChronos` facade 9 个 public method 后，第一次全量跑真数据 (2026-07-07 13:10 UTC 集成测试) 暴露出 9 个 client 层 bug，分散在 `client.py` / `meta/db.py` / 文档中。本 sprint 一次性收口，使 v1.4.1 成为稳定的 read-only query facade。

**修复后状态**:
- `tdx.kline('920001')` 不再归到 `sh` (北交所新股归 bj)
- `tdx.list_quarters()` 输出 `DESC` 且过滤脏数据
- `tdx.close()` 在 `readonly=False` 时仍释放 db 连接
- `tdx.index_klines()` 与 `tdx.kline()` 列契约一致
- 版本号 3 处对齐 (pyproject + __init__ + CHANGELOG)
- README 测试 badge 297 同步
- `client.py` 不再调用 `MetaDB._connect()` 私有方法

---

## 📋 修复清单 (9 项)

| # | 文件 | 行号 (现状) | 严重度 | 现象 |
|---|---|---|---|---|
| 1 | `client.py` `_normalize_symbol` | L324-336 | **P0** | `920001` 归 sh，实际是 bj |
| 2 | `client.py` `list_quarters` | L297-307 | **P0** | docstring 承诺 DESC，实现返回 ASC |
| 3 | `data/fin/parsed/gpcw0.parquet` | (data) | **P0** | 0 行脏文件被 `glob` 命中，输出 `'0--'` |
| 4 | `client.py` `close` | L73-89 | **P0** | `readonly=False` 时 `_db` 不释放 |
| 5 | `client.py` `index_klines` | L265-295 | P1 | 返回列比 `kline` 多 4 个 (含 `symbol` 应 drop) |
| 6 | `pyproject.toml` + `__init__.py` | L7 / L3 | P1 | `1.1.0.dev0` vs README `v1.4.0` |
| 7 | `README.md` badge | L5 | P1 | badge 写 229 passed, 实际 297 |
| 8 | `client.py` `symbol_info/list_symbols` | L101-139 | P2 | 直接 `db._connect()` 绕 MetaDB 公开 API |
| 9 | `data/meta/meta.db-shm` | (data) | P3 | 每次启动都触发 stale SHM 0400 警告 (Sprint 11 已自动恢复) |

---

## 📐 设计

### T1 · `_normalize_symbol` 92→bj 修复 (P0)

**现状** (client.py:324-336):
```python
def _normalize_symbol(symbol: str) -> str:
    s = symbol.lower().strip()
    if s.startswith(("sh", "sz", "bj")):
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("5", "6", "9")):    # ← 9 一刀切 → sh
            return "sh" + s
        if s.startswith(("0", "2", "3")):
            return "sz" + s
        if s.startswith(("4", "8")):
            return "bj" + s
    return s
```

**问题**: A 股市场规则实际为：
- `sh`: 5xxxxx (基金), 6xxxxx (A 股), 9xxxxx (B 股, 但 **9 开头两位** 例 900xxx)
- `sz`: 0xxxxx, 2xxxxx, 3xxxxx
- `bj`: 4xxxxx, 8xxxxx, **92xxxxx** (北交所新股)

`9` 单独开头走 sh，但 `92` 开头两位走 bj。需把 `92` 提到 `9` 前面判断。

**修复后**:
```python
if len(s) == 6 and s.isdigit():
    if s.startswith("92"):                  # ← 新增 · 北交所新股优先
        return "bj" + s
    if s.startswith(("5", "6", "9")):      # 不动 · sh 通用
        return "sh" + s
    if s.startswith(("0", "2", "3")):
        return "sz" + s
    if s.startswith(("4", "8")):
        return "bj" + s
return s
```

**测试** (4 个):
- `test_normalize_92_to_bj` · `920001 → bj920001` (P0 主测)
- `test_normalize_9_b_share_to_sh` · `900901 → sh900901` (回归)
- `test_normalize_other_prefixes_unchanged` · `600000/000001/430017` 保持原行为
- `test_normalize_already_prefixed_passthrough` · `bj920001 → bj920001` (大小写不敏感)

---

### T2 · `list_quarters()` 排序方向 + 脏数据过滤 (P0)

**现状** (client.py:297-307):
```python
def list_quarters(self) -> List[str]:
    """List 已 parsed 季度 · 'YYYY-MM-DD' strings

    Returns:
        List[str] · sorted by date DESC (newest first: ...)
    """
    files = sorted(self.fin_parsed.glob("gpcw*.parquet"))   # ← ASC, 错
    return [
        _int_to_yyyymmdd_dash(int(f.stem.replace("gpcw", ""))) for f in files
    ]
```

**问题**:
1. `sorted()` 升序，docstring 写降序 — 行为与文档矛盾
2. `gpcw0.parquet` (0 行) 被 `gpcw*.parquet` glob 命中，`int('0')=0` 拆出 `0--`

**修复后**:
```python
import re
_QUARTER_STEM_RE = re.compile(r"^gpcw(\d{8})\.parquet$")

def list_quarters(self) -> List[str]:
    """List 已 parsed 季度 · 'YYYY-MM-DD' strings

    Returns:
        List[str] · sorted by date DESC (newest first: '2026-03-31', '2025-12-31', ...)
        Files not matching 8-digit date stem are skipped (defensive)
    """
    matches: list[tuple[int, Path]] = []
    for f in self.fin_parsed.glob("gpcw*.parquet"):
        m = _QUARTER_STEM_RE.match(f.name)
        if m is None:
            continue                                  # 跳过 gpcw0.parquet 等
        matches.append((int(m.group(1)), f))
    matches.sort(key=lambda t: t[0], reverse=True)    # DESC
    return [_int_to_yyyymmdd_dash(d) for d, _ in matches]
```

**附加**: 删 `data/fin/parsed/gpcw0.parquet` (1390 字节 · 0 行 · gitignored) — 已用 `git status` 确认不在追踪内。

**测试** (3 个):
- `test_list_quarters_desc_order` · 验证返回顺序为 DESC
- `test_list_quarters_skips_invalid_stem` · 手动建 `gpcw999.parquet` + `gpcw20251231.parquet`，验证前者被过滤
- `test_list_quarters_empty_when_no_files` · 临时清空 fin_parsed glob 范围，验证返回 `[]`

---

### T3 · `close()` 资源释放 (P0)

**现状** (client.py:73-89):
```python
def close(self):
    if not self.readonly:
        return                                # ← readonly=False 时早 return
    db, self._db = self._db, None
    if db is not None:
        db.close()
    for p in [...]:
        if p.is_file():
            try:
                os.chmod(p, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            except PermissionError as e:
                raise RuntimeError(...) from e
```

**问题**: `readonly=False` 路径下，若用户已通过 `symbol_info`/`list_symbols` 触发 `_ensure_db()`，`_db` 句柄泄漏到 GC。

**修复后**:
```python
def close(self):
    """Always release db connection; restore chmod only when readonly=True"""
    db, self._db = self._db, None             # ← 移到最前
    if db is not None:
        db.close()
    if not self.readonly:
        return                                # ← chmod 恢复段才跳过
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

**关键不变量**: 无论 readonly 与否，db 连接一定释放。chmod 恢复仅 readonly=True 路径需要。

**测试** (2 个):
- `test_close_releases_db_when_readonly_false` · `readonly=False` + `_ensure_db()` 后 `t._db is None`
- `test_close_releases_db_when_readonly_true` · 回归测试，确保 readonly=True 路径不变

---

### T4 · `index_klines` 列对齐 (P1)

**现状** (client.py:265-295): 返回列含 `symbol` 字段。`kline` 显式 `df.drop(columns=["symbol"])`，两者契约不一致。

**修复**: 在 `index_klines` 末尾加:
```python
if not df.empty and "symbol" in df.columns:
    df = df.drop(columns=["symbol"])
```

**决策记录**: 保留 `code/ds_code/name/market/source_zip/ingested_at` — 这些是指数元信息，kline 也有同名列 (除 symbol 外)。仅 drop `symbol` 是因为 symbol 是查询 key，重复无意义。

**测试** (2 个):
- `test_index_klines_drops_symbol_column` · 验证返回 df 不含 `symbol` 列
- `test_index_klines_preserves_other_metadata_columns` · 验证 `market/code/ds_code/name` 等保留

---

### T5 · 版本对齐 + MetaDB 公开 API + 文档同步 (P1/P2)

**5a · 版本号 bump (P1)**
- `pyproject.toml` L7: `version = "1.1.0.dev0"` → `"1.4.1"`
- `src/tdx_chronos/__init__.py` L3: `__version__ = "1.1.0.dev0"` → `"1.4.1"`
- `CHANGELOG.md`: 顶部新增 `## [v1.4.1] - 2026-07-08` 段，列 9 项修复 + test count 229 → 297 (Sprint 10 已达) → 317 (本次 +20)

**5b · README badge 同步 (P1)**
- `README.md` L5: `[![Tests](...tests-229%20passed-brightgreen)]()` → `[![Tests](...tests-317%20passed-brightgreen)]()`
- 注: 实际 = Sprint 10 的 297 + Sprint 12 新增 20 = 317

**5c · MetaDB 公开 API (P2)**

**新增** (meta/db.py):
```python
def get_symbol(self, symbol: str) -> dict | None:
    """Public symbol metadata lookup. Returns dict or None."""
    conn = self._connect()
    row = conn.execute(
        "SELECT * FROM symbol_metadata WHERE symbol = ?",
        (symbol.lower(),),
    ).fetchone()
    return dict(row) if row else None

def list_symbols(self, market: str | None = None) -> list[str]:
    """Public symbol list. market in {sh, sz, bj} or None for all."""
    conn = self._connect()
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

**改动** (client.py:101-139):
```python
def symbol_info(self, symbol: str) -> Dict[str, Any]:
    db = self._ensure_db()
    return db.get_symbol(_normalize_symbol(symbol)) or {}   # ← 改用 public method

def list_symbols(self, market: Optional[str] = None) -> List[str]:
    db = self._ensure_db()
    return db.list_symbols(market)                           # ← 改用 public method
```

**5d · `gpcw0.parquet` 清理** (T2 已述，物理删除 `data/fin/parsed/gpcw0.parquet`)

**5e · stale SHM 观察 (P3)**
- 行为: 每次 `TdxChronos(readonly=True)` 初始化时，若 `meta.db-shm` 存在且 mode < 0o600，`_clean_stale_wal_files()` 自动删
- 现状: Sprint 11 hotfix 已工作
- 行动: 仅在 `CHANGELOG.md` v1.4.1 段加一条 Known Issue 记录: "启动时偶发 SHM 0400 警告 · Sprint 11 hotfix 已自动恢复 · 根因待查"
- **不修根因** (避免 scope 膨胀)

**测试** (9 个, 5c 部分):
- `test_meta_db_get_symbol_found` / `test_meta_db_get_symbol_not_found_returns_none`
- `test_meta_db_list_symbols_all` / `test_meta_db_list_symbols_filtered_by_market`
- `test_meta_db_list_symbols_sorted_asc`
- `test_client_symbol_info_uses_meta_db_public_api` (用 mock 验证不调 `_connect`)
- `test_client_list_symbols_uses_meta_db_public_api`
- `test_client_symbol_info_unchanged_behavior` (回归)
- `test_client_list_symbols_unchanged_behavior` (回归)

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| T1 92→bj 改坏其他 9 开头代码 | 低 | sh B 股归错 | 单元测试覆盖 900901/900902 (回归) |
| T2 glob 严格化漏掉边界 case | 极低 | 跳过有效季度 | 正则 `^gpcw(\d{8})\.parquet$` 严格 8 位 |
| T3 早 return 移除影响 readonly=True 路径 | 极低 | 提早 chmod 失败 | db close 先于 chmod (顺序保持) |
| T4 drop symbol 破坏下游脚本 | 中 | 集成测试挂 | 集成测试断言列数 |
| T5c MetaDB 公开 API 行为偏差 | 低 | 查询结果错 | 8 个回归测试 + integration 跑全量 |
| T5d 删 gpcw0.parquet 误删 | 0 | 数据丢失 | git status 验证 gitignored + 0 行确认 |

---

## 验收标准 (Acceptance Criteria)

```bash
# 1) 全部 unit tests PASS
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit -v --tb=short
# 期望: 旧 297 + 新 20 = 317 PASS

# 2) integration tests PASS (不变)
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/integration -m "" -v --tb=short
# 期望: 9/9 PASS

# 3) 复现反向验证 1: 920001 归 bj
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
from tdx_chronos.client import _normalize_symbol
assert _normalize_symbol('920001') == 'bj920001', '92 should be bj'
assert _normalize_symbol('900901') == 'sh900901', '9 single should be sh (B-share)'
print('PASS · normalize ok')
"

# 4) 复现反向验证 2: list_quarters DESC
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

# 5) 复现反向验证 3: close() 释放 db
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

# 6) 复现反向验证 4: index_klines drop symbol
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
from pathlib import Path
from tdx_chronos.client import TdxChronos
t = TdxChronos(Path('data'))
df = t.index_klines('sh000001', start='2024-01-01')
assert 'symbol' not in df.columns, f'symbol should be dropped, got: {list(df.columns)}'
t.close()
print('PASS · index_klines drops symbol column')
"

# 7) 版本号 3 处一致
grep -E "version" pyproject.toml | grep -q "1.4.1" && \
  grep -q "1.4.1" src/tdx_chronos/__init__.py && \
  grep -q "v1.4.1" CHANGELOG.md && \
  echo "PASS · version 1.4.1 in pyproject + __init__ + CHANGELOG"
```

---

## 实施模式

**Subagent-Driven (Phase 3, 5 任务串行)**:
1. T1 implementer → 92→bj 修复 + 4 测试
2. T2 implementer → list_quarters + 删 gpcw0.parquet + 3 测试
3. T3 implementer → close() 资源释放 + 2 测试
4. T4 implementer → index_klines drop symbol + 2 测试
5. T5 implementer → 版本号 + MetaDB API + 文档 + 9 测试

每个 task: TDD 先 RED (写测试) → impl → GREEN → commit
每 task 独立 commit, **NO amend**

**commit 序列**:
- `T1 · _normalize_symbol 92→bj 北交所新股归类修复`
- `T2 · list_quarters DESC + 过滤 gpcw0.parquet 脏数据`
- `T3 · TdxChronos.close() 修复 readonly=False 路径 db 泄漏`
- `T4 · index_klines drop symbol 列对齐 kline 契约`
- `T5 · v1.4.1 版本对齐 + MetaDB 公开 API + README badge`

**最后**: 写 `logs/sprint12-report.md` (per existing convention)

---

## 关键标识

- repo: `/app/tdx-chronos`
- HEAD: 升级前 (Sprint 11 之后)
- venv: `.venv/bin/python`
- PYTHONPATH: `src:vendor/_vendor`
- target files:
  - `src/tdx_chronos/client.py` (T1/T2/T3/T4)
  - `src/tdx_chronos/meta/db.py` (T5c, public methods)
  - `pyproject.toml` + `src/tdx_chronos/__init__.py` (T5a)
  - `README.md` + `CHANGELOG.md` (T5b/T5d/T5e)
- test files:
  - `tests/unit/test_client.py` (T1/T2/T3/T4 测试)
  - `tests/unit/test_meta_db.py` (T5c 测试)
- 删除文件: `data/fin/parsed/gpcw0.parquet` (gitignored)

---

## 范围外 (Out of Scope)

- 修复 stale SHM 根因 (T5e 仅观察, 不修)
- 改 `doctor.py` / `alertor.py` (本次不动)
- 改 `cron/*.sh` (本次不动)
- 改 README 的 9 方法 API 描述 (本次只改 badge)
- vendor/mootdx/ 任何修改 (硬规则)
