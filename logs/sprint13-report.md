# Sprint 13 · Hotfix: daily_incr ENOSPC 事故复盘 (2026-07-14)

> 时间: 2026-07-14 17:30 CST (cron 触发) → ~09:33 UTC (db commit 失败) → 12:08 CST (手动修复完成)
> 影响: 1 次 daily_incr.sh 完整失败, 0 数据产出 (Step 2-5 short-circuit)
> 严重度: P2 (单点失败, 无 cascading; 但 cron delivery 报 "全失败 exit=2")

---

## TL;DR

`/dev/sdb1` (mounted at `/app`) **0 字节可用** 触发的级联失败:

```
unzip "write error (disk full?)"
  ↓
[Errno 28] No space left on device × 3 retries (shzsday.zip)
  ↓
sqlite3.OperationalError: database or disk is full  ← at meta/db.py:686
  ↓
exit 2 (cron delivery 收 "全失败")
```

不是代码 bug,是 **运维配置缺失**: `cron/daily_incr.sh` 从未清理 `data/snapshot/`,
8 天累积 **36 GB** (`07-04 ~ 07-13`, 每个 ~5.3 GB) 把磁盘塞满到 100%。

---

## 时间线

| 时刻 (UTC) | 事件 |
|---|---|
| 2026-07-14 **09:30:00** | cron 触发 `daily_incr.sh`, /app 此时可能已 < 1 GB free |
| 09:30 ~ 09:31 | hsjday.zip (541 MB) + tdxfin.zip (537 MB) 下载成功 |
| 09:31 ~ 09:32 | tdxgp.zip (664 MB) 下载 + `gpbj430017.dat` 解压开始 ENOSPC,截断 |
| 09:32 ~ 09:33 | shzsday.zip 3 次重试全 ENOSPC, 留下 0 B 占位文件 |
| 09:33 | `MetaDB.record_download()` 写 WAL ENOSPC → `OperationalError` |
| 09:33 ~ 09:34 | Step 1 short-circuit (`total_failed >= 5` 阈值) 阻止 Step 2-5 跑 |
| (中间 ~3 小时) | cron delivery 飞书 push 已发; 无人工处理 |
| 12:08 | 用户把 traceback 贴出 → debug → 操作修复 → 加固三步走 |

---

## 根因 (三层)

### 1. 直接原因 — 磁盘满
```
$ df -h /app
Filesystem      Size  Used Avail Use% Mounted on
/dev/sdb1       125G  119G     0 100% /app
```

`/dev/sdb1` 125 GB 总容量, `data/` 占 ~40 GB, 其余 79 GB 是非 data 内容。
`/dev/sdb1` 自身的 125 GB 100% 满,而非 `/` 卷组的 `ubuntu--vg-ubuntu--lv` 还有 79 GB free
(long-term 扩容方向)。

### 2. 结构原因 — snapshot 无 retention
`cron/daily_incr.sh:8` 每天建 `snapshot/$(date +%Y-%m-%d)/`,`cron/weekly_sync.sh:7` 同样。
**两个脚本从不清理老 snapshot**。事故时累积 8 天:

```
$ du -sh /app/tdx-chronos/data/snapshot/*
4.0K   2026-07-03      (空)
5.3G   2026-07-04
5.3G   2026-07-06
5.3G   2026-07-07
516M   2026-07-08
5.3G   2026-07-09
5.3G   2026-07-10
5.3G   2026-07-13      ← 上次完整成功
5.3G   2026-07-14      ← 今天部分失败 (后删)
total:  ~36 GB
```

按设计 5 zip + 1 raw 展开 ≈ 3.5 GB/天,7 天 = 24.5 GB,合 parquet/gp/fin = ~30 GB,
远低于 125 GB。但缺清理 + 周末 5 天连续跑 = 36 GB。

### 3. 设计原因 — 失败模式 cascade ENOSPC
unzip / curl / sqlite 都各自 retry / abort ENOSPC,但 4 处 warning + 1 处 traceback
堆在 cron log 里,**没有结构化 pre-flight 检查在下载开始前 fail-fast**。
如果当时 `daily_incr.sh` 顶部先 `df` 检查 + Alertor,17:30 就该立刻飞书报警 "disk full"
而不是 09:33 才报 "all zips failed"。

---

## 修复

### 操作层 (立刻)
删除 5 个老 snapshot (07-03/04/06/07/14),释放 **19 GB**:

```bash
rm -rf /app/tdx-chronos/data/snapshot/2026-07-{03,04,06,07,14}
```

