"""TDX-chronos Bulk Downloader (v1.1 Sprint 3a · 1d 简化版)

§四.5 / §四.6 官方下载源 + §七 P0 #3 包级重试化解

设计:
  - 单镜像 (data.tdx.com.cn · Sprint 5 cron 完整化 + 备)
  - 断点续传 (HTTP Range request)
  - 在线算 SHA256 (无 fixed hash 表维护)
  - 包级重试 3 次 (5 zip × 3 ≈ 0.0003% 失败率 · 化解 P0 #3)
  - meta.db record_download 追溯 (§四.A)

用法:
    >>> dl = BulkDownloader()
    >>> summary = dl.download_all(
    ...     snap_dir='/app/tdx-chronos/data/snapshot/2026-07-04',
    ...     db_path='/app/tdx-chronos/data/meta/meta.db',
    ... )
    >>> summary.success_count
    3
"""
from __future__ import annotations

import errno
import hashlib
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Type
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


# Sprint 14 · Condition-based retry policy
# (incident: 2026-07-14 ENOSPC retry 空转 5 zip × 3 次 × 5-15s = 数分钟浪费)
DEFAULT_TRANSIENT_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

DEFAULT_TERMINAL_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    KeyboardInterrupt,
    PermissionError,
)


@dataclass
class RetryPolicy:
    """Condition-based retry policy for bulk_download.

    **Sprint 14 motivation**: previous behavior retried on *every* exception up
    to ``max_retries`` times. For terminal conditions (ENOSPC, 404, KeyboardInterrupt)
    this wastes seconds-to-minutes per zip × 5 zips = minutes of pointless sleep.

    New behavior:
      * **Transient** exceptions (network glitch, server 5xx) → retry with backoff
      * **Terminal** exceptions (ENOSPC / ENOMEM / 4xx / auth) → fail-fast, 0 retry
      * Errors not in either set fall through to default retry behavior (backwards compat)

    Args:
        max_retries:        max transient retry count (default 3)
        backoff_schedule:   sleep seconds between retries; len(max_retries) recommended
        transient_exceptions: tuple of exception classes that trigger retry
        terminal_exceptions:  tuple of exception classes that skip retry and fail
        terminal_os_errno:    specific ``OSError.errno`` values that are terminal
                              (default: ENOSPC, ENOMEM, EROFS — never self-heal)
    """

    max_retries: int = 3
    backoff_schedule: Tuple[float, ...] = (5.0, 10.0, 15.0)
    transient_exceptions: Tuple[Type[Exception], ...] = field(
        default_factory=lambda: DEFAULT_TRANSIENT_EXCEPTIONS,
    )
    terminal_exceptions: Tuple[Type[Exception], ...] = field(
        default_factory=lambda: DEFAULT_TERMINAL_EXCEPTIONS,
    )
    terminal_os_errno: Tuple[int, ...] = (
        errno.ENOSPC,
        errno.ENOMEM,
        errno.EROFS,
        errno.EFBIG,
    )

    def classify(self, exc: Exception) -> str:
        """Return one of: ``'terminal'``, ``'transient'``, ``'unknown'``.

        Unknown errors fall back to legacy retry behavior (treated as transient)
        for backward compat — operators can override policy to tighten this.

        Order matters: explicit terminal first, then requests HTTPError (which
        is itself a subclass of OSError — must check before generic OSError),
        then plain OSError by errno, then explicit transient.
        """
        # Explicit terminal types first
        for cls in self.terminal_exceptions:
            if isinstance(exc, cls):
                return "terminal"
        # requests HTTPError BEFORE generic OSError (HTTPError <: OSError in mro)
        if isinstance(exc, requests.exceptions.HTTPError):
            resp = getattr(exc, "response", None)
            if resp is not None and getattr(resp, "status_code", 500) < 500:
                return "terminal"
            return "transient"
        # Generic OSError with specific errno
        if isinstance(exc, OSError):
            if exc.errno in self.terminal_os_errno:
                return "terminal"
            # Other OSError (EIO, etc.) → transient (may be I/O flake)
            return "transient"
        # Explicit transient
        for cls in self.transient_exceptions:
            if isinstance(exc, cls):
                return "transient"
        return "unknown"


