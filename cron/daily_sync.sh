#!/bin/bash
# Sprint 3a · 5 zip 全量下载验收
# 一次跑 · Sprint 5 cron 化后会改为每日增量
set -euo pipefail

SNAP_DIR="/app/tdx-chronos/data/snapshot/2026-07-04"
DB_PATH="/app/tdx-chronos/data/meta/meta.db"

mkdir -p "$(dirname "$DB_PATH")" "$SNAP_DIR"

echo "============================================================"
echo "Sprint 3a 真下载验收 · 开始"
echo "Time:     $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "Snap dir: $SNAP_DIR"
echo "DB path:  $DB_PATH"
echo "============================================================"

cd /app/tdx-chronos

PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
import logging
from pathlib import Path
from datetime import datetime, timezone
from tdx_chronos.sources.bulk_download import BulkDownloader

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

dl = BulkDownloader()
summary = dl.download_all(
    snap_dir=Path('$SNAP_DIR'),
    db_path=Path('$DB_PATH'),
    unzip=True,
    max_retries=3,
)

print()
print('=' * 60)
print('5 zip 真下载验收结果')
print('=' * 60)
print(f'start_at:       {summary.start_at}')
print(f'end_at:         {summary.end_at}')
print(f'total_seconds:  {summary.total_seconds:.1f}')
print(f'total_size:     {summary.total_size:,} bytes ({summary.total_size / 1024 / 1024:.1f} MB)')
print(f'success_count:  {summary.success_count}')
print(f'failed_count:   {summary.failed_count}')
print()
print('Per-zip:')
for r in summary.results:
    status = 'OK' if r.status == 'success' else 'FAIL'
    print(f'  {status}  {r.zip_name:8s}  size={r.size_bytes:>12,}  '
          f'sha256={r.sha256[:16]}…  retries={r.retry_count}  '
          f'duration={r.duration_seconds:.1f}s')
print()
print('=' * 60)
print('run_full_parse 跑 (Sprint 2 验证复用)')
print('=' * 60)

from tdx_chronos.sources.official_zip import run_full_parse
fs = run_full_parse(
    '/app/tdx-chronos/data/snapshot/2026-07-04/raw',
    '/app/tdx-chronos/data/parquet',
    '/app/tdx-chronos/data/meta/meta.db',
    show_progress=True,
)
print(f'  total_files:    {fs.total_files}')
print(f'  parsed_ok:      {fs.parsed_ok}')
print(f'  parsed_failed:  {fs.parsed_failed}')
print(f'  elapsed:        {fs.elapsed_seconds:.1f}s')
print(f'  bytes_read:     {fs.bytes_read:,}')
print(f'  parquet_bytes:  {fs.parquet_bytes:,}')
print(f'  compression:    {fs.parquet_bytes / fs.bytes_read * 100:.1f}%')
"