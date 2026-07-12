# AGENTS.md · tdx-chronos

> A-share offline data warehouse. Pulls 通达信 `.day` / `.dat` / `.zip` → Parquet → exposes a read-only `TdxChronos` facade.
> v1.4.3 (Sprint 13, ETF 显式化) · Python 3.12 · 330 tests.

---

## Quick start

```bash
# Install / re-activate venv (already provisioned)
.venv/bin/pip install -e .            # one-time editable install
.venv/bin/pip install -e ".[dev]"     # adds pytest-cov

# Run the full suite
.venv/bin/pytest tests/               # ~120s, all 330 tests; full suite routinely times out at 120s, use no timeout or run in background

# Run a single test file
.venv/bin/pytest tests/unit/test_client.py -v

# Run a single test
.venv/bin/pytest tests/unit/test_client.py::TestTdxChronos::test_kline_basic -v

# Run only unit (skip the slow integration suite)
.venv/bin/pytest tests/unit/ -q
```

**PYTHONPATH is required for ad-hoc python** — `pyproject.toml`'s `pythonpath = ["src"]` covers pytest, but direct `python` calls do not pick it up:

```bash
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "from tdx_chronos.client import TdxChronos; ..."
```

All `cron/*.sh` scripts `export PYTHONPATH=src:vendor/_vendor` at the top — match that pattern in any new script.

---

## Repository layout

```
src/tdx_chronos/         # importable package (src/ layout, NOT flat)
├── client.py            # TdxChronos facade · 9 public methods · readonly lock
├── doctor.py            # Doctor() · 10 health checks · alert_if_unhealthy
├── alertor.py           # Alertor · Feishu wrapper · dry-run default
├── sources/             # bulk_download · official_zip parser · index_parser
├── fin/                 # tdxfin · tdxgp · tdxgp_record · tdxgp_types · field_*
├── meta/db.py           # MetaDB · SQLite · symbol_metadata + download_log
└── optimization/        # parquet_compression (snappy / zstd)
vendor/_vendor/          # vendored deps (mootdx + 18 transitive) · commit this
vendor/mootdx/           # upstream mootdx 0.11.7 source · DO NOT EDIT (see UPGRADE_NOTES.md)
tests/unit/              # ~26 files, fast
tests/integration/       # test_client_integration.py only · real-data on ./data
tests/fixtures/          # real .day / .dat / .parquet samples · committed
data/                    # local data dir, NOT committed (see .gitignore)
data/research/           # exception · small CSVs committed for record
cron/                    # daily_sync / daily_incr / weekly_sync / weekly_doctor
docs/plans/              # sprint design + execution plans
logs/                    # sprint reports + cron logs (cron/ subdir gitignored)
```

`data/` weighs ~21 GB locally. `data/snapshot/`, `data/parquet/`, `data/xdxr/` are gitignored. Re-running `daily_sync.sh` re-downloads all zips (~10–15 min) so prefer reusing an existing snapshot.

---

## Hard rules (will silently break things if violated)

1. **Do not edit `vendor/mootdx/`** — it is vendored from upstream 0.11.7 with 4 known bugs. Record workarounds in `vendor/UPGRADE_NOTES.md`; do not patch the vendor copy. Refresh via `python -m vendoring sync vendor/mootdx/`.
2. **Do not `import mootdx.financial`** — that file is 0 bytes in 0.11.7 and ImportError's. Use `tdx_chronos.sources.financial` / `tdx_chronos.fin.tdxfin` instead (struct-based, 264-field record format).
3. **Do not commit `data/`** — `.gitignore` excludes the whole tree except `data/research/`. New ad-hoc samples belong there.
4. **Do not remove or skip tests to make CI green** — the 324→330 count is the canonical regression baseline (see `CHANGELOG.md`).
5. **Do not import `TdxChronos` from the package root** — actually false as of Sprint 11 T6; `from tdx_chronos import TdxChronos` now works. Use either form. (This hard-rule is kept for historical context.)

---

## TdxChronos facade — the only public API

Single entry point: `TdxChronos(data_dir, *, readonly=True)`. `data_dir` must already contain:

```
parquet_compact/   # K-line shards, one parquet per symbol under {market}/
fin/parsed/        # gpcw{YYYYMMDD}.parquet per quarter
gp/                # records.parquet (shareholder data)
index/             # indices.parquet
meta/              # meta.db (SQLite · symbol_metadata + download_log)
```

10 public methods (Sprint 13 加 `list_etfs`), all read-only unless `readonly=False`:

| method | source file | purpose |
|---|---|---|
| `symbol_info(symbol)` | `client.py` | metadata dict or `{}` (never raises) |
| `list_symbols(market=None)` | `client.py` | sorted ASC; market in `sh`/`sz`/`bj`; **含全部场内基金/可转债** |
| `list_etfs(market=None)` 🆕 | `client.py` | 仅场内基金/ETF/LOF/REITs/可转债 (代码段过滤) |
| `kline(symbol, start, end, columns=None)` | `client.py` | pyarrow predicate pushdown + column projection; **支持 ETF/可转债** |
| `finance(symbol, report_date, ratio_only)` | `client.py` | 1 quarter if `report_date` set, else all; **ETF 返回空 DataFrame** |
| `shareholders(symbol)` | `client.py` | filter `gp/records.parquet` by `code`; **支持 ETF (tdxgp.zip 含)** |
| `index_klines(index_code, start, end)` | `client.py` | filter `index/indices.parquet` |
| `list_quarters()` | `client.py` | **DESC by date** (newest first) |
| `doctor()` | `client.py` | wraps `Doctor().run()` |
| `close()` | `client.py` | closes db; restores chmod (may `RuntimeError` if external lock) |

