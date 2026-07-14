"""Sprint 13 + 14 · cron pre-flight checks.

A full disk produces cascading ENOSPC + sqlite "database or disk is full"
errors deep in the stack (incident: 2026-07-14 daily_incr crash
at `bulk_download.py:352` and `meta/db.py:686`). This module surfaces the
problem *before* download starts so cron delivery can alert on schedule
rather than fail 8 minutes in with a partial snapshot.

Public API (Sprint 14 扩):
- check_disk_free(path, min_free_gb=5.0) -> DiskReport
- check_zip_integrity(snapshot_dir, *, today_only=True) -> list[tuple[name, ok, error]]
- check_data_writable(data_dir) -> dict[str, tuple[bool, str]]
- run_preflight(path, min_free_gb=5.0, alertor=None, source=...) -> int
- run_extended_preflight(data_dir, ..., alertor=None, source=...) -> int
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tdx_chronos.alertor import Alertor
from tdx_chronos.retention import SOURCE_ZIP_NAMES

logger = logging.getLogger(__name__)

# Sprint 14 · subdirs that cron needs write access to (daily_incr)
WRITABLE_REQUIRED_SUBDIRS = ("meta", "snapshot")


@dataclass
class DiskReport:
    path: Path
    total_gb: float
    used_gb: float
    free_gb: float
    min_free_gb: float
    ok: bool

    @property
    def short(self) -> str:
        return (
            f"{self.path}: free={self.free_gb:.2f}GB "
            f"used={self.used_gb:.2f}GB total={self.total_gb:.2f}GB "
            f"(min={self.min_free_gb:.1f}GB · ok={self.ok})"
        )


def check_disk_free(path, min_free_gb: float = 5.0) -> DiskReport:
    """Return a ``DiskReport`` for the filesystem containing ``path``.

    Args:
        path:        any path on the filesystem to inspect.
        min_free_gb: threshold below which the report is not-ok.
    """
    p = Path(path)
    usage = shutil.disk_usage(p)
    return DiskReport(
        path=p,
        total_gb=round(usage.total / 1024 ** 3, 2),
        used_gb=round(usage.used / 1024 ** 3, 2),
        free_gb=round(usage.free / 1024 ** 3, 2),
        min_free_gb=min_free_gb,
        ok=usage.free >= min_free_gb * 1024 ** 3,
    )


def check_zip_integrity(
    snapshot_dir,
    *,
    today_only: bool = True,
    today: Optional[date] = None,
) -> List[Tuple[str, bool, Optional[str]]]:
    """检查昨日/今日 snapshot dir 内的源 zip 完整性.

    For each of the 6 SOURCE_ZIP_NAMES under ``snapshot_dir/``:
      * missing → 跳过 (zip 已被 retention 删掉, 无问题)
      * exists but empty / corrupted → ``(name, False, error_msg)``
      * exists and valid → ``(name, True, None)``

    Args:
        snapshot_dir: e.g. ``data/snapshot/2026-07-14``
        today_only:   if True, only check this dir; if False, walk all dated subdirs
        today:        override ``date.today()`` for tests
    """
    snap = Path(snapshot_dir)
    results: List[Tuple[str, bool, Optional[str]]] = []

    def _check_one(zip_path: Path) -> Optional[Tuple[str, bool, Optional[str]]]:
        if not zip_path.exists():
            return None  # missing, not a problem
        if zip_path.stat().st_size == 0:
            return (zip_path.name, False, "0 字节文件")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                # testzip() returns the first bad file (CRC mismatch) or None
                bad = zf.testzip()
                if bad:
                    return (zip_path.name, False, f"CRC 错: {bad}")
        except zipfile.BadZipFile as e:
            return (zip_path.name, False, f"不是有效 zip: {e}")
        return (zip_path.name, True, None)

    if today_only:
        if not snap.is_dir():
            return results
        for name in SOURCE_ZIP_NAMES:
            r = _check_one(snap / name)
            if r is not None:
                results.append(r)
    else:
        if not snap.exists():
            return results
        for dated in sorted(snap.iterdir()):
            if not dated.is_dir() or not _is_dated(dated.name):
                continue
            for name in SOURCE_ZIP_NAMES:
                r = _check_one(dated / name)
                if r is not None:
                    results.append(r)

    return results


def _is_dated(name: str) -> bool:
    """Quick check for YYYY-MM-DD dir name (no regex import needed in hot path)."""
    try:
        datetime.strptime(name, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def check_data_writable(data_dir) -> Dict[str, Tuple[bool, str]]:
    """检查 data_dir/{meta, snapshot} 等 subdir 是否可写 (cron 写入需要).

    Writes a tiny tempfile (0 bytes, immediate delete) to each. Returns dict:
      ``{"meta": (True, "ok"), "snapshot": (False, "PermissionError: ..."), ...}``
    """
    out: Dict[str, Tuple[bool, str]] = {}
    root = Path(data_dir)
    for sub in WRITABLE_REQUIRED_SUBDIRS:
        target = root / sub
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(prefix=".preflight_", dir=str(target), delete=True):
                pass
            out[sub] = (True, "ok")
        except OSError as e:
            out[sub] = (False, f"{type(e).__name__}: {e}")
    return out


def run_preflight(
    path,
    min_free_gb: float = 5.0,
    alertor: Alertor | None = None,
    source: str = "tdx-chronos",
) -> int:
    """Check free disk, alert via Alertor on failure, return shell exit code.

    Returns:
        ``0`` when ok; ``2`` (matching daily_incr.sh's "全失败" code) when
        insufficient space — cron delivery branches on this.
    """
    report = check_disk_free(path, min_free_gb=min_free_gb)
    logger.info("preflight: %s", report.short)
    if report.ok:
        return 0

    detail = (
        f"{report.path} 仅剩 {report.free_gb:.2f} GB "
        f"(阈值 {report.min_free_gb:.1f} GB)。\n"
        f"清理 data/snapshot/ 或扩容磁盘后重跑。"
    )
    logger.error("preflight FAIL: %s", detail)

    if alertor is None:
        alertor = Alertor()
    alertor.send_alert(
        level="error",
        summary=f"disk full: {report.free_gb:.1f}GB free on {report.path}",
        detail=detail,
        source=source,
    )
    return 2


def run_extended_preflight(
    data_dir,
    *,
    min_free_gb: float = 5.0,
    snapshot_dir=None,
    alertor: Alertor | None = None,
    source: str = "tdx-chronos",
) -> int:
    """Sprint 14 · 扩展 preflight, 跑 3 检查 (disk + zip integrity + writability).

    Args:
        data_dir:     e.g. ``/app/tdx-chronos/data``
        min_free_gb:  磁盘阈值 (默认 5 GB)
        snapshot_dir: today snapshot dir; None → 用今天日期自动推导
        alertor:      Alertor 实例 (默认 DRY-RUN)
        source:       cron 脚本名 (alert source 字段)

    Returns:
        ``0`` 全过; ``2`` 任一失败.
    """
    if snapshot_dir is None:
        today_str = (date.today() if not isinstance(data_dir, date) else data_dir).isoformat()
        snapshot_dir = Path(data_dir) / "snapshot" / today_str

    # 1. disk check
    disk_report = check_disk_free(data_dir, min_free_gb=min_free_gb)
    logger.info("extended preflight disk: %s", disk_report.short)

    # 2. zip integrity (today only)
    zip_results = check_zip_integrity(snapshot_dir, today_only=True)
    bad_zips = [(n, e) for n, ok, e in zip_results if not ok]
    if bad_zips:
        logger.error("extended preflight zips: %d broken", len(bad_zips))

    # 3. writability
    writable = check_data_writable(data_dir)
    bad_writable = {k: (ok, msg) for k, (ok, msg) in writable.items() if not ok}
    if bad_writable:
        logger.error("extended preflight writability: %s", bad_writable)

    ok = disk_report.ok and not bad_zips and not bad_writable
    if ok:
        return 0

    detail_lines = []
    if not disk_report.ok:
        detail_lines.append(f"disk: {disk_report.short}")
    if bad_zips:
        detail_lines.append(
            "broken zips: " + ", ".join(f"{n} ({e})" for n, e in bad_zips)
        )
    if bad_writable:
        detail_lines.append("writability: " + str(bad_writable))
    detail = "\n".join(detail_lines)

    if alertor is None:
        alertor = Alertor()
    alertor.send_alert(
        level="error",
        summary="preflight FAIL",
        detail=detail,
        source=source,
    )
    return 2