# 5 个核心 zip（v1.1 主路径）—— 指数 5 个 zip 在 Sprint 4b/Sprint 5 cron 加
DEFAULT_ZIPS: List[dict] = [
    {
        "name": "hsjday",
        "url": "https://data.tdx.com.cn/vipdoc/hsjday.zip",
        "approx_size": 540_000_000,
        "contains": "sh 5,880 + sz 5,788 + bj 588 · 35 年 .day",
    },
    {
        "name": "tdxfin",
        "url": "https://data.tdx.com.cn/vipdoc/tdxfin.zip",
        "approx_size": 537_000_000,
        "contains": "297 文件 · 1989→2026 季报 .dat/.zip",
    },
    {
        "name": "tdxgp",
        "url": "https://data.tdx.com.cn/vipdoc/tdxgp.zip",
        "approx_size": 666_000_000,
        "contains": "7,573 股本 .dat · sh/sz/bj + 场内基金 / 可转债",
    },
]

# Sprint 4b D2 指数 zip (主机 www.tdx.com.cn · 速度较慢 ~0.27 MB/s)
DEFAULT_INDEX_ZIPS: List[dict] = [
    {
        "name": "shzsday",
        "url": "https://www.tdx.com.cn/products/data/data/vipdoc/shzsday.zip",
        "approx_size": 27_000_000,
        "contains": "上证综指 000001.SH",
    },
    {
        "name": "szzsday",
        "url": "https://www.tdx.com.cn/products/data/data/vipdoc/szzsday.zip",
        "approx_size": 36_000_000,
        "contains": "深证成指 399001.SZ",
    },
    {
        "name": "tdxzs_day",
        "url": "https://www.tdx.com.cn/products/data/data/vipdoc/tdxzs_day.zip",
        "approx_size": 78_000_000,
        "contains": "通达信板块指数 (含沪深300/创业板/科创50)",
    },
]


@dataclass
class ZipResult:
    """单个 zip 下载结果

    Attributes:
        zip_name:        e.g. 'hsjday'
        url:             完整 URL
        output_path:     落盘路径 · snap_dir/{name}.zip
        size_bytes:      实际下载字节
        sha256:          64-hex 在线算
        duration_seconds: 总耗时 (含重试)
        retry_count:     重试次数 · 0/1/2/3
        status:          'success' / 'failed'
        error:           失败原因 (success 时为 None)
    """

    zip_name: str
    url: str
    output_path: Path
    size_bytes: int
    sha256: str
    duration_seconds: float
    retry_count: int
    status: str
    error: Optional[str]


@dataclass
class DownloadSummary:
    """多 zip 批量下载总结"""

    snap_dir: Path
    start_at: datetime
    end_at: datetime
    results: List[ZipResult]

    @property
    def total_size(self) -> int:
        return sum(r.size_bytes for r in self.results)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.status == "success")

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    @property
    def total_seconds(self) -> float:
        return (self.end_at - self.start_at).total_seconds()


