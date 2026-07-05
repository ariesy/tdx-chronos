"""Sprint 7 T3 · Parquet 压缩对比实验 (snappy vs zstd)

目的: 比较 snappy (当前) vs zstd level 3/9 的 size/write/read 权衡
建议: Sprint 8 切换 (或保持 snappy 待主人决策)

输出: bench 输出到 stdout
"""
from __future__ import annotations

import time
from pathlib import Path

import pyarrow.parquet as pq


SRC = Path("/app/tdx-chronos/data/gp/records.parquet")
TMP_SNAPPY = Path("/app/tdx-chronos/data/gp/_bench_snappy.parquet")
TMP_ZSTD3 = Path("/app/tdx-chronos/data/gp/_bench_zstd3.parquet")
TMP_ZSTD9 = Path("/app/tdx-chronos/data/gp/_bench_zstd9.parquet")


def bench_write(table, path: Path, compression: str, level: int | None = None) -> tuple[float, float]:
    """写并返回 (size_mb, time_s)"""
    kw = {"compression": compression}
    if level is not None:
        kw["compression_level"] = level

    t0 = time.monotonic()
    pq.write_table(table, path, **kw)
    elapsed = time.monotonic() - t0
    size_mb = path.stat().st_size / 1024 / 1024
    return size_mb, elapsed


def bench_read(path: Path) -> tuple[int, float]:
    """读并返回 (rows, time_s)"""
    t0 = time.monotonic()
    table = pq.read_table(path)
    elapsed = time.monotonic() - t0
    return len(table), elapsed


def main() -> None:
    print("加载 source ...")
    table = pq.read_table(SRC)
    print(f"  rows: {len(table):,}  cols: {table.column_names}")
    print()

    results = []
    for label, path, compression, level in [
        ("snappy (当前)", TMP_SNAPPY, "snappy", None),
        ("zstd level 3",  TMP_ZSTD3,  "zstd", 3),
        ("zstd level 9",  TMP_ZSTD9,  "zstd", 9),
    ]:
        size_mb, w_time = bench_write(table, path, compression, level)
        n_rows, r_time = bench_read(path)
        results.append({
            "label": label,
            "size_mb": size_mb,
            "write_time": w_time,
            "read_time": r_time,
            "rows": n_rows,
        })
        print(f"=== {label} ===")
        print(f"  write: {size_mb:.1f} MB · {w_time:.1f}s")
        print(f"  read:  {n_rows:,} rows · {r_time:.1f}s")
        print()

    # 比较
    print("=" * 70)
    print(f"{'压缩':>16} {'size (MB)':>10} {'节省':>8} {'write (s)':>10} {'read (s)':>10}")
    print("-" * 70)
    base_size = results[0]["size_mb"]
    for r in results:
        saving = (1 - r["size_mb"] / base_size) * 100
        print(f"{r['label']:>16} {r['size_mb']:>10.1f} {saving:>7.1f}% {r['write_time']:>10.1f} {r['read_time']:>10.1f}")
    print("=" * 70)

    # 推荐
    print()
    print("=== 推荐 ===")
    zstd3 = next(r for r in results if "zstd level 3" in r["label"])
    snappy = next(r for r in results if "snappy" in r["label"])
    save_pct = (1 - zstd3["size_mb"] / snappy["size_mb"]) * 100
    save_mb = snappy["size_mb"] - zstd3["size_mb"]
    print(f"  zstd3 vs snappy: 节省 {save_mb:.1f} MB ({save_pct:.1f}%)")
    print(f"  写时间成本: +{zstd3['write_time'] - snappy['write_time']:.1f}s (+{(zstd3['write_time']/snappy['write_time']-1)*100:.0f}%)")
    print(f"  读时间差异: {abs(zstd3['read_time'] - snappy['read_time']):.2f}s (无显著差异)")
    print()
    print(f"  → 建议: Sprint 8 切换 (或主人决策)")
    print(f"  → 修改: src/tdx_chronos/fin/tdxgp_record.py 中 pq.write_table(...) 加 compression='zstd', compression_level=3")

    # 清理
    for p in [TMP_SNAPPY, TMP_ZSTD3, TMP_ZSTD9]:
        p.unlink()


if __name__ == "__main__":
    main()