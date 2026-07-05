"""Sprint 7 T1 · 摸排未分类 28 types 的样本

对每个未分类 type (Sprint 6 后 type 1-48 中 CATEGORY_BUCKETS 不包含的):
- 从 5 只大蓝筹各取 5 条 sample
- 输出: data/research/type_samples.csv

设计原则 (内存安全):
- 单次 read_table + pc.filter 分类型取样本
- 不重复加载 587 MB parquet
- 取 sample 逻辑: 每只股票 + 每 type 用 pc.filter + slice(0, 5)

用法:
    PYTHONPATH=src:vendor/_vendor python3 scripts/sample_uncategorized_types.py

输出:
    code, type, sample_date, sample_value_1, sample_value_2, sample_market,
    sample_value_1_human, sample_value_2_human, category, confidence
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

# 让脚本能 import tdx_chronos
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vendor" / "_vendor"))

from tdx_chronos.fin.tdxgp_types import (  # noqa: E402
    CATEGORY_BUCKETS,
    TYPE_CATEGORY_MAPPING,
    get_category,
    get_confidence,
    get_type_name,
)


RECORDS_PATH = Path("/app/tdx-chronos/data/gp/records.parquet")
OUTPUT_CSV = Path("/app/tdx-chronos/data/research/type_samples.csv")

# 28 个未分类 types (Sprint 6 摸排实证)
UNCATEGORIZED_TYPES = sorted([
    2, 4, 5, 6, 7, 8, 9, 10, 14, 15, 17, 18, 19, 20,
    21, 22, 23, 24, 26, 28, 29, 30, 32, 33, 34, 35, 37,
    41, 42, 43, 44, 45, 46, 48,
])

# 5 只大蓝筹: 茅台/平安/招行/石化/中信
SAMPLE_CODES = ["600519", "601318", "600036", "600028", "600030"]

# 每只股票 + 每 type 抽样数
SAMPLES_PER_CODE_TYPE = 5


def value_human(value: int | None) -> str:
    """把 13 字节股本值转人类可读

    股本 records 中 value 是 float * 1000 = 实际股本
    e.g. 1256190000 / 1000 = 1,256,190 (万股) = 12.56 亿
    """
    if value is None or value == 0:
        return "0"
    actual = value / 1000  # 股本 = value / 1000 (万股)
    if actual >= 100_000_000:  # 100 亿
        return f"{actual/100_000_000:.2f}亿股"
    elif actual >= 10_000:  # 1 万
        return f"{actual/10_000:.2f}万股"
    else:
        return f"{actual:.0f}股"


def main() -> int:
    """主流程"""
    print(f"加载 {RECORDS_PATH}...")
    table = pq.read_table(RECORDS_PATH)
    print(f"  rows: {len(table):,}")
    print(f"  columns: {table.column_names}")
    print()

    # 把 code 转 string 便于过滤
    code_arr = pc.cast(table["code"], pa.string())
    type_arr = table["type"]

    rows: list[dict] = []
    for sample_type in UNCATEGORIZED_TYPES:
        # 先按 type 过滤
        type_mask = pc.equal(type_arr, sample_type)
        sub = table.filter(type_mask)
        if len(sub) == 0:
            print(f"  type {sample_type:>3d}: 无数据")
            continue

        sub_codes = pc.cast(sub["code"], pa.string())

        for code in SAMPLE_CODES:
            code_mask = pc.equal(sub_codes, code)
            code_sub = sub.filter(code_mask)
            if len(code_sub) == 0:
                # 这只股票没这个 type
                continue

            # 取前 N 条 sample
            n = min(SAMPLES_PER_CODE_TYPE, len(code_sub))
            sliced = code_sub.slice(0, n)

            code_list = sliced["code"].to_pylist()
            date_list = sliced["date"].to_pylist()
            v1_list = sliced["value_1"].to_pylist()
            v2_list = sliced["value_2"].to_pylist()
            market_list = sliced["market"].to_pylist() if "market" in sliced.column_names else [None] * n

            for i in range(n):
                rows.append({
                    "code": code_list[i],
                    "type": sample_type,
                    "sample_date": date_list[i],
                    "sample_value_1": v1_list[i],
                    "sample_value_2": v2_list[i],
                    "sample_market": market_list[i],
                    "sample_value_1_human": value_human(v1_list[i]),
                    "sample_value_2_human": value_human(v2_list[i]),
                    "category": get_category(sample_type),
                    "type_name": get_type_name(sample_type),
                    "confidence": get_confidence(sample_type),
                })

        print(f"  type {sample_type:>3d} ({get_type_name(sample_type):>35s} · "
              f"{get_confidence(sample_type)}): {len(sub):,} records · "
              f"sampled {sum(1 for r in rows if r['type'] == sample_type)}")

    # 输出 CSV
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "code", "type", "sample_date", "sample_value_1", "sample_value_2",
        "sample_market", "sample_value_1_human", "sample_value_2_human",
        "category", "type_name", "confidence",
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n✅ 写入 {len(rows)} samples → {OUTPUT_CSV}")

    # 总结
    print("\n=== 摸排总结 ===")
    from collections import Counter
    type_counter = Counter(r["type"] for r in rows)
    type_records_counter = {}
    for t in UNCATEGORIZED_TYPES:
        cnt = int(pc.sum(pc.cast(pc.equal(type_arr, t), pa.int64())).as_py())
        type_records_counter[t] = cnt
    print(f"{'type':>4} {'samples':>8} {'records':>12} {'type_name':>35}")
    for t in sorted(type_records_counter.keys(), key=lambda x: -type_records_counter[x]):
        rec_cnt = type_records_counter[t]
        smp_cnt = type_counter.get(t, 0)
        print(f"  {t:>3d} {smp_cnt:>8} {rec_cnt:>12,} {get_type_name(t):>35}")

    return 0


if __name__ == "__main__":
    sys.exit(main())