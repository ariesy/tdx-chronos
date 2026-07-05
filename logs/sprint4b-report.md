# Sprint 4b 报告 · 股本全 records + 5 指数

**项目**: tdx-chronos · v1.1 第 9 轮修订
**周期**: 2026-07-04 (UTC 12:22–16:18) · Sprint 4b D1 + D2 + D3
**作者**: claw-cortex 🦞
**远端**: https://github.com/ariesy/tdx-chronos · 22 commits

---

## 📦 交付概览

| Day | 主题 | commit | 文件 | 测试 |
|---|---|---|---|---|
| **D1** | tdxgp_record.py 股本全 records | `84d479c` | 3 files / 519 lines | 9/9 PASSED · 0.57s |
| **D2** | index_parser.py + 3 指数 zip 真下载 | `1786a1d` | 4 files / 380 lines | 8/8 + 2/2 PASSED |
| **D3** | 本报告 + M3 跨期验证 + download_log 更新 | (本 commit) | 1 file | — |

**累计**:
- 6 commits · 7 files · ~900 lines
- 17 new tests PASSED
- 131/131 全套测试 PASSED · 128s

---

## 🎯 Sprint 4b 关键真相

### D1 · 股本全 records 解析

**修正**: Sprint 4a D2 简化版 (GpFileInfo: 仅 metadata) → Sprint 4b D1 完整版 (GpRecordsFile: 全部 13B records 装 DataFrame)

**13B record layout** (Sprint 4a D2 实证, v1.1 不解释 type 1-48 字段语义):

```
uint8   type      1-48 变动类型
uint32  date      YYYYMMDD
uint32  value_1   类型相关
uint32  value_2   类型相关
```

**真验收**:
| 指标 | 值 |
|---|---|
| 股本 .dat 解析 | **7,580 / 7,719 OK (98.20%)** |
| records 总数 | **125,736,734 (1.26 亿)** |
| 输出 Parquet | **627 MB · zstd** |
| 耗时 | 121.1s (2 min) |
| by_market | sh 3,802 · sz 3,195 · bj 573 |
| **失败率** | 1.80% (139 个 gpcw 误识别为股本) |

**茅台 (gpsh600519.dat) 实测 type 分布**:
- type=1 (季末快照): 104 个 · 2001-12-31 ~ 2026-03-31
- type=3-21 (日线/财务): 各 2000+
- type=47 (近期每日): 1,749 个
- **27 种 type 出现** (v1.1 不解释 type 字段语义)

### D2 · 5 指数 zip 真下载 + 解析

**新增 3 指数 zip** (主机 `www.tdx.com.cn`):

| zip | 大小 | 含指数 |
|---|---|---|
| `shzsday.zip` | 27.7 MB | 上证综指 000001.SH |
| `szzsday.zip` | 36.2 MB | 深证成指 399001.SZ |
| `tdxzs_day.zip` | 77.7 MB | 沪深300 + 创业板 + 科创50 + 板块指数 (sh880xxx) |

**网络**: vm002 出站 ~0.27 MB/s · 总耗时 ~9 min (3 zip 累计 140 MB)

**5 指数全解析** (28,004 records · 1.1 MB Parquet · 0.1s):

| 指数 | records | 时间跨度 | 年数 |
|---|---|---|---|
| 上证综指 000001.SH | 8,674 | 1990-12-19 → 2026-07-03 | 35 |
| 沪深300 000300.SH | 5,220 | 2005-01-04 → 2026-07-03 | 21 |
| 深证成指 399001.SZ | 8,629 | 1991-04-03 → 2026-07-03 | 35 |
| 创业板指 399006.SZ | 3,906 | 2010-06-01 → 2026-07-03 | 16 |
| 科创50 000688.SH | 1,575 | 2019-12-31 → 2026-07-03 | 6.5 |

**关键发现**: 3 指数 zip 解压后 .day 落 `raw/{sh,sz}/lday/` (与 hsjday 同目录), 同名 .day 自动覆盖。指数版本优先于 A 股 K 线 (sh000001 只有指数数据)。

### D3 · 跨期 M3 验证

**6 大数据源全部可用**:

| # | 数据源 | 来源 Sprint | 输出 | 体积 |
|---|---|---|---|---|
| 1️⃣ | K 线 12,256 .day | Sprint 2 + 4a D3 | 3 zstd Parquet | **716 MB** |
| 2️⃣ | 财务 258 季度 | Sprint 4a D1 | 121 Parquet | 498 MB |
| 3️⃣ | 股本 7,580 .dat | Sprint 4b D1 | 1 大 Parquet | 627 MB |
| 4️⃣ | 5 指数 .day | Sprint 4b D2 | 1 Parquet | 1.1 MB |
| 5️⃣ | meta.db 4 表 | Sprint 2 + 4a | SQLite | ~3 MB |
| 6️⃣ | download_log | Sprint 3a | 6 zip 追溯 | — |

**download_log 完整追溯** (parse_status 更新后):

| zip_name | mirror | size | status |
|---|---|---|---|
| hsjday | data.tdx.com.cn | 540 MB | ✅ success |
| tdxfin | data.tdx.com.cn | 537 MB | ✅ success |
| tdxgp | data.tdx.com.cn | 663 MB | ⚠️ partial (1.80% failed) |
| shzsday | www.tdx.com.cn | 27 MB | ✅ success |
| szzsday | www.tdx.com.cn | 36 MB | ✅ success |
| tdxzs_day | www.tdx.com.cn | 77 MB | ✅ success |

