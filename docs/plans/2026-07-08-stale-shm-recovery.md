# Plan · Stale SHM Recovery · 2026-07-08

**Status**: Approved (主人 "OK" · 2026-07-08 11:57 UTC)
**Type**: Defensive fix · Sprint 11 T9 · post-Sprint 10 v1.4.0 hotfix
**Scope**: 1 file (`src/tdx_chronos/meta/db.py`) + 1 test file (`tests/unit/test_meta_db.py`)

---

## Context (Phase 1 根因)

2026-07-08 17:30 CST `daily_incr.sh` cron 失败:
```
sqlite3.OperationalError: attempt to write a readonly database
  at src/tdx_chronos/meta/db.py:244 record_download()
```

**根因**: Sprint 10 集成测试 (2026-07-07 13:10 UTC) 期间,某次 `sqlite3.connect()` 在受限制 umask (0o277) 环境下创建了 `data/meta/meta.db-shm` 文件,权限 **`-r--------` (400)**,owner 也不能写。下次 SQLite WAL 模式启动 mmap SHM 失败 → 报 "readonly database"。

**复现验证** (Phase 3): 删除 stale SHM + WAL → `record_download` PASS。**修复 100% 有效**。

---

## Design · 方案 C (db.py 防御)

### 改动 1: 新增 helper `_clean_stale_wal_files()`

```python
def _clean_stale_wal_files(self) -> None:
    """检测并清理 stale SQLite WAL/SHM 残留

    Why: Sprint 10 集成测试期间,某次 sqlite3.connect() 在 umask 0o277 环境
    下创建了 400 权限 (-r--------) 的 meta.db-shm · owner 也不能写 ·
    下次 SQLite WAL 模式启动时 mmap 失败报 'attempt to write a readonly database'

    规则:
    - SHM 文件存在且权限 < 0o600 (owner 不可写) → 删 (SQLite 会重建)
    - WAL 文件存在且 0 字节 + 同目录无 SHM → 删 (stale,安全)
    - WAL 非 0 字节 → 保留 (可能含未提交事务,不碰)
    - :memory: DB → 跳过
    """
    if str(self.db_path) == ":memory:":
        return
    base = self.db_path.name
    parent = self.db_path.parent
    shm = parent / (base + "-shm")
    wal = parent / (base + "-wal")
    if shm.exists() and (shm.stat().st_mode & 0o777) < 0o600:
        logging.warning(
            "Removing stale SHM (mode=%04o): %s",
            shm.stat().st_mode & 0o777, shm,
        )
        shm.unlink()
    # 0 字节 WAL + SHM 已删 → 一定是 stale
    if wal.exists() and wal.stat().st_size == 0 and not shm.exists():
        wal.unlink()
```

### 改动 2: `_connect()` 顶部加 1 行调用

```python
def _connect(self) -> sqlite3.Connection:
    self._clean_stale_wal_files()  # ← 新增 · 先清 stale
    if self._conn is None:
        ...
```

### 改动 3: 3 个新单元测试 (TDD-先 RED)

**文件**: `tests/unit/test_meta_db.py`

1. `test_stale_shm_with_mode_400_is_removed`
   - 手工创建 SHM,`os.chmod(shm, 0o400)`,`MetaDB(...)` 初始化
   - 验证: 后续 `record_download` PASS,`stale_shm_removed` 标志为 True

2. `test_empty_wal_with_no_shm_is_removed`
   - 手工创建 0 字节 WAL (无 SHM)
   - 验证: `MetaDB(...)` 后 WAL 已删

3. `test_record_download_after_stale_shm_recovery`
   - 完整场景: stale SHM 400 → `MetaDB(...)` → `init_schema()` → `record_download()` → PASS

### 改动 4: 清理 dirty data (在 commit 之前)

```python
# T9 实施者在 GREEN 之后、commit 之前手动跑
from tdx_chronos.meta.db import MetaDB
db = MetaDB('data/meta/meta.db')
cur = db._conn.cursor()
cur.execute("DELETE FROM download_log WHERE zip_name = 'test.zip'")
db._conn.commit()
db.close()
```

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| SHM 误删 (正常 644/600) | 0% | 写失败 | 阈值 < 0o600 才删 |
| WAL 误删 (非 0 字节) | 0% | 丢未提交事务 | 仅删 0 字节 WAL |
| 2 进程 race | 极低 | 同时删 SHM | 删完 SQLite 重建,单进程 cron 无风险 |
| :memory: 误清 | 0% | 测试挂 | 提前 return |

---

## 验收标准 (Acceptance Criteria)

```bash
# 1) 全部 unit tests PASS
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/unit -v --tb=short
# 期望: 49/49 PASS (旧 46 + 新 3)

# 2) integration tests PASS (不变)
PYTHONPATH=src:vendor/_vendor .venv/bin/python -m pytest tests/integration -m "" -v --tb=short
# 期望: 9/9 PASS

# 3) 复现反向验证: 模拟 stale SHM,MetaDB 能恢复
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
import os
from pathlib import Path
from tdx_chronos.meta.db import MetaDB
db_path = Path('data/meta/meta.db')
shm = db_path.parent / (db_path.name + '-shm')
shm.touch()
os.chmod(shm, 0o400)
print(f'Pre: SHM mode={oct(shm.stat().st_mode & 0o777)}')
db = MetaDB(str(db_path))
rid = db.record_download('recovered.zip', 'test.tdx', 100, 'abc', 'pending', None)
print(f'PASS · rowid={rid}, recovery successful')
db.close()
"

# 4) dirty data 清理验证
sqlite3 data/meta/meta.db "SELECT COUNT(*) FROM download_log WHERE zip_name='test.zip'"
# 期望: 0
```

---

## 实施模式

**Subagent-driven (Phase 3)**:
1. `sessions_spawn` T9 implementer (HIGH-speed model) · TDD: write test → RED → impl → GREEN → commit
2. Wait for completion announcement
3. `sessions_spawn` T9 spec-reviewer · cross-validate
4. 若有 issue → 修 → 再 review
5. Phase 5 finish

**NO amend** · NEW commit on HEAD `c25fedf`

**commit message**:
`T9 · MetaDB._clean_stale_wal_files() defensive recovery (Sprint 10 stale 400-mode SHM hotfix)`

---

## 关键标识

- repo: `/app/tdx-chronos`
- HEAD: `c25fedf51ba23a160eaf765f7aaf18fcc2220863` (v1.4.0)
- venv: `.venv/bin/python`
- PYTHONPATH: `src:vendor/_vendor`
- target file: `src/tdx_chronos/meta/db.py` (line ~100-150 范围)
- test file: `tests/unit/test_meta_db.py`
- dirty data: `data/meta/meta.db` rowid=74 zip_name='test.zip'
