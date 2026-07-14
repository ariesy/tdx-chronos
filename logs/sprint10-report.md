# Sprint 10 报告 · TdxChronos Query Facade (v1.4.0)

**项目**: tdx-chronos v1.3 → v1.4.0
**作者**: claw-cortex 🦞
**日期**: 2026-07-06 ~ 2026-07-08 (3 天)
**关联**: requirements.md §四.7 read-only facade · `docs/plans/2026-07-07-query-facade*.md`

---

## 🎯 Sprint 10 目标

把 Sprint 9 之前散落的 bulk-download / parse / sqlite 直调用,**统一收敛**到一个
`TdxChronos` read-only facade。9 个 public 方法承担全部查询入口;`readonly=True`
进入时 chmod 400 保护 `meta.db` / `gp/records.parquet` / `index/indices.parquet`,
`close()` 时 chmod 644 还原 (失败抛 `RuntimeError` 让 cron 捕获)。

**完成目标**:
- ✅ `TdxChronos(data_dir, *, readonly=True)` facade + 9 public methods
- ✅ `__init__` 校验 5 子目录 + meta.db 必存在
- ✅ PyArrow predicate pushdown 替代内存过滤
- ✅ Integration test 真数据 9 cases (依赖 `data/` 真实 snapshot)

---

## 📋 Sprint 10 9 commits (chronological)

| T | commit | 主题 | 测试 |
|---|---|---|---|
| 1 | `4cec61f` | scaffold `TdxChronos class` + import test | +1 |
| 2 | `e3901cd` | `__init__` 校验 5 子路径 + readonly mode (chmod 400) | +0 |
| 3 | `d32a735` | `symbol_info()` + `list_symbols()` (MetaDB 查询) | +9 |
| T3-fix | `e974b9b` | **Critical #1** `close()` resource leak · **#2** DRY fixture · **#3-5** docstrings | +0 |
| 4 | `4e134ee` | `kline()` pyarrow predicate pushdown (gp 588 MB 不再 load 全量) | +12 |
| T4-fix | `18eabc6` | narrow except block + start/end 校验 + pyarrow imports top | +0 |
| 5 | `932dd30` | `finance()` + `shareholders()` + `index_klines()` + `list_quarters()` + `doctor()` | +25 |
| T5-fix | `9bbf789` | empty-DF on missing file + `DoctorReport` type + `ratio_only` test | +3 |
| T6-fix | `f0d5a86` | **修 5 真数据 schema mismatch** (kline 分文件, shareholders/index_klines 列名, finance pyarrow `index_columns`) | +0 |
| 6 | `54bdf27` | integration test 真数据 9 cases (6 spec + 3 T5-fix) | (counted above) |
| 7 | `afd5900` | README v1.4.0 update (Query Facade API + quick start) | - |
| 8 | `c25fedf` | v1.4.0 minor fix-up (sync unit fixtures per-symbol parquet layout) | - |
| 9 | `d6f60b4` | **MetaDB._clean_stale_wal_files() defensive recovery** (stale 0400-mode SHM hotfix) | +3 |

Sprint 净增 **53 测试** (Sprint 9 baseline 244 → Sprint 10 收口 297)。

---

## 🔥 Sprint 10 关键事故与修复

### 1. close() resource leak (T3-fix · critical)
Sprint 10 T3 初版 `close()` 写 `readonly=True` 路径没问题, `readonly=False`
路径早 `return` 跳过了 `db.close()`。修复: db release 与 readonly 解耦.

### 2. Stale 0400-mode SHM (T9 · hotfix)
Sprint 9 之前的 cron 跑过 `chmod 400 meta.db`, 残留 `meta.db-shm` 也是 0400 权限。
下次启动 SQLite WAL 写时:
```
sqlite3.OperationalError: attempt to write a readonly database
```
修复: `MetaDB._connect()` 启动时调 `_clean_stale_wal_files()` 自动 chmod 重置。
详见 `docs/plans/2026-07-08-stale-shm-recovery.md`。

### 3. Schema mismatch on real data (T6-fix)
T5 单元测试通过, 但跑真 `data/snapshot/2026-07-04` 失败:
- `kline()`: 期望 `parquet/` 单文件, 实际是 `parquet_compact/{market}/{symbol}.parquet` 分文件
- `shareholders` / `index_klines`: 列名 `code` vs `ds_code` 不一致
- `finance`: pyarrow 缺 `index_columns=[]` 时丢失索引列

修复 5 处全部对齐 v1.4.0 实际数据布局。

---

## 📦 Sprint 10 交付

### Public API (9 methods)
```python
from tdx_chronos import TdxChronos  # Sprint 11 T6 后 re-export

client = TdxChronos("/app/tdx-chronos/data", readonly=True)

client.symbol_info("sh600000")       # → {"code": "sh600000", "name": "浦发银行", ...}
client.list_symbols(market="sh")      # → ["sh600000", "sh600036", ...] (含 ETF/可转债)
client.kline("sh600000", "2024-01-01", "2024-12-31")  # pyarrow predicate pushdown
client.finance("sh600000", "20240331")         # 1 quarter or all
client.shareholders("sh600000")                # filter gp/records.parquet
client.index_klines("sh000300")                # filter index/indices.parquet
client.list_quarters()                         # (Sprint 12 改 DESC)
client.doctor()                                # wraps Doctor().run()
client.close()                                 # chmod 644 restore
```

### Tests 总数
- Sprint 9 末: 244 tests
- Sprint 10 末: **297 tests** (+53)
- 其中 integration: 9 (测试真 `data/snapshot/2026-07-04/`)

---

## 🪦 Sprint 10 已知 tech debt (在 Sprint 11-13 fix)

1. **__init__ 不导出 TdxChronos**: 只能 `from tdx_chronos.client import TdxChronos`。
   AGENTS.md 当时误标为 "硬规则"。Sprint 11 T6 才 re-export。
2. **list_quarters 排序**: Sprint 10 实现 ASC (跟 docstring 不一致)。Sprint 12 T2 改 DESC。
3. **_normalize_symbol 92 前缀**: Sprint 10 把北交所新股归 sh。Sprint 12 T1 改 bj。
4. **gpcw0.parquet 0 行文件**: Sprint 10 glob 命中, 输出 `'0--'`。Sprint 12 T2 过滤。

---

## 🔗 关联文档

- `docs/plans/2026-07-07-query-facade-design.md` · TdxChronos 单 class 设计
- `docs/plans/2026-07-07-query-facade.md` · Sprint 10 plan
- `docs/plans/2026-07-08-stale-shm-recovery.md` · T9 SHM 0400 hotfix
- `CHANGELOG.md [v1.4.0]` · v1.4 收口
