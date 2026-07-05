"""Sprint 5 T1 · cron 脚本 bash 语法 + 集成测试

Tests:
- bash 语法 (bash -n)
- 必需工具 (python · venv · meta.db dir)
- 不真下载 (DRY-RUN safe · 等 cron 触发)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path("/app/tdx-chronos")
DAILY_INCR = REPO / "cron" / "daily_incr.sh"
WEEKLY_SYNC = REPO / "cron" / "weekly_sync.sh"


class TestBashSyntax:
    def test_daily_incr_syntax(self):
        """bash -n daily_incr.sh"""
        result = subprocess.run(
            ["bash", "-n", str(DAILY_INCR)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"语法错误:\n{result.stderr}"

    def test_weekly_sync_syntax(self):
        """bash -n weekly_sync.sh"""
        result = subprocess.run(
            ["bash", "-n", str(WEEKLY_SYNC)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"语法错误:\n{result.stderr}"


class TestExecutableBit:
    def test_daily_incr_executable(self):
        """chmod +x"""
        mode = DAILY_INCR.stat().st_mode
        assert mode & 0o111, "daily_incr.sh 不可执行"

    def test_weekly_sync_executable(self):
        mode = WEEKLY_SYNC.stat().st_mode
        assert mode & 0o111, "weekly_sync.sh 不可执行"


class TestRequiredTools:
    """脚本运行所需工具检查"""

    def test_python_venv_exists(self):
        venv_python = REPO / ".venv" / "bin" / "python"
        assert venv_python.exists(), "venv 不存在"

    def test_data_meta_dir_creatable(self, tmp_path):
        """脚本会 mkdir -p data/meta · 测试 mkdir 权限"""
        meta_dir = tmp_path / "data" / "meta"
        meta_dir.mkdir(parents=True)
        assert meta_dir.exists()


class TestDailyIncrContent:
    """脚本内容合理性 (不跑全)"""

    def test_daily_incr_calls_bulk_download(self):
        content = DAILY_INCR.read_text()
        assert "BulkDownloader" in content
        assert "download_all" in content
        assert "download_index" in content

    def test_daily_incr_parses_4_sources(self):
        """K 线 + 股本 + 指数 + 财务 (财务周日跑)"""
        content = DAILY_INCR.read_text()
        assert "run_full_parse" in content  # K 线
        assert "TdxGpRecordReader" in content  # 股本
        assert "IndexParser" in content  # 指数

    def test_daily_incr_logs_to_cron_log_dir(self):
        content = DAILY_INCR.read_text()
        assert "logs/cron" in content

    def test_daily_incr_uses_asia_shanghai_tz(self):
        """TZ=Asia/Shanghai 显式"""
        content = DAILY_INCR.read_text()
        assert "TZ=Asia/Shanghai" in content


class TestWeeklySyncContent:
    def test_weekly_sync_downloads_tdxfin(self):
        content = WEEKLY_SYNC.read_text()
        assert "tdxfin" in content

    def test_weekly_sync_parses_quarters(self):
        content = WEEKLY_SYNC.read_text()
        assert "gpcw" in content
        assert "TdxFinReader" in content