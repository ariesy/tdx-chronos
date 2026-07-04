"""Sprint 4a D3 · tdx-chronos Parquet 压缩优化子包

Sprint 2 末负发现 (2026-07-04):
  Parquet 134.9% input = 1.27 GB (input 917 MB)
  原因: snappy 压缩率低 + 12k 文件独立元数据

Sprint 4a D3 优化:
  - 选项 1 (默认): zstd codec level 3 · 1 file 1 Parquet (保留结构)
    预期: 1.27 GB → 880 MB (~30% 节省)
  - 选项 2: zstd + 1-market-1-file (3 大文件)
    预期: 1.27 GB → 400-600 MB (~50-70% 节省)
  - 选项 3: zstd + 1-market-1-file + zstd level 9
    预期: 1.27 GB → 350-500 MB (~60-75% 节省)

v1.1 默认采用 选项 3 · 决策 2026-07-04 Sprint 4a D3

设计:
  - 不动 raw .day 文件 (可重生)
  - 重写 Parquet 到 data/parquet_compact/<market>.parquet
  - meta.db symbol_metadata.parquet_path 指向新位置
  - 失败回退到旧 parquet (compat)
"""
from .parquet_compression import ParquetOptimizer, OptimizationSummary  # noqa: F401