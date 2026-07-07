"""Sprint 10 · Query Facade (TdxChronos)

Phase 1 骨架: 仅暴露 TdxChronos class (方法 stub 后续 task 加)
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd


class TdxChronos:
    """5 类离线数据统一 facade · data_dir 必传 (零数据拷贝)

    Args:
        data_dir: 必传 · 数据根目录

    Attributes:
        data_dir: Path (resolved)
    """

    SUBDIRS_REQUIRED = [
        "parquet_compact",
        "fin/parsed",
        "gp",
        "index",
        "meta",
    ]
    FILES_REQUIRED = [
        "gp/records.parquet",
        "index/indices.parquet",
        "meta/meta.db",
    ]

    def __init__(self, data_dir: Path | str, *, readonly: bool = True) -> None:
        self.data_dir = Path(data_dir).resolve()
        if not self.data_dir.is_dir():
            raise FileNotFoundError(f"data_dir 不存在: {self.data_dir}")
        missing = []
        for sub in self.SUBDIRS_REQUIRED:
            if not (self.data_dir / sub).is_dir():
                missing.append(str(self.data_dir / sub))
        for f in self.FILES_REQUIRED:
            if not (self.data_dir / f).is_file():
                missing.append(str(self.data_dir / f))
        if missing:
            raise FileNotFoundError(
                f"data_dir 不完整 ({len(missing)}/8 缺失):\n  "
                + "\n  ".join(missing)
            )
        self.parquet_compact = self.data_dir / "parquet_compact"
        self.fin_parsed = self.data_dir / "fin" / "parsed"
        self.gp_records = self.data_dir / "gp" / "records.parquet"
        self.index_klines = self.data_dir / "index" / "indices.parquet"
        self.meta_db_path = self.data_dir / "meta" / "meta.db"
        self.readonly = readonly
        self._db: Optional[Any] = None
        if readonly:
            self._lock_for_readonly()

    def _lock_for_readonly(self):
        for p in [self.gp_records, self.index_klines, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR)
                except PermissionError:
                    pass

    def close(self):
        if not self.readonly:
            return
        for p in [self.gp_records, self.index_klines, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                except PermissionError as e:
                    raise RuntimeError(
                        f"close() failed to restore write permission on {p}: {e}. "
                        f"cron may be unable to write until manually chmod'd."
                    ) from e
        if self._db is not None:
            self._db.close()
            self._db = None

    # ─── Task 3: symbol_info + list_symbols ────────────────────────────────────

    def _ensure_db(self):
        """Lazy init MetaDB connection"""
        if self._db is None:
            from tdx_chronos.meta.db import MetaDB
            self._db = MetaDB(self.meta_db_path)
            self._db.init_schema()
        return self._db

    def symbol_info(self, symbol: str) -> Dict[str, Any]:
        """symbol metadata · 12,256 行中一行

        Args:
            symbol: 'sh600000' / 'sz000001' / 'bj838000'

        Returns:
            dict · 含 symbol/market/first_listing_date/record_count/source_zip
            找不到返回 {} (不 raise)
        """
        db = self._ensure_db()
        conn = db._connect()
        row = conn.execute(
            "SELECT * FROM symbol_metadata WHERE symbol = ?",
            (symbol.lower(),),
        ).fetchone()
        return dict(row) if row else {}

    def list_symbols(self, market: Optional[str] = None) -> List[str]:
        """list 全部 symbols (or 仅 sh/sz/bj)

        Args:
            market: None=all · 'sh'='sz'='bj'
        """
        db = self._ensure_db()
        conn = db._connect()
        if market:
            rows = conn.execute(
                "SELECT symbol FROM symbol_metadata WHERE market = ? ORDER BY symbol",
                (market.lower(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT symbol FROM symbol_metadata ORDER BY symbol"
            ).fetchall()
        return [r["symbol"] for r in rows]

    # ─── Task 4: kline (pyarrow predicate pushdown) ──────────────────────────

    def kline(
        self,
        symbol: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """K 线 · 单 symbol · pandas DataFrame (sorted by date ASC)

        Args:
            symbol: 'sh600000' / 'sz000001' / 'bj838000'
            start:  起始日期 (inclusive) · 'YYYY-MM-DD' or 'YYYYMMDD'
            end:    截止日期 (inclusive)
            columns:  子集 columns · None=全部

        Returns:
            DataFrame [date, open, high, low, close, volume, amount]
            找不到返回 empty DataFrame (不 raise)
        """
        import pyarrow.parquet as pq

        norm = _normalize_symbol(symbol)
        market = norm[:2]
        market_file = self.parquet_compact / f"{market}.parquet"

        if not market_file.exists():
            return pd.DataFrame()

        filters = [("symbol", "=", norm)]
        if start:
            filters.append(("date", ">=", _to_yyyymmdd_int(start)))
        if end:
            filters.append(("date", "<=", _to_yyyymmdd_int(end)))

        try:
            table = pq.read_table(market_file, filters=filters, columns=columns)
        except Exception:
            return pd.DataFrame()

        df = table.to_pandas()
        if not df.empty:
            # kline return cols: no symbol column (already used for predicate)
            if "symbol" in df.columns:
                df = df.drop(columns=["symbol"])
            df = df.sort_values("date").reset_index(drop=True)
        return df


def _normalize_symbol(symbol: str) -> str:
    """Normalize bare 6-digit codes to sh/sz/bj prefix"""
    s = symbol.lower().strip()
    if s.startswith(("sh", "sz", "bj")):
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("5", "6", "9")):
            return "sh" + s
        if s.startswith(("0", "2", "3")):
            return "sz" + s
        if s.startswith(("4", "8")):
            return "bj" + s
    return s


def _to_yyyymmdd_int(s: str) -> int:
    """'2024-01-02' → 20240102"""
    s = s.replace("-", "").replace("/", "")
    return int(s)
