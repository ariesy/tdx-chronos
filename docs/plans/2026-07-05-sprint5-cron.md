# Sprint 5 Implementation Plan · tdx-chronos cron 接入

**Design**: [2026-07-05-sprint5-cron-design.md](2026-07-05-sprint5-cron-design.md)
**执行模式**: Subagent-Driven (4 任务串行)

---

## T1 · cron/daily_incr.sh + cron/weekly_sync.sh

**目标**: 2 bash 脚本 + dry-run 测试 + 真跑 1 次

### 步骤
1. 写 `cron/daily_incr.sh`:
   - 设置 SNAP_DIR=`/app/tdx-chronos/data/snapshot/$(date +%Y-%m-%d)`
   - 调用 BulkDownloader(download_index + download_all)
   - 调用 OfficialZipParser.run_full_parse (K 线)
   - 调用 TdxGpRecordReader.run_full_parse (股本 · Sprint 4b D1)
   - 调用 IndexParser.parse_all (5 指数 · Sprint 4b D2)
   - 末尾 alertor.send_summary (DRY-RUN 默认)
2. 写 `cron/weekly_sync.sh`:
   - 下载 tdxfin
   - 解析全 258 季度
3. 写 `tests/unit/test_cron_scripts.py`:
   - DRY-RUN 测试 (TDX_DRY_RUN=1)
   - bash 语法检查 (`bash -n`)
4. commit

**Verify**: 
- `bash -n cron/daily_incr.sh` → exit 0
- `TDX_DRY_RUN=1 bash cron/daily_incr.sh` → 输出预期不下载
- `bash tests/unit/test_cron_scripts.py -v` → PASSED

---

## T2 · src/tdx_chronos/doctor.py

**目标**: 健康检查 + 8 测试 + 真 meta.db 跑出 healthy

### 步骤
1. 写 `src/tdx_chronos/doctor.py`:
   - `DoctorReport` dataclass (8 checks + level)
   - `Doctor(meta_db_path, parquet_dir).run()` → DoctorReport
   - 8 项检查: K线symbols / 财务quarter / 股本records / 指数records / download_log_7d / parquet_sizes / 数据新鲜度 / error_rate
2. 写 `tests/unit/test_doctor.py` (8 测试):
   - healthy / degraded (1 failed) / unhealthy (3 failed)
   - DRY-RUN mock
3. 真跑一次: `PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "from tdx_chronos.doctor import Doctor; print(Doctor().run())"`
4. commit

**Verify**:
- 8/8 PASSED · 真 meta.db healthy

---

## T3 · src/tdx_chronos/alertor.py

**目标**: 飞书告警封装 + 5 测试 + dry-run 卡片验证

### 步骤
1. 写 `src/tdx_chronos/alertor.py`:
   - `Alertor(chat_id, dry_run=True).send_card(title, blocks, tone)`
   - 调用 `message` tool (OpenClaw 注入) 或直接 `feishu_perm` (按 SKILL.md 查)
   - 实际实现: 用 `os.environ["TDX_DRY_RUN"]` 控制, dry_run=True 时只 print 卡片 JSON 不真发
2. 写 `tests/unit/test_alertor.py` (5 测试):
   - dry-run 不发, 只 print
   - 卡片格式校验 (title/blocks/tone)
   - 3 种 tone (info/success/warning/danger)
   - 默认 chat_id 验证
3. commit

**Verify**:
- 5/5 PASSED
- dry-run 输出预期 JSON 卡片

---

## T4 · OpenClaw cron 接入 + report

**目标**: 3 cron job 创建 + dry-run 验证 + sprint5-report.md

### 步骤
1. 创建 3 OpenClaw cron job:
   ```bash
   # daily_incr: Mon-Fri 17:30 Asia/Shanghai
   openclaw cron add --name tdx-daily-incr \
     --schedule "30 9 * * 1-5" --tz UTC \
     --session-target isolated \
     --payload "..." \
     --delivery "announce:feishu:oc_812b4a80dbf93832f71b6135ef6cb25a"
   
   # weekly_sync: Sun 02:00 Asia/Shanghai = Sat 18:00 UTC
   openclaw cron add --name tdx-weekly-sync ...
   
   # weekly_doctor: Sun 03:00 Asia/Shanghai = Sat 19:00 UTC
   openclaw cron add --name tdx-weekly-doctor ...
   ```
   **注**: 用 UTC 算术 (TOOLS.md "东八区 17:30 → 30 9 * * 1-5 + 不加 tz")
2. dry-run 验证: `openclaw cron list` 看到 3 job
3. 写 `logs/sprint5-report.md`:
   - 4 commits
   - 27 total commits
   - 144/144 测试
   - cron 接入清单
4. commit + push

**Verify**:
- `openclaw cron list` 包含 tdx-daily-incr / tdx-weekly-sync / tdx-weekly-doctor
- sprint5-report.md 已写
- 远端 27 commits

---

## 完成标志

- [ ] T1 commit
- [ ] T2 commit
- [ ] T3 commit
- [ ] T4 commit + push
- [ ] sprint5-report.md
- [ ] 144/144 测试 PASSED
- [ ] 远端 27 commits

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>