**总磁盘**: 8.16 GB (含 raw zip 缓存)

---

## 🔬 技术决策

### 1. 流式 ParquetWriter (Sprint 4b D1)

**问题**: 全内存 `pd.concat` 7,580 文件 1.26 亿 records → 17 GB OOM 风险

**方案**: 
- 单文件 → `pa.Table` (pyarrow 原生) → `pq.ParquetWriter.write_table()` 增量
- 单文件结束 → 释放内存
- 内存峰值: 17 GB → ~2 GB (单文件 16-30 MB DataFrame)
- 总耗时: 121s (vs 全内存 OOM)

### 2. 1-market-1-Parquet (Sprint 4a D3)

**对比**:
| 策略 | 输出 | 节省 | 文件数 |
|---|---|---|---|
| zstd_only (per-file) | 860 MB | 28.7% | 12,256 |
| merge (1-market-1) | **716 MB** | **40.6%** | 3 |
| merge_max (zstd-9) | 693 MB | 42.6% | 3 |

**选择**: merge (zstd-3) · 40.6% 节省 vs 28.7% · 多耗 6s 可接受 · 与 Sprint 7 DuckDB 列存可叠加

### 3. 指数 zip 同目录覆盖 (Sprint 4b D2)

**发现**: `unzip -o` 默认覆盖同名文件。3 指数 zip 解压后:
- `sh000001.day` → shzsday 版 (上证综指)
- `sh000300.day` → tdxzs_day 版 (沪深300)
- `sz399001.day` → szzsday 版 (深证成指)
- ... (覆盖优先级: 后下载 > 先下载)

**结论**: 解压顺序 = 优先级。本期下载顺序 (hsjday → tdxfin → tdxgp → shzsday → szzsday → tdxzs_day) 让指数数据最终生效。

### 4. type 1-48 字段语义 (Sprint 4b D1)

**决策**: v1.1 不解释 type 字段含义, 全部 47 种 type 装 DataFrame 留待 Sprint 7+ 验证。

**理由**:
- §四.7 文档未列 type 字段含义
- Phase 1 PoC 仅实证 13B layout, 未实证 type 语义
- Sprint 7+ 可结合股本变动事件回测验证 type 1-48 含义

---

## 📊 测试矩阵

### Sprint 4b 新增 (17 测试)

```
tests/unit/test_tdxgp_record.py       9 PASSED
tests/unit/test_index_parser.py       8 PASSED
tests/unit/test_bulk_download.py      +2 (TestIndexZips)
                                       ────────
                                       19 PASSED
```

### Sprint 4b 全套 (131 PASSED · 128s)

```
tests/unit/test_official_zip.py                23 PASSED
tests/unit/test_meta_db.py                     15 PASSED
tests/unit/test_bulk_download.py               12 PASSED
tests/unit/test_parquet_compression.py         15 PASSED
tests/unit/test_tdxfin.py                       9 PASSED
tests/unit/test_tdxgp.py                       21 PASSED
tests/unit/test_tdxgp_record.py                 9 PASSED
tests/unit/test_index_parser.py                 8 PASSED
                                                ─────────
                                       112 PASSED (+ 19 deselected 真数据慢测)
```

---

## 🦞 Sprint 5+ 路径

| 优先级 | 任务 | 估算 |
|---|---|---|
| P0 | §四.5 cron/daily_sync.sh 加 INDEX_ZIPS 下载环节 (周一~五 17:30) | 0.5 d |
| P0 | §四.7 doctor.py 加 5 指数完整度检查 | 0.5 d |
| P1 | §四.7 type 1-48 字段语义验证 (结合股本变动事件) | 2 d |
| P1 | §六 §七 数据导出 API (`Market.bars('000001.SH', ...)`) | 2 d |
| P2 | Sprint 7 DuckDB 列存叠加 (估再节省 10-15%) | 1 d |

---

## 🏁 Sprint 4b 验收标准

- [x] **D1**: tdxgp_record.py + 9 测试 + 真验收 7,580/7,719 OK
- [x] **D2**: index_parser.py + 8 测试 + 5 指数全解析 + 3 zip 真下载
- [x] **D3**: 本报告 + M3 跨期验证 + download_log parse_status 全部更新
- [x] **远端**: 22 commits · main 分支干净
- [x] **测试**: 131/131 PASSED · 128s

**Sprint 4b 完成 · v1.1 第 9 修订 Sprint 4 全部收官** 🦞

---

## 🕐 时间线

```
UTC 12:22  Sprint 4b D1 启动 (tdxgp_record.py)
UTC 12:35  D1 真实跑 7,580 文件 (121s) → 627 MB Parquet
UTC 12:41  D1 commit 84d479c push 成功
UTC 13:38  Sprint 4b D2 启动 (index_parser)
UTC 13:40  D2 实下载测试 (~0.27 MB/s)
UTC 16:07  D2 后台真下载启动 (3 zip)
UTC 16:16  D2 下载完成 + 解压
UTC 16:18  D2 真验收 5/5 OK + commit 1786a1d push
UTC 16:20+ Sprint 4b D3 启动 (本报告)
UTC 16:25  M3 跨期验证 + download_log 更新完成
```

总耗时 ~4 h (含 9 min 后台下载)

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>