# Sprint 11 报告 · Incremental Finance + Shareholders History (v1.4.2)

**项目**: tdx-chronos v1.4.1 → v1.4.2
**作者**: claw-cortex 🦞
**日期**: 2026-07-08 (1 天)
**关联**: `docs/plans/2026-07-08-sprint11-incremental.md`

---

## 🎯 Sprint 11 目标

Sprint 10 全量每周跑一次 finance 解析 (258 季度 × 12 MB = 1.8 GB 重新写盘)。
为了 **周日 weekly_sync + 工作日 daily_incr 增量跑** 增量:

1. 在 `quarter_metadata` 表加 `file_mtime REAL` 列, 跟踪原始文件 mtime
2. `MetaDB.should_skip_quarter(report_date, raw_path)` → True/False
3. `TdxFinReader.parse_quarters_incremental()` 跳已 OK quarter
4. `cron/daily_incr.sh` Step 5 调增量入口
5. `TdxChronos.shareholders_history()` 新方法 (filter type/since_date/until_date/limit)

---

## 📋 Sprint 11 6 commits

| T | commit | 主题 | 测试 |
|---|---|---|---|
| 1 | `55dd5d8` | `MetaDB.should_skip_quarter()` + `quarter_metadata.file_mtime` 列 (`ALTER TABLE` 幂等迁移) | +2 |
| 2 | `b98d289` | `TdxFinReader.parse_quarters_incremental()` + 5 TDD tests | +5 |
| 3 | `21b623e` | `cron/daily_incr.sh` Step 5 调增量入口 | +0 |
| 4 | `ffd93dc` | `TdxChronos.shareholders_history()` 新方法 (filter types/since_date/until_date/limit) | +5 |
| 5 | `9291344` | README/CHANGELOG/version v1.4.2 收口 | - |
| 5b | `df12046` | Sprint 11 plan doc | - |
| 6 | `dfe859a` | **fix-up**: `file_mtime` 迁移到 `init_schema()` + `TdxChronos` `__init__` re-export (2 production bug) | (Re-counted below) |

Sprint 11 净增 **+7 测试** (297 → 304), 后续 Sprint 12 fix 为 317。

---

## ⚠️ Sprint 11 fix-up 修复的 2 production bug

### 1. `_clean_stale_wal_files()` 后 ALREADY-PARSED 旧 quarter 仍重跑
T1 写 `should_skip_quarter` 时, `file_mtime` 列检查只对新 quarter 有效。已有 quarter
(`file_mtime IS NULL`) 会强制被重跑一遍。Fix-up T6 把 file_mtime ALTER TABLE 移到
`init_schema()`, 让旧 DB 也能補默认值。

### 2. `from tdx_chronos import TdxChronos` ImportError
Sprint 10 实现 `TdxChronos` 只 export 在 `client.py`, `__init__.py` 只导 `__version__` /
`__author__`。Fix-up T6 加 `from tdx_chronos.client import TdxChronos` re-export。
(AGENTS.md "硬规则 #5" 当时误标, 后改 actual true)

---

## 📦 Sprint 11 交付

### Schema 变更 (幂等迁移)
```sql
ALTER TABLE quarter_metadata ADD COLUMN file_mtime REAL;
-- Sprint 11+ 写入: db.record_quarter_metadata(..., file_mtime=q.raw_path.stat().st_mtime)
-- 旧 quarter 迁移: init_schema() 自动 UPDATE file_mtime = COALESCE(file_mtime, 0)
```

### Public API 新增
```python
client.shareholders_history(
    "sh600000",
    types=("type_1", "type_10"),   # Optional in-list filter
    since_date="2024-01-01",        # Optional YYYY-MM-DD
    until_date="2024-12-31",        # Optional YYYY-MM-DD
    limit=100,                       # Optional, pandas limit applied post-sort
)
```

### Cron 新增入口
`cron/daily_incr.sh` Step 5:
```python
fs = TdxFinReader.parse_quarters_incremental(
    raw_dir=snap / "raw",
    output_dir=Path("$TDX_ROOT/data/fin/parsed"),
    db_path=Path("$DB_PATH"),
)
# 输出: skipped=240 parsed=18 failed=0 elapsed=0.1s
```

---

## 🔗 关联文档

- `docs/plans/2026-07-08-sprint11-incremental.md` · Sprint 11 plan
- `CHANGELOG.md [v1.4.2]` · v1.4.2 收口

---

## 🪦 Sprint 11 已知 tech debt (后续 fix)

- `kline()` 用 `parquet_path` 旧路径 (Sprint 14 删 `data/parquet/` legacy)
- `bulk_download` retry ENOSPC 时空转 3 次 (Sprint 14 condition-based)
- snapshot 永久累积无 retention (Sprint 13 hotfix 才加 7 天 → 后改 3 天)
