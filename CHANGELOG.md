# Changelog

所有项目变更记录于此。

---

## [v1.4.2] - 2026-07-08

Sprint 11 · Incremental finance 解析 + `shareholders_history()` 新方法 · 317 → 324 tests (+7)

### Added (新增)

- ✨ **`MetaDB.should_skip_quarter()` + `quarter_metadata.file_mtime` 列** (`55dd5d8`) - 增量跳过判断基础
  - `should_skip_quarter(report_date, raw_path)` → True/False
  - `file_mtime REAL` 列跟踪原始文件 mtime; `ALTER TABLE` 幂等迁移已有 DB
- ✨ **`TdxFinReader.parse_quarters_incremental()` 增量入口** (`b98d289`) - 跳过已 OK 的 quarter
  - 返回 `IncrementalSummary(skipped, parsed, failed, elapsed_seconds)`
  - 遍历 `raw_dir/gpcw*.zip` + `gpcw*.dat` → `db.should_skip_quarter()` 判断
- ✨ **`TdxChronos.shareholders_history()` 新方法** (`ffd93dc`) - 带 filter 的股本历史
  - 支持 `types` (type in-list filter) / `since_date` / `until_date` (YYYY-MM-DD) / `limit`
  - PyArrow dataset filter expression + date DESC 排序 + pandas limit
- 🔧 **`cron/daily_incr.sh` Step 5** (`21b623e`) - 增量 finance 解析
  - 调用 `TdxFinReader.parse_quarters_incremental(snap/raw, $TDX_ROOT/data/fin/parsed, $DB_PATH)`
  - Summary 输出 skipped/parsed/failed

---

## [v1.4.1] - 2026-07-08

Sprint 12 · 9 个 client 层 bug 集中修复 · 297 → 317 tests (+20)

### Fixed (修复)

- 🐛 **`_normalize_symbol` 92→bj** (`1e08813`) - 北交所新股 (`920001`/`830017`) 误归 sh
  - 修复: `92` 前缀在 `9` 之前特判 → bj; sh B 股 (`900901`) 保持
- 🐛 **`list_quarters` 排序方向反** (`99e2e7b`) - docstring 承诺 DESC, 实现 ASC
  - 修复: `sorted(..., reverse=True)` + 严格 8 位日期 stem 正则
- 🐛 **`gpcw0.parquet` 脏数据** (`99e2e7b`) - 0 行文件被 `glob` 命中, 输出 `'0--'`
  - 修复: 正则 `^gpcw(\d{8})\.parquet$` 过滤 + 物理删除
- 🐛 **`TdxChronos.close()` readonly=False 路径 db 泄漏** (`e2774fa`) - 早 return 跳过 `db.close()`
  - 修复: db 释放与 readonly 解耦, 永远先 release
- 🐛 **`index_klines` 多 `symbol` 列** (`7c2423a`) - 与 `kline` 契约不一致
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

## [v1.1.0] - 2026-07-05

v1.1 是首个 **生产可用** 版本。38 commits · 229 PASSED · 7 Sprint。

### Added (新增)

#### Sprint 0-1: 基础设施
- ✅ 项目初始化 + pyproject.toml + venv
- ✅ mootdx 库 vendoring (vendor/mootdx/0.11.7 + 18 依赖 → vendor/_vendor/)
- ✅ 4 bug 真相记录 (vendor/UPGRADE_NOTES.md · 主路径不触发)

#### Sprint 2-4: 数据层
- ✅ K线解析器 (12,256 stocks · 日线 .day → Parquet)
- ✅ 财务解析器 (121 quarters · 5 zip 周更)
- ✅ 股本解析器 (1.26 亿 records · 13 字节 record 格式)
- ✅ 指数解析器 (28,004 records · 5 个指数)
- ✅ SQLite 元数据 (meta.db · symbols/quarters/index)
- ✅ row group 优化 (7570 row groups · Parquet 587.7 MB)

#### Sprint 5: 运维
- ✅ cron 脚本 (daily_sync.sh / weekly_sync.sh / weekly_doctor.sh)
- ✅ OpenClaw cron 接入 (3 jobs · Mon-Fri 17:30 / Sun 02:00 / Sun 03:00)
- ✅ HealthDoctor (8 项健康检查 + 3 级别)
- ✅ Alertor (飞书告警封装 · DRY-RUN 默认)

#### Sprint 6: 字段语义
- ✅ 14 types 字段语义映射 (type 1-48 中常用)
- ✅ 5 categories 设计 (capital/circulating/shareholder/finance/rare)
- ✅ gpcw 误识别 Bug 修复 (-5,396,310 dirty records)
- ✅ `to_categorized(category)` API + 真跑摸排 (83.1M records 验证)

#### Sprint 7: 语义补全 + 性能
- ✅ 未分类 28 types 语义映射 (新增 19 types · 总 33 types)
- ✅ 100% records 覆盖 (4 大类 99.5% + rare_event 0.5%)
- ✅ 摸排脚本 (scripts/sample_uncategorized_types.py · 511 samples)
- ✅ zstd 压缩实验 (snappy → zstd3 节省 26.1% · 待 Sprint 8 切换)

### Changed

- README.md - 项目介绍 + 数据规模 + Sprint 历史
- .gitignore - `!data/research/` (调研数据可 commit)

### Fixed

- 🐛 **gpcw 误识别 Bug** (`0fb9cd3`) - 148 个财务 .dat 文件被股本解析器误识别
  - 修复: `_discover_files` 用 `gp(sh|sz|bj)\d{6}\.dat` 精确过滤
  - 效果: records 125.7M → **120.3M** (clean)

### Performance

- ⏱️ zstd3 (Sprint 8 切换): 节省 26.1% disk · 写 +33% 时间 · 读 -5% 时间

### Test Summary

| Sprint | 测试数 | 累计 | 累计时间 |
|---|---:|---:|---:|
| 0-1 | 12 | 12 | - |
| 2 | 21 | 33 | - |
| 3-4 | 134 | 167 | 129s |
| 5 | 36 | **203** | 129s |
| 6 | 22 | 225 | 129s |
| 7 | 33 | **229** | 131s |

### Sprint 7 数据规模

| 指标 | Sprint 6 | Sprint 7 | 变化 |
|---|---:|---:|---:|
| 已分类 types | 14 | **33** | +19 |
| 4 大类覆盖 records | 69% | **99.5%** | +30.5pp |
| 总覆盖 | 69% | **100%** | +31pp |
| 测试 PASSED | 22 | **29** | +7 |
| 总 PASSED (累计) | 201 | **229** | +28 |

### v1.1.0 Release Tag

`git tag -a v1.1.0` - 38 commits 验证通过

---

## [v1.0.0] - 2026-07-03 (内部预发)

- 项目初始化 + vendoring 可行性验证
- Sprint 0 · 项目骨架 + pyproject.toml
- Sprint 1 · mootdx Vendor 化

---

## [v0.9.0] - 2026-07-03 (设计)

- requirements.md 初版
- v1.1 设计 (25.5-27 工作日 · 9 Sprint · 5 验证里程碑)

---

## v2.0 预览

- type 49-255 字段语义 (207 types)
- 长尾 (41-48) 进一步分析
- 公开股本变动公告全文匹配验证
- gpcw 财务领域 (Sprint 8 主体)
- 多源验证 (sina/同花顺/tushare)
- HTTP 兜底
- 在线实时推送

---

**Co-Authored-By**: claw-cortex 🦞 <ariesy.bleiben@gmail.com>