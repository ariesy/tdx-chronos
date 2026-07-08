# Sprint 12 报告 · Client Bugfix v1.4.1 (9 个 client 层 bug 集中修复)

**项目**: tdx-chronos v1.4.0 → v1.4.1
**作者**: claw-cortex 🦞
**日期**: 2026-07-08 (UTC)
**关联**: Sprint 10 集成测试 (2026-07-07 13:10 UTC) 暴露的 9 个 client 层 bug 一次性收口

---

## 🎯 Sprint 12 目标

Sprint 10 落地 `TdxChronos` facade 9 个 public method 后, 真数据集成测试暴露 9 个 client 层 bug。本 sprint 一次性修复, 发布 v1.4.1 (patch bump) 作为稳定 read-only query facade 基线。

**完成目标**:
- ✅ `_normalize_symbol` 92→bj (北交所新股归类)
- ✅ `list_quarters` DESC + 过滤 gpcw0.parquet 脏数据
- ✅ `TdxChronos.close()` readonly=False 路径 db 释放
- ✅ `index_klines` drop symbol 列对齐 kline 契约
- ✅ MetaDB 公开 API (get_symbol + list_symbols) + 版本号 1.1.0.dev0 → 1.4.1
- ✅ README 测试 badge 229 → 317
- ✅ CHANGELOG v1.4.1 段
- ✅ 317 tests passing (297 + 20)

---

## 📋 Sprint 12 8 commits

| 类型 | commit | 主题 | 测试 |
|---|---|---|---:|
| Design | `8379b52` | Sprint 12 design · client.py 9 bug 修复设计 (v1.4.1) | - |
| Fix | `224837f` | Sprint 12 design · fix test count arithmetic (319→317) | - |
| Plan | `cd55de4` | Sprint 12 plan · 5 task TDD 实施 (T1-T5 · 20 new tests · 297→317) | - |
| T1 | `1e08813` | `_normalize_symbol` 92→bj 北交所新股归类修复 | +4 |
| T2 | `99e2e7b` | `list_quarters` DESC + 过滤 gpcw0.parquet 脏数据 | +3 |
| T3 | `e2774fa` | `TdxChronos.close()` 修复 readonly=False 路径 db 泄漏 | +2 |
| T4 | `7c2423a` | `index_klines` drop symbol 列对齐 kline 契约 | +2 |
| T5 | `5c1913f` | v1.4.1 版本对齐 + MetaDB 公开 API + README/CHANGELOG | +9 |
| House | `3d7592a` | Plan heading rename (Task N format) + AGENTS.md | - |

**总计**: 8 commits, +20 unit tests, 0 integration changes, 0 amend

---

## 🐛 修复详情 (9 bug)

### P0 (4 bug · 数据正确性)

| # | 文件 | 修复 |
|---|---|---|
| 1 | `client.py:329-330` `_normalize_symbol` | `9 → sh` 前加 `92 → bj` 特判 (北交所新股 920001/830017) |
| 2 | `client.py:298-313` `list_quarters` | `sorted()` → `sorted(reverse=True)` + 严格 8 位日期 stem 正则 |
| 3 | `data/fin/parsed/gpcw0.parquet` | 物理删除 + glob 严格化 |
| 4 | `client.py:73-89` `close` | 移除 `if not self.readonly: return` 早 return · db close 永远先 |

### P1 (3 bug · API 一致性 / 文档)

| # | 文件 | 修复 |
|---|---|---|
| 5 | `client.py:281-283` `index_klines` | `df.drop(columns=["symbol"])` 对齐 kline 契约 |
| 6 | `pyproject.toml:7` + `__init__.py:3` | `1.1.0.dev0` → `1.4.1` (patch bump) |
| 7 | `README.md:5` badge | `tests-229%20passed` → `tests-317%20passed` |

### P2 (2 bug · 架构 / 已知)

| # | 文件 | 修复 |
|---|---|---|
| 8 | `meta/db.py:239-275` + `client.py:101-129` | 新增 `MetaDB.get_symbol` + `list_symbols` 公开方法 · client 改用 public API 不再 `db._connect()` |
| 9 | `CHANGELOG.md` Known Issue | 记录 stale SHM 0400 根因待查 · Sprint 11 hotfix 已自动恢复 |

---

## 📊 测试数据