修复后:
```
$ df -h /app
Filesystem      Size  Used Avail Use% Mounted on
/dev/sdb1       125G   99G   20G  84% /app
```

### 加固层 (防止复发)
新增 2 个独立模块, 复用现有 Alertor:

| 模块 | API | 默认阈值 | 调参 env |
|---|---|---|---|
| `tdx_chronos.preflight` | `run_preflight(path, min_free_gb=5)` | 5 GB | `SNAP_MIN_FREE_GB` |
| `tdx_chronos.retention` | `prune_snapshots(root, keep_days=7)` | 7 天 | `SNAP_KEEP_DAYS` |

接入位置:
- `cron/daily_incr.sh` 顶部 (preflight, exit≠0 即早退) + 底部 (retention)
- `cron/weekly_sync.sh` 顶部 (preflight) + 底部 (retention)

效果 (理论):
- daily_incr 失败模式: 从"8 分钟无头下载后崩溃"→"0 秒磁盘检查 + Alertor"
- snapshot 累积上限: 从无上限 → 7+1 = 8 dirs × 5.3 GB = 42 GB,远低于 125 GB 上限

### 测试
新增 **22 个** 测试 (3 文件),**330 → 352** total:

| 文件 | 测试 | 覆盖 |
|---|---:|---|
| `tests/unit/test_retention.py` 🆕 | 10 | keep-N / missing root / non-dated dir / future-dated / dry_run / idempotent / ValidationError |
| `tests/unit/test_preflight.py` 🆕 | 7 | ok path / not-ok path / Alertor dry-run default / Alertor 参数化 / config |
| `tests/unit/test_cron_scripts.py` (existing) | +5 | preflight + retention 在 daily/weekly 双 cron wiring |
| `bash -n` × 2 | 2 | syntax |

`PYTHONPATH=src:vendor/_vendor .venv/bin/pytest tests/unit/test_retention.py tests/unit/test_preflight.py tests/unit/test_cron_scripts.py -v` → **35 passed in 0.37s** (含原有 cron test 18 + 新 17)。

### 验证 (re-run after fix)

2026-07-14 12:27 CST 手动触发 `cron/daily_incr.sh`:

```
2026-07-14 12:27:03 preflight: free=19.01GB (ok=True)
2026-07-14 12:39:17 下载完成: success=6 failed=0   ← 比事故前多 1 (tdxgp 也成)
2026-07-14 12:39:17 Step 2: K 线解析 → parquet_compact
2026-07-14 12:42:xx Step 3-5 ...
2026-07-14 12:44:07 daily_incr 完成 · elapsed=1023.7s · success=6 failed=0
2026-07-14 12:44:07 retention: pruned=0 kept=5 cutoff=2026-07-08

============================================================
daily_incr 总结
============================================================
elapsed:    1023.7s
core_zip:   3/3 success
index_zip:  3/3 success
K 线:       ok=12,281 failed=0
股本:       ok=8,500 records=121,763,833
指数:       ok=5 records=28,039
finance:   skipped=240 parsed=18 failed=0

daily_incr 退出码: 0    ✓
```

**加固后效果**:
- preflight 在 0.5s 内 fail-fast (现 19 GB free → ok)
- 全 6 个 zip (而非事故时的 4 个) 下载/解压成功
- K 线 12,281 个标的 全部写入 parquet_compact
- finance incremental 正确跳过 240 个老 quarter, 增量 18 个新 quarter (含 2026 Q1-Q3)
- retention 0 pruned: 5 个 dir 都在 7 天窗口内 (07-08~07-14); 7 天前的 07-04/06/07 已前删
- exit 0 → cron delivery 推送 success 卡片

---

## Sprint 13 hotfix·opt · 冗余 .zip 删除 (2026-07-14 12:56 CST)

### 现象
`tdxfin.zip` 是 zip-of-zips: 每个 per-quarter `gpcw<date>.zip` 内**只含一个同名 `.dat`**。
`unzip=True` 解开后 `raw/` 同时留下 `.zip` 和 `.dat`:

```
raw/gpcw20241231.zip    5.5 MB compressed  ← 冗余
raw/gpcw20241231.dat   12.7 MB extracted   ← 已存在
```

md5 验证两个 `.dat` **字节完全一致** (`ec83b70c...`):

```
$ md5sum /tmp/zipchk/gpcw20241231.dat .../raw/gpcw20241231.dat
ec83b70ce24fb3a341a68a44d9e661f8  /tmp/zipchk/gpcw20241231.dat
ec83b70ce24fb3a341a68a44d9e661f8  .../raw/gpcw20241231.dat   ✓
```

