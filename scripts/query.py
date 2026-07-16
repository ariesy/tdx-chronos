#!/usr/bin/env python3
"""tdx-chronos CLI query tool — JSON output for programmatic consumption.

Usage (from ai-berkshire):
    /app/tdx-chronos/.venv/bin/python /app/tdx-chronos/scripts/query.py <subcommand> [args]

All subcommands output JSON to stdout. Stderr reserved for diagnostics.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tdx_chronos import TdxChronos

DATA_DIR = Path("/app/tdx-chronos/data")



def cmd_symbol(args):
    tdx = TdxChronos(data_dir=DATA_DIR)
    try:
        info = tdx.symbol_info(args.code)
        if info:
            for k in list(info.keys()):
                v = info[k]
                if hasattr(v, 'isoformat'):
                    info[k] = v.isoformat()
                elif isinstance(v, Path):
                    info[k] = str(v)
        print(json.dumps(info, ensure_ascii=False, default=str))
    finally:
        tdx.close()


def cmd_kline(args):
    tdx = TdxChronos(data_dir=DATA_DIR)
    try:
        start = args.start if args.start else None
        end = args.end if args.end else None
        df = tdx.kline(args.code, start=start, end=end,
                       columns=args.columns.split(",") if args.columns else None)
        if df.empty:
            print(json.dumps([], ensure_ascii=False))
            return
        if args.limit:
            df = df.tail(int(args.limit))
        records = df.to_dict(orient="records")
        for r in records:
            if "date" in r:
                r["date"] = str(r["date"])
        print(json.dumps(records, ensure_ascii=False, default=str))
    finally:
        tdx.close()


def cmd_financials(args):
    tdx = TdxChronos(data_dir=DATA_DIR)
    try:
        report_date = args.quarter if args.quarter else None
        df = tdx.finance(args.code, report_date=report_date,
                         ratio_only=args.ratio_only)

        if df.empty:
            print(json.dumps([], ensure_ascii=False))
            return

        if args.fields:
            wanted = ["code", "report_date"] + args.fields.split(",")
            available = [c for c in wanted if c in df.columns]
            df = df[available]

        if args.latest:
            df = df.tail(1)

        records = df.to_dict(orient="records")
        for r in records:
            if "report_date" in r:
                r["report_date"] = str(r["report_date"])
            for k, v in list(r.items()):
                if hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
        print(json.dumps(records, ensure_ascii=False, default=str))
    finally:
        tdx.close()


def cmd_valuation(args):
    """Compute valuation metrics from latest K-line + FY2025 financial data."""
    tdx = TdxChronos(data_dir=DATA_DIR)
    try:
        info = tdx.symbol_info(args.code)
        if not info:
            print(json.dumps({"error": f"symbol not found: {args.code}"}, ensure_ascii=False))
            return

        # Latest K-line
        kl = tdx.kline(args.code, columns=["date", "close"])
        if kl.empty:
            print(json.dumps({"error": "no kline data"}, ensure_ascii=False))
            return
        latest_kl = kl.iloc[-1]
        price = float(latest_kl["close"])
        kl_date = str(latest_kl["date"])

        result = {
            "symbol": info.get("symbol", args.code),
            "price": price,
            "kl_date": kl_date,
            "first_listing_date": str(info.get("first_listing_date", "")),
        }

        # Financial data — use most recent annual report (1231-ending quarter)
        fin = tdx.finance(args.code)
        if not fin.empty:
            quarters = tdx.list_quarters()
            annual = sorted([q for q in quarters if str(q).endswith("1231")], reverse=True)
            fy_current = annual[0] if annual else 20251231
            fy_previous = annual[1] if len(annual) > 1 else fy_current - 10000
            fy_current_data = fin[fin["report_date"] == fy_current]
            if fy_current_data.empty:
                fy_current_data = fin.tail(1)
                fy_current = fy_current_data.iloc[0]["report_date"]
            row = fy_current_data.iloc[0]
            fin_date = str(row.get("report_date", ""))

            def _f(col):
                v = row.get(col)
                if v is None or (isinstance(v, float) and v == 0.0 and "业绩预告" in col):
                    return None
                try:
                    return round(float(v), 4)
                except (ValueError, TypeError):
                    return None

            eps = _f("基本每股收益")
            bps = _f("每股净资产")
            revenue_wan = _f("营业总收入(万元)")
            # 归母净利润: tdx stores in 元, use 近一年归母净利润（万元）for clarity
            net_profit = _f("近一年归母净利润（万元）")
            if net_profit is None:
                raw_np_yuan = _f("归属于母公司所有者的净利润")
                if raw_np_yuan:
                    net_profit = round(raw_np_yuan / 10000, 4)
            if net_profit is None:
                net_profit = _f("净利润")
                if net_profit and net_profit > 1000000:  # looks like 元 not 万元
                    net_profit = round(net_profit / 10000, 4)
            roe = _f("净资产收益率")
            gross_margin = _f("销售毛利率(%)(非金融类指标)")
            net_margin = _f("销售净利率(%)")

            # Balance sheet — tdx stores in 元, convert to 万元
            def _f_yuan(col):
                v = row.get(col)
                if v is None:
                    return None
                try:
                    return round(float(v) / 10000, 4)
                except (ValueError, TypeError):
                    return None

            total_assets = _f_yuan("资产总计")
            net_assets = _f_yuan("所有者权益（或股东权益）合计")
            if net_assets is None:
                net_assets = _f_yuan("归属于母公司股东权益(资产负债表)")
            if net_assets is None:
                bps_val = row.get("每股净资产")
                shares_from_eps = None
                np_val = row.get("归属于母公司所有者的净利润")
                eps_val = row.get("基本每股收益")
                if np_val and eps_val and float(eps_val) > 0:
                    shares_from_eps = float(np_val) / float(eps_val)
                if bps_val and shares_from_eps:
                    net_assets = round(float(bps_val) * shares_from_eps / 10000, 4)
            total_liabilities = _f_yuan("负债合计")
            op_cf_per_share = _f("每股经营性现金流(元)")
            fcf_per_share = _f("每股企业自由现金流")
            dividend_per_share = _f("每股股利(税前)")

            # Revenue growth: current year vs prior year (both in 万元)
            fy_previous_data = fin[fin["report_date"] == fy_previous]
            rev_growth = None
            if not fy_previous_data.empty and revenue_wan:
                prev_rev = fy_previous_data.iloc[0].get("营业总收入(万元)")
                if prev_rev and float(prev_rev) > 0:
                    rev_growth = round((float(revenue_wan) / float(prev_rev) - 1) * 100, 2)

            # Net profit growth: use 近一年归母净利润 columns (both in 万元)
            np_growth = None
            if not fy_previous_data.empty and net_profit:
                prev_np_wan = fy_previous_data.iloc[0].get("近一年归母净利润（万元）")
                if prev_np_wan is None:
                    prev_raw = fy_previous_data.iloc[0].get("归属于母公司所有者的净利润")
                    if prev_raw:
                        prev_np_wan = float(prev_raw) / 10000
                if prev_np_wan and float(prev_np_wan) > 0:
                    np_growth = round((float(net_profit) / float(prev_np_wan) - 1) * 100, 2)

            result.update({
                "fin_date": fin_date,
                "eps": eps,
                "bps": bps,
                "revenue_wan": revenue_wan,
                "net_profit_wan": net_profit,
                "roe_pct": roe,
                "gross_margin_pct": gross_margin,
                "net_margin_pct": net_margin,
                "total_assets_wan": total_assets,
                "net_assets_wan": net_assets,
                "total_liabilities_wan": total_liabilities,
                "op_cf_per_share": op_cf_per_share,
                "fcf_per_share": fcf_per_share,
                "dividend_per_share": dividend_per_share,
                "rev_growth_pct": rev_growth,
                "np_growth_pct": np_growth,
            })

            # Compute shares from raw NP/元 / raw EPS (most reliable)
            if eps and eps > 0:
                raw_np = float(row.get("归属于母公司所有者的净利润") or row.get("净利润") or 0)
                raw_eps = float(row.get("基本每股收益") or 0)
                if raw_np > 0 and raw_eps > 0:
                    shares = raw_np / raw_eps
                    result["total_shares_yi"] = round(shares / 1e8, 4)
                    result["market_cap_yi"] = round(price * shares / 1e8, 2)

                    if revenue_wan:
                        rev_total = float(revenue_wan) * 10000
                        result["ps"] = round(price * shares / rev_total, 2) if rev_total > 0 else None

            # Compute derived valuation metrics
            if eps and eps > 0:
                result["pe"] = round(price / eps, 2)
                result["earnings_yield_pct"] = round(eps / price * 100, 2)
            if bps and bps > 0:
                result["pb"] = round(price / bps, 2)
                if eps and eps > 0:
                    if roe is None:
                        result["roe_calc_pct"] = round(eps / bps * 100, 2)

            # Dividend yield
            if dividend_per_share and dividend_per_share > 0:
                result["dividend_yield_pct"] = round(dividend_per_share / price * 100, 2)

            # Debt ratio
            if total_assets and total_liabilities and total_assets > 0:
                result["debt_ratio_pct"] = round(total_liabilities / total_assets * 100, 2)

        print(json.dumps(result, ensure_ascii=False, default=str))
    finally:
        tdx.close()


def cmd_shareholders(args):
    tdx = TdxChronos(data_dir=DATA_DIR)
    try:
        if args.history:
            types = [int(t) for t in args.types.split(",")] if args.types else None
            df = tdx.shareholders_history(
                args.code, types=types,
                since_date=args.since, until_date=args.until,
                limit=int(args.limit) if args.limit else None,
            )
        else:
            df = tdx.shareholders(args.code)

        if df.empty:
            print(json.dumps([], ensure_ascii=False))
            return

        records = df.to_dict(orient="records")
        for r in records:
            if "date" in r:
                r["date"] = str(r["date"])
            for k, v in list(r.items()):
                if hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
        print(json.dumps(records, ensure_ascii=False, default=str))
    finally:
        tdx.close()


def cmd_search(args):
    """Search symbols by code substring (no name field in TDX metadata)."""
    tdx = TdxChronos(data_dir=DATA_DIR)
    try:
        query = args.code_prefix.lower().strip()
        clean = query.replace("sh", "").replace("sz", "").replace("bj", "")
        all_syms = tdx.list_symbols()

        results = []
        for sym in all_syms:
            if clean in sym.lower():
                info = tdx.symbol_info(sym)
                results.append({
                    "symbol": sym,
                    "market": info.get("market", ""),
                    "first_listing_date": str(info.get("first_listing_date", "")),
                    "record_count": info.get("record_count", 0),
                })
            if len(results) >= (int(args.limit) if args.limit else 50):
                break

        print(json.dumps(results, ensure_ascii=False, default=str))
    finally:
        tdx.close()


def cmd_health(args):
    tdx = TdxChronos(data_dir=DATA_DIR)
    try:
        report = tdx.doctor()
        print(json.dumps({
            "level": report.level,
            "summary": report.summary,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail or "",
                 "actual": str(c.actual) if c.actual is not None else None}
                for c in report.checks
            ],
            "total_passed": sum(1 for c in report.checks if c.passed),
            "total_checks": len(report.checks),
        }, ensure_ascii=False, default=str))
    finally:
        tdx.close()


def cmd_quarters(args):
    tdx = TdxChronos(data_dir=DATA_DIR)
    try:
        quarters = tdx.list_quarters()
        if args.latest:
            quarters = quarters[:int(args.latest)]
        print(json.dumps(quarters, ensure_ascii=False))
    finally:
        tdx.close()



def main():
    parser = argparse.ArgumentParser(description="tdx-chronos CLI query tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("symbol", help="Get symbol metadata")
    p.add_argument("code", help="Symbol code (e.g. sh688248 or 688248)")
    p.set_defaults(func=cmd_symbol)

    p = sub.add_parser("kline", help="Get daily K-line data")
    p.add_argument("code")
    p.add_argument("--start", default=None, help="Start date YYYYMMDD or YYYY-MM-DD")
    p.add_argument("--end", default=None, help="End date")
    p.add_argument("--columns", default=None, help="Comma-separated column list")
    p.add_argument("--limit", default=None, help="Return last N rows only")
    p.set_defaults(func=cmd_kline)

    p = sub.add_parser("financials", help="Get financial statement data")
    p.add_argument("code")
    p.add_argument("--quarter", default=None, help="Specific quarter YYYYMMDD")
    p.add_argument("--ratio-only", action="store_true", help="Only ratio-type columns")
    p.add_argument("--fields", default=None, help="Comma-separated field names")
    p.add_argument("--latest", action="store_true", help="Return latest row only")
    p.set_defaults(func=cmd_financials)

    p = sub.add_parser("valuation", help="Compute comprehensive valuation metrics")
    p.add_argument("code")
    p.set_defaults(func=cmd_valuation)

    p = sub.add_parser("shareholders", help="Get shareholder/capital records")
    p.add_argument("code")
    p.add_argument("--history", action="store_true", help="Use shareholders_history (with filters)")
    p.add_argument("--types", default=None, help="Comma-separated type IDs")
    p.add_argument("--since", default=None, help="Since date YYYYMMDD")
    p.add_argument("--until", default=None, help="Until date YYYYMMDD")
    p.add_argument("--limit", default=None, help="Max records")
    p.set_defaults(func=cmd_shareholders)

    p = sub.add_parser("search", help="Search symbols by code prefix (no name field in TDX metadata)")
    p.add_argument("code_prefix")
    p.add_argument("--limit", default="50")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("health", help="Run data health check")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("quarters", help="List available financial quarters")
    p.add_argument("--latest", default=None, help="Show only latest N quarters")
    p.set_defaults(func=cmd_quarters)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
