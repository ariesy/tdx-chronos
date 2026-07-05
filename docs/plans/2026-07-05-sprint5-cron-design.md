# Sprint 5 Design · tdx-chronos cron 接入

**项目**: tdx-chronos v1.1 第 9 修订
**作者**: claw-cortex 🦞
**日期**: 2026-07-05 (UTC)
**关联**: §三 IN #5/#5b/#6/#7/#8 · §四.5 · §四.6 · §四.7 · §四.8 · §六 Sprint 5

---

## 🎯 目标

把 Sprint 3a/4a/4b 一次性手动跑的 6 zip 下载 + 解析流程，**转为 3 个 OpenClaw cron 自动化作业**：

| Cron | 频率 | 触发 (Asia/Shanghai) | 任务 |
|---|---|---|---|
| `daily_incr` | 工作日 | 17:30 (周一~五) | 5 zip 增量 (hsjday + shzsday + szzsday + tdxzs_day + tdxgp) · ~750 MB |
| `weekly_sync` | 周日 | 02:00 | tdxfin (~537 MB) |
| `weekly_doctor` | 周日 | 03:00 | doctor.py 健康检查 + 飞书告警 |

**告警群**: `oc_812b4a80dbf93832f71b6135ef6cb25a` (已存在 · auto-commit 同群)

---

## 📐 设计

### 1. cron 脚本 (`cron/daily_incr.sh` + `cron/weekly_sync.sh`)

**设计原则**:
- 调用 Sprint 3a 已实现的 `BulkDownloader` + Sprint 4a `OfficialZipParser.run_full_parse` + Sprint 4b `IndexParser`
- DRY-RUN 默认关闭 (`TDX_DRY_RUN=1` 环境变量开启)
- 失败重试 3 次 (Sprint 3a `BulkDownloader.max_retries=3`)
- 失败告警到飞书 (`alertor.send_alert`)
- 退出码: 0=全成功, 1=部分失败, 2=全失败

**daily_incr.sh 工作流**:
```bash
1. SET SNAP_DIR=/app/tdx-chronos/data/snapshot/$(date +%Y-%m-%d)
2. BulkDownloader().download_all(zips=DEFAULT_ZIPS + DEFAULT_INDEX_ZIPS,
                                   snap_dir=$SNAP_DIR, unzip=True)
   (注: 默认 3 核心 zip + 3 指数 zip 一起下, 总 ~880 MB, 耗时 ~10-15 min)
3. 解析:
   - K 线  → parquet_compact (Sprint 4a D3 merge zstd)
   - 股本  → gp/records.parquet (Sprint 4b D1 流式)
   - 指数  → index/indices.parquet (Sprint 4b D2)
   - 财务  → 不下 (周日 5b 周日跑)
4. alertor.send_summary(report)  → 飞书群
```

**weekly_sync.sh 工作流**:
```bash
1. BulkDownloader().download_all(zips=[tdxfin])  (~10 min)
2. 解析: tdxfin.py 历史季报 (258 季度)
3. alertor.send_summary
```

### 2. `src/tdx_chronos/doctor.py` 健康检查

**输入**: meta.db + Parquet 目录
**输出**: `DoctorReport` dataclass
**检查项**:
| # | 检查 | 阈值 |
|---|---|---|
| 1 | K 线 symbol count | == 12,256 (±10) |
| 2 | 财务季度 count | >= 100 (近 5 年) |
| 3 | 股本 record_count | >= 100M records |
| 4 | 5 指数 record_count | == 28,004 (±10) |
| 5 | download_log 7 天内 success_rate | >= 95% |
| 6 | Parquet 文件大小 | 各项 >= 100 MB (K 线) / >= 1 MB (指数) |
| 7 | 数据新鲜度 (last_date vs today) | K 线 <= 2 天, 指数 <= 2 天 |
| 8 | error_rate (parse_status='partial'/'failed') | <= 5% |

