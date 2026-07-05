"""Sprint 9 T3 · 摸排 gpcw 中未命名字段 (colXXX + _colXXX)

对每个 colXXX 字段 (col323-400, col440-500, col522-560) + _colXXX (_col582-585):
- 总共 178 + 4 = 182 字段
- 输出真实分布数据: nonzero count/ratio, mean/min/max, unique_count, is_binary
- best_correlation_field + best_correlation_value 与已知字段
- 茅台 2025 样本值

设计原则 (内存安全):
- 单次 read_parquet · 不分批加载
- 计算相关性时只取 nonzero stocks · pc.corr 不分批
- 输出: data/research/sprint9_unknown_fields.csv

用法:
    PYTHONPATH=src:vendor/_vendor python3 scripts/sample_unknown_fields.py

输出:
    column_name, nonzero_count, nonzero_ratio, mean, min_val, max_val,
    unique_count, is_binary, best_correlation_field, best_correlation_value,
    maotai_2025_value
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np

# --- Path 注入 ---
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "vendor" / "_vendor"))


# --- 待摸排字段 (Sprint 9 摸排定义) ---
UNKNOWN_RANGES = [
    ("col323-400", 323, 400),  # 78 fields
    ("col440-500", 440, 500),  # 61 fields
    ("col522-560", 522, 560),  # 39 fields
]

# _colXXX 命名规律 (Sprint 9 摸排发现)
UNNAMED_FIELDS = ["_col582", "_col583", "_col584", "_col585"]


def get_all_unknown_fields() -> list[str]:
    """返回所有摸排字段名 (按区间顺序)"""
    fields = []
    for _label, start, end in UNKNOWN_RANGES:
        for n in range(start, end + 1):
            fields.append(f"col{n}")
    fields.extend(UNNAMED_FIELDS)
    return fields


def get_correlation_target_fields(df: pd.DataFrame) -> list[str]:
    """获取已知字段 (用于 best correlation 验证)"""
    candidates = [
        "营业总收入(万元)", "营业收入(万元)", "净利润", "归属于母公司所有者的净利润",
        "营业成本(万元)", "营业利润", "利润总额", "资产总计", "负债合计",
        "货币资金", "应收账款", "存货", "固定资产", "无形资产",
        "经营活动产生的现金流量净额", "投资活动产生的现金流量净额",
        "筹资活动产生的现金流量净额", "每股收益(摊薄)(元/股)",
        "归属于母公司所有者权益合计", "所有者权益合计",
    ]
    return [c for c in candidates if c in df.columns]


def analyze_field(
    col_name: str,
    df: pd.DataFrame,
    known_fields: list[str],
    maotai_value: float | None,
) -> dict:
    """单字段摸排数据"""
    vals = df[col_name]
    total = len(df)
    nonzero_mask = vals != 0
    nonzero_count = int(nonzero_mask.sum())
    nonzero_ratio = nonzero_count / total

    nz_vals = vals[nonzero_mask]
    if len(nz_vals) > 0:
        mean = float(nz_vals.mean())
        min_val = float(nz_vals.min())
        max_val = float(nz_vals.max())
    else:
        mean = min_val = max_val = 0.0

    unique_count = int(vals.nunique())
    # binary 判断: 只 2 个 unique 值
    is_binary = unique_count <= 2

    # best correlation 与已知字段
    best_corr_field = ""
    best_corr_value = 0.0
    if nonzero_count >= 30:
        for kf in known_fields:
            try:
                m = (vals != 0) & (df[kf] != 0)
                if m.sum() < 30:
                    continue
                corr = float(vals[m].corr(df[kf][m]))
                if corr is not None and not np.isnan(corr):
                    if abs(corr) > abs(best_corr_value):
                        best_corr_value = corr
                        best_corr_field = kf
            except Exception:
                continue

    return {
        "column_name": col_name,
        "nonzero_count": nonzero_count,
        "nonzero_ratio": round(nonzero_ratio * 100, 2),
        "mean": round(mean, 4),
        "min_val": round(min_val, 4),
        "max_val": round(max_val, 4),
        "unique_count": unique_count,
        "is_binary": is_binary,
        "best_correlation_field": best_corr_field,
        "best_correlation_value": round(best_corr_value, 4),
        "maotai_2025_value": round(maotai_value, 4)
            if maotai_value is not None and not pd.isna(maotai_value)
            else "",
    }


def main():
    """主流程: 单次 read + 逐字段分析 + CSV 输出"""
    fin_dir = ROOT / "data" / "fin" / "parsed"
    output_dir = ROOT / "data" / "research"
    output_dir.mkdir(exist_ok=True, parents=True)
    output_csv = output_dir / "sprint9_unknown_fields.csv"

    # 找最近 parquet
    parquet_files = sorted(fin_dir.glob("gpcw*.parquet"), reverse=True)
    if not parquet_files:
        print(f"❌ 未找到 parquet · {fin_dir}")
        sys.exit(1)

    latest = parquet_files[0]
    print(f"📂 摸排文件: {latest.name}")

    df = pd.read_parquet(latest)
    print(f"  总股数: {len(df)}")

    unknown_fields = get_all_unknown_fields()
    existing_fields = [f for f in unknown_fields if f in df.columns]
    missing = [f for f in unknown_fields if f not in df.columns]
    if missing:
        print(f"⚠️ {len(missing)} 字段缺失: {missing[:3]}...")

    print(f"  待摸排字段: {len(unknown_fields)} 个 (存在: {len(existing_fields)})")

    known_fields = get_correlation_target_fields(df)
    print(f"  相关性参考字段: {len(known_fields)} 个已知字段")

    # 茅台 (600519) 样本
    maotai_vals = {}
    if "600519" in df.index.values:
        maotai_row = df.loc["600519"]
        for f in existing_fields:
            maotai_vals[f] = float(maotai_row[f])

    print(f"\n=== 开始逐字段摸排 ({len(existing_fields)} 字段) ===")
    rows = []
    for i, f in enumerate(existing_fields, 1):
        row = analyze_field(f, df, known_fields, maotai_vals.get(f))
        rows.append(row)
        if i % 30 == 0 or i == len(existing_fields):
            print(f"  进度: {i}/{len(existing_fields)}")

    # 写出 CSV
    result_df = pd.DataFrame(rows)
    result_df.to_csv(output_csv, index=False)
    print(f"\n✅ 已输出 {len(rows)} 行到:")
    print(f"   {output_csv}")

    # 摘要
    print(f"\n=== 摸排摘要 ===")
    binary_count = sum(1 for r in rows if r["is_binary"])
    print(f"  total fields: {len(rows)}")
    print(f"  binary (0/1) fields: {binary_count}")
    high_nonzero = sum(1 for r in rows if r["nonzero_ratio"] >= 95)
    print(f"  high nonzero (>= 95%): {high_nonzero}")
    low_nonzero = sum(1 for r in rows if r["nonzero_ratio"] <= 10)
    print(f"  low nonzero (<= 10%): {low_nonzero}")
    corr_found = sum(1 for r in rows if r["best_correlation_field"])
    print(f"  with strong correlation (>= 30 nz stocks): {corr_found}")

    print(f"\n=== 前 8 行预览 ===")
    print(result_df.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
