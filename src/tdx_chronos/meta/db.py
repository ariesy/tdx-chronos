"""TDX-chronos SQLite 元数据层 (v1.1 Sprint 2)

§四.A 持久化层 (SQLite 子集):
  - symbol_metadata  : 每只股票 1 行 (12,256 行 · sh/sz/bj)
  - download_log     : 每次下载 1 行 (5 zip · 月度 ~50 行)

设计决策 (Sprint 2):
  - 用 sqlite3 builtin (不引入 SQLAlchemy · v1.1 简化)
  - 1 个 long-lived connection (per MetaDB instance · 单线程足够)
  - PRAGMA journal_mode=WAL (并发读 + 顺序写)
  - PRAGMA synchronous=NORMAL (突发掉电丢 ≤ 1 事务 · 接受)
  - path 默认 'data/meta/meta.db' · 测试允许 :memory: (in-memory SQLite)

用法:
  >>> db = MetaDB('/tmp/test_meta.db')   # 真实路径
  >>> db.init_schema()
  >>> db.record_symbol('sh600000', 'sh', 19991110, 6338, 'hsjday.zip',
  ...                  'data/parquet/sh/sh600000.parquet')
  >>> db.record_download('hsjday.zip', 'data.tdx.com.cn', 540_000_000, 'abc...')
  >>> len(db.get_symbols_by_market('sh'))
  1
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Union

# Sprint 2 接受的 parse_status 取值
PARSE_STATUS_PENDING = "pending"
PARSE_STATUS_SUCCESS = "success"
PARSE_STATUS_FAILED = "failed"
PARSE_STATUS_PARTIAL = "partial"


class MetaDB:
    """SQLite 元数据 + 下载日志接口

    Attributes:
        db_path: SQLite 文件路径 · 测试可传 ':memory:'
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS symbol_metadata (
        symbol            TEXT PRIMARY KEY,
        market            TEXT NOT NULL,
        first_listing_date INTEGER NOT NULL,        -- YYYYMMDD
        last_parsed_at    TIMESTAMP,
        record_count      INTEGER,
        source_zip        TEXT NOT NULL,            -- 'hsjday.zip' 等
        parquet_path      TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_sym_market ON symbol_metadata(market);

    CREATE TABLE IF NOT EXISTS download_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        zip_name        TEXT NOT NULL,
        mirror          TEXT,                        -- 'data.tdx.com.cn' 等
        downloaded_at   TIMESTAMP NOT NULL,
        size_bytes      INTEGER,
        sha256          TEXT,
        parse_status    TEXT NOT NULL DEFAULT 'pending',
        error_msg       TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_dl_zip ON download_log(zip_name);

    CREATE TABLE IF NOT EXISTS gp_metadata (
        file_path        TEXT PRIMARY KEY,
        file_size        INTEGER NOT NULL,
        record_count     INTEGER NOT NULL,
        market           TEXT,                        -- 'sh' | 'sz' | 'bj' | '?'
        code             TEXT,                        -- 6-digit code
        first_date       INTEGER,                     -- YYYYMMDD (sample type=1 first)
        last_date        INTEGER,                     -- YYYYMMDD (sample type=1 last)
        parse_ok         INTEGER NOT NULL DEFAULT 0, -- 0/1
        error            TEXT,
        parsed_at        TIMESTAMP NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_gp_market ON gp_metadata(market);
    CREATE INDEX IF NOT EXISTS idx_gp_code ON gp_metadata(code);

    CREATE TABLE IF NOT EXISTS quarter_metadata (
        report_date      INTEGER PRIMARY KEY,        -- YYYYMMDD · e.g. 20260331
        file_path        TEXT NOT NULL,               -- 原始 gpcw{date}.zip/.dat 路径
        file_size        INTEGER,                     -- bytes
        stock_count      INTEGER,                     -- 解析出的股票数 (~5524)
        parquet_path     TEXT,                        -- 输出 parquet 路径
        is_placeholder   INTEGER NOT NULL DEFAULT 0,  -- 164B zip 占位 flag
        parsed_at        TIMESTAMP,
        parse_ok         INTEGER NOT NULL DEFAULT 0,  -- 0/1
        error            TEXT,
        file_mtime       REAL                         -- 原始文件 mtime (用于增量跳过判断)
    );
    CREATE INDEX IF NOT EXISTS idx_quarter_ok ON quarter_metadata(parse_ok);
    CREATE INDEX IF NOT EXISTS idx_quarter_placeholder ON quarter_metadata(is_placeholder);
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path) if str(db_path) != ":memory:" else db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ---------------------------------------------------------------------
    # Connection mgmt
    # ---------------------------------------------------------------------

    def _clean_stale_wal_files(self) -> None:
        """检测并清理 stale SQLite WAL/SHM 残留

        Sprint 10 集成测试期间,某次 sqlite3.connect() 在 umask 0o277 环境
        下创建了 400 权限 (-r--------) 的 meta.db-shm · owner 也不能写 ·
        下次 SQLite WAL 模式启动时 mmap 失败报 'attempt to write a readonly database'

        规则:
        - SHM 文件存在且权限 < 0o600 (owner 不可写) → 删 (SQLite 会重建)
        - WAL 文件存在且 0 字节 + 同目录无 SHM → 删 (stale,安全)
        - WAL 非 0 字节 → 保留 (可能含未提交事务,不碰)
        - :memory: DB → 跳过
        """
        import os
        if str(self.db_path) == ":memory:":
            return
        base = self.db_path.name
        parent = self.db_path.parent
        shm = parent / (base + "-shm")
        wal = parent / (base + "-wal")
        if shm.exists() and (shm.stat().st_mode & 0o777) < 0o600:
            logging.warning(
                "Removing stale SHM (mode=%04o): %s",
                shm.stat().st_mode & 0o777, shm,
            )
            shm.unlink()
        # 0 字节 WAL + SHM 已删 → 一定是 stale
        if wal.exists() and wal.stat().st_size == 0 and not shm.exists():
            wal.unlink()

    def _connect(self) -> sqlite3.Connection:
        """Get (or create) the long-lived SQLite connection.

        - check_same_thread=False : Sprint 2 单线程够用
        - WAL : 读并发 + 顺序写
        - row_factory=Row : 列名访问
        - 默认 isolation_level (deferred · autocommit=False 隐式开事务)
          + 手动 BEGIN/COMMIT/ROLLBACK 控制点
        """
        self._clean_stale_wal_files()  # ← Sprint 11 T9 hotfix
        if self._conn is None:
            if str(self.db_path) != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            # WAL 模式仅对磁盘 DB 有效 · :memory: 跳过
            if str(self.db_path) != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
        return self._conn

    def close(self) -> None:
        """关闭连接 · 测试必备"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # ---------------------------------------------------------------------
    # Schema
    # ---------------------------------------------------------------------

    def init_schema(self) -> None:
        """初始化 schema (idempotent)"""
        conn = self._connect()
        with self._txn() as cur:
            cur.executescript(self.SCHEMA)

    # ---------------------------------------------------------------------
    # CRUD · symbol_metadata
    # ---------------------------------------------------------------------

    def record_symbol(
        self,
        symbol: str,
        market: str,
        first_listing_date: int,
        record_count: int,
        source_zip: str,
        parquet_path: Optional[str] = None,
    ) -> None:
        """Upsert 1 行到 symbol_metadata

        Args:
            symbol:              e.g. 'sh600000'
            market:              'sh' / 'sz' / 'bj'
            first_listing_date:  YYYYMMDD
            record_count:        解析后记录数
            source_zip:          'hsjday.zip' 等
            parquet_path:        e.g. 'data/parquet/sh/sh600000.parquet'
        """
        conn = self._connect()
        now = datetime.now(timezone.utc).isoformat()
        with self._txn() as cur:
            # upsert via ON CONFLICT (SQLite ≥ 3.24)
            cur.execute(
                """
                INSERT INTO symbol_metadata
                    (symbol, market, first_listing_date, last_parsed_at,
                     record_count, source_zip, parquet_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    market = excluded.market,
                    first_listing_date = excluded.first_listing_date,
                    last_parsed_at = excluded.last_parsed_at,
                    record_count = excluded.record_count,
                    source_zip = excluded.source_zip,
                    parquet_path = excluded.parquet_path
                """,
                (symbol, market, first_listing_date, now,
                 record_count, source_zip, parquet_path),
            )

    def get_symbols_by_market(self, market: str) -> List[str]:
        """返回某市场全部 symbols (按 symbol 升序)"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT symbol FROM symbol_metadata WHERE market=? ORDER BY symbol",
            (market,),
        ).fetchall()
        return [r["symbol"] for r in rows]

    def get_symbol(self, symbol: str) -> Optional[dict]:
        """Sprint 12 T5a · public symbol metadata lookup

        Args:
            symbol: 归一化后的 symbol, e.g. 'sh600000'

        Returns:
            dict (含 symbol/market/first_listing_date/record_count/source_zip/...)
            or None if not found
        """
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM symbol_metadata WHERE symbol = ?",
            (symbol.lower(),),
        ).fetchone()
        return dict(row) if row else None

    def list_symbols(self, market: Optional[str] = None) -> List[str]:
        """Sprint 12 T5a · public symbol list (replaces client._connect() bypass)

        Args:
            market: 'sh' / 'sz' / 'bj' filter · None=全部 3 个市场 (case-insensitive)

        Returns:
            List[str] · sorted by symbol ASC
        """
        conn = self._connect()
        if market is not None:
            rows = conn.execute(
                "SELECT symbol FROM symbol_metadata WHERE market = ? ORDER BY symbol",
                (market.lower(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT symbol FROM symbol_metadata ORDER BY symbol"
            ).fetchall()
        return [r["symbol"] for r in rows]

    def get_unparsed_files(self, source_zip: str) -> List[str]:
        """返回某 zip 的未解析 symbols (供 cron 重跑用)"""
        conn = self._connect()
        # 没有 parquet_path 或 last_parsed_at IS NULL 的
        rows = conn.execute(
            """
            SELECT symbol FROM symbol_metadata
            WHERE source_zip=? AND (parquet_path IS NULL OR last_parsed_at IS NULL)
            ORDER BY symbol
            """,
            (source_zip,),
        ).fetchall()
        return [r["symbol"] for r in rows]

    def count_symbols(self) -> int:
        """总 symbol 数"""
        conn = self._connect()
        row = conn.execute("SELECT COUNT(*) AS c FROM symbol_metadata").fetchone()
        return row["c"]

    # ---------------------------------------------------------------------
    # CRUD · download_log
    # ---------------------------------------------------------------------

    def record_download(
        self,
        zip_name: str,
        mirror: Optional[str],
        size_bytes: Optional[int],
        sha256: Optional[str],
        parse_status: str = PARSE_STATUS_PENDING,
        error_msg: Optional[str] = None,
    ) -> int:
        """Insert 1 行到 download_log · 返回 rowid"""
        conn = self._connect()
        now = datetime.now(timezone.utc).isoformat()
        with self._txn() as cur:
            cur.execute(
                """
                INSERT INTO download_log
                    (zip_name, mirror, downloaded_at, size_bytes,
                     sha256, parse_status, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (zip_name, mirror, now, size_bytes, sha256,
                 parse_status, error_msg),
            )
            return cur.lastrowid

    def update_parse_status(
        self,
        log_id: int,
        status: str,
        error_msg: Optional[str] = None,
    ) -> None:
        """更新 download_log 行的状态"""
        if status not in {
            PARSE_STATUS_PENDING, PARSE_STATUS_SUCCESS,
            PARSE_STATUS_FAILED, PARSE_STATUS_PARTIAL,
        }:
            raise ValueError(f"Unknown parse_status: {status}")
        conn = self._connect()
        with self._txn() as cur:
            cur.execute(
                """
                UPDATE download_log
                SET parse_status=?, error_msg=?
                WHERE id=?
                """,
                (status, error_msg, log_id),
            )

    def get_recent_downloads(self, limit: int = 10) -> List[sqlite3.Row]:
        """最近 N 条 download_log 行 (按 id DESC)"""
        conn = self._connect()
        return conn.execute(
            "SELECT * FROM download_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def upgrade_pending_downloads(
        self,
        success_threshold: int = 1,
        success_status: str = PARSE_STATUS_SUCCESS,
    ) -> int:
        """升级 pending → success (Step 2/3/4 全部完成后批量调用)

        Args:
            success_threshold: 仅当总 success >= 此值才升级 (默认 1)
            success_status:    目标 status · 默认 'success'

        Returns:
            升级的行数 (cursor.rowcount)

        Example:
            >>> db = MetaDB('/path/meta.db')
            >>> # 跑完 Step 1-4 后调:
            >>> upgraded = db.upgrade_pending_downloads(success_threshold=5)
            >>> print(f'升级 {upgraded} 行')
        """
        if success_status not in {
            PARSE_STATUS_SUCCESS, PARSE_STATUS_PARTIAL, PARSE_STATUS_FAILED,
        }:
            raise ValueError(f"Unknown success_status: {success_status}")

        conn = self._connect()
        with self._txn() as cur:
            cur.execute(
                """
                UPDATE download_log
                SET parse_status=?, error_msg=NULL
                WHERE parse_status=? AND downloaded_at > datetime('now', '-7 days')
                """,
                (success_status, PARSE_STATUS_PENDING),
            )
            return cur.rowcount

    # ---------------------------------------------------------------------
    # CRUD · gp_metadata (Sprint 4a D2)
    # ---------------------------------------------------------------------

    def init_gp_metadata_schema(self) -> None:
        """创建 gp_metadata 表 (Sprint 4a D2 股本元信息)

        Note: SCHEMA 已包含 · 保留为公开 API 以便外部调用
        """
        conn = self._connect()
        with self._txn() as cur:
            cur.executescript(self.SCHEMA)

    def record_gp_metadata(
        self,
        file_path: str,
        file_size: int,
        record_count: int,
        market: str,
        code: str,
        first_date: Optional[int] = None,
        last_date: Optional[int] = None,
        parse_ok: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Upsert 1 行到 gp_metadata

        Args:
            file_path:    完整 .dat 路径
            file_size:    文件大小 (bytes)
            record_count: 13B record 数量
            market:       'sh'/'sz'/'bj'/'?'
            code:         6 位股票代码
            first_date:   最早 type=1 季末记录 (YYYYMMDD)
            last_date:    最晚 type=1 季末记录 (YYYYMMDD)
            parse_ok:     True/False
            error:        失败原因 (parse_ok=True 时 None)
        """
        conn = self._connect()
        now = datetime.now(timezone.utc).isoformat()
        with self._txn() as cur:
            cur.execute(
                """
                INSERT INTO gp_metadata
                    (file_path, file_size, record_count, market, code,
                     first_date, last_date, parse_ok, error, parsed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_size = excluded.file_size,
                    record_count = excluded.record_count,
                    market = excluded.market,
                    code = excluded.code,
                    first_date = excluded.first_date,
                    last_date = excluded.last_date,
                    parse_ok = excluded.parse_ok,
                    error = excluded.error,
                    parsed_at = excluded.parsed_at
                """,
                (file_path, file_size, record_count, market, code,
                 first_date, last_date, 1 if parse_ok else 0,
                 error, now),
            )

    def count_gp_metadata(self, parse_ok: Optional[bool] = None) -> int:
        """gp_metadata 总数 / parse_ok 过滤"""
        conn = self._connect()
        if parse_ok is None:
            row = conn.execute("SELECT COUNT(*) AS c FROM gp_metadata").fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM gp_metadata WHERE parse_ok=?",
                (1 if parse_ok else 0,),
            ).fetchone()
        return row["c"]

    def get_gp_market_stats(self) -> List[sqlite3.Row]:
        """按 market 统计 (sh/sz/bj/? · parse_ok=True only)"""
        conn = self._connect()
        return conn.execute(
            """
            SELECT market, COUNT(*) AS file_count, SUM(file_size) AS total_bytes,
                   SUM(record_count) AS total_records
            FROM gp_metadata
            WHERE parse_ok=1
            GROUP BY market
            ORDER BY market
            """,
        ).fetchall()

    def get_gp_failed(self, limit: int = 50) -> List[sqlite3.Row]:
        """返回 parse_ok=False 的行 (错误率报表)"""
        conn = self._connect()
        return conn.execute(
            "SELECT * FROM gp_metadata WHERE parse_ok=0 ORDER BY file_path LIMIT ?",
            (limit,),
        ).fetchall()

    # ---------------------------------------------------------------------
    # CRUD · quarter_metadata (Sprint 8 T1 · 财务领域元信息)
    # ---------------------------------------------------------------------

    def init_quarter_metadata_schema(self) -> None:
        """创建 quarter_metadata 表 (Sprint 8 T1)

        Note: SCHEMA 已包含 · 保留为公开 API 以便外部调用
        Note: 对已有 DB,使用 PRAGMA table_info 检查 file_mtime 列是否存在,不存在则 ALTER TABLE ADD (Sprint 11 T1)
        """
        conn = self._connect()
        with self._txn() as cur:
            cur.executescript(self.SCHEMA)
        # Sprint 11 T1: 迁移已有 quarter_metadata 表 (无 file_mtime 列)
        conn = self._connect()
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(quarter_metadata)").fetchall()}
        if "file_mtime" not in cols:
            with self._txn() as cur:
                cur.execute("ALTER TABLE quarter_metadata ADD COLUMN file_mtime REAL")

    def record_quarter_metadata(
        self,
        report_date: int,
        file_path: str,
        file_size: int,
        stock_count: int,
        parquet_path: Optional[str] = None,
        is_placeholder: bool = False,
        parse_ok: bool = True,
        error: Optional[str] = None,
        file_mtime: Optional[float] = None,
    ) -> None:
        """Upsert 1 行到 quarter_metadata

        Args:
            report_date:    YYYYMMDD (e.g. 20260331)
            file_path:      原始 gpcw{date}.zip 或 .dat 路径
            file_size:      文件大小 (bytes)
            stock_count:    解析出的股票数 (~5524)
            parquet_path:   输出 parquet 路径
            is_placeholder: 164B zip 占位 (未来季未披露)
            parse_ok:       True/False
            error:          失败原因 (parse_ok=True 时 None)
            file_mtime:     原始文件的 mtime (用于增量跳过判断)
        """
        conn = self._connect()
        now = datetime.now(timezone.utc).isoformat()
        with self._txn() as cur:
            cur.execute(
                """
                INSERT INTO quarter_metadata
                    (report_date, file_path, file_size, stock_count,
                     parquet_path, is_placeholder, parsed_at,
                     parse_ok, error, file_mtime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_date) DO UPDATE SET
                    file_path = excluded.file_path,
                    file_size = excluded.file_size,
                    stock_count = excluded.stock_count,
                    parquet_path = excluded.parquet_path,
                    is_placeholder = excluded.is_placeholder,
                    parsed_at = excluded.parsed_at,
                    parse_ok = excluded.parse_ok,
                    error = excluded.error,
                    file_mtime = excluded.file_mtime
                """,
                (report_date, file_path, file_size, stock_count,
                 parquet_path, 1 if is_placeholder else 0, now,
                 1 if parse_ok else 0, error, file_mtime),
            )

    def should_skip_quarter(self, report_date: int, raw_path: Union[str, Path]) -> bool:
        """判断 quarter 是否可跳过 (已 parse_ok 且 mtime 未变)

        Args:
            report_date: YYYYMMDD (e.g. 20260331)
            raw_path:    原始 .dat/.zip 路径

        Returns:
            True = 跳过, False = 需要 parse
        """
        conn = self._connect()
        raw_path = Path(raw_path)
        if not raw_path.exists():
            return False  # 文件不在,留给 caller 处理
        file_mtime = raw_path.stat().st_mtime
        row = conn.execute(
            """
            SELECT parse_ok, parsed_at, file_mtime
            FROM quarter_metadata WHERE report_date = ?
            """,
            (report_date,),
        ).fetchone()
        if row is None:
            return False  # 无 record,需要 parse
        parse_ok = row["parse_ok"]
        db_mtime = row["file_mtime"]
        if not parse_ok:
            return False  # 之前 failed,重试
        # 关键: 用 file_mtime 比较,不用 parsed_at(后者是 wall clock)
        if db_mtime is None or db_mtime < file_mtime:
            return False  # DB 无 mtime 记录 或 mtime 变化
        return True

    def get_quarters(
        self,
        parsed_only: bool = False,
        exclude_placeholders: bool = False,
    ) -> List[int]:
        """返回 quarter_metadata 全部 report_date (按时间升序)

        Args:
            parsed_only:         仅 parse_ok=1
            exclude_placeholders: 排除 is_placeholder=1
        """
        conn = self._connect()
        clauses = []
        params: list = []
        if parsed_only:
            clauses.append("parse_ok=1")
        if exclude_placeholders:
            clauses.append("is_placeholder=0")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT report_date FROM quarter_metadata {where} ORDER BY report_date",
            params,
        ).fetchall()
        return [r["report_date"] for r in rows]

    def count_quarters(
        self,
        parse_ok: Optional[bool] = None,
        exclude_placeholders: bool = False,
    ) -> int:
        """quarter_metadata 总数 / parse_ok 过滤"""
        conn = self._connect()
        clauses = []
        params: list = []
        if parse_ok is not None:
            clauses.append("parse_ok=?")
            params.append(1 if parse_ok else 0)
        if exclude_placeholders:
            clauses.append("is_placeholder=0")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        row = conn.execute(
            f"SELECT COUNT(*) AS c FROM quarter_metadata {where}", params,
        ).fetchone()
        return row["c"]

    def get_quarter_stats(self) -> List[sqlite3.Row]:
        """按 parse_ok × is_placeholder 聚合统计

        Returns: rows of (parse_ok, is_placeholder, count, total_stocks)
        """
        conn = self._connect()
        return conn.execute(
            """
            SELECT parse_ok, is_placeholder, COUNT(*) AS q_count,
                   SUM(stock_count) AS total_stocks,
                   SUM(file_size) AS total_bytes
            FROM quarter_metadata
            GROUP BY parse_ok, is_placeholder
            ORDER BY parse_ok DESC, is_placeholder DESC
            """,
        ).fetchall()

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    @contextmanager
    def _txn(self) -> Iterator[sqlite3.Cursor]:
        """简单事务上下文 (commit on success · rollback on exception)

        使用 sqlite3 默认 isolation_level:
        - conn.execute() 自动 BEGIN (隐式)
        - 我们不需要 BEGIN/COMMIT · 直接 cursor.execute(COMMIT/ROLLBACK) 控制
        - 测试 :memory: db 在退出 yield 后 ROLLBACK 不报错 (无 active txn)
          时跳过失败 · 用 try/except wrapped
        """
        conn = self._connect()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except sqlite3.OperationalError:
                pass
            raise
        finally:
            cur.close()
