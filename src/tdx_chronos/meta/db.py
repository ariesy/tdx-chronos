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

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

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
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path) if str(db_path) != ":memory:" else db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ---------------------------------------------------------------------
    # Connection mgmt
    # ---------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Get (or create) the long-lived SQLite connection.

        - check_same_thread=False : Sprint 2 单线程够用
        - WAL : 读并发 + 顺序写
        - row_factory=Row : 列名访问
        - 默认 isolation_level (deferred · autocommit=False 隐式开事务)
          + 手动 BEGIN/COMMIT/ROLLBACK 控制点
        """
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
