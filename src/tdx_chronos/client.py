"""Sprint 10 · Query Facade (TdxChronos)

Phase 1 骨架: 仅暴露 TdxChronos class (方法 stub 后续 task 加)
"""
from __future__ import annotations

import logging
import os
import re
import stat
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


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
        self._index_klines_path = self.data_dir / "index" / "indices.parquet"
        self.meta_db_path = self.data_dir / "meta" / "meta.db"
        self.readonly = readonly
        self._db: Optional[Any] = None
        if readonly:
            self._lock_for_readonly()

    def _lock_for_readonly(self):
        for p in [self.gp_records, self._index_klines_path, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR)
                except PermissionError:
                    pass

    def close(self):
        if not self.readonly:
            return
        # 1. Release db connection FIRST (before any chmod that may fail)
        db, self._db = self._db, None
        if db is not None:
            db.close()
        # 2. Then restore chmod (may fail with RuntimeError; that's OK — caller will know)
        for p in [self.gp_records, self._index_klines_path, self.meta_db_path]:
            if p.is_file():
                try:
                    os.chmod(p, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                except PermissionError as e:
                    raise RuntimeError(
                        f"close() failed to restore write permission on {p}: {e}. "
                        f"cron may be unable to write until manually chmod'd."
                    ) from e

    # ─── Task 3: symbol_info + list_symbols ────────────────────────────────────

    def _ensure_db(self) -> Any:
        """Lazy init MetaDB connection"""
        if self._db is None:
            from tdx_chronos.meta.db import MetaDB
            self._db = MetaDB(self.meta_db_path)
            self._db.init_schema()
        return self._db

    def symbol_info(self, symbol: str) -> Dict[str, Any]:
        """symbol metadata lookup · returns dict or {} when not found

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
        """list symbols in meta.db

        Args:
            market: 'sh'/'sz'/'bj' filter · None=全部 3 个市场

        Returns:
            List[str] · sorted by symbol ASC
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
        norm = _normalize_symbol(symbol)
        if start and end and _to_yyyymmdd_int(start) > _to_yyyymmdd_int(end):
            raise ValueError(f"start ({start}) must be <= end ({end})")

        market = norm[:2]
        kline_path = self.parquet_compact / market / f"{norm}.parquet"

        if not kline_path.exists():
            return pd.DataFrame()

        filters = [("symbol", "=", norm)]
        if start:
            filters.append(("date", ">=", _to_yyyymmdd_int(start)))
        if end:
            filters.append(("date", "<=", _to_yyyymmdd_int(end)))

        try:
            table = pq.read_table(str(kline_path), filters=filters, columns=columns)
        except (pa.ArrowInvalid, OSError) as e:
            logging.warning("kline read failed for %s: %s", kline_path, e)
            return pd.DataFrame()

        df = table.to_pandas()
        if not df.empty:
            # kline return cols: no symbol column (already used for predicate)
            if "symbol" in df.columns:
                df = df.drop(columns=["symbol"])
            df = df.sort_values("date").reset_index(drop=True)
        return df

    # ─── Task 5: finance + shareholders + index_klines + list_quarters + doctor ─

    def finance(
        self,
        symbol: str,
        report_date: Optional[str] = None,
        ratio_only: bool = False,
    ) -> pd.DataFrame:
        """单 symbol 财务 · 多 quarter 默认

        Args:
            symbol: 'sh600000' 或 '600000'
            report_date: 单 quarter · None=全部 available
            ratio_only: True=仅 ratio 类型 columns (简化版)

        Returns:
            DataFrame 每行 = 1 个 (symbol, quarter) · 找不到返回 empty DataFrame
        """
        norm = _normalize_symbol(symbol)
        bare = norm[2:] if norm.startswith(("sh", "sz", "bj")) else norm

        files = sorted(self.fin_parsed.glob("gpcw*.parquet"))
        if not files:
            return pd.DataFrame()

        if report_date:
            target_yyyymmdd = _to_yyyymmdd_int(report_date)
            files = [
                f for f in files
                if f.stem.replace("gpcw", "") == str(target_yyyymmdd)
            ]
            if not files:
                return pd.DataFrame()

        rows = []
        for f in files:
            df = pd.read_parquet(f)
            if not df.empty:
                df = df.reset_index() if "code" not in df.columns else df
                match = df[df["code"].astype(str) == bare]
                if not match.empty:
                    rd = int(f.stem.replace("gpcw", ""))
                    match = match.assign(report_date=rd)
                    if ratio_only:
                        ratio_cols = [
                            c for c in match.columns
                            if "ratio" in c.lower() or "率" in c
                        ]
                        match = match[["code", "report_date"] + ratio_cols]
                    rows.append(match)
        return pd.concat(rows).reset_index(drop=True) if rows else pd.DataFrame()

    def shareholders(self, symbol: str) -> pd.DataFrame:
        """股本 · 按 symbol 过滤

        Args:
            symbol: 'sh600000'

        Returns:
            DataFrame (可能 empty) · 不 raise · 找不到返回 empty DataFrame
        """
        norm = _normalize_symbol(symbol)
        bare = norm[2:] if norm.startswith(("sh", "sz", "bj")) else norm
        try:
            table = pq.read_table(str(self.gp_records), filters=[("code", "=", bare)])
        except (pa.ArrowInvalid, OSError) as e:
            logging.warning("shareholders read failed for %s: %s", self.gp_records, e)
            return pd.DataFrame()
        df = table.to_pandas()
        if not df.empty and "symbol" not in df.columns:
            df = df.assign(symbol=df["market"] + df["code"])
        return df

    def index_klines(
        self,
        index_code: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """5 指数日线 · pandas DataFrame

        Args:
            index_code: 'sh000001'
            start: 起始日期 (inclusive) · 'YYYY-MM-DD' or 'YYYYMMDD'
            end:  截止日期 (inclusive)

        Returns:
            DataFrame sorted by date ASC · 找不到返回 empty DataFrame
        """
        code = index_code.lower()
        filters: List[tuple] = [("symbol", "=", code)]
        if start:
            filters.append(("date", ">=", _to_yyyymmdd_int(start)))
        if end:
            filters.append(("date", "<=", _to_yyyymmdd_int(end)))
        try:
            table = pq.read_table(str(self._index_klines_path), filters=filters)
        except (pa.ArrowInvalid, OSError) as e:
            logging.warning("index_klines read failed for %s: %s", self._index_klines_path, e)
            return pd.DataFrame()
        df = table.to_pandas()
        if not df.empty:
            df = df.sort_values("date").reset_index(drop=True)
        return df

    def list_quarters(self) -> List[str]:
        """list 已 parsed 季度 · 'YYYY-MM-DD' strings

        Returns:
            List[str] · sorted by date DESC (newest first: '2026-03-31', '2025-12-31', ...)
            Files not matching 8-digit date stem are skipped (defensive)
        """
        _QUARTER_STEM_RE = re.compile(r"^gpcw(\d{8})\.parquet$")
        dates: list[int] = []
        for f in self.fin_parsed.glob("gpcw*.parquet"):
            m = _QUARTER_STEM_RE.match(f.name)
            if m is None:
                continue
            dates.append(int(m.group(1)))
        dates.sort(reverse=True)
        return [_int_to_yyyymmdd_dash(d) for d in dates]

    def doctor(self) -> DoctorReport:
        """复用现有 Doctor().run()"""
        from tdx_chronos.doctor import Doctor  # lazy to avoid circular import
        return Doctor(
            meta_db_path=self.meta_db_path,
            parquet_root=self.data_dir,
        ).run()


def _int_to_yyyymmdd_dash(n: int) -> str:
    """20251231 → '2025-12-31'"""
    s = str(n)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _normalize_symbol(symbol: str) -> str:
    """Normalize bare 6-digit codes to sh/sz/bj prefix"""
    s = symbol.lower().strip()
    if s.startswith(("sh", "sz", "bj")):
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith("92"):                  # Sprint 12 T1 · 北交所新股优先
            return "bj" + s
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
