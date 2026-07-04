# Sprint 2 报告 · 2026-07-04

**Sprint**: Sprint 2 · 抽象层 + 元数据 SQLite  
**周期**: 3 d（估算） · **D1 + D2 上午末 已经走完** · D3 = 报告 + 推送  
**状态**: ✅ **M1 验证里程碑 跑通 · Sprint 2 完成**

---

## 交付物清单

- [x] **D1 上午** `src/tdx_chronos/sources/official_zip.py` · 公开 4 方法
- [x] **D1 上午** 5 真 .day fixture (覆盖 sh/sz/bj · 老股/新股/北交所)
- [x] **D1 上午** `tests/unit/test_official_zip.py` · **13 测试 PASSED**
- [x] **D1 下午** `src/tdx_chronos/meta/db.py` · SQLite 持久化
- [x] **D1 下午** `tests/unit/test_meta_db.py` · **13 测试 PASSED**
- [x] **D2 上午** `official_zip.py` 扩展 `parse_hsjday_dir` + `run_full_parse`
- [x] **D2 上午** `tests/unit/test_batch_parse.py` · **9 测试 PASSED**
- [x] **D2 下午** **M1 验证里程碑**：12,256 真 .day 全集跑通

## 总测试统计

| 套件 | 测试 | 状态 |
|---|---|---|
| `test_official_zip.py` | 13 | ✅ 全部 PASSED |
| `test_meta_db.py` | 13 | ✅ 全部 PASSED |
| `test_batch_parse.py` | 9 | ✅ 全部 PASSED |
| **Sprint 2 新增** | **35** | **0.58s 全过** |
| Sprint 1 已有 | 9 | ✅ |
| **总 Sprint 1+2** | **44** | **PASSED** |

---

## 🏗️ 架构总览

```
┌────────────────────────────────────────────────────────────┐
│  Sprint 2 主路径                                            │
│                                                              │
│  ┌──────────────────┐    ┌──────────────────┐              │
│  │ hsjday_raw/      │───▶│ OfficialZipParser │              │
│  │  sh/sz/bj/lday/  │    │   (32 bytes/rec)  │              │
│  │  *.day (12,256)  │    └────────┬─────────┘              │
│  └──────────────────┘             │                          │
│                                    ▼                          │
│                          ┌──────────────────┐                │
│                          │ run_full_parse() │ generator      │
│                          └────────┬─────────┘                │
│                                   │                          │
│              ┌────────────────────┼────────────────────┐    │
│              ▼                    ▼                    ▼    │
│     ┌──────────────┐      ┌──────────────┐      ┌────────┐ │
│     │ data/parquet │      │ data/meta.db │      │  tqdm  │ │
│     │   .{sh,sz,bj}/│      │symbol_metadata│     │ progress│ │
│     │   <sym>.parq │      │  (12,256 行) │      │  bar    │ │
│     │   (~100KB)   │      │ download_log │      └────────┘ │
│     └──────────────┘      └──────────────┘                  │
└────────────────────────────────────────────────────────────────┘
```

## Sprint 2 公开 API

### `tdx_chronos.sources.official_zip`

```python
class OfficialZipParser:
    def parse_day_file(path) -> ParseResult            # 单 .day
    def iter_day_files(raw_dir) -> Iterator[Path]      # 流式遍历
    def parse_to_parquet(path, output_dir) -> Path     # 单 .day → Parquet

def parse_hsjday_dir(             # 流式全量 · generator
    raw_dir, output_dir,
    db=None,                     # 可选 MetaDB 集成
    show_progress=True,
) -> Iterator[ParseResult]

def run_full_parse(               # 一键全量 · M1 验证用
    raw_dir, output_dir, db_path,
    show_progress=True,
) -> BatchSummary               # 含 elapsed / bytes_read / parquet_bytes
```

### `tdx_chronos.meta.db`

```python
class MetaDB:
    def init_schema()                              # 幂等
    def record_symbol(symbol, market, first_listing_date,
                     record_count, source_zip, parquet_path)
    def record_download(zip_name, mirror, size_bytes, sha256,
                       parse_status='pending') -> rowid
    def update_parse_status(log_id, status, error_msg=None)
    def get_symbols_by_market(market) -> List[str]
    def get_unparsed_files(source_zip) -> List[str]  # cron 重跑
    def get_recent_downloads(limit=10) -> List[Row]
```

---

## 📊 M1 验证里程碑 · 12,256 真 .day 全集

**运行命令**：
```bash
PYTHONPATH=src:vendor/_vendor .venv/bin/python -c "
from tdx_chronos.sources.official_zip import run_full_parse
summary = run_full_parse(
    '/tmp/tdx_data/day/hsjday_raw',
    '/app/tdx-chronos/data/parquet',
    '/app/tdx-chronos/data/meta/meta.db',
    show_progress=True,
)"
```

### 验证结果

| 指标 | 值 | 评估 |
|---|---|---|
| **total_files** | **12,256** | sh 5,880 + sz 5,788 + bj 588 |
| **parsed_ok** | **12,256** | ✅ 100% 成功 |
| **parsed_failed** | **0** | ✅ 无失败文件 |
| **elapsed_seconds** | **123.18** (~2 分钟) | ✅ 远超预期 |
| **bytes_read** | **917 MB** | input = hsjday_raw 总大小 |
| **parquet_bytes** | **1,202 MB** | output = Parquet 总占用 |
| **compression** | **134.9%** | ⚠️ Parquet **比 input 大 35%** |
| **start_at** | 2026-07-04 07:03:00 UTC | — |
| **end_at** | 2026-07-04 07:05:03 UTC | — |

### ⚠️ 重要负发现 · Parquet 比 input 大 35%

