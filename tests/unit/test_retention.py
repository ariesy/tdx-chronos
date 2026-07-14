"""Sprint 13 · snapshot_retention 单元测试

`tdx_chronos.retention.prune_snapshots` 是 daily_incr.sh / weekly_sync.sh
共用的清理入口。本测试覆盖:
  1. keep_days=N 正好保留 N 个最新 dated dir
  2. 缺失 snapshot_root 不报错
  3. 非 'YYYY-MM-DD' 命名的 dir 永远保留
  4. 未来日期 (clock skew) dir 永远保留
  5. `dry_run=True` 不删, 返回一致结果
  6. `keep_days < 1` 抛 ValueError
  7. 第二次调用 idempotent (rerun 是 no-op)
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from tdx_chronos.retention import (
    DEFAULT_KEEP_DAYS,
    CleanupSummary,
    PruneResult,
    dedup_all_snapshots,
    prune_redundant_finance_zips,
    prune_snapshots,
    prune_source_zips,
    run_all_cleanup,
)


def _touch(tmp: Path, name: str) -> Path:
    """Create a subdir under tmp with the given name (and a sentinel file)."""
    p = tmp / name
    p.mkdir()
    (p / ".sentinel").write_text("x")
    return p


class TestKeepRecentN:
    def test_keeps_exactly_n_days(self, tmp_path: Path):
        """keep_days=7 应保留今天 + 前 6 天 = 共 7 个 dated dir."""
        today = date(2026, 7, 14)
        for offset in range(0, 10):
            _touch(tmp_path, (today - timedelta(days=offset)).isoformat())

        result = prune_snapshots(tmp_path, keep_days=7, today=today)

        assert result.keep_days == 7
        assert result.cutoff == today - timedelta(days=6)
        assert len(result.kept) == 7
        assert len(result.pruned) == 3

        kept_names = {p.name for p in result.kept}
        pruned_names = {p.name for p in result.pruned}
        assert kept_names == {(today - timedelta(days=i)).isoformat() for i in range(7)}
        assert pruned_names == {(today - timedelta(days=i)).isoformat() for i in range(7, 10)}

        # 实际文件应已删
        for offset in range(7, 10):
            assert not (tmp_path / (today - timedelta(days=offset)).isoformat()).exists()
        for offset in range(7):
            assert (tmp_path / (today - timedelta(days=offset)).isoformat()).exists()

    def test_default_keep_days_is_3(self, tmp_path: Path):
        today = date(2026, 7, 14)
        for offset in range(0, 8):
            _touch(tmp_path, (today - timedelta(days=offset)).isoformat())
        result = prune_snapshots(tmp_path, today=today)
        assert result.keep_days == DEFAULT_KEEP_DAYS == 3
        assert len(result.kept) == 3
        assert len(result.pruned) == 5

    def test_only_today_no_prune(self, tmp_path: Path):
        """keep_days >= 1 + 只有今天 → 不删任何东西."""
        today = date(2026, 7, 14)
        _touch(tmp_path, today.isoformat())
        result = prune_snapshots(tmp_path, keep_days=7, today=today)
        assert result.pruned == []
        assert result.pruned_count == 0
        assert len(result.kept) == 1


class TestEdgeCases:
    def test_missing_root_is_noop(self, tmp_path: Path):
        """不存在的 snapshot_root 不报错, 返回空结果."""
        result = prune_snapshots(tmp_path / "does-not-exist", today=date(2026, 7, 14))
        assert isinstance(result, PruneResult)
        assert result.pruned == []
        assert result.kept == []

    def test_non_dated_dirs_always_kept(self, tmp_path: Path):
        """非 'YYYY-MM-DD' 命名的 dir 一律保留, 即使 '看起来旧'."""
        _touch(tmp_path, "keep_me_forever")
        _touch(tmp_path, ".hidden")
        _touch(tmp_path, "legacy_data_2024")
        result = prune_snapshots(tmp_path, keep_days=1, today=date(2026, 7, 14))
        kept_names = {p.name for p in result.kept}
        assert {"keep_me_forever", ".hidden", "legacy_data_2024"} <= kept_names

    def test_future_dated_dirs_kept(self, tmp_path: Path):
        """未来日期的 dir (clock skew) 一律保留."""
        today = date(2026, 7, 14)
        _touch(tmp_path, (today + timedelta(days=30)).isoformat())  # 1 个月后
        _touch(tmp_path, (today + timedelta(days=365)).isoformat())  # 明年
        result = prune_snapshots(tmp_path, keep_days=7, today=today)
        assert len(result.pruned) == 0
        assert {p.name for p in result.kept} >= {
            (today + timedelta(days=30)).isoformat(),
            (today + timedelta(days=365)).isoformat(),
        }

    def test_files_under_root_ignored(self, tmp_path: Path):
        """根目录下的文件不算 snapshot dir, 不参与 prune."""
        (tmp_path / "README.md").write_text("# snapshots")
        result = prune_snapshots(tmp_path, keep_days=1, today=date(2026, 7, 14))
        assert result.pruned == []
        assert result.kept == []
        assert (tmp_path / "README.md").exists()

    def test_keep_days_less_than_one_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="keep_days"):
            prune_snapshots(tmp_path, keep_days=0, today=date(2026, 7, 14))
        with pytest.raises(ValueError):
            prune_snapshots(tmp_path, keep_days=-3, today=date(2026, 7, 14))


class TestDryRunAndIdempotence:
    def test_dry_run_does_not_delete(self, tmp_path: Path):
        today = date(2026, 7, 14)
        for offset in range(0, 12):
            _touch(tmp_path, (today - timedelta(days=offset)).isoformat())

        result = prune_snapshots(tmp_path, keep_days=7, today=today, dry_run=True)

        assert len(result.pruned) == 5
        # 所有 12 个 dir 都还在
        remaining = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
        assert len(remaining) == 12

    def test_idempotent_second_call_noop(self, tmp_path: Path):
        """第一次 prune 后再跑一次, 应是 no-op."""
        today = date(2026, 7, 14)
        for offset in range(0, 12):
            _touch(tmp_path, (today - timedelta(days=offset)).isoformat())

        first = prune_snapshots(tmp_path, keep_days=7, today=today)
        assert first.pruned_count == 5

        second = prune_snapshots(tmp_path, keep_days=7, today=today)
        assert second.pruned_count == 0
        # 第一次删的已经没了, 第二次什么都不删
        kept_names_round2 = {p.name for p in second.kept}
        assert len(kept_names_round2) == 7


class TestPruneRedundantFinanceZips:
    """Sprint 13 hotfix·opt: gpcw<date>.zip 与 .dat 字节等同, 删 .zip 节省 ~1.1 GB/snapshot.

    验证:
      1. .zip + .dat 同在 → 删 .zip, 留 .dat
      2. .zip 单飞 (无 .dat) → **不删** (防御 ENOSPC 截断场景)
      3. dry_run=True → 不真删, 同返回 list
      4. 二次调用 idempotent (rerun 0 删除)
      5. 不存在/非目录的 raw_root → 空 list noop
      6. 没有 gpcw*.zip 的目录 → 空 list
      7. 不误删 sh/sz/bj 子目录下的同名 .day 文件
    """

    def _write_quarter(self, raw: Path, date: str, content: bytes = b"X" * 100):
        (raw / f"gpcw{date}.zip").write_bytes(content)
        (raw / f"gpcw{date}.dat").write_bytes(content)

    def test_deletes_zips_when_dat_exists(self, tmp_path: Path):
        """正常情况: 删 .zip, .dat 保留."""
        raw = tmp_path / "raw"
        raw.mkdir()
        for d in ("20241231", "20250331", "20250630"):
            self._write_quarter(raw, d, b"q" * 100)

        removed = prune_redundant_finance_zips(raw)

        assert len(removed) == 3
        assert not (raw / "gpcw20241231.zip").exists()
        assert (raw / "gpcw20241231.dat").exists()  # .dat 保留
        assert (raw / "gpcw20250331.dat").exists()

    def test_keeps_zip_when_dat_missing(self, tmp_path: Path):
        """关键安全网: .dat 缺失时不删 .zip (2026-07-14 ENOSPC 截断事故复现)."""
        raw = tmp_path / "raw"
        raw.mkdir()
        # 只放 .zip, 没有 .dat
        (raw / "gpcw20241231.zip").write_bytes(b"orphan")
        # 同时放一个正常 pair + 一个只有 .dat 的 (无 .zip)
        self._write_quarter(raw, "20250331")

        removed = prune_redundant_finance_zips(raw)

        # 1 个正常对 (20250331) 被删, 1 个孤儿 (20241231.zip) 保留
        assert len(removed) == 1
        assert removed[0].name == "gpcw20250331.zip"
        assert (raw / "gpcw20241231.zip").exists(), "orphan zip 必须保留"
        assert (raw / "gpcw20241231.dat").exists() is False  # 只有 .zip 没 .dat

    def test_dry_run_does_not_delete(self, tmp_path: Path):
        raw = tmp_path / "raw"
        raw.mkdir()
        self._write_quarter(raw, "20241231")
        self._write_quarter(raw, "20250331")

        removed = prune_redundant_finance_zips(raw, dry_run=True)

        assert len(removed) == 2
        assert (raw / "gpcw20241231.zip").exists(), "dry_run 不应删"
        assert (raw / "gpcw20250331.zip").exists(), "dry_run 不应删"
        # 但 .dat 也没动
        assert (raw / "gpcw20241231.dat").exists()

    def test_idempotent_second_run_is_noop(self, tmp_path: Path):
        raw = tmp_path / "raw"
        raw.mkdir()
        for d in ("20241231", "20250331"):
            self._write_quarter(raw, d)

        first = prune_redundant_finance_zips(raw)
        second = prune_redundant_finance_zips(raw)

        assert len(first) == 2
        assert len(second) == 0, "第二次应无 .zip 可删"
        # .dat 全保留
        assert (raw / "gpcw20241231.dat").exists()
        assert (raw / "gpcw20250331.dat").exists()

    def test_missing_raw_root_returns_empty(self, tmp_path: Path):
        assert prune_redundant_finance_zips(tmp_path / "does-not-exist") == []
        # 文件而非目录
        f = tmp_path / "somefile"
        f.write_text("not a dir")
        assert prune_redundant_finance_zips(f) == []

    def test_no_quarter_zips_returns_empty(self, tmp_path: Path):
        """raw/ 存在但只有 .day / .txt, 无 gpcw*.zip."""
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "sh600000.day").write_bytes(b"\x00" * 32)
        (raw / "tdx.txt").write_text("notes")

        assert prune_redundant_finance_zips(raw) == []

    def test_does_not_touch_day_files_in_market_subdirs(self, tmp_path: Path):
        """严格只看 raw 顶层 gpcw*.zip; sh/sz/bj/ 下的 .day 文件不动."""
        raw = tmp_path / "raw"
        (raw / "sh").mkdir(parents=True)
        (raw / "sz").mkdir(parents=True)
        self._write_quarter(raw, "20241231")  # 顶层 finance zip
        (raw / "sh" / "sh600000.day").write_bytes(b"\x00" * 32)
        (raw / "sz" / "sz000001.day").write_bytes(b"\x00" * 32)

        removed = prune_redundant_finance_zips(raw)

        assert len(removed) == 1
        assert removed[0].name == "gpcw20241231.zip"
        assert (raw / "sh" / "sh600000.day").exists()
        assert (raw / "sz" / "sz000001.day").exists()


class TestDedupAllSnapshots:
    """递归 dedup 所有 <snapshot_root>/<dir>/raw/.

    验证:
      1. 跨多个 dated snapshot 全部 dedup, 返回总删除数
      2. 某 snapshot 没 raw/ → skip, 不报错
      3. 第二次调用 idempotent
      4. snapshot_root 不存在 → 返回 0
      5. dry_run 跨 snapshot 也走 dry_run 模式
    """

    def _snap_with_quarter(self, root: Path, date: str, n: int = 2):
        s = root / date / "raw"
        s.mkdir(parents=True)
        # n 个连续季度 (倒推)
        quarters = [
            "20241231", "20250331", "20250630", "20250930",
            "20251231", "20260331", "20260630", "20260930",
            "20261231",
        ]
        for d in quarters[:n]:
            (s / f"gpcw{d}.dat").write_bytes(b"x")
            (s / f"gpcw{d}.zip").write_bytes(b"x")

    def test_dedups_every_snapshot(self, tmp_path: Path):
        self._snap_with_quarter(tmp_path, "2026-07-13", n=3)
        self._snap_with_quarter(tmp_path, "2026-07-14", n=2)

        total = dedup_all_snapshots(tmp_path)

        assert total == 5
        # 07-13 raw/ 0 zip
        assert list((tmp_path / "2026-07-13" / "raw").glob("gpcw*.zip")) == []
        assert len(list((tmp_path / "2026-07-13" / "raw").glob("gpcw*.dat"))) == 3
        # 07-14 raw/ 0 zip, 2 dat
        assert list((tmp_path / "2026-07-14" / "raw").glob("gpcw*.zip")) == []
        assert len(list((tmp_path / "2026-07-14" / "raw").glob("gpcw*.dat"))) == 2

    def test_skips_snapshot_without_raw(self, tmp_path: Path):
        """只有 zip 没 raw/ 的 snapshot 不算入 (defensive)."""
        (tmp_path / "2026-07-13").mkdir()  # 无 raw/
        (tmp_path / "2026-07-14" / "raw").mkdir(parents=True)
        (tmp_path / "2026-07-14" / "raw" / "gpcw20241231.zip").write_bytes(b"x")
        (tmp_path / "2026-07-14" / "raw" / "gpcw20241231.dat").write_bytes(b"x")

        total = dedup_all_snapshots(tmp_path)

        assert total == 1
        assert not (tmp_path / "2026-07-14" / "raw" / "gpcw20241231.zip").exists()

    def test_idempotent(self, tmp_path: Path):
        self._snap_with_quarter(tmp_path, "2026-07-13", n=3)
        self._snap_with_quarter(tmp_path, "2026-07-14", n=3)

        first = dedup_all_snapshots(tmp_path)
        second = dedup_all_snapshots(tmp_path)

        assert first == 6
        assert second == 0

    def test_missing_root_returns_zero(self, tmp_path: Path):
        assert dedup_all_snapshots(tmp_path / "no-such-dir") == 0

    def test_dry_run_does_not_delete(self, tmp_path: Path):
        self._snap_with_quarter(tmp_path, "2026-07-14", n=2)

        total = dedup_all_snapshots(tmp_path, dry_run=True)

        assert total == 2
        # all zips still there
        assert len(list((tmp_path / "2026-07-14" / "raw").glob("gpcw*.zip"))) == 2


class TestPruneSourceZips:
    """删 snapshot 根目录的 6 个原始下载 zip (parse 完成后冗余, 省 ~1.8 GB/snap).

    验证:
      1. raw/ 存在 → 6 个 zip 全删
      2. raw/ 缺失 → 不删 (保护 raw-less snapshot 用于手工 recovery)
      3. 部分 zip 缺失 → 只删存在的
      4. dry_run 不删
      5. 跨多个 snapshot 全跑
      6. snapshot_root 不存在 → 0
    """

    def _make_snap(self, parent: Path, date: str, *, with_raw=True):
        s = parent / date
        s.mkdir()
        for name in ("hsjday.zip", "tdxgp.zip", "tdxfin.zip",
                     "shzsday.zip", "szzsday.zip", "tdxzs_day.zip"):
            (s / name).write_bytes(b"z" * 1024)
        if with_raw:
            (s / "raw").mkdir()
            (s / "raw" / "marker").write_text(".")
        return s

    def test_deletes_all_six_when_raw_present(self, tmp_path: Path):
        snap = self._make_snap(tmp_path, "2026-07-14", with_raw=True)

        n = prune_source_zips(tmp_path)

        assert n == 6
        for name in ("hsjday.zip", "tdxgp.zip", "tdxfin.zip",
                     "shzsday.zip", "szzsday.zip", "tdxzs_day.zip"):
            assert not (snap / name).exists()
        # raw/ 不动
        assert (snap / "raw" / "marker").exists()

    def test_preserves_zips_when_raw_missing(self, tmp_path: Path):
        """raw/ 缺失时不删 (extraction 中断场景, 保护手工 recovery)."""
        snap = self._make_snap(tmp_path, "2026-07-14", with_raw=False)

        n = prune_source_zips(tmp_path)

        assert n == 0
        # 全 6 个 zip 仍在
        for name in ("hsjday.zip", "tdxgp.zip", "tdxfin.zip",
                     "shzsday.zip", "szzsday.zip", "tdxzs_day.zip"):
            assert (snap / name).exists()

    def test_partial_zips_only_drops_existing(self, tmp_path: Path):
        snap = self._make_snap(tmp_path, "2026-07-14", with_raw=True)
        # 删 2 个 zip 模拟 download 部分失败
        (snap / "szzsday.zip").unlink()
        (snap / "tdxzs_day.zip").unlink()

        n = prune_source_zips(tmp_path)

        assert n == 4
        assert not (snap / "hsjday.zip").exists()
        assert not (snap / "shzsday.zip").exists()
        # szzsday.zip 和 tdxzs_day.zip 本来就不在, 跳过

    def test_dry_run_does_not_delete(self, tmp_path: Path):
        snap = self._make_snap(tmp_path, "2026-07-14", with_raw=True)

        n = prune_source_zips(tmp_path, dry_run=True)

        assert n == 6
        assert (snap / "hsjday.zip").exists()
        assert (snap / "tdxgp.zip").exists()

    def test_multiple_snapshots(self, tmp_path: Path):
        self._make_snap(tmp_path, "2026-07-08", with_raw=True)
        self._make_snap(tmp_path, "2026-07-13", with_raw=True)
        self._make_snap(tmp_path, "2026-07-14", with_raw=False)  # raw missing - skip

        n = prune_source_zips(tmp_path)

        assert n == 12  # 2 snaps × 6 zips
        # 07-14 (no raw) 保留
        assert (tmp_path / "2026-07-14" / "hsjday.zip").exists()
        # 07-08 / 07-13 删干净
        for d in ("2026-07-08", "2026-07-13"):
            for name in ("hsjday.zip", "tdxfin.zip"):
                assert not (tmp_path / d / name).exists()

    def test_missing_root_returns_zero(self, tmp_path: Path):
        assert prune_source_zips(tmp_path / "no-such-dir") == 0

    def test_does_not_delete_other_files(self, tmp_path: Path):
        """不应误删 6 个 zip 之外的文件 (例如 weekly_sync 写的 raw.tar.gz)."""
        snap = self._make_snap(tmp_path, "2026-07-14", with_raw=True)
        (snap / "extra_backup.tar.gz").write_bytes(b"x" * 1024)
        (snap / "notes.md").write_text("manual analysis")

        n = prune_source_zips(tmp_path)

        assert n == 6
        assert (snap / "extra_backup.tar.gz").exists()
        assert (snap / "notes.md").exists()


class TestRunAllCleanup:
    """run_all_cleanup() 一体化入口, cron 末尾一行调用."""

    def test_runs_three_passes_in_order(self, tmp_path: Path):
        """keep_days=3: kept=[14,13,12]; pruned=[11,10,09].

        Layout:
          - 5 in-window 完整 (raw + 6 zips + 2 finance pairs)
          - 1 in-window raw/yes 但没 source zip (模拟 download 部分失败)
          - 1 out-of-window 完整 (被 snapshot pass 删)
          - 1 out-of-window raw-less (snap pass 删, source-pass 不参与)
        """
        today = date(2026, 7, 14)

        def _full(d: str, with_source_zips: bool = True):
            s = tmp_path / d
            s.mkdir()
            (s / "raw").mkdir()
            for q in ("20241231", "20250331"):
                (s / "raw" / f"gpcw{q}.zip").write_bytes(b"x")
                (s / "raw" / f"gpcw{q}.dat").write_bytes(b"x")
            if with_source_zips:
                for name in ("hsjday.zip", "tdxgp.zip", "tdxfin.zip",
                             "shzsday.zip", "szzsday.zip", "tdxzs_day.zip"):
                    (s / name).write_bytes(b"y" * 100)

        # In-window snapshots (offset 0..2): kept
        for offset in range(0, 3):
            d = (today - timedelta(days=offset)).isoformat()
            _full(d)

        # In-window 2026-07-13 (offset 1) DROP source zips - simulate partial download
        (tmp_path / "2026-07-13" / "hsjday.zip").unlink()
        (tmp_path / "2026-07-13" / "tdxgp.zip").unlink()

        # Out-of-window snapshots (offset 3..5): pruned by snapshot pass
        for offset in (3, 4, 5):
            d = (today - timedelta(days=offset)).isoformat()
            _full(d)

        # Raw-less in-window (shouldn't exist normally, but covered for safety)
        # None left in window after raws — skip

        summary = run_all_cleanup(tmp_path, keep_days=3, today=today)

        assert isinstance(summary, CleanupSummary)
        assert summary.snapshots_pruned == 3  # offset 3, 4, 5
        assert summary.snapshots_kept == 3    # offset 0, 1, 2
        # finance_zips: 3 kept × 2 quarters = 6
        assert summary.finance_zips_deduped == 6
        # source_zips: 14×6 + 13×4 (lost 2) + 12×6 = 16
        assert summary.source_zips_pruned == 16
        # string summary
        s = str(summary)
        assert "snapshots_pruned=3" in s
        assert "snapshots_kept=3" in s
        assert "finance_zips_deduped=6" in s
        assert "source_zips_pruned=16" in s

    def test_dry_run_noop(self, tmp_path: Path):
        today = date(2026, 7, 14)
        d = (today - timedelta(days=10)).isoformat()  # 老, 该被 prune
        (tmp_path / d).mkdir()
        (tmp_path / d / "raw").mkdir()
        (tmp_path / d / "hsjday.zip").write_bytes(b"x" * 100)
        (tmp_path / d / "raw" / "gpcw20241231.zip").write_bytes(b"x")
        (tmp_path / d / "raw" / "gpcw20241231.dat").write_bytes(b"x")

        summary = run_all_cleanup(tmp_path, keep_days=3, today=today, dry_run=True)

        # 老 dir 应仍在 (dry_run)
        assert (tmp_path / d).exists()
        assert (tmp_path / d / "hsjday.zip").exists()
        assert summary.snapshots_pruned >= 1  # 但 counts 仍报告
        assert summary.source_zips_pruned >= 1

    def test_missing_root(self, tmp_path: Path):
        summary = run_all_cleanup(tmp_path / "no-such")
        assert summary.snapshots_pruned == 0
        assert summary.snapshots_kept == 0
        assert summary.finance_zips_deduped == 0
        assert summary.source_zips_pruned == 0
