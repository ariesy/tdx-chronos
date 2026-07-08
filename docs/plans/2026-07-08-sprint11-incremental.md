# Sprint 11 Implementation Plan · Incremental Finance + shareholders_history

**Type**: Sprint 11 · post-v1.4.1 (Sprint 10 facade + Sprint 12 client bugfix) 延续
**Goal**: 2 个 user-facing 改进:
1. **增量 finance 解析** · daily_incr 跑时只 parse 新 quarter,跳过已 OK 的 120 个
2. **`shareholders_history()` 新方法** · 旧 `shareholders()` 全量返回,新方法支持 types/date_range/limit filter

**设计**: 本文 (design + plan 合并)
**目标 tag**: v1.4.2 (小 patch: 新 method + 防御性优化, 无 breaking change)

---

## 上下文 (Context)

### Sprint 11 T9 (前置 hotfix · 已 shipped)
- `MetaDB._clean_stale_wal_files()` 防御性 helper,清 stale SHM/WAL
- commit `d6f60b4` · 含在 v1.4.0→v1.4.1 链路
- tests: `tests/unit/test_meta_db.py` 27/27 PASS

### Sprint 12 (前置 v1.4.1 · 已 shipped)
- 9 client 层 bug 修复
- v1.4.1 tag: 2eb3b32
- tests: 308 unit + 9 integration = 317 PASS
- 已知问题 (§Sprint 12 报告): finance 解析未在 daily_incr,需手动触发

### Sprint 11 本期 (本 plan)
填上面那个"已知问题 #1 stale SHM 根因"以外的两个 gap:
- **Gap 1**: daily_incr 没有增量 finance (每次手动)
- **Gap 2**: `shareholders(symbol)` 没 types/date filter,实战用户只关心部分数据

---

## Task 1: `MetaDB.should_skip_quarter()` helper

**Files**:
- Modify: `src/tdx_chronos/meta/db.py`
- Test: `tests/unit/test_meta_db.py`

**目标**:`MetaDB.should_skip_quarter(report_date, raw_path) -> bool`
- True = 跳过(parse_ok=1 AND parsed_at > file_mtime)
- False = 重 parse(新 quarter / mtime 变 / 之前 failed)

**接口**:
```python
def should_skip_quarter(self, report_date: int, raw_path: Union[str, Path]) -> bool:
    """判断 quarter 是否可跳过 (已 parse_ok 且 mtime 未变)

    Args:
        report_date: YYYYMMDD (e.g. 20260331)
        raw_path: 原始 .dat/.zip 路径

    Returns:
        True = 跳过, False = 需要 parse
    """
    conn = self._connect()
    raw_path = Path(raw_path)
    if not raw_path.exists():
        return False  # 文件不在,留给 caller 处理
    file_mtime = raw_path.stat().st_mtime
    row = conn.execute(
        """
        SELECT parse_ok, parsed_at, file_mtime
        FROM quarter_metadata WHERE report_date = ?
        """,
        (report_date,),
    ).fetchone()
    if row is None:
        return False  # 无 record,需要 parse
    parse_ok, parsed_at, db_mtime = row["parse_ok"], row["parsed_at"], row["file_mtime"]
    if not parse_ok:
        return False  # 之前 failed,重试
    # 关键: 用 file_mtime 比较,不用 parsed_at(后者是 wall clock)
    if db_mtime is None or db_mtime < file_mtime:
        return False  # DB 无 mtime 记录 或 mtime 变化
    return True
```

**Schema 改动**:`quarter_metadata` 表加 1 列 `file_mtime REAL`(用 `ALTER TABLE`,幂等检查)
- Sprint 8 已有 `parsed_at`(写入时间),但**不是文件 mtime**(若源文件被覆盖/更新,parsed_at 不会变)
- 新加 `file_mtime` 字段,raw_path 的 mtime 写到 DB
- 这是"增量"逻辑的物理基础

**TDD**:
1. Test: 写 1 个 quarter + mtime=1.0 → `should_skip_quarter` returns True
2. Test: 改 raw_path mtime=2.0 → returns False
3. Test: 无 DB record → returns False
4. Test: parse_ok=0 → returns False
5. Test: file_path 不存在 → returns False

---

## Task 2: `TdxFinReader.parse_quarters_incremental()` 增量入口

**Files**:
- Modify: `src/tdx_chronos/fin/tdxfin.py`
- Test: `tests/unit/test_tdxfin.py`

**目标**: 新增 `parse_quarters_incremental(raw_dir, output_dir, db_path) -> IncrementalSummary`
- 遍历 `raw_dir/gpcw*.zip` + `gpcw*.dat`
- 调 `db.should_skip_quarter(report_date, raw_path)` 判断是否跳过
- 跳过 → continue
- 不跳 → 调 `parse_quarter()` + `db.record_quarter_metadata()` (含 mtime)
- 返回 `IncrementalSummary(skipped, parsed, failed, elapsed_seconds)`