**预期**：列存压缩应小于 raw binary  
**实际**：反常 —— Parquet 134.9% (即 Parquet 比 raw 大 35%)  
**根因分析**：

| 因素 | 影响 |
|---|---|
| **OHLCV 数据高度随机**（每天价格不同）| snappy 压缩率极低 (~1.0x) |
| **Parquet 元数据开销** | schema/column metadata 每个文件 ~1 KB × 12,256 = ~12 MB |
| **每文件独立 Parquet** | 字典压缩无法跨文件复用 |
| **默认 snappy 压缩** | 不如 zstd (~30% 压缩) |

**v1.1 决策**：**先用现方案**，功能 100% OK · 1.2 GB on disk 可接受
**Sprint 3b / Sprint 6 优化点**：
- (选项 1) 切换 zstd 压缩 → 估算 input × 0.4-0.6
- (选项 2) 1 市场 1 Parquet 文件 (12k → 3 大文件)
- (选项 3) DuckDB 列存格式 (替代 Parquet)

**判断**：**功能 Sprint 2 完成 ✅** · **压缩优化 Sprint 3b 验证里程碑**

### M1 验证结论

```
M1 通过 =
  1. 抽象层能调取 mock vendor 验证 .day schema 正确 · meta.db 追溯     ✅
  2. 真数据全跑通 (12,256 / 12,256 · 0 失败)                         ✅
  3. meta.db 12,256 行 · 完整追溯到 parquet_path                       ✅
```

### data/ 实际状态

```
data/parquet/
├── sh/   5,880 files · 640 MB
├── sz/   5,788 files · 566 MB
└── bj/     588 files · 23 MB
              ─────────
              12,256 files · 1,229 MB total

data/meta/
└── meta.db   (12,256 symbol_metadata + N download_log)
```

---

## 🔍 Sprint 2 实证新发现

### 1. sz000001 真实上市首日 = 1991-04-03（不是 Phase 1 PoC 的 1995）

- Phase 1 PoC 文档写 `1995-04-14`（错）
- 实测：sz000001 是「深发展」(现平安银行) · **1991-04-03** 上市 (Phase 1 PoC 错了一年)
- 影响：v1.1 追溯链以**真数据为准** —— 第一条 record = 1991-04-03

### 2. reserved 字段实际形态（§四.B schema 注释修正）

| 标的 | date | close | reserved | 注释 |
|---|---|---|---|---|
| sz000001 (1991-04-03) | 19910403 | 10.62 | **0** | 老数据无此字段 |
| sh600000 | 20040212 | 11.51 | 1175 | ≈ 100 × close |
| sh600519 | 20051103 | 47.21 | 4816 | ≈ 100 × close + 微调 |
| sz300750 (宁德) | 20220622 | 507.00 | **65536** | 期权标记 / 特殊状态 |
| bj920193 | 20260703 | 79.36 | 65536 | 同上 |

**v1.1 决策**：
- 保留 reserved 字段 int32 原始值（schema 不变）
- 不解释语义（Sprint 7 验证阶段分析）

### 3. sh600519 茅台今日 (2026-07-03) 数据

```
开盘 1205.24 · 最高 1210.14 · 最低 1185.00 · 收盘 1194.45
成交额 40.99 亿元 · 成交量 342.7 万股 · reserved=65536
```

—— 与今日 (UTC 2026-07-04 07:03 跑的) CST 时间完全对应

---

## 💾 Sprint 2 commit 计划

| # | Commit | 主题 | 文件数 |
|---|---|---|---|
| 1 | `affb5ce` | Sprint 2 · official_zip.py (§四.B schema) + 5 fixture + 13 测试 | 10 |
| 2 | `c424b9c` | Sprint 2 · meta/db.py SQLite schema + 13 测试 | 3 |
| 3 | (待提交) | Sprint 2 · official_zip 流式 + run_full_parse + 9 测试 + M1 验证 | 2 |
| 4 | (待提交) | Sprint 2 · sprint2-report.md + .gitignore verify | 1 |

## Sprint 2 周期重算

| 任务 | 估算 | 实际 |
|---|---|---|
| D1 上午 (official_zip + 13 测试) | 0.75 d | **0.5 h** |
| D1 下午 (meta/db + 13 测试) | 0.75 d | **1 h** |
| D2 上午 (流式 + 9 测试) | 1 d | **0.5 h** |
| D2 下午 (M1 验证 12,256) | 0.5 d | **2 min** |
| **Sprint 2 实际总耗时** | **3 d** | **~2 h** ✅ |

**节省时间**：3 d → 2 h（节省 2.85 d）

---

## 🚀 Sprint 3 启动

按 requirements.md §六，Sprint 3 = 全量 K 线下载 + 解析 + 验证 (3a + 3b 共 6d)。

但 Sprint 2 已实现：
- 解析 (`official_zip.py` + `parse_hsjday_dir` + `run_full_parse`)
- 元数据 (`MetaDB` + 追溯)

**Sprint 3a (下载)** 现在是相对独立的 + 简单的「curl + zip 解压」 · Sprint 3b (解析 + 验证) **已被 Sprint 2 覆盖**。

**推荐**：
- Sprint 3a 简化版（直接 cron 调用 curl，**无需新 commit**）
- **Sprint 3b 直接合并到 Sprint 4a 报告** （功能已被 Sprint 2 跑通）

⚠️ 这是一个**重要决策** —— 主人签字决定：
- 选项 A：保留 Sprint 3 + Sprint 4 串行结构（按 requirements.md §六 字面）
- 选项 B：合并 Sprint 3b 到 Sprint 4a 总账里（节省 3 d）· Sprint 3a 单独落地即可

**报告是建议性** —— 不阻塞 Sprint 2 完成签字。