**健康级别**:
- `healthy`: 8 项全过
- `degraded`: 1-2 项失败
- `unhealthy`: 3+ 项失败 → 自动触发飞书告警

### 3. `src/tdx_chronos/alertor.py` 飞书告警

**实现**: 调用 `feishu_app_scopes` (OpenClaw 内置)
**API**:
- `Alertor(chat_id="oc_812b4a80dbf93832f71b6135ef6cb25a").send_card(title, blocks, tone)`
- 卡片格式 (text + buttons)
- 干跑模式 (`TDX_DRY_RUN=1` 不真发)

**触发场景**:
- `cron/daily_incr.sh` 失败 → `alertor.send_alert(level="error", ...)`
- `cron/weekly_doctor.sh` unhealthy → `alertor.send_alert(level="critical", ...)`
- `cron/weekly_sync.sh` 失败 → `alertor.send_alert(level="error", ...)`

### 4. OpenClaw cron 接入

**3 个 cron job** (创建后验证跑通 dry-run):
```
job-daily-incr    : Mon-Fri 17:30 Asia/Shanghai
job-weekly-sync   : Sun 02:00 Asia/Shanghai
job-weekly-doctor : Sun 03:00 Asia/Shanghai
```

**sessionTarget=isolated, payload.kind=agentTurn**
**delivery**: announce → feishu:oc_812b4a80dbf93832f71b6135ef6cb25a

---

## 🧪 测试矩阵

| 测试 | 验证内容 |
|---|---|
| `test_daily_incr_dry_run` | DRY-RUN 模式不下载 + 输出预期量 |
| `test_daily_incr_full_run_mock` | mock 5 zip → 跑完解析流程 + 检查 Parquet |
| `test_weekly_sync_dry_run` | DRY-RUN tdxfin |
| `test_doctor_healthy` | mock 完整 meta.db → healthy |
| `test_doctor_degraded` | mock 缺失 1 项 → degraded |
| `test_doctor_unhealthy` | mock 缺失 3+ → unhealthy |
| `test_alertor_dry_run` | DRY-RUN 卡片生成但不发送 |
| `test_alertor_card_format` | 卡片字段必填校验 |

---

## 🦞 4 任务清单

| Task | 估算 | 文件 |
|---|---|---|
| **T1**: cron/daily_incr.sh + cron/weekly_sync.sh | 1 h | 2 bash |
| **T2**: src/tdx_chronos/doctor.py + 8 测试 | 2 h | 1 py + 1 tests |
| **T3**: src/tdx_chronos/alertor.py + 5 测试 | 1.5 h | 1 py + 1 tests |
| **T4**: OpenClaw cron 接入 (3 job) + dry-run 验证 + report | 1 h | 3 cron + 1 log |

**总计 ~5.5 h** (与 Sprint 4b 相当)

---

## ⚠️ 风险与缓解

| 风险 | 缓解 |
|---|---|
| Sprint 5 触发时 vm002 网络限速 | 已有包级重试 3 次 (§四.7) |
| Parquet 写失败 (OOM/磁盘满) | 流式 ParquetWriter (Sprint 4b D1) + 磁盘监控 (doctor 检查) |
| 飞书告警炸群 (false positive) | DRY-RUN 默认 + doctor 健康级别分层 |
| cron 时区错乱 | 显式 `--tz Asia/Shanghai` + 东八区时间戳 |

---

## 🎯 验收标准

- [ ] T1: 2 bash 脚本 + dry-run + 真跑 1 次 (download_all 跑通)
- [ ] T2: doctor.py + 8 测试 PASSED + 真 meta.db 跑出 healthy report
- [ ] T3: alertor.py + 5 测试 PASSED + dry-run 卡片格式正确
- [ ] T4: 3 OpenClaw cron job 创建 + 1 次 dry-run 验证 + sprint5-report.md
- [ ] 全套测试 131 + 13 = **144/144 PASSED**
- [ ] 远端 23 + 4 = **27 commits**

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>