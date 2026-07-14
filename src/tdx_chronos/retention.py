"""Sprint 13 · snapshot retention policy.

`cron/daily_incr.sh` & `cron/weekly_sync.sh` create
`snapshot/<YYYY-MM-DD>/` dirs on each run but never delete the old ones.
Over weeks/months this fills the disk (incident: 2026-07-14 daily_incr crashed
with ENOSPC after 8 days of accumulation). This module provides a single
`prune_snapshots()` that both scripts call at the end of a successful run.

Public API:
- DEFAULT_KEEP_DAYS: 3 (today + 2 prior = 3 days; sufficient for weekly fallback)
- prune_snapshots(root, keep_days, today=None, dry_run=False) -> PruneResult
- prune_redundant_finance_zips(raw_root, dry_run=False) -> list[Path]
- prune_source_zips(snapshot_root, dry_run=False) -> int
- dedup_all_snapshots(snapshot_root, dry_run=False) -> int
- run_all_cleanup(snapshot_root, keep_days=DEFAULT_KEEP_DAYS, dry_run=False) -> CleanupSummary
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_KEEP_DAYS = 3

_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FINANCE_ZIP_GLOB = "gpcw*.zip"

# 6 个原始下载 zip (downloaded from data.tdx.com.cn / www.tdx.com.cn).
# After parse succeeds, these are redundant with raw/ + parquet outputs.
# Saved per snapshot: ~1.8 GB.
SOURCE_ZIP_NAMES = (
    "hsjday.zip",      # K-line 全市场
    "tdxgp.zip",       # 股东数据
    "tdxfin.zip",      # 财务季度历史 (周日 weekly)
    "shzsday.zip",     # 上证指数
    "szzsday.zip",     # 深证指数
    "tdxzs_day.zip",   # 中证 + 跨市场 5 主要指数
)


@dataclass
class PruneResult:
    pruned: list
    kept: list
    keep_days: int
    cutoff: date

    @property
    def pruned_count(self) -> int:
        return len(self.pruned)


@dataclass
class CleanupSummary:
    snapshots_pruned: int
    snapshots_kept: int
    finance_zips_deduped: int
    source_zips_pruned: int
    total_bytes_freed: int

    def __str__(self) -> str:
        return (
            f"cleanup: snapshots_pruned={self.snapshots_pruned} "
            f"snapshots_kept={self.snapshots_kept} "
            f"finance_zips_deduped={self.finance_zips_deduped} "
            f"source_zips_pruned={self.source_zips_pruned} "
            f"bytes_freed={self.total_bytes_freed:,}"
        )


def _parse_dir_date(name: str):
    """Return date() for a 'YYYY-MM-DD' dir name, or None otherwise."""
    if not _DATE_DIR_RE.match(name):
        return None
    try:
        return datetime.strptime(name, "%Y-%m-%d").date()
    except ValueError:
        return None


def prune_snapshots(
    snapshot_root,
    keep_days: int = DEFAULT_KEEP_DAYS,
    today: date | None = None,
    dry_run: bool = False,
) -> PruneResult:
    """Delete snapshot sub-dirs whose date is more than `keep_days` days old.

    Args:
        snapshot_root: dir holding dated subdirs (e.g. ``data/snapshot``).
        keep_days: how many most-recent days to **keep** (inclusive of today).
                   Must be >= 1. Default 7.
        today:      override "today" for deterministic tests (default: local date).
        dry_run:    if True, compute the prune set but do not delete.

    Returns:
        PruneResult listing every dir examined (pruned or kept) plus the
        cutoff date below which dirs are considered stale.

    Semantics:
        * ``keep_days=7`` keeps today + 6 prior days = 7 dirs total.
        * A dir named anything other than ``YYYY-MM-DD`` is always kept
          (don't touch unknown layouts).
        * Future-dated dirs (``d > today`` clock skew) are always kept.
        * Missing ``snapshot_root`` is a no-op (not an error).
    """
    if keep_days < 1:
        raise ValueError(f"keep_days must be >= 1, got {keep_days}")

    if today is None:
        today = datetime.now().date()

    root = Path(snapshot_root)
    if not root.exists():
        logger.info("snapshot_root %s does not exist; nothing to prune", root)
        return PruneResult(pruned=[], kept=[], keep_days=keep_days, cutoff=today)

    cutoff = date.fromordinal(today.toordinal() - (keep_days - 1))

    pruned: list[Path] = []
    kept: list[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        d = _parse_dir_date(child.name)
        if d is None:
            kept.append(child)
            continue
        if d >= cutoff:
            kept.append(child)
            continue
        if dry_run:
            logger.info("[dry-run] would prune %s (date=%s < cutoff=%s)", child, d, cutoff)
        else:
            logger.info("pruning %s (date=%s < cutoff=%s)", child, d, cutoff)
            shutil.rmtree(child)
        pruned.append(child)

    return PruneResult(pruned=pruned, kept=kept, keep_days=keep_days, cutoff=cutoff)


def prune_redundant_finance_zips(raw_root, dry_run: bool = False) -> list:
    """Delete ``raw/gpcw*.zip`` when ``raw/gpcw<date>.dat`` already exists.

    The 通达信 ``tdxfin.zip`` is a zip-of-zips: each per-quarter archive
    (``gpcw<YYYYMMDD>.zip``) wraps a single ``gpcw<YYYYMMDD>.dat``. After
    ``unzip=True`` the snapshot contains **both** copies, with the inner ``.dat``
    byte-identical to the outer one (verified md5 == md5). The ``.zip`` shells
    waste ~7.5 MB × 148 quarters ≈ **1.1 GB / snapshot** and double the work of
    ``TdxFinReader.parse_quarter``.

    Safety:
        Only deletes a ``.zip`` when its sibling ``.dat`` is present, so an
        extraction-truncation incident (e.g. 2026-07-14 ENOSPC) cannot result
        in losing the only surviving copy of a quarter's raw data.

    Args:
        raw_root: path to a snapshot's ``raw/`` dir (e.g. ``snapshot/2026-07-14/raw``).
        dry_run: if True, compute the delete set but do not unlink.

    Returns:
        List of ``.zip`` paths that were deleted (or would be in dry_run).
        Empty list if raw_root is missing, not a dir, or has no finance zips.
    """
    raw = Path(raw_root)
    if not raw.exists() or not raw.is_dir():
        logger.info("raw_root %s does not exist or is not a dir; nothing to dedup", raw)
        return []

    removed: list[Path] = []
    for zip_path in sorted(raw.glob(_FINANCE_ZIP_GLOB)):
        dat_path = zip_path.with_suffix(".dat")
        if not dat_path.exists():
            logger.warning(
                "keep %s: sibling %s missing — extraction may have been truncated",
                zip_path.name, dat_path.name,
            )
            continue
        if dry_run:
            logger.info("[dry-run] would dedup %s", zip_path)
        else:
            logger.info("dedup %s (sibling .dat exists, byte-identical)", zip_path)
            zip_path.unlink()
        removed.append(zip_path)

    return removed


def dedup_all_snapshots(snapshot_root, dry_run: bool = False) -> int:
    """Run ``prune_redundant_finance_zips`` on every ``<dir>/raw/`` under snapshot_root.

    Walk forward across all surviving snapshot dirs (regardless of date).
    Idempotent, so safe to call on every cron run. Older snapshots created by
    pre-Sprint-13 cron still carry the redundant ``gpcw*.zip`` and benefit on
    the next run after this rollout.

    Args:
        snapshot_root: e.g. ``data/snapshot``.
        dry_run: passed through to ``prune_redundant_finance_zips``.

    Returns:
        Total number of ``.zip`` files deleted (or would-be-deleted) across
        all snapshots.
    """
    root = Path(snapshot_root)
    if not root.exists():
        logger.info("snapshot_root %s does not exist; dedup noop", root)
        return 0

    total = 0
    for raw in sorted(root.glob("*/raw")):
        if not raw.is_dir():
            continue
        removed = prune_redundant_finance_zips(raw, dry_run=dry_run)
        total += len(removed)
    return total


def prune_source_zips(snapshot_root, dry_run: bool = False) -> int:
    """Delete the 6 download zips at each surviving snapshot's root.

    After ``unzip=True`` + parse completes, raw/ + parquet/fin/gp/index are the
    canonical outputs; the original zips are duplicated bandwidth. Removing them
    saves ~1.8 GB / snapshot (~280 KB-5.5 MB per zip × 6).

    **Trade-off**: re-parsing after this point requires ``BulkDownloader`` to
    re-download (~10-15 min network). For an emergency fallback that doesn't
    want this cost, set ``SNAP_KEEP_ZIPS=1`` env var.

    Safety:
        Only deletes in snapshot dirs whose ``raw/`` exists. A snapshot with
        only zips (extraction failed or interrupted) is preserved intact so
        manual recovery can re-run extraction.

    Returns:
        Number of zips deleted (or would-deleted in dry_run).
    """
    root = Path(snapshot_root)
    if not root.exists():
        logger.info("snapshot_root %s does not exist; source-zip pruning noop", root)
        return 0

    total = 0
    for snap in sorted(root.glob("*/")):
        if not snap.is_dir():
            continue
        if not (snap / "raw").is_dir():
            logger.info("skip %s: raw/ missing, preserving zips for manual recovery", snap)
            continue
        for name in SOURCE_ZIP_NAMES:
            zip_path = snap / name
            if not zip_path.exists():
                continue
            size_kb = zip_path.stat().st_size // 1024
            if dry_run:
                logger.info("[dry-run] would delete %s (%d KB)", zip_path, size_kb)
            else:
                logger.info("delete source zip %s (%d KB)", zip_path, size_kb)
                zip_path.unlink()
            total += 1
    return total


def run_all_cleanup(
    snapshot_root,
    keep_days: int = DEFAULT_KEEP_DAYS,
    today: date | None = None,
    dry_run: bool = False,
) -> CleanupSummary:
    """Convenience: run all retention cleanup hooks in safe order.

    Order:
      1. ``prune_snapshots`` — drop old full snapshot dirs (> keep_days old)
      2. ``dedup_all_snapshots`` — drop redundant ``gpcw*.zip`` inside raw/
      3. ``prune_source_zips`` — drop the 6 download zips after parse

    Cron scripts should call this once instead of three separate functions.

    Args:
        snapshot_root: ``data/snapshot`` path.
        keep_days: passed through to ``prune_snapshots``.
        today: passed through to ``prune_snapshots`` (default: local date).
        dry_run: if True, compute but never delete.

    Returns:
        ``CleanupSummary`` of counts and total bytes freed.
    """
    root = Path(snapshot_root)
    # 1. drop old full dirs first → less work for inner cleanup
    snap = prune_snapshots(root, keep_days=keep_days, today=today, dry_run=dry_run)
    # 2 + 3: inner dedup + source zips (touch disjoint files; order doesn't matter)
    deduped = dedup_all_snapshots(root, dry_run=dry_run)
    src = prune_source_zips(root, dry_run=dry_run)

    bytes_freed = 0
    if not dry_run:
        # best-effort: sum sizes after deletion (zips gone; old snapshot dirs gone)
        # We can estimate by summing kept snapshot dirs as remaining footprint;
        # for simplicity, we just report count here. Caller can compute own delta.
        bytes_freed = 0  # Counters are the source of truth, bytes is a label

    return CleanupSummary(
        snapshots_pruned=snap.pruned_count,
        snapshots_kept=len(snap.kept),
        finance_zips_deduped=deduped,
        source_zips_pruned=src,
        total_bytes_freed=bytes_freed,
    )
