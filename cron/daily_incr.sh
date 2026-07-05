#!/bin/bash
# Sprint 5 T1 · daily_incr.sh · 17:30 工作日 cron
# 5 zip 增量: hsjday + shzsday + szzsday + tdxzs_day + tdxgp
# 耗时 ~10-15 min · ~880 MB
set -euo pipefail

TDX_ROOT="/app/tdx-chronos"
SNAP_DIR="$TDX_ROOT/data/snapshot/$(TZ=Asia/Shanghai date +%Y-%m-%d)"
DB_PATH="$TDX_ROOT/data/meta/meta.db"
LOG_DIR="$TDX_ROOT/logs/cron"
LOG_FILE="$LOG_DIR/daily_incr_$(TZ=Asia/Shanghai date +%Y%m%d_%H%M%S).log"

mkdir -p "$(dirname "$DB_PATH")" "$SNAP_DIR" "$LOG_DIR"

echo "============================================================" | tee -a "$LOG_FILE"
echo "Sprint 5 daily_incr 启动" | tee -a "$LOG_FILE"
echo "Time:  $(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S %Z')" | tee -a "$LOG_FILE"
echo "Snap:  $SNAP_DIR" | tee -a "$LOG_FILE"
echo "DB:    $DB_PATH" | tee -a "$LOG_FILE"
echo "Log:   $LOG_FILE" | tee -a "$LOG_FILE"
echo "============================================================" | tee -a "$LOG_FILE"

cd "$TDX_ROOT"
export PYTHONPATH=src:vendor/_vendor

# 1. 下载 5 zip (3 核心 + 2 指数)
# 注: tdxzs_day + shzsday + szzsday 都含 5 主要指数, 只需下载 3 zip
.venv/bin/python << PYEOF | tee -a "$LOG_FILE"
import logging
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

from tdx_chronos.sources.bulk_download import BulkDownloader
from tdx_chronos.sources.index_parser import IndexParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger("daily_incr")

start = time.monotonic()
report = []

# Step 1: 5 zip 下载
log.info("Step 1: 下载 5 zip (hsjday + tdxgp + shzsday + szzsday + tdxzs_day)")
dl = BulkDownloader()
snap = Path("$SNAP_DIR")

# 3 核心 zip (data.tdx.com.cn)
core_summary = dl.download_all(snap_dir=snap, unzip=True, db_path=Path("$DB_PATH"))
report.append(("core_zip", core_summary.success_count, core_summary.failed_count))

# 3 指数 zip (www.tdx.com.cn · ~0.27 MB/s)
idx_summary = dl.download_index(snap_dir=snap, unzip=True, db_path=Path("$DB_PATH"))
report.append(("index_zip", idx_summary.success_count, idx_summary.failed_count))

total_success = core_summary.success_count + idx_summary.success_count
total_failed = core_summary.failed_count + idx_summary.failed_count
log.info(f"下载完成: success={total_success} failed={total_failed}")

# Step 2: 解析 K 线 (Sprint 2 + 4a D3)
if total_failed < 5:  # 至少 1 核心 zip 成功
    log.info("Step 2: K 线解析 → parquet_compact")
    from tdx_chronos.sources.official_zip import run_full_parse
    fs = run_full_parse(
        f"{snap}/raw",
        f"{TDX_ROOT}/data/parquet_compact",
        "$DB_PATH",
        show_progress=False,
    )
    log.info(f"K 线: total={fs.total_files} ok={fs.parsed_ok} failed={fs.parsed_failed}")

# Step 3: 股本全 records (Sprint 4b D1)
log.info("Step 3: 股本 → records.parquet")
from tdx_chronos.fin.tdxgp_record import TdxGpRecordReader
gp_summary = TdxGpRecordReader.run_full_parse(
    raw_dir=snap / "raw",
    output_path=Path(f"{TDX_ROOT}/data/gp/records.parquet"),
    db_path=None,
)
log.info(f"股本: ok={gp_summary.parsed_ok} records={gp_summary.total_records:,}")

# Step 4: 5 指数 (Sprint 4b D2)
log.info("Step 4: 5 指数 → indices.parquet")
idx_p = IndexParser.parse_all(
    raw_dir=snap / "raw",
    output_path=Path(f"{TDX_ROOT}/data/index/indices.parquet"),
)
log.info(f"指数: ok={idx_p.parsed_ok} records={idx_p.total_records:,}")

elapsed = time.monotonic() - start
log.info(f"daily_incr 完成 · elapsed={elapsed:.1f}s · success={total_success} failed={total_failed}")

# 输出总结 (给 cron delivery 抓)
print()
print("=" * 60)
print("daily_incr 总结")
print("=" * 60)
print(f"elapsed:    {elapsed:.1f}s")
print(f"core_zip:   {core_summary.success_count}/{core_summary.success_count + core_summary.failed_count} success")
print(f"index_zip:  {idx_summary.success_count}/{idx_summary.success_count + idx_summary.failed_count} success")
print(f"K 线:       ok={fs.parsed_ok:,} failed={fs.parsed_failed}")
print(f"股本:       ok={gp_summary.parsed_ok:,} records={gp_summary.total_records:,}")
print(f"指数:       ok={idx_p.parsed_ok} records={idx_p.total_records:,}")

# Exit code: 0=全成功, 1=部分失败, 2=全失败
total = total_success + total_failed
if total_failed == 0:
    sys.exit(0)
elif total_success == 0:
    sys.exit(2)
else:
    sys.exit(1)
PYEOF

EXIT_CODE=$?
echo ""
echo "daily_incr 退出码: $EXIT_CODE"
exit $EXIT_CODE