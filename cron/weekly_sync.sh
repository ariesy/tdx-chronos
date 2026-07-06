#!/bin/bash
# Sprint 5 T1 · weekly_sync.sh · 周日 02:00 cron
# 下载 + 解析 tdxfin (~537 MB · ~10 min)
set -euo pipefail

TDX_ROOT="/app/tdx-chronos"
SNAP_DIR="$TDX_ROOT/data/snapshot/$(TZ=Asia/Shanghai date +%Y-%m-%d)"
DB_PATH="$TDX_ROOT/data/meta/meta.db"
LOG_DIR="$TDX_ROOT/logs/cron"
LOG_FILE="$LOG_DIR/weekly_sync_$(TZ=Asia/Shanghai date +%Y%m%d_%H%M%S).log"

mkdir -p "$(dirname "$DB_PATH")" "$SNAP_DIR" "$LOG_DIR"

echo "============================================================" | tee -a "$LOG_FILE"
echo "Sprint 5 weekly_sync 启动" | tee -a "$LOG_FILE"
echo "Time:  $(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S %Z')" | tee -a "$LOG_FILE"
echo "Snap:  $SNAP_DIR" | tee -a "$LOG_FILE"
echo "Log:   $LOG_FILE" | tee -a "$LOG_FILE"
echo "============================================================" | tee -a "$LOG_FILE"

cd "$TDX_ROOT"
export PYTHONPATH=src:vendor/_vendor

.venv/bin/python << PYEOF | tee -a "$LOG_FILE"
import logging
import sys
import time
from pathlib import Path

from tdx_chronos.sources.bulk_download import BulkDownloader

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger("weekly_sync")

start = time.monotonic()

# Step 1: 下载 tdxfin
log.info("Step 1: 下载 tdxfin (~537 MB · ~10 min)")
dl = BulkDownloader()
snap = Path("$SNAP_DIR")

# 单 zip 下载
result = dl.download_one(
    spec={"name": "tdxfin", "url": "https://data.tdx.com.cn/vipdoc/tdxfin.zip",
          "approx_size": 537_000_000},
    snap_dir=snap,
    max_retries=3,
)

log.info(f"下载: status={result.status} size={result.size_bytes:,} retries={result.retry_count}")

if result.status != "success":
    log.error(f"tdxfin 下载失败: {result.error}")
    sys.exit(2)

# Step 2: 解压 (unzip -d $snap/raw tdxfin.zip)
log.info("Step 2: 解压 tdxfin → $snap/raw")
import zipfile
zip_path = snap / "tdxfin.zip"
with zipfile.ZipFile(zip_path) as zf:
    zf.extractall(snap / "raw")

# Step 3: 全 258 季度解析 (Sprint 4a D1)
log.info("Step 3: 财务全量解析 (258 季度)")
from tdx_chronos.fin.tdxfin import TdxFinReader

raw_dir = snap / "raw"
parsed_dir = Path("$TDX_ROOT/data/fin/parsed")
parsed_dir.mkdir(parents=True, exist_ok=True)

quarter_count = 0
db_recorded = 0
for dat in sorted(raw_dir.glob("gpcw*.dat")) + sorted(raw_dir.glob("gpcw*.zip")):
    try:
        reader = TdxFinReader()
        result_df = reader.read(dat)
        if result_df is not None:
            out = parsed_dir / f"{dat.stem}.parquet"
            result_df.to_parquet(out, compression="zstd", compression_level=3)
            quarter_count += 1

            # Sprint 8 T1 · record quarter_metadata
            from tdx_chronos.meta.db import MetaDB
            try:
                # 从文件名提取 report_date (gpcwYYYYMMDD)
                stem = dat.stem  # e.g. 'gpcw20260331'
                date_str = stem.replace("gpcw", "").replace("gpcw", "")
                if len(date_str) == 8 and date_str.isdigit():
                    report_date = int(date_str)
                    file_size = dat.stat().st_size if dat.exists() else 0
                    stock_count = len(result_df)
                    is_placeholder = file_size <= 164
                    # 只记录有效 quarters (有数据 且 日期合法)
                    if stock_count > 0 and report_date > 0:
                        db = MetaDB("$DB_PATH")
                        db.record_quarter_metadata(
                            report_date=report_date,
                            file_path=str(dat),
                            file_size=file_size,
                            stock_count=stock_count,
                            parquet_path=str(out),
                            is_placeholder=is_placeholder,
                            parse_ok=True,
                        )
                        db.close()
                        db_recorded += 1
                    else:
                        log.debug(f"  skip quarter_metadata {dat.name}: "
                                  f"stock_count={stock_count} report_date={report_date}")
            except Exception as db_err:
                log.warning(f"  quarter_metadata skip {dat.name}: {db_err}")
    except Exception as e:
        log.warning(f"  skip {dat.name}: {e}")

elapsed = time.monotonic() - start
log.info(f"weekly_sync 完成 · quarters={quarter_count} db_recorded={db_recorded} elapsed={elapsed:.1f}s")

print()
print("=" * 60)
print("weekly_sync 总结")
print("=" * 60)
print(f"elapsed:        {elapsed:.1f}s")
print(f"quarters:       {quarter_count}")
print(f"db_recorded:    {db_recorded}")
print(f"tdxfin:         {result.size_bytes / 1024 / 1024:.1f} MB · sha256={result.sha256[:16]}")

sys.exit(0)
PYEOF

EXIT_CODE=$?
echo ""
echo "weekly_sync 退出码: $EXIT_CODE"
exit $EXIT_CODE