**关键设计**:
- 不改 `iter_quarters()` (Sprint 4a D1 公开 API,保持 backward compat)
- 新方法独立,只在新 daily_incr Step 5 调用
- 用真实 DB 路径,不上 :memory: (因为要跨 process 持久化 mtime)

**TDD**:
1. Test: 0 quarter in DB → 全部 parse, 0 skipped
2. Test: 1 quarter 已 OK + mtime 同 → skipped=1 parsed=0
3. Test: 1 quarter 已 OK + mtime 变 → skipped=0 parsed=1
4. Test: 1 quarter 已 failed → skipped=0 parsed=1 (重试)
5. Test: 占位 file (164B zip) → is_placeholder=1, 不视为真 quarter

---

## Task 3: daily_incr.sh 加 Step 5 (增量 finance)

**Files**:
- Modify: `cron/daily_incr.sh`

**目标**: 在 Step 4 (指数) 之后加 Step 5,跑增量 finance
- ~10 行代码,同 Step 3 风格
- 输出: `log.info(f"finance: skipped={s.skipped} parsed={s.parsed} failed={s.failed} elapsed={s.elapsed:.1f}s")`
- 同时在底部 summary block 加 1 行

**TDD**:
- `tests/unit/test_cron_scripts.py` 加 1 个 test: 验证 daily_incr.sh 包含 "Step 5" + "parse_quarters_incremental"

---

## Task 4: `TdxChronos.shareholders_history()` 新方法

**Files**:
- Modify: `src/tdx_chronos/client.py`
- Test: `tests/unit/test_client.py`

**目标**: 新 public method,支持 types/date/limit filter
**签名**:
```python
def shareholders_history(
    self,
    symbol: str,
    types: Optional[List[int]] = None,
    since_date: Optional[Union[int, str]] = None,
    until_date: Optional[Union[int, str]] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """股本历史 · 带 filter 条件

    Args:
        symbol:     'sh600000'
        types:      type filter · e.g. [1, 2, 3, 4] 股本变动; None=全部
        since_date: YYYYMMDD (int) or 'YYYY-MM-DD' (str); None=不限
        until_date: 同上
        limit:      返回最多 N 行 (按 date DESC); None=全部

    Returns:
        DataFrame · type/date/value_1/value_2/market/code/symbol
        可能 empty (找不到 symbol) · 不 raise
    """
```

**实现**:
```python
import pyarrow.dataset as ds
norm = _normalize_symbol(symbol)
bare = norm[2:] if norm.startswith(("sh", "sz", "bj")) else norm

# Build pyarrow filter expression
filters = [ds.field("code") == bare]
if types:
    filters.append(ds.field("type").isin(types))
if since_date is not None:
    since_int = int(str(since_date).replace("-", ""))
    filters.append(ds.field("date") >= since_int)
if until_date is not None:
    until_int = int(str(until_date).replace("-", ""))
    filters.append(ds.field("date") <= until_int)
combined = filters[0] if len(filters) == 1 else ds.and_(*filters)

dataset = ds.dataset(str(self.gp_records), format="parquet")
table = dataset.to_table(filter=combined, columns=[
    "type", "date", "value_1", "value_2", "market", "code"
])

# Sort by date DESC + limit (pyarrow filter 不内置 sort, 在 pandas 端做)
df = table.to_pandas()
if not df.empty:
    df = df.sort_values("date", ascending=False)
    if limit is not None:
        df = df.head(limit).reset_index(drop=True)
    if "symbol" not in df.columns:
        df = df.assign(symbol=df["market"] + df["code"])
return df
```

**TDD** (5 个新 test):
1. Empty DataFrame for unknown symbol
2. types=[1,2,3,4] 只返回股本变动 (verify type column 只含 1,2,3,4)
3. since_date=20240101 只返回 ≥ 2024-01-01
4. limit=10 返回最多 10 行 (按 date DESC)
5. combined: types=[1,4] + since=20240101 + limit=5 (composability)

---

## Task 5: README + CHANGELOG 更新

**Files**:
- Modify: `README.md` (加 shareholders_history 到 API Reference)
- Modify: `CHANGELOG.md` (加 v1.4.2 段)
- Modify: `src/tdx_chronos/__init__.py` (version bump 1.4.1 → 1.4.2)
- Modify: `pyproject.toml` (version bump 1.4.1 → 1.4.2)

**README 改**:
- API Reference 表加 1 行: `shareholders_history(symbol, types=None, since_date=None, until_date=None, limit=None)`
- Quick Start 加 1 个示例: `tdx.shareholders_history('600000', types=[1,2,3,4], since_date='2024-01-01', limit=10)`
- 测试 badge 308 → 预期 ~316 (5 new shareholders_history + 5 new tdxfin + 1 new cron = +11)