class BulkDownloader:
    """5 zip 批量下载器 (Sprint 3a 主入口)

    Args:
        mirror: 镜像主机 (Sprint 3a 默认 'data.tdx.com.cn')
        chunk_size: 流式下载 chunk 大小 (128 KB · 平衡内存和吞吐)
        timeout: 每次请求超时 (秒)
    """

    def __init__(
        self,
        mirror: str = "data.tdx.com.cn",
        chunk_size: int = 128 * 1024,
        timeout: int = 60,
    ):
        self.mirror = mirror
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.session = requests.Session()
        # 友好 UA（防 403 · TDX 站点有时拒绝默认 python-requests）
        self.session.headers.update(
            {
                "User-Agent": "tdx-chronos/1.1 (+https://github.com/ariesy/tdx-chronos)",
            }
        )

    # ---------------------------------------------------------------------
    # 单文件下载 (含重试 + 断点续传 + SHA256)
    # ---------------------------------------------------------------------

    def download_one(
        self,
        zip_spec: dict,
        snap_dir: Path,
        max_retries: int = 3,
        retry_policy: Optional[RetryPolicy] = None,
    ) -> ZipResult:
        """下载 1 个 zip · 包级重试 max_retries 次

        Args:
            zip_spec:   DEFAULT_ZIPS 的元素 · {name, url, approx_size, contains}
            snap_dir:   输出顶层 · $snap_dir/$name.zip 落盘
            max_retries: 最大重试 (默认 3 · 委员会 P0 #3 化解)
            retry_policy: Optional RetryPolicy (Sprint 14) · None = default
                          RetryPolicy(max_retries=max_retries).

        Returns:
            ZipResult · 含 status='success' / 'failed'

        Behavior (Sprint 14 condition-based retry):
          * Terminal errors (ENOSPC, ENOMEM, 4xx, KeyboardInterrupt, PermissionError)
            → fail immediately with retry_count=0
          * Transient errors (ConnectionError, Timeout, 5xx) → retry up to
            ``max_retries`` with backoff
          * Unknown errors fall back to legacy retry behavior
        """
        name = zip_spec["name"]
        url = zip_spec["url"]
        out_path = snap_dir / f"{name}.zip"
        snap_dir.mkdir(parents=True, exist_ok=True)

        if retry_policy is None:
            retry_policy = RetryPolicy(max_retries=max_retries)

        start = time.monotonic()
        retry_count = 0
        last_error = None

        for attempt in range(1, retry_policy.max_retries + 1):
            try:
                size, sha = self._download_with_resume(
                    url, out_path, zip_spec["approx_size"],
                )
                duration = time.monotonic() - start
                # 成功时 retry_count = 已失败过的次数 (attempt - 1)
                return ZipResult(
                    zip_name=name,
                    url=url,
                    output_path=out_path,
                    size_bytes=size,
                    sha256=sha,
                    duration_seconds=duration,
                    retry_count=attempt - 1,
                    status="success",
                    error=None,
                )
            except Exception as exc:
                classification = retry_policy.classify(exc)
                last_error = str(exc)

                if classification == "terminal":
                    logger.error(
                        "Terminal error %s (no retry, errno=%s): %s",
                        name, getattr(exc, "errno", None), exc,
                    )
                    # 立即失败, 不等 backoff, 不计入 retry count
                    retry_count = 0
                    last_error = f"terminal: {last_error}"
                    break

                retry_count = attempt - 1
                logger.warning(
                    "Failed %s attempt %d/%d (classification=%s): %s",
                    name, attempt, retry_policy.max_retries, classification, exc,
                )
                # 退避: 第 N 次失败 backoff_schedule[N-1] 秒 (默认 5/10/15)
                if attempt < retry_policy.max_retries:
                    idx = min(attempt - 1, len(retry_policy.backoff_schedule) - 1)
                    time.sleep(retry_policy.backoff_schedule[idx])

        # 全部 retry 后失败
        duration = time.monotonic() - start
        return ZipResult(
            zip_name=name,
            url=url,
            output_path=out_path,
            size_bytes=out_path.stat().st_size if out_path.exists() else 0,
            sha256="",
            duration_seconds=duration,
            retry_count=retry_count,
            status="failed",
            error=last_error[:500] if last_error else "unknown",
        )

    def _download_with_resume(
        self,
        url: str,
        out_path: Path,
        approx_size: int,
    ) -> tuple[int, str]:
        """HTTP Range 断点续传 + 流式 + SHA256 在线算

        Returns:
            (size_bytes, sha256_hex)
        """
        # 先 HEAD 拿 Content-Length
        head = self.session.head(url, timeout=self.timeout, allow_redirects=True)
        head.raise_for_status()
        total = int(head.headers.get("Content-Length", approx_size))

        # 已下载部分 (断点续传) · 检查现有文件
        existing_size = out_path.stat().st_size if out_path.exists() else 0
        if existing_size >= total:
            # 已完整下载 · 算 SHA256
            sha = self._sha256_file(out_path)
            return existing_size, sha

        # Range 请求
        headers = {}
        if 0 < existing_size < total:
            headers["Range"] = f"bytes={existing_size}-"
        # mode='ab' 追加 · 'wb' 覆盖
        mode = "ab" if existing_size > 0 else "wb"

        sha = hashlib.sha256()
        if existing_size > 0:
            # 哈希初始化 (读已下载部分)
            with open(out_path, "rb") as f:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    sha.update(chunk)

        # 流式 GET
        with self.session.get(
            url, headers=headers, timeout=self.timeout, stream=True,
        ) as resp:
            if resp.status_code not in (200, 206):
                raise IOError(
                    f"HTTP {resp.status_code} for {url} "
                    f"(Content-Length={total}, existing={existing_size})"
                )
            with open(out_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    if chunk:  # filter out keep-alive chunks
                        f.write(chunk)
                        sha.update(chunk)

        final_size = out_path.stat().st_size
        if final_size != total:
            raise IOError(
                f"Size mismatch for {out_path.name}: "
                f"expected {total}, got {final_size}"
            )
        return final_size, sha.hexdigest()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(128 * 1024)
                if not chunk:
                    break
                sha.update(chunk)
        return sha.hexdigest()

    # ---------------------------------------------------------------------
    # 批量 + 集成 meta.db + 解压
    # ---------------------------------------------------------------------

    def download_all(
        self,
        snap_dir: Path,
        zips: Optional[List[dict]] = None,
        max_retries: int = 3,
        db_path: Optional[Path] = None,
        unzip: bool = True,
    ) -> DownloadSummary:
        """5 zip 批量下载 + (可选) 解压 + meta.db 追溯

        Args:
            snap_dir:    顶层目录 · $snap_dir/{name}.zip 落盘
            zips:        默认 DEFAULT_ZIPS
            max_retries: 包级重试 (默认 3)
            db_path:     Optional MetaDB 路径 · 提供则 record_download
            unzip:       是否解压到 $snap_dir/raw/ (供 Sprint 2 official_zip.py 用)
        """
        zips = zips or DEFAULT_ZIPS
        snap_dir = Path(snap_dir)
        snap_dir.mkdir(parents=True, exist_ok=True)

        start_at = datetime.now(timezone.utc)
        results: List[ZipResult] = []

        # 延迟 import 避免循环引用 (db.py imports sources? 不 · 是 sources imports db)
        from tdx_chronos.meta.db import MetaDB  # type: ignore

        # 用 with 自动 close
        db_ctx = MetaDB(db_path) if db_path else None
        if db_ctx is not None:
            db_ctx.init_schema()

        try:
            for spec in zips:
                result = self.download_one(
                    spec, snap_dir, max_retries=max_retries,
                )
                results.append(result)
                if db_ctx is not None:
                    db_ctx.record_download(
                        zip_name=result.zip_name,
                        mirror=self.mirror,
                        size_bytes=result.size_bytes,
                        sha256=result.sha256,
                        parse_status=(
                            "pending" if result.status == "success"
                            else "failed"
                        ),
                        error_msg=result.error,
                    )
            # 解压 raw 子目录
            if unzip:
                for result in results:
                    if result.status == "success" and result.output_path.exists():
                        self._unzip_into_raw(result.output_path, snap_dir / "raw")
        finally:
            if db_ctx is not None:
                db_ctx.close()

        end_at = datetime.now(timezone.utc)
        return DownloadSummary(
            snap_dir=snap_dir,
            start_at=start_at,
            end_at=end_at,
            results=results,
        )

    # ---------------------------------------------------------------------
    # Sprint 4b D2 指数 zip 下载 (主机 www.tdx.com.cn)
    # ---------------------------------------------------------------------

    def download_index(
        self,
        snap_dir: Path,
        zips: Optional[List[dict]] = None,
        max_retries: int = 3,
        db_path: Optional[Path] = None,
        unzip: bool = True,
    ) -> DownloadSummary:
        """3 指数 zip 下载 (www.tdx.com.cn · 较慢 ~0.27 MB/s)

        Args:
            snap_dir:    顶层目录 · $snap_dir/{name}.zip 落盘
            zips:        默认 DEFAULT_INDEX_ZIPS
            max_retries: 包级重试 (默认 3)
            db_path:     Optional MetaDB 路径
            unzip:       是否解压到 $snap_dir/raw/

        Returns:
            DownloadSummary · 含 3 zip 结果
        """
        return self.download_all(
            snap_dir=snap_dir,
            zips=zips or DEFAULT_INDEX_ZIPS,
            max_retries=max_retries,
            db_path=db_path,
            unzip=unzip,
        )

    @staticmethod
    def _unzip_into_raw(zip_path: Path, raw_dir: Path) -> Path:
        """unzip to raw/{sh,sz,bj}/lday/*.day

        注: 通达信 zip 使用 Windows 风格反斜杠路径（\"sh\\lday\\sh000001.day\"）
        unzip 报警 'backslashes as path separators' 但仍正常解压 · exit 1 (warning)
        → check=False + 验证文件落盘数 (预期总文件数) 判定成功
        """
        raw_dir.mkdir(parents=True, exist_ok=True)
        # 先获预期文件数
        list_result = subprocess.run(
            ["unzip", "-l", str(zip_path)],
            capture_output=True,
            text=True,
            check=False,  # unzip -l 也可能 exit 1 (windows path warning)
        )
        expected_files = 0
        for line in list_result.stdout.splitlines():
            line = line.strip()
            # e.g. '22880  2026-07-03 15:38   sh\\lday\\sh000001.day'
            parts = line.split()
            if (
                len(parts) >= 4
                and parts[0].isdigit()
                and not line.startswith("-")
                and not line.startswith("Archive")
            ):
                expected_files += 1

        # 实际解压 (check=False · 容忍 backslash warning)
        subprocess.run(
            [
                "unzip", "-q", "-o",
                str(zip_path),
                "-d", str(raw_dir),
            ],
            check=False,
        )

        # 验证: 实际落盘文件数 == 预期
        actual_files = sum(1 for _ in raw_dir.rglob("*") if _.is_file())
        if expected_files > 0 and actual_files < expected_files:
            raise IOError(
                f"unzip incomplete for {zip_path.name}: "
                f"expected {expected_files} files, got {actual_files}"
            )
        return raw_dir