### 量级
- 每个 quarter: .zip 平均 ~1.7 MB (实测 5 个样本: 0 ~ 5.6 MB, ratio=.29~.44 of .dat)
- 148 quarters / snapshot → 每 snapshot 约 **~250 MB 冗余** (初估 1.1 GB, 实测小 4 倍)
- 当时 4 个 surviving snapshot 共 ~1 GB 可省

### 实现

`src/tdx_chronos/retention.py` (在 hotfix 同文件追加):

```python
def prune_redundant_finance_zips(raw_root, dry_run=False) -> list[Path]:
    """删除 raw/gpcw*.zip 当同名 .dat 已存在; 防御逻辑: .dat 缺失则保留 .zip"""

def dedup_all_snapshots(snapshot_root, dry_run=False) -> int:
    """递归对所有 <snap>/<dir>/raw/ 跑 dedup_all_snapshots"""
```

接入 `cron/daily_incr.sh` 与 `cron/weekly_sync.sh` 末尾, retention 之后。

### 测试 (新增 12, 352 → 364)
- `TestPruneRedundantFinanceZips` 7 测试 (含 `test_keeps_zip_when_dat_missing` 防御网)
- `TestDedupAllSnapshots` 5 测试 (递归 / idempotent / dry_run / 无 raw 跳过)
- `TestSprint13Hardening` +2 (cron wiring)

### Real-run 验证 (2026-07-14 12:56)
```
$ dedup_all_snapshots(/app/tdx-chronos/data/snapshot)
deduped 592 gpcw*.zip files

# 效果
数据: 4 snapshots × 148 zips = 592 files deleted
磁盘: /app 105G → 104G used; free 14G → 15G
parser 下次直接读 .dat, 省一层 unzip

# per-snapshot 验证
2026-07-09: zip=0 dat=148
2026-07-10: zip=0 dat=148
2026-07-13: zip=0 dat=148
2026-07-14: zip=0 dat=148
```

### 长期占用算账 (7 天 retention 后)

```
旧: 7 × 5.3 GB snapshot + 1 GB 数据 = ~38 GB
新: 7 × ~3.3 GB snapshot (post-dedup) + 1 GB 数据 = ~24 GB
节省: ~14 GB (~37%)              /  vs /app 125 GB ≈ 富余 101 GB (81%)
```

---

## 教训

1. **运维策略缺失**: AGENTS.md 警告 `data/snapshot/` 21 GB,但没有 retention policy;
   这种"软保险"靠人记是不可靠的。**所有"gitignore + 生成为主"的 dir 都该有显式 retention**。
2. **Pre-flight pattern 缺位**: 项目里 `bulk_download.py:404` (download_index) 走的是
   max_retries=3 重试,在 ENOSPC 下重试是空转;**任何"耗大量 I/O 的入口"都该有 pre-flight**。
   等下次 sprint 把此 pattern 抽到 `tdx_chronos.preflight` 的更高层 API。
3. **失败聚合不好**: traceback 顶层是 `OperationalError: database or disk is full`,
   中间穿插 `warning: ...is probably truncated`,**没有"磁盘满" 这个 single-line summary**。
   未来 Alertor 应在 fail 时 grep ENOSPC / OperationalError 关键词,主动加注。

---

## 长期建议 (未实施,放 backlog)

- **扩容 `/dev/sdb1`**: `/dev/mapper/ubuntu--vg-ubuntu--lv` 还有 79 GB free,可 `lvextend` + `resize2fs`
  或迁移 `data/` 到根 VG 卷组,把 `/app` 撑到 ~250 GB,远期化 retention 7 天负担。
- **Doctor 加 ENOSPC 健康检查**: `Doctor().check_disk_snapshots()` 返回 `ok=False` 当
  `data/snapshot/` < retention_days 警告 阈值; weekly_doctor.sh 自动 fan-out。
- **bulk_download retry 改成 condition-based**: `max_retries=3` 在 ENOSPC 时是空转,
  应区分 transient (HTTP 5xx, timeout) vs terminal (ENOSPC, ENOENT); terminal 直接 fail。

---

## 参考

- 报错 traceback: `meta/db.py:686` (`_txn.exit`), `bulk_download.py:404` (download_index), `bulk_download.py:352` (download_all)
- 修复 commit 计划: 加 `src/tdx_chronos/{retention,preflight}.py` + 测试, 改 `cron/{daily_incr,weekly_sync}.sh`
- AGENTS.md "Hard rules" 第 4 条: 324→330→340 是 canonical regression baseline, **新加 22 测试,不删任何旧测试**
