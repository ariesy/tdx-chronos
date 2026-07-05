# Changelog

所有项目变更记录于此。

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