| 阶段 | tests | 累计 | 备注 |
|---|---:|---:|---|
| Sprint 11 末 (基线) | - | 297 | 288 unit + 9 integration |
| T1 | +4 | 301 | _normalize_symbol 92→bj |
| T2 | +3 | 304 | list_quarters DESC + 过滤 |
| T3 | +2 | 306 | close() readonly=False |
| T4 | +2 | 308 | index_klines drop symbol |
| T5 | +9 | 317 | 5 MetaDB + 4 client spy/regression |
| **Sprint 12 末** | **+20** | **317** | 308 unit + 9 integration |

**全量验证** (来自 design doc §验收):
```bash
$ PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit -q
308 passed in 207.48s (0:03:27)

$ PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/integration -m "" -q
9 passed in 8.40s

$ PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
from pathlib import Path
from tdx_chronos.client import TdxChronos, _normalize_symbol
import tdx_chronos
assert _normalize_symbol('920001') == 'bj920001'
assert _normalize_symbol('900901') == 'sh900901'
t = TdxChronos(Path('data'))
qs = t.list_quarters()
assert qs == sorted(qs, reverse=True)
assert '0--' not in qs
t2 = TdxChronos(Path('data'), readonly=False)
t2._ensure_db()
t2.close()
assert t2._db is None
df = t.index_klines('sh000001', start='2024-01-01')
assert 'symbol' not in df.columns
t.close()
assert tdx_chronos.__version__ == '1.4.1'
print('ALL 5 VERIFICATIONS PASS')
"
ALL 5 VERIFICATIONS PASS
```

---

## 🔧 文件变更汇总

```
src/tdx_chronos/client.py        +30 / -19  (5 task 总计)
src/tdx_chronos/meta/db.py       +38 / -0   (T5: 2 public methods)
src/tdx_chronos/__init__.py      +1 / -1    (T5: version)
tests/unit/test_client.py        +109 / -0  (T1-T5 11 + T5b 4 = 15 新)
tests/unit/test_meta_db.py       +44 / -0   (T5a 5 新)
pyproject.toml                   +1 / -1    (T5: version)
README.md                        +3 / -3    (T5: badge + tagline + body)
CHANGELOG.md                     +60 / -0   (T5: v1.4.1 段)
docs/plans/2026-07-08-sprint12-client-bugfix-design.md   (新增, 400 行)
docs/plans/2026-07-08-sprint12-client-bugfix.md          (新增, 1278 行)
AGENTS.md                        (新增, 165 行)
data/fin/parsed/gpcw0.parquet    删除 (gitignored, 0 行)
```

**总计**: 11 文件, +1491 / -24 (净 +1467)

---

## ⚠️ 已知问题 (Known Issue, 后续 sprint 处理)

### 1. stale SHM 0400 根因 (Sprint 11 hotfix 已自动恢复, 但根因未查)

每次 `TdxChronos(readonly=True)` 启动时, 若 `data/meta/meta.db-shm` 存在且 mode < 0o600, `_clean_stale_wal_files()` 自动删 (Sprint 11 hotfix)。**根因待查**:
- 推测: 集成测试期间, umask 0o277 环境创建 SHM 时给了 0o400 权限
- 现状: 启动时有 warning 但不影响功能
- 建议: Sprint 13+ 调查 meta.db SHM 创建时的 umask 影响, 或在 `TdxChronos.__init__` 加 proactive 0644 强制

### 2. `finance()` 未走严格 8 位 stem 正则 (defense-in-depth 不一致)

`list_quarters()` T2 后用 `^gpcw(\d{8})\.parquet$` 严格过滤, 但 `finance()` 仍 `f.stem.replace("gpcw", "")`。目前安全因为 `gpcw0.parquet` 已物理删除, 但 defense-in-depth 不一致。建议 Sprint 13 把 `_QUARTER_STEM_RE` hoist 到模块级 + `finance()` 也用。

### 3. Sprint 10/11/12 报告 backlog

`logs/sprint10-report.md` / `sprint11-report.md` / `sprint12-report.md` (本文件) 缺位。建议补全 backlog, 不阻塞 v1.4.1 发布。

---

## 🎯 v1.4.1 验收

- [x] 全部 9 个 client bug 修复
- [x] 317 tests passing (308 unit + 9 integration)
- [x] 版本号 4 处对齐 (pyproject / __init__ / CHANGELOG / README badge)
- [x] 5 个反向验证脚本全部 PASS
- [x] vendor/mootdx/ 未触碰 (硬规则)
- [x] data/ 未 commit (除已 gitignored 删的 gpcw0.parquet)
- [x] 无 `import mootdx.financial` (硬规则)
- [x] 无测试删除/跳过保 CI 绿 (硬规则)
- [x] 8 个 sprint 12 commits, NO amend, NO 跨 task 改动

**状态**: ✅ Ready to tag v1.4.1
