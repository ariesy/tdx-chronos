"""Sprint 3a · bulk_download.py 单元测试

mock HTTP 服务器 (threading + http.server) 测试:
- TestSha256           · 在线算 SHA256
- TestRetryLogic       · 包级重试 3 次后失败 → status='failed'
- TestSuccessFirstTry  · 第 1 次就成功 → retry_count=0
- TestDownloadAll      · 一键全量 3 zip mock server + meta.db 集成
- TestUnzipIntoRaw     · unzip 到 raw/{sh,sz,bj}/lday
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import time
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from tdx_chronos.meta.db import MetaDB, PARSE_STATUS_FAILED, PARSE_STATUS_PENDING
from tdx_chronos.sources.bulk_download import (
    DEFAULT_ZIPS,
    BulkDownloader,
    DownloadSummary,
    ZipResult,
)


# ---------------------------------------------------------------------
# Mock HTTP server · 提供可控制响应的 zip
# ---------------------------------------------------------------------
class MockZipHandler(http.server.BaseHTTPRequestHandler):
    """返回小的伪 zip (满足 zipfile 格式)

    Query-string 控制:
        ?fail_count=2   → 前 N 次 HTTP 500  · 第 3 次成功
    """

    # 设置在每个测试
    payload: bytes = b""
    fail_count: int = 0  # 剩余失败次数
    current_calls: int = 0  # 当前 handler 调用计数 (atomic-ish)

    def do_HEAD(self):  # noqa
        # 返回 Content-Length · 让客户端用 Range 请求
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", '"mock-etag"')
        self.end_headers()

    def do_GET(self):  # noqa
        type(self).current_calls += 1
        if type(self).fail_count > 0:
            type(self).fail_count -= 1
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(type(self).payload)

    # 静默 · 避免测试输出混乱
    def log_message(self, *_args):
        pass


@pytest.fixture
def mock_server(tmp_path):
    """启动 1 个 mock HTTP server · 跑测试完成后停"""
    # 准备 mock zip payload (valid zip · 1 个 dummy .day inside)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sh/lday/sh000001.day", b"\x00" * 32)
        zf.writestr("sz/lday/sz000001.day", b"\x00" * 32)
    payload = buf.getvalue()

    server = socketserver.TCPServer(("127.0.0.1", 0), MockZipHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # 各测试可重置的 state
    MockZipHandler.payload = payload
    MockZipHandler.fail_count = 0
    MockZipHandler.current_calls = 0

    host, port = server.server_address
    base_url = f"http://{host}:{port}"

    yield base_url

    server.shutdown()
    server.server_close()


def _zips_for_url(base_url: str) -> list[dict]:
    return [
        {"name": "testzip", "url": f"{base_url}/test.zip",
         "approx_size": 4096, "contains": "mock"},
    ]


# ---------------------------------------------------------------------
# TestSha256
# ---------------------------------------------------------------------
class TestSha256:
    def test_sha256_of_known_bytes(self):
        path = Path("/tmp/test_sha.txt")
        path.write_bytes(b"hello world")
        sha = BulkDownloader._sha256_file(path)
        # Known value for "hello world"
        assert (
            sha == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        )
        path.unlink()


# ---------------------------------------------------------------------
# TestSuccessFirstTry
# ---------------------------------------------------------------------
class TestDownloadOne:
    def test_success_no_retry(self, tmp_path, mock_server):
        """第 1 次成功 · retry_count=0"""
        url = f"{mock_server}/test.zip"
        spec = {"name": "test", "url": url, "approx_size": 4096, "contains": "x"}
        dl = BulkDownloader(timeout=10)
        result = dl.download_one(
            spec, tmp_path / "snap", max_retries=3,
        )

        assert result.status == "success"
        assert result.retry_count == 0
        assert result.size_bytes == len(MockZipHandler.payload)
        # SHA256 of the mock zip
        assert len(result.sha256) == 64  # hex 256
        assert result.output_path.exists()
        assert result.output_path.stat().st_size == len(MockZipHandler.payload)


# ---------------------------------------------------------------------
# TestRetryLogic
# ---------------------------------------------------------------------
class TestRetryLogic:
    def test_retries_then_succeeds(self, tmp_path, mock_server):
        """前 2 次失败 · 第 3 次成功 · retry_count=2"""
        MockZipHandler.fail_count = 2
        url = f"{mock_server}/test.zip"
        spec = {"name": "test", "url": url, "approx_size": 4096, "contains": "x"}
        dl = BulkDownloader(timeout=10)
        result = dl.download_one(
            spec, tmp_path / "snap", max_retries=3,
        )
        assert result.status == "success"
        assert result.retry_count == 2  # 前 2 次失败 → 第 3 次成功
        # 3 次调用 (2 fail + 1 success)
        assert MockZipHandler.current_calls == 3

    def test_exhausts_retries_then_failed(self, tmp_path, mock_server):
        """3 次都失败 · status='failed' · retry_count=3"""
        MockZipHandler.fail_count = 10  # 永远失败
        url = f"{mock_server}/test.zip"
        spec = {"name": "test", "url": url, "approx_size": 4096, "contains": "x"}
        dl = BulkDownloader(timeout=10)
        result = dl.download_one(
            spec, tmp_path / "snap", max_retries=3,
        )
        assert result.status == "failed"
        assert result.retry_count == 2  # 第 1 2 3 次都失败 (第 3 次后放弃)
        assert result.error is not None
        # 3 次 attempts
        assert MockZipHandler.current_calls == 3

    def test_404_immediate_failure(self, tmp_path):
        """HTTP 404 (资源不存在) → 立即标记失败 · 不 retry"""
        # 用一个不存在的端口
        spec = {
            "name": "badtest",
            "url": "http://127.0.0.1:1/nope.zip",
            "approx_size": 100,
            "contains": "x",
        }
        dl = BulkDownloader(timeout=2)
        result = dl.download_one(
            spec, tmp_path / "snap", max_retries=3,
        )
        assert result.status == "failed"
        assert result.error is not None


# ---------------------------------------------------------------------
# TestDownloadAll
# ---------------------------------------------------------------------
class TestDownloadAll:
    def test_download_all_with_meta_db(self, tmp_path, mock_server):
        """一键 download_all + meta.db record_download"""
        zips = _zips_for_url(mock_server)
        dl = BulkDownloader(timeout=10)

        summary = dl.download_all(
            snap_dir=tmp_path / "snap",
            zips=zips,
            max_retries=3,
            db_path=tmp_path / "meta.db",
            unzip=True,
        )
        assert isinstance(summary, DownloadSummary)
        assert summary.success_count == 1
        assert summary.failed_count == 0
        assert summary.total_size > 0

        # meta.db 应有 1 行 download_log
        db = MetaDB(tmp_path / "meta.db")
        try:
            rows = db.get_recent_downloads(limit=10)
            assert len(rows) == 1
            assert rows[0]["zip_name"] == "testzip"
            assert rows[0]["parse_status"] == PARSE_STATUS_PENDING
            assert len(rows[0]["sha256"]) == 64
        finally:
            db.close()

    def test_download_all_records_failure(self, tmp_path, mock_server):
        """download_all 失败也记录 (parse_status='failed')"""
        MockZipHandler.fail_count = 10
        zips = _zips_for_url(mock_server)
        dl = BulkDownloader(timeout=10)

        summary = dl.download_all(
            snap_dir=tmp_path / "snap",
            zips=zips,
            max_retries=2,
            db_path=tmp_path / "meta.db",
            unzip=False,
        )
        assert summary.failed_count == 1

        db = MetaDB(tmp_path / "meta.db")
        try:
            rows = db.get_recent_downloads(limit=10)
            assert len(rows) == 1
            assert rows[0]["parse_status"] == PARSE_STATUS_FAILED
            assert rows[0]["error_msg"] is not None
        finally:
            db.close()

    def test_unzip_into_raw(self, tmp_path, mock_server):
        """download_all(unzip=True) → raw/{sh,sz}/lday/*.day"""
        zips = _zips_for_url(mock_server)
        dl = BulkDownloader(timeout=10)
        summary = dl.download_all(
            snap_dir=tmp_path / "snap",
            zips=zips,
            max_retries=3,
            db_path=None,
            unzip=True,
        )
        assert summary.success_count == 1
        raw = tmp_path / "snap" / "raw"
        assert (raw / "sh" / "lday" / "sh000001.day").exists()
        assert (raw / "sz" / "lday" / "sz000001.day").exists()


# ---------------------------------------------------------------------
# TestDefaults
# ---------------------------------------------------------------------
class TestDefaults:
    def test_default_zips_have_three_entries(self):
        """Sprint 3a 3 个核心 zip (Sprint 4 加 5 指数 zip)"""
        assert len(DEFAULT_ZIPS) == 3
        names = {z["name"] for z in DEFAULT_ZIPS}
        assert names == {"hsjday", "tdxfin", "tdxgp"}

    def test_default_zips_have_https_url(self):
        """v1.1 只支持 https (HTTPS 简单 · Sprint 5 cron 加 backup)"""
        for spec in DEFAULT_ZIPS:
            assert spec["url"].startswith("https://"), spec


class TestIndexZips:
    def test_default_index_zips_three_entries(self):
        """Sprint 4b D2 3 指数 zip"""
        from tdx_chronos.sources.bulk_download import DEFAULT_INDEX_ZIPS
        assert len(DEFAULT_INDEX_ZIPS) == 3
        names = {z["name"] for z in DEFAULT_INDEX_ZIPS}
        assert names == {"shzsday", "szzsday", "tdxzs_day"}

    def test_index_zips_https_www_tdx(self):
        """指数 zip 主机 www.tdx.com.cn (与 hsjday 不同)"""
        from tdx_chronos.sources.bulk_download import DEFAULT_INDEX_ZIPS
        for spec in DEFAULT_INDEX_ZIPS:
            assert spec["url"].startswith("https://www.tdx.com.cn/"), spec