**CHANGELOG 改**:
- 加 `## v1.4.2 (2026-07-08) · Incremental finance + shareholders_history`
- 2 个 `### Added` 段

---

## 实施模式 (Execution)

**Subagent-Driven (推荐)**:
- 派 1 个 implementer sub-agent 跑 T1-T5 (TDD-先 RED → GREEN → commit)
- 派 1 个 spec-reviewer 验证 commit 内容 + 跑 tests
- 修 issue → 再 review
- Phase 5: 推 + tag v1.4.2

**NO amend** · NEW commits on HEAD `2eb3b32` (Sprint 12 终点)

**commit message 模板**:
- T1: `T1 · MetaDB.should_skip_quarter() + quarter_metadata.file_mtime column (Sprint 11 增量基础)`
- T2: `T2 · TdxFinReader.parse_quarters_incremental() + TDD 5 tests (Sprint 11 Task 1)`
- T3: `T3 · daily_incr.sh Step 5: 增量 finance 解析 (Sprint 11 Task 1)`
- T4: `T4 · TdxChronos.shareholders_history() + 5 TDD tests (Sprint 11 Task 2)`
- T5: `T5 · README/CHANGELOG/version v1.4.2 (Sprint 11 收口)`

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| ALTER TABLE 失败 (Sprint 8 之前 DB 不兼容) | 低 | schema 漂移 | `init_quarter_metadata_schema` 用 `PRAGMA table_info` 检查,有则跳过 |
| `parse_quarters_incremental` 漏算 quarter | 中 | 数据不全 | 完整 test 覆盖 (T2-1~5) + integration test 跑 daily_incr.sh |
| shareholders_history filter 表达错 | 中 | 结果错 | T4-1~5 完整覆盖 + reverse verify (types=[1,4] 实际只含 1,4) |
| 测试 badge 数字 drift | 低 | 文档失准 | T5 完成后跑 `pytest --collect-only -q` 拿真实数字 |
| vendor/mootdx 误碰 | 极低 | 违反硬规则 | sub-agent 显式 prompt 强调"DO NOT touch vendor/" |

---

## 验收标准 (Acceptance)

```bash
# 1) TDD cycle
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit/test_meta_db.py -v --tb=short
# 期望: 27 + 5 = 32 PASS (T1)

PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit/test_tdxfin.py -v --tb=short
# 期望: 旧 N + 5 = N+5 PASS (T2)

PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit/test_client.py -v --tb=short
# 期望: 旧 + 5 = ... PASS (T4)

PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit -q --tb=short
# 期望: 旧 308 + 11 = 319 PASS (T1+T2+T3+T4)

PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/integration -m "" -q --tb=short
# 期望: 9/9 PASS (不变)

# 2) Reverse verify: 增量 finance
PYTHONPATH=src:vendor/_vendor .venv/bin/python << 'EOF'
from tdx_chronos.fin.tdxfin import TdxFinReader
from pathlib import Path
from tdx_chronos.meta.db import MetaDB

db = MetaDB('data/meta/meta.db')
# 跑增量,期望 119 skipped + 1 parsed (latest quarter)
summary = TdxFinReader.parse_quarters_incremental(
    raw_dir=Path('data/snapshot/2026-07-08/raw'),
    output_dir=Path('data/fin/parsed'),
    db_path=Path('data/meta/meta.db'),
)
print(f"skipped={summary.skipped} parsed={summary.parsed}")
db.close()
EOF

# 3) Reverse verify: shareholders_history
PYTHONPATH=src:vendor/_vendor .venv/bin/python << 'EOF'
from tdx_chronos import TdxChronos
tdx = TdxChronos(data_dir='data', readonly=True)
df = tdx.shareholders_history('600000', types=[1,2,3,4], since_date='2024-01-01', limit=10)
print(f"rows={len(df)} types={sorted(df['type'].unique())} date_range={df['date'].min()}-{df['date'].max()}")
EOF
```

---

## 关键标识

- repo: `/app/tdx-chronos`
- HEAD: `2eb3b32` (Sprint 12 终点, v1.4.1)
- target HEAD: `~5 commits later` (v1.4.2 收口)
- venv: `.venv/bin/python`
- PYTHONPATH: `src:vendor/_vendor`
- 目标 tag: `v1.4.2` (`2eb3b32..<new>`)
- 待清理: 10 个 Sprint 12 commit 没 push (Phase 5 一起推)

---

## 已知 deferral (后续 sprint)

- Sprint 12 报告提到的 stale SHM 根因 (umask 调查) — Sprint 12+
- Sprint 12 报告提到的 `finance()` 严格 8 位 stem — Sprint 12+
- 3 个 sprint 10/11/12 report backlog — Sprint 12+ 补 logs
- Sprint 11 完成后: Sprint 12 candidates (data update pipeline 自动化 / write path 测试覆盖 / DuckDB SQL 查询 / 等等) — 主人拍
