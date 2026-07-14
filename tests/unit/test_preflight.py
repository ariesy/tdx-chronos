"""Sprint 13 · preflight 单元测试

`tdx_chronos.preflight.check_disk_free` 和 `run_preflight` 是 cron 入口
的磁盘空间检查。覆盖:
  1. free >= min → ok=True, run_preflight 返回 0
  2. free < min → ok=False, run_preflight 返回 2, Alertor.dry_run 写入 stdout
  3. `Alertor` 显式传入优先于默认构造
  4. TDX_DRY_RUN 环境变量驱动 Alertor dry_run 默认值
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from tdx_chronos.alertor import Alertor
from tdx_chronos.preflight import (
    DiskReport,
    check_data_writable,
    check_disk_free,
    check_zip_integrity,
    run_extended_preflight,
    run_preflight,
)


class TestCheckDiskFree:
    def test_ok_when_above_threshold(self, tmp_path: Path):
        """`/tmp` 通常有几十 GB 空间, 应该远大于 0.001 GB 阈值."""
        report = check_disk_free(tmp_path, min_free_gb=0.001)
        assert isinstance(report, DiskReport)
        assert report.ok is True
        assert report.free_gb > 0
        assert report.min_free_gb == 0.001

    def test_not_ok_when_threshold_unreasonably_high(self, tmp_path: Path):
        """阈值设到 1e9 GB → 一定不通过."""
        report = check_disk_free(tmp_path, min_free_gb=1_000_000_000)
        assert report.ok is False

    def test_short_string_format(self, tmp_path: Path):
        report = check_disk_free(tmp_path, min_free_gb=0.001)
        s = report.short
        assert "free=" in s
        assert "GB" in s
        assert str(tmp_path) in s
        assert "ok=True" in s


class TestRunPreflight:
    def test_returns_zero_when_ok(self, tmp_path: Path):
        """磁盘充足时 run_preflight 应返回 0 (cron 继续)."""
        rc = run_preflight(tmp_path, min_free_gb=0.001)
        assert rc == 0

    def test_returns_two_on_disk_full(self, tmp_path: Path, capsys):
        """阈值过高 → run_preflight 返回 2 并触发 Alertor 卡 (DRY-RUN 走 stdout)."""
        rc = run_preflight(
            tmp_path,
            min_free_gb=1_000_000_000,
            alertor=Alertor(dry_run=True),
            source="test_preflight",
        )
        assert rc == 2
        captured = capsys.readouterr()
        assert "[Alertor DRY-RUN]" in captured.out
        assert "disk full" in captured.out.lower() or "disk free" in captured.out.lower()
        assert "test_preflight" in captured.out

    def test_alertor_argument_is_respected(self, tmp_path: Path):
        """传入的 alertor 必须使用, 不允许内部默认覆盖."""
        sent = []

        class StubAlertor:
            dry_run = False
            chat_id = "stub"

            def send_alert(self, *, level, summary, detail=None, source=None):
                sent.append({"level": level, "summary": summary, "source": source})
                return None

        rc = run_preflight(
            tmp_path,
            min_free_gb=1_000_000_000,
            alertor=StubAlertor(),
            source="stub-source",
        )
        assert rc == 2
        assert len(sent) == 1
        assert sent[0]["source"] == "stub-source"
        assert sent[0]["level"] == "error"

    def test_default_alertor_uses_env(self, tmp_path: Path, monkeypatch, capsys):
        """未传 alertor → 走 Alertor() 默认构造 (受 TDX_DRY_RUN 控制)."""
        monkeypatch.delenv("TDX_DRY_RUN", raising=False)
        rc = run_preflight(tmp_path, min_free_gb=1_000_000_000)
        assert rc == 2
        captured = capsys.readouterr()
        # 默认 Alertor(dry_run=True) → 走 DRY-RUN 路径
        assert "[Alertor DRY-RUN]" in captured.out


class TestCheckZipIntegrity:
    """Sprint 14 · check_zip_integrity(snapshot_dir) 各 edge cases."""

    def _make_real_zip(self, p: Path, files: dict):
        """Create a valid zip with given {internal_name: content}."""
        import zipfile
        with zipfile.ZipFile(p, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)

    def test_missing_zip_is_skipped(self, tmp_path: Path):
        """zip 不存在 → 跳过, 不算坏 (retention 删除后的情况)."""
        snap = tmp_path / "2026-07-14"
        snap.mkdir()
        # 不创建任何 zip
        results = check_zip_integrity(snap)
        assert results == []

    def test_valid_zip_returns_ok(self, tmp_path: Path):
        snap = tmp_path / "2026-07-14"
        snap.mkdir()
        self._make_real_zip(snap / "hsjday.zip", {"sh/lday/sh000001.day": b"x" * 32})

        results = check_zip_integrity(snap)
        assert len(results) == 1
        name, ok, err = results[0]
        assert name == "hsjday.zip"
        assert ok is True
        assert err is None

    def test_empty_zip_is_broken(self, tmp_path: Path):
        snap = tmp_path / "2026-07-14"
        snap.mkdir()
        (snap / "tdxfin.zip").write_bytes(b"")  # 0 bytes

        results = check_zip_integrity(snap)
        assert len(results) == 1
        assert results[0] == ("tdxfin.zip", False, "0 字节文件")

    def test_truncated_zip_detected(self, tmp_path: Path):
        snap = tmp_path / "2026-07-14"
        snap.mkdir()
        # valid zip but truncated to 100 bytes (corrupt)
        zpath = snap / "tdxgp.zip"
        self._make_real_zip(zpath, {"sh/gpsh600000.dat": b"data" * 100})
        # truncate
        zpath.write_bytes(zpath.read_bytes()[:100])

        results = check_zip_integrity(snap)
        assert len(results) == 1
        name, ok, err = results[0]
        assert name == "tdxgp.zip"
        assert ok is False
        assert err is not None


class TestCheckDataWritable:
    """Sprint 14 · check_data_writable: 探测 cron 写入路径."""

    def test_writable_subdirs_report_ok(self, tmp_path: Path):
        data = tmp_path / "data"
        (data / "meta").mkdir(parents=True)
        (data / "snapshot").mkdir(parents=True)
        (data / "meta").chmod(0o755)
        (data / "snapshot").chmod(0o755)

        result = check_data_writable(data)

        assert result["meta"] == (True, "ok")
        assert result["snapshot"] == (True, "ok")

    def test_readonly_dir_detected(self, tmp_path: Path):
        """chmod 555 (read-only) → 写入失败 → ok=False."""
        data = tmp_path / "data"
        readonly = data / "meta"
        readonly.mkdir(parents=True)
        readonly.chmod(0o555)

        result = check_data_writable(data)

        assert result["meta"][0] is False
        assert "PermissionError" in result["meta"][1] or "OSError" in result["meta"][1]
        # cleanup: 还原 chmod, 让 tmp_path 清理能跑
        readonly.chmod(0o755)

    def test_missing_subdir_created(self, tmp_path: Path):
        """subdir 不存在 → 自动 mkdir."""
        data = tmp_path / "data"
        data.mkdir()

        result = check_data_writable(data)

        # meta + snapshot 自动建好了
        assert (data / "meta").is_dir()
        assert (data / "snapshot").is_dir()
        assert result["meta"] == (True, "ok")
        assert result["snapshot"] == (True, "ok")


class TestRunExtendedPreflight:
    """Sprint 14 · run_extended_preflight: 3-pass 综合 (disk + zip + write)."""

    def test_all_ok_returns_zero(self, tmp_path: Path, capsys, monkeypatch):
        """所有检查通过 → 0."""
        monkeypatch.delenv("TDX_DRY_RUN", raising=False)
        data = tmp_path / "data"
        (data / "meta").mkdir(parents=True)
        (data / "snapshot" / "2026-07-14").mkdir(parents=True)
        # 把 data 链接到一个有足够空间的目录, 让 disk check 通过
        # (tmp_path 默认在有空间的 fs)

        rc = run_extended_preflight(
            data, min_free_gb=0.001, snapshot_dir=data / "snapshot" / "2026-07-14",
        )
        assert rc == 0

    def test_unwritable_meta_triggers_alert(self, tmp_path: Path, capsys, monkeypatch):
        """meta 不可写 → exit 2 + Alertor DRY-RUN stdout."""
        monkeypatch.delenv("TDX_DRY_RUN", raising=False)
        data = tmp_path / "data"
        readonly = data / "meta"
        readonly.mkdir(parents=True)
        readonly.chmod(0o555)
        snap = data / "snapshot" / "2026-07-14"
        snap.mkdir(parents=True)

        rc = run_extended_preflight(
            data, min_free_gb=0.001, snapshot_dir=snap,
        )

        assert rc == 2
        captured = capsys.readouterr()
        assert "[Alertor DRY-RUN]" in captured.out
        assert "preflight FAIL" in captured.out or "writability" in captured.out

        # cleanup
        readonly.chmod(0o755)