Symbol normalization (`_normalize_symbol`): bare 6-digit codes get prefixed — `5/6/9 → sh`, `0/2/3 → sz`, `4/8 → bj`. Already-prefixed codes pass through lowercased.

`readonly=True` (default) `chmod 400`s `meta.db`, `gp/records.parquet`, `index/indices.parquet` at init, and `chmod 644`s on `close()`. If `close()` cannot restore write permission (e.g. external chmod), it raises `RuntimeError` so the cron job can be alerted.

---

## Footguns (README lies on these)

| Claim in README | Reality |
|---|---|
| `from tdx_chronos import TdxChronos` | `__init__.py` only exports `__version__` / `__author__`. **But** Sprint 11 T6 fix added a re-export — both forms now work. |
| `pip install -e .` works | It does, but it does **not** register vendored deps. Always run with `PYTHONPATH=src:vendor/_vendor` for ad-hoc invocations. |
| `gp/records.parquet` size | ~120M records, ~588 MB. Filtering on `code` uses pyarrow predicate pushdown — do not load then filter in pandas. |
| `list_quarters()` order | **DESC** (newest first), not ASC. The docstring says so; the name does not. |
| `date` column type in K-line | Stored as `int` `YYYYMMDD` (e.g. `20240102`), not `datetime`. `_to_yyyymmdd_int` accepts both `'2024-01-02'` and `'20240102'`. |
| `data/meta/meta.db-shm` exists | Yes, WAL mode. If a previous run left it with mode `<0o600` (umask 0o277 reproducer), SQLite throws "attempt to write a readonly database". `MetaDB._connect()` calls `_clean_stale_wal_files()` to auto-recover (Sprint 11 hotfix). |
| **`finance(symbol)` 适用于所有标的** | **错**。`tdxfin.zip` 仅含 A 股; 对场内基金 / ETF / LOF / REITs / 可转债调用会返回空 DataFrame 而非报错。判断方法: 先看 `symbol_info()['source_zip']=='tdxfin.zip'?`，否者改用 tushare `fund_basic`。 |
| **`list_symbols()` 不含 ETF** | **错**。12,279 symbols 中约 1,121+ 只是 ETF (sh510/511/512/513/588 + sz159),再叠加 ~777 LOF + 61 REITs + ~1,072 可转债,占总量 ~20%。要精准过滤用 `list_etfs(market=...)`。 |

---

## Cron / operational conventions

- All 4 cron scripts: `set -euo pipefail`, `cd "$TDX_ROOT"`, `export PYTHONPATH=src:vendor/_vendor`, then `<<PYEOF .venv/bin/python ... PYEOF`.
- Log path: `logs/cron/{name}_$(TZ=Asia/Shanghai date +%Y%m%d_%H%M%S).log` — gitignored.
- `TDX_DRY_RUN=1` (default) — `Alertor` prints instead of POSTing Feishu. Set `0` in production cron env.
- `daily_incr.sh` exit code: `0`=全成功, `1`=部分失败, `2`=全失败. Cron delivery can branch on this.
- Shanghai timezone is used for date stamping everywhere; use `TZ=Asia/Shanghai` in shell.

---

## Test conventions

- Layout: `tests/unit/test_<module>.py` for the module in `src/tdx_chronos/<module>.py`. Integration lives in `tests/integration/` (only one file today: `test_client_integration.py`).
- The integration suite reads real `data/` — keep `data/` present for CI. It is gitignored and not provided; CI must provision it.
- `_clean_stale_wal_files` is verified by 3 tests in `test_meta_db.py` (Sprint 11 T9).
- `tests/fixtures/` contains real `.day`, `.dat`, and `parquet_input/` — these are committed because they are < 1 MB.
- A single integration test can take several seconds (pyarrow opens big files); favor unit tests for new logic.

---

## Where to look for context

- `README.md` — public API + sprint history table (slightly out of date: badge says v1.4.0, pyproject still says 1.1.0.dev0).
- `requirements.md` — 63K requirement doc, the authoritative spec.
- `docs/plans/2026-07-07-query-facade*.md` — current TdxChronos design + 9-method contract.
- `docs/plans/2026-07-08-stale-shm-recovery.md` — explains the SHM 0400 root cause and the auto-recovery design.
- `CHANGELOG.md` — per-sprint deliverables, test counts, data-scale deltas.
- `vendor/UPGRADE_NOTES.md` — mootdx 4-bug record (real locations differ from the original Phase 1 PoC text).
- `docs/CONTRIBUTING.md` — v1.1-era workflow (mostly superseded; `requirements.md` is the new authoritative ref).

---

## Stack quirks worth knowing

- **No lint / format / typecheck config** in `pyproject.toml` — only pytest. Don't introduce ruff/black/mypy without asking.
- **pyarrow predicate pushdown** is the read path for `kline` / `shareholders` / `index_klines`. Filters must use `pyarrow.dataset.Expression` tuples, not pandas masks. See `pq.read_table(..., filters=[("col", "op", val)])`.
- **SQLite WAL** mode is on. Always go through `MetaDB`; don't `sqlite3.connect("data/meta/meta.db")` directly (bypasses `_clean_stale_wal_files`).
- **vendoring tool** is a runtime dep (`vendoring>=1.4`). It is configured by `vendoring.ini` at the repo root.
- **3 source mirrors**: core 3 zips from `data.tdx.com.cn`, 3 index zips from `www.tdx.com.cn`. Both fetched in `daily_incr.sh` via `BulkDownloader().download_all()` + `.download_index()`.
- **`meta/meta.db` schema** lives in `src/tdx_chronos/meta/db.py::MetaDB.init_schema()` — add new tables there, not via raw DDL.
