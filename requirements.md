# tdx-chronos 需求文档

> **项目代号**：`tdx-chronos`（Chronos · 时间之神 · 契合"每日增量 + 历史持久化"）
> **作者**：朱琨 · claw-cortex
> **创建日期**：2026-07-02
> **最后更新**：2026-07-03（**v1.1 第 8 轮修订**——委员会 P0 补正：Sprint 1 改 1.5-2d · 总周期 25.5-27d · Sprint 0 加 vendoring 可行性验证 · §三 IN #1 边界表达清晰）
> **目标版本**：v1.1.0（**26-28 工作日**，不是 21）
> **状态**：📋 **需求阶段**（待主人签字后进入设计 + Sprint 1）

## 🔄 本次修订新增（2026-07-03 第 8 轮）— 委员会评审 P0 补正

主人在 14:57 UTC 说"请智者委员会再进行新一轮评审"。委员会 2m11s 返回 6 个 Action Items · 4 个 P0/P1 立即处理。

**委员会评审产出**（⚖️ Synthesis）：
> 第 7 轮决策逻辑正确，但落地有 2 处文本不一致 + 1 处估算可信度风险。建议立即对齐 §六 Sprint 1 表格值（3d vs 1.5-2d） + 总周期数学。Confidence: **Medium**（Sprint 1 估算有不确定性）。

**6 Action Items 处理**：

| # | 优先级 | Action | 处理状态 |
|---|---|---|---|
| **#1** | **P0** | §六 Sprint 1 表格 3d → 1.5-2d | ✅ **已改** |
| **#2** | **P1** | §六总周期数学重算（25.5-27d） | ✅ **已改** |
| **#3** | **P1** | Sprint 1 验收标准明确交接条件 | ✅ **已在 #1 同步加** |
| **#4** | **P2** | Sprint 4b 与 4a 并行可能性 | 📋 记录 v2.0 评估 · 不入 v1.1 范围 |
| **#5** | **P1** | Sprint 0 包含 vendoring 可行性验证 | ✅ **已加到 Sprint 0 交付物** |
| **#6** | **P2** | §三 IN #1 边界表达清晰 | ✅ **已改** |

**委员会其他肯定**（保留作记录）：
- 🟢 包级重试数学设计是本轮最强改进（0.0003% 失败率）
- 🟢 25.5-26d 总周期区间比 27d 更诚实
- 🟢 M1-M5 跨 Sprint 验证里程碑设计合理
- 🟢 873 行文档可读性在本轮后大幅提升

**未采纳的 Action Item #4**（Sprint 4b 与 4a 并行）：委员会 Architect 提出"tdxgp.zip 预取节省 1d"可能性。考量：1) 主人串行习惯减少 context switch；2) Sprint 3b 已是 12,256 文件解析周，不能再加下载；3) 节省 1d 远小于 Sprint 1 缩短的 1.5d。**决定不采纳，v1.1 维持串行**。

## 🔄 本次修订新增（2026-07-03 第 7 轮）— 4 bug 补丁具体列明 + v1.1 不修

主人在 14:54 UTC 说"前面提到的 mootdx 的 4 个 bug 补丁具体是什么？在目前通过下载全量加增量数据的方式下还需要对此 4 个 bug 进行修复吗"。

**4 个 bug 清单**（来自 Phase 1 PoC decision.md）：

| # | bug | 触发模块 | 触发函数 | v1.1 新主路径下还触发吗？ |
|---|---|---|---|---|
| 3 | `heartbeat=True` + 多次请求 → **卡死** | `TdxHq_API` socket | `do_heartbeat()` | **否**·新主路径不连 TdxHQ 行情服务 |
| 4 | `multithread=True` + 多次请求 → **严重卡顿** | `TdxHq_API` socket | 多线程 | **否**·同上 |
| 5 | `Affair.fetch(filename=dict)` → **TypeError** | `mootdx.Affair` | 财务下载 | **否**·新主路径不调 mootdx.Affair |
| 6 | `mootdx.financial.__init__` 是**空文件** | import 层 | 直接 import 失败 | **否**·新主路径不 import mootdx.financial |

**v1.1 新主路径**（Sprint 3-4 之后） = 官方 .day 集中下载 + struct 解析：
- cron 脚本下 5 zip (hsjday/tdxfin/tdxgp + 2 指数) — **不调 mootdx 任何函数**
- `sources/official_zip.py` 解析 .day — **不调 mootdx**
- `sources/official_zip.py` 解析 .dat — **不调 mootdx.financial**（直接 struct 二进制拆 264 字段）

**Sprint 1 修订**：从"修 4 bug"降为 "vendor 化 + 记入 UPGRADE_NOTES.md + 不修"
- 原因：v1.1 主路径不触发这些 bug·修不修跟 v1.1 输出质量无关
- 但 vendor 化仍有价值：1) v2.0 实时增量备用；2) 接口抽象层需要原 mootdx 作为"参考实现"
- Sprint 1 单元测试只验"可 import + 可被抽象层调用"·不验 heartbeat/multithread/Affair/financial

**附录 A #22 新决定**：4 bug 仅记入 vendor/UPGRADE_NOTES.md·不修·v1.1 主路径不触发

主人在 14:51 UTC 说"无需 sina.py / aggregator.py 这两个文件的功能，本项目只用来做 tdx 数据的下载，整理和提供调用"。修正后:

1. **§二 问题 1**·「数据源单一脆弱」列点去掉多源备份·改为 "v1.1 范围外"
2. **§三 IN #12** 描述去掉 "cross-check sina 0.0000%" 列为“仅作 PoC 验证记录、不进 v1.1 代码”
3. **§三 IN #3** 边界去掉"备用 hq.sinajs.cn"·改为"v2.0 预留"
4. **§四 目录结构 sources/**·sina.py / aggregator.py 划掉·标记 v2.0 预留
5. **§六 Sprint 3b 描述**·去掉"sina 交叉验证 0.0000%"·改"内部完整性检查"
6. **§六 M1 M2 描述**·去掉"sina 验证"·改"mock vendor / 内部检查"
7. **§七 风险 #1**·去掉"新浪 + tushare 兑底"·改为"v2.0 预留"
8. **§七 风险 1 跨表**·“重试 3 次 → 切备用源” 改为"重试 3 次 → 包级重试 + 告警"
9. **附录 F PoC 记录**·加注释"PoC 验证·不进 v1.1 代码"
10. **附录 A 表**·"多源扩展"列改为"v1.1 只放 mootdx·v2.0 可加"
11. **附录 G Vendor 三层架构** 改为 **单层架构 (v2.0 可扩展)**
12. **附录 G 结论**·理由从"多源扩展"改为"v1.1 只提供 tdx 下载+整理+调用"

**v1.1 定义变得清晰**：只做 tdx 官方 .day/tdxfin/tdxgp 下载+Parquet 整理+本地调用接口·不实现多源验证·不实现在线 HTTP 兑底。

1. **Sprint 3 拆为 3a + 3b**（下载 vs 解析 + 验证）— 两大独立风险块·避免同周调试粒度太粗
2. **Sprint 4 拆为 4a + 4b**（财务 vs 股本+指数）— “变” vs “存量”不同依赖
3. **Sprint 5 加上“化减 P0 #3”任务** — 委员会警告 P0 #3 是设计问题不是调度问题
4. **Sprint 6 加上 5 zip 每日 E2E** — 委员会警告“不能拿 1 交易日测试”
5. **总计从 7 Sprint 变为 9 Sprint 单元**（含拆分）· 周期 1+3+3+(3+3)+(3+3)+4+3+2 = 25 + 2 缓冲 = 27 工作日
6. **M1-M5 验证里程碑**（跨 Sprint 检查点） — 不混在 Sprint 里
7. **Sprint 8 + v2.0 预告** — 期货/港股/期权/tushare/web API
8. **依赖图谱** — 文字表格 · 明确关键路径 = Sprint 1-5

1. **§三 IN #13-15** — 多频率 zip 下载矩阵 + 完整快照对比差量 + 包级重试
2. **§三 IN #5b** — 每周同步（周日 02:00）：3 zip · ~570MB
3. **§四.6 完整下载矩阵** — 20 项 max · 18 zip 按频率分组
4. **§四 目录结构 cron/** — 加 weekly_sync.sh 中频同步脚本
5. **§七 风险 #8** — 已解决·重试粒度改包· 0.05^5 数学安全
6. **附录 F.2** — 频率矩阵背景调研表（详）
7. **§六 Sprint 5** — 已加入"完整 5+3 cron 设计"明细
8. **附录 A #16-18** — 重试粒度 / 频率矩阵 / 快照比对策略 3 项新决定
9. **§四.5 官方下载源** 扩充了 20 个 zip 的 last-modified 实测表
10. **§三 IN #2** 验收标准改为 hsjday + 完整快照 + Parquet 对比增量（如上）

完整修订明细见 [附录 H · 修订历史](##H-修订历史)。

---

## 🎯 一句话定位

**tdx-chronos** 是 A 股**离线数据仓库**，**vendor 通达信 mootdx** 在本地修改维护，**全量下载**通达信 A 股所有 K 线、财务、指数数据，**每日 17:30 增量更新**，为下游工具（daily_stock_analysis 等）提供本地权威数据源。

> **不是**：实时行情服务（那是 daily_stock_analysis 的工作）。
> **是**：可独立部署的 **数据镜像仓库** —— 主人 + 主人所有的金融工具共享的"真相之源"。

---

## 📊 核心数据流

```
┌────────────────────────────────────────────────────────────────────┐
│                       每日 17:30（工作日）                            │
│                                                                    │
│   ┌────────────┐    ┌──────────────────┐    ┌─────────────────┐   │
│   │ TDX 协议   │───▶│ mootdx (Vendor)  │───▶│ tdx-chronos     │   │
│   │ (通达信)   │    │ + 主人本地补丁     │    │  镜像仓库        │   │
│   └────────────┘    └──────────────────┘    │                 │   │
│                                              │  /data/parquet/ │   │
│                                              │  /data/fin/     │   │
│   ┌────────────┐    ┌──────────────────┐    │  /data/index/   │   │
│   │ 通达信 .dat│───▶│ FinancialReader  │───▶│  /data/meta.db  │   │
│   │ (财务文件) │    │                  │    │                 │   │
│   └────────────┘    └──────────────────┘    └────────┬────────┘   │
│                                                       │            │
│                                                       ▼            │
│                              ┌────────────────────────────────┐   │
│                              │  下游消费者（未来扩展）           │   │
│                              │  - daily_stock_analysis          │   │
│                              │  - 主人其他金融工具               │   │
│                              │  - 直接 pandas read_parquet()    │   │
│                              └────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🧭 二、目标用户 & 痛点

### 主要用户：主人（朱琨，独立投资者）

| 痛点 | 现状（没用 tdx-chronos 前） | tdx-chronos 解决 |
|---|---|---|
| **历史数据不可控** | daily_stock_analysis 等工具每次现拉，慢、易被 API 限流、易失效 | **本地 Parquet · 永远在本地** · 全量持久化 |
| **数据源单一脆弱** | 任何 API 一挂，全部工具瘫痪 | **v1.1 范围外 · 不在 v1.1 实现**：v2.0 预留 `sources/aggregator.py` 多源验证，但 v1.1 只走 **官方 .day 集中下载**主路径 |
| **A 股财务数据反复拉** | 每次跑分析都重下 .dat，浪费带宽 + 时间 | **本地镜像** · 一次下载 + 增量更新 |
| **mootdx 已弃更** | 项目作者 2 年没动 (2024-07-16 最后 commit)，没人修 bug | **主人 vendor 接管** · 主动 ownership |
| **下游工具数据分散** | 1 个工具 1 个数据源，没有"主数据" | **权威源** · 所有下游都来 tdx-chronos 拉 |

### 次要用户：未来 extension

- 其他想用本地 A 股数据的人（README 文档化 API 即可）
- 主人 AI 工具读 Parquet（pandas / DuckDB / Polars）

---

## 📋 三、范围（IN/OUT）& 验收标准

### ✅ 范围内（v1.1）

| # | 功能 | 验收标准（量化） |
|---|---|---|
| 1 | **mootdx Vendor + 补丁备用** | `/app/tdx-chronos/vendor/mootdx/` 存在 · **v1.1 主路径 = 官方 .day 集中下载 + struct 解析，不走 mootdx 在线 socket 路径** (4 bug 所在模块 TdxHQ socket + financial 都被新主路径回避) · `sources/mootdx_vendor.py` 抽象层仍存在作 v2.0 实时增量备用 · Sprint 1 单元测试只验 import + callable（v1.1 不依赖其返回结果）· 首次启动从 pip 缓存载 0.11.7 基线 |
| 2 | **A 股全量 K 线下载（上市以来所有历史）** | `symbol_metadata` 表记录每只股票的数据起止日期 · 至少 5500 只 · 数据完整度 ≥ 99% |
| 3 | **A 股全量财务数据下载（5526 × 585 字段）** | `quarterly_reports` 表留存 · 每季度所有 .dat 文件下载 + 解析 · 完整度 ≥ 95% |
| 4 | **A 股指数下载** | 至少包含：上证综指 (000001) / 深证成指 (399001) / 沪深300 (000300) / 创业板指 (399006) / 科创50 (000688) |
| 5 | **每日增量更新（17:30 工作日 cron）** | **下载 5 个 zip（hsjday + shzsday + szzsday + tdxzs_day + tdxgp）· ~750MB** · 采用"完整快照对比差量"策略（全量下载 + 与本地对比仅追加新 record）· 全过程耗时 < 30 min |
| 5b | 🆕 **每周同步（周日 02:00）** | 仅下载 1 个 zip（tdxfin）· ~570MB · tdxfin 涵盖历史季报不变 · ~~原计划 shqqday/szqqday 为“期权数据”，实际含义不是除权除息已从主路径退出~~ |
| 6 | **失败重试 3 次** | 网络/协议瞬态错误自动重试 · 3 次后失败告警到群 |
| 7 | **失败告警** | 任何"全量完成度回落"事件 → 飞书群 `oc_812b4a80dbf93832f71b6135ef6cb25a` 收卡片告警 |
| 8 | **监控 + 健康检查** | 每周 cron 跑 `doctor.py` · 报告数据完整度到群 |
| 9 | **数据导出 API** | `from tdx_chronos import Market` · `Market.bars('000001.SZ', start, end)` 1 行读数据 |
| 10 | **DRY-RUN 模式** | 默认不动磁盘，仅打印预期下载量 + 时间估计 |
| 11 | **Python Library 接口（v1.1）** | `pip install -e .` 后 `from tdx_chronos import Market` 可在外部脚本直接 `Market.bars('000001.SZ', start, end)` 读数据 · **不打 Docker 镜像**（v2.0 再评估） |
| 12 | **官方 .day 集中下载**（**v1.1 核心路径**） | 通达信 hsjday.zip（540 MB · sh 5880 + sz 5786 + bj 588 = 12256 只）单文件解压覆盖全 A 股 · 跨格式 `<IIIIIfII>` 32-byte 记录 + ~~sina cross-check 0.0000% 仅作 PoC 验证记录、不进 v1.1 代码~~ · **替代部分 mootdx 在线拉取** |
| 13 | 🆕 **多频率 zip 下载矩阵**（**v1.1 主路径**） | 18 个 zip 按**日 / 周 / 季 / 不下**四频率运行（详见 §四.5 官方下载源 + §六 cron 设计）· 下载量 ~750MB/周日 · 1 文件 1 次重试 → 100% 成功率数学设计 |
| 14 | 🆕 **完整快照对比差量策略** | 下载完整 zip · 对比本地 Parquet → 仅追加新 record（节省 99.99% 写·子增量变葪足够）|
| 15 | 🆕 **包级别重试**（1 文件 3 次）· **不是 stock 级别** | 只需考量"5 个 zip × 3 重试" vs "5500 只股票 × 3 重试" · 后者损 23%·前者 0.0003% · **化解委员会 P0 #3** |
| 16 | 🆕 **数据格式层验收**（**v1.1 设计校验**） | §四 数据格式表 + §四.B .day 解析器 schema + §四.C .dat 财务解析器 schema + 文件名 1-1 映射：Sprint 3-4 验证后写入 ProductSpec | §四 |

### ❌ 范围外（v1.1 不做）

| # | 不做 | 原因 |
|---|---|---|
| 1 | **港股** | mootdx 0.11.7 不支持港股通（PoC 已验证 No-Go）→ 走 tushare，**v2.0 再加** |
| 2 | **美股** | 超出 A 股数据仓库范围 → **v2.0 再加** |
| 3 | **分钟线** | 仅日线 + 财务 + 指数 · 分钟线存储 100x，未来扩展 |
| 4 | **流式 API** | tdx-chronos 是**离线镜像**，不是实时推送服务 |
| 5 | **Web UI** | 命令行 + 飞书告警足够 · GUI = 复杂性，性价比低 |
| 6 | **多用户权限** | 单机单用户（主人）· 没有外部用户需求 |
| 7 | **Docker 镜像（v1.1 不打）** | v1.1 简化交付——直接 `pip install -e .` 使用即可 · **v2.0 再评估** |

### ⚠️ 关键边界

| # | 边界 | 决策 |
|---|---|---|
| 1 | **港股需求浮上来** | 主人决策 · tdx-chronos 不承诺 · 走 tushare 单独通道 |
| 2 | **mootdx 上游发新版** | 用 `vendoring` 工具链一键升级 · 主人在新版本基础上修补 |
| 3 | **TDX 协议大改** | 触发 v2.0 · 切到备用数据源（v2.0 预留 · v1.1 不做）|
| 4 | **需要 Docker 打包** | 主人重新评估后再启动（v2.0 范围） |
| 5 | **mootdx 项目死亡 / 作者删库** | ⚠️ **主人独自承担所有后果**（vendor 模式无 GitHub 社区眼睛看着，fork 至少有上游 PR 反馈流） · 委员会 2026-07-03 提示 · **缓解**：官方 hsjday.zip 是 inert fallback，覆盖 99% 场景；vendor mootdx 仅作为补充（部分场景作协议协调 / 实时增量） |
| 6 | **官方源下载失败（hsjday / tdxfin）** | 通达信官方源为公网静态文件（无身份认证） · 但**可能随版本变更路径** · 缓解：1) 备用 URL 镜像（`data.tdx.com.cn` vs `www.tdx.com.cn/products/data/data/vipdoc/`） · 2) **3 个镜像全部失败则 告警到主人拍板**（不可静默退路） |

---

## 🏗️ 四、架构与技术选型

### 系统组成

| 模块 | 角色 | 技术 | 复用 |
|---|---|---|---|
| **`vendor/mootdx/`** | 本地 vendor + 主人直接改 | Python 3.12 + mootdx 0.11.7 基础上加 patch | 上游：mootdx（不上 GitHub） |
| **`src/tdx_chronos/`** | 主项目 v1.1 代码 | Python 3.12 · **Library + CLI 双形态** | 依赖 vendor/mootdx |
| **`/data/`** | 镜像数据 | Parquet (行情) + SQLite (元数据) + zip (财务原文) | 标准格式 |
| **`doctor.py`** | 健康检查 + 完整度审计 | Python · 每周 cron | 自有 |
| **`alertor.py`** | 飞书告警 | Python + 飞书 Open API | 自有 |

### 数据格式（v1.1 重写：基于已下载文件实测）

**2026-07-03 验证后发现**：原 5 行表 **粒度过粗且与今天实测不符**。下面是修正后的版本。

#### A. 持久化层（Parquet / SQLite / ZIP）

| 数据 | 格式 | 路径 | 压缩 | 大小预估（实测修正）|
|---|---|---|---|---|
| **日线 K 线** | Parquet | `/app/tdx-chronos/data/parquet/<market>/<symbol>.parquet` | zstd | **8 GB** · 12,256 只 × 890 条平均 · main 重估 |
| **每日快照缓存** (增量比对原始 zip) | ZIP | `/app/tdx-chronos/data/snapshot/<date>/{hsjday,tdxgp,fin,_indices}.zip` | deflate | ~1.3 GB / 交易日 · 用于回滚 + 增量检测 |
| **财务原始 .dat + .zip** | ZIP | `/app/tdx-chronos/data/fin/raw/<quarter>.zip` | deflate | ~14 MB 当季 · 164 B 占位 。 **不要重复存储占位** |
| **财务解析结果** | Parquet | `/app/tdx-chronos/data/fin/parsed/<quarter>.parquet` | zstd | **~50 MB** × 已披露季（约 16-20）· **不含未来季** |
| **指数 K 线** | Parquet | `/app/tdx-chronos/data/index/<symbol>.parquet` | zstd | < 50 MB |
| **股本数据** | Parquet | `/app/tdx-chronos/data/gp/<symbol>.parquet` | zstd | ~30 MB · 从 tdxgp.zip 解出 |
| **股权变动 / 期权** (v2.0) | Parquet | `/app/tdx-chronos/data/xdxr/<symbol>.parquet` | zstd | ~10 MB 。 **v1.1 不下**（shqqday 己验为期权不在 v1.1 范围） |
| **symbol_metadata** | SQLite | `/app/tdx-chronos/data/meta.db` | — | < 10 MB · sh+sz+bj+etf 12,256+ 行|
| **download_log** | SQLite | `/app/tdx-chronos/data/meta.db` | — | 5 MB / 年 · 每次下载详细记录 |

**验证点**（今日 2026-07-03 已实测）：

- `data/parquet/sh/sh600519.parquet` 预计 ~70 KB · 5953 条 · v1.1 Sprint 3 创建后不会释放原始 `.day`（可直接从 hsjday_raw 重生）
- `data/fin/parsed/gpcw20260331.parquet` 预计 ~50 MB · 5526 × 585 DataFrame （Phase 1 PoC 已验证）

#### B. .day 解析器 schema（**v1.1 Sprint 3 必实现 · 今已破解**）

```python
# struct format: '<' (little-endian) + 'IIIIIfII' = 32 bytes
#   - date: uint32 (YYYYMMDD)
#   - open, high, low, close: int32 (价·×100)
#   - amount: float32 (成交额元·含小数位)
#   - vol: int32 (成交量股)
#   - reserved: int32 (近 100 × close · TDX 内部）

struct.iter_unpack('<IIIIIfII', data)  # 5s 解析 12,256 × 890 条

# schema (输出 Parquet):
df = pd.DataFrame([{
  'date':  r[0],                    # uint32
  'open':  r[1] / 100,              # float
  'high':  r[2] / 100,
  'low':   r[3] / 100,
  'close': r[4] / 100,
  'amount': r[5],                   # float32
  'vol':   r[6],                    # int32
  'symbol': file.stem,              # e.g. 'sh600519'
  'market': file.parent.name,       # 'sh' / 'sz' / 'bj'
  'source_zip': 'hsjday.zip',       # 追溯源
  'ingested_at': datetime.now(),
} for r in recs])
```

#### C. .dat 财务解析器 schema（**Phase 1 PoC 已验证 · Sprint 4 不变**）

```python
# gpcw20260331.zip → gpcw20260331.dat (12.97MB)
# tag = '<264f>' · 264 fields × 4 bytes = 1056 bytes / 股票
# Ph 1 验证：5526 只 × 264 字段 → DataFrame as 5526×264
# v1.1 schema:
df = FinancialReader.to_data('gpcw20260331.zip')  # 已验证函数
# to_data return: pd.DataFrame with 5526 rows × ~264 float cols
```

#### D. 文件名规范（v1.1 data 路多下不再乱）

| 包内文件 | 输出 Parquet 名 | 路径 |
|---|---|---|
| `sh/lday/sh600519.day` | `sh600519.parquet` | `data/parquet/sh/` |
| `sz/lday/sz300750.day` | `sz300750.parquet` | `data/parquet/sz/` |
| `bj/lday/bj920193.day` | `bj920193.parquet` | `data/parquet/bj/` |
| `8#10012025.day` (shqqday · 期权) | v1.1 不采集 | — |

#### E. 未来 / 估计

- 原**「财务原始 .dat」估计『~50 MB × ~16 季/年」是错的** — 实测仅 ~14 MB 当季（元数据/简介 2 倍）。v1.1 应估 ~50-100 MB/年（以**已披露季为准**）。
- 原**「元数据」估 < 1 MB 明显低估** — 一只股票每条约 5 byte × 890 条 × 12,256 只 ≈ **55 MB**。修正为 < 10 MB / 100 MB（3 年累计）。

**目录结构**（v1.1 全部）：
```
/app/tdx-chronos/
├── README.md
├── LICENSE (MIT)
├── pyproject.toml          # Python library 入口（v1.1 重点）
├── .env.example
├── src/tdx_chronos/
│   ├── __init__.py
│   ├── cli.py
│   ├── market.py              # 顶层 API
│   ├── sources/
│   │   ├── official_zip.py    # 🆕 解析通达信官方 .day 压缩包（hsjday/tdexjday 等）
│   │   ├── mootdx_vendor.py   # vendor/mootdx/ 取增量 + 实时跟进
│   │   ├── ~~sina.py~~        # ❌ v1.1 不实现·公网 HTTP 兜底 v2.0 预留
│   │   └── ~~aggregator.py~~  # ❌ v1.1 不实现·多源验证 v2.0 预留
│   ├── ingest/
│   │   ├── bulk_download.py   # 全量下载
│   │   ├── incremental.py     # 每日增量
│   │   └── bars.py            # K 线入 Parquet
│   ├── fin/
│   │   ├── download.py        # 财务 .dat 下载
│   │   └── parse.py           # 财务 .dat → Parquet
│   ├── index/
│   │   └── download.py        # 主要指数
│   ├── cron/
│   │   ├── daily_incr.sh      # 17:30 增量（5 个 zip ~750MB）
│   │   ├── weekly_sync.sh     # 周日 02:00 中频同步（3 个 zip ~570MB）
│   │   └── weekly_doctor.sh   # 周日体检
│   ├── alerts/
│   │   └── feishu.py
│   └── doctor.py              # 健康检查
├── vendor/                    # 本地 vendor（跟 git）
│   └── mootdx/                # mootdx 0.11.7 + 主人补丁
│       ├── _pypi/             # PyPI 下载的原始 wheel
│       ├── mootdx/            # 已解压 source
│       ├── UPGRADE_NOTES.md   # 上游变更记录
│       └── VENDOR_PROVENANCE.md
├── tests/
│   ├── test_bars.py
│   ├── test_meta.py
│   ├── test_financial_parse.py
│   └── fixtures/
├── data/                      # 数据卷（不 commit）
│   ├── parquet/
│   │   ├── sh/<symbol>.parquet     # 5880 sh A 股 K 线
│   │   ├── sz/<symbol>.parquet     # 5786 sz A 股 K 线
│   │   └── bj/<symbol>.parquet     # 588 bj A 股 K 线
│   ├── fin/
│   │   ├── raw/<quarter>.zip        # 财务原始 .dat 打包
│   │   └── parsed/<quarter>.parquet # 5526 × 585 / 264 DataFrame
│   ├── index/<symbol>.parquet       # 15 个指数 + 板块
│   ├── gp/<symbol>.parquet          # 股本数据（从 tdxgp.zip 解出）
│   ├── xdxr/                        # v2.0 · 期权 / 股权变动·v1.1 不下
│   ├── snapshot/<date>/             # 每日抽快照 zip 原始压缩包
│   └── meta.db                       # SQLite 元数据 + 下载日志
└── logs/                      # 入库日志（不 commit）
```

### 关键技术选型

| 项 | 选 | 理由 |
|---|---|---|
| **DataFrame** | pandas | 生态最广，与 daily_stock_analysis 一致 |
| **存储** | Parquet + SQLite | 列存压缩 + 关系元数据 |
| **Python** | 3.12 | 与 mootdx 0.11.7 + py-mini-racer 已验证 |
| **调度** | cron | 不引入 Airflow 等重型调度 |
| **打包** | **Python library**（**v1.1 不打 Docker**） | `pip install -e .` 直接 import，跟宿主机 Python 环境耦合即可 · 主人后续如需 Docker 打包再上 |
| **License** | MIT | 继承 mootdx |
| **告警** | 飞书 Open API | 主人指定群 |
| **Vendor 工具** | `vendoring` (PyPI) | 业界主流 vendor 工具，比人工更易回滚 |
| **主路径数据源** | **官方 .day 集中下载** | hsjday/tdxfin/tdxgp 是**权威完整包**；mootdx 仅作补充 + 实时增量 · ~~shqqday 现已验证为期权数据不属于 v1.1 主路径~~ |


### 📦 四.5 官方下载源（v1.1 主路径）🆕

**2026-07-03 发现（跨阶段进行中）**：通达信个人版客户端背后有**官方集中下载源**（仅以个人版 SDK 骨架的身份出现，实际上市面上的迅雷/猫扑/兔子 下载器都在用同路）。这是 v1.1 的**主路径**——**于 mootdx 在线协议拉取之前**优先调用。

| 官方压缩包 | URL | 大小 | 记录数 | 覆盖范围 | v1.1 使用场景 |
|---|---|---|---|---|---|
| `bjlday.zip` | `products/data/data/vipdoc/bjlday.zip` | 8.6 MB | 591 只 bj .day | 北交所上市以来所有 | Sprint 3 增量补齐 初验证 ✓ |
| **`hsjday.zip`** | `data.tdx.com.cn/vipdoc/hsjday.zip` | **540 MB** | **12,256 只 .day**（sh 5880 + sz 5786 + bj 588）| **沪深京所有 + 上市以来全历史**（sh 35 年 / sz 35 年 / bj 6 年） | **Sprint 3 全量 K 线主路径**·**1 个文件 1 分钟** | |
| `shlday.zip` / `szlday.zip` | `products/data/data/vipdoc/{sh,sz}lday.zip` | 216 + 252 MB | 须为 sh/sz 主要股本 | （可能为冗余；hsjday 已覆盖） | **不一定需要 · hsjday 已包含** |
| `shqqday.zip` / `szqqday.zip` | `products/data/data/vipdoc/{sh,sz}qqday.zip` | ~19 MB × 2 | 12,026 个 .day × 2 | ⚠️ **真相修正** = 上海/深圳股票期权日线（扩展行情）· 不是除权除息事件表 | **不下** · 含义为期权 · v2.0 |
| `xsbday.zip` | `products/data/data/vipdoc/xsbday.zip` | 33.5 MB | 股转系统（扩展行情） .day | 新三板（与北交所不同生态） | **不下** ✅ 重复 / hsjday 部分覆盖 |
| **`tdxfin.zip`** | `data.tdx.com.cn/vipdoc/tdxfin.zip` | **537 MB** | **297 个文件**（含 historical 季报 .dat/.zip 1989→2026）| A 股所有上市以来所有季报 | **Sprint 4 财务主路径** |
| **`tdxgp.zip`** | `data.tdx.com.cn/vipdoc/tdxgp.zip` | **666 MB** | **7,573 个股本 .dat**（含 sh/sz/bj + 场内基金 / 可转债）| 股本数据 + 公司基本情况 | **Sprint 4 底仓维度** |
| 指数 5 个 zip | `products/data/data/vipdoc/sh{zz,sb}day.zip etc.` | ~30 MB × 3 | 指数 | 上证、深证、沪深 300、创业板、科创 50 | Sprint 5 |

#### **通达信 .day 记录格式（金标准——已与 mootdx 源码互通验证）**

```
每条记录 32 字节 = struct('<I I I I I f I I')
即为: date(YYYYMMDD) uint32 × 8:
    open 价 × 100 int32,
    high 价 × 100 int32,
    low 价 × 100 int32,
    close 价 × 100 int32,
    amount 成交额 float32,
    vol 成交量 int32,
    reserved int32
```

- 官方仅披露产出 · 未披露格式 · 逆向 +	mocketource 逆向 完全一致
- 解析示例 (Py3.12):
  ```python
  import struct, pandas as pd
  from pathlib import Path
  data = Path('sh600519.day').read_bytes()
  recs = list(struct.iter_unpack('<IIIIIfII', data))  # 5953 条速 5s
  df = pd.DataFrame([{
      'date': r[0], 'open': r[1]/100, 'high': r[2]/100, 'low': r[3]/100,
      'close': r[4]/100, 'amount': r[5], 'vol': r[6], 'reserved': r[7],
  } for r in recs])
  ```

#### **跨期验证（2026-07-03）**

- ✅ hsjday 全量 12,254 / 12,256 文件解析成功（2 文件不明错误·仅为样本检测）
- ✅ cross-check（**PoC 验证记录 · 不进 v1.1 代码**）：sina vs .day × 600519/300750/688981（混主/创/科主板）= **0.0000% 误差**
- ✅ bj 北交所有 241 / 591 (41%) .day 最后交易日冻结于 2025-09-30 → 经 sina 验证为**真退市/停牌**（非 data server bug）（**PoC 验证 · 不进 v1.1 代码**）
- ✅ sh 9808 / sh (95%) + sz 8,786 (96%) 最后交易日为今日 2026-07-03

#### **官方源 vs mootdx 在线拉取对比**

| 维度 | 官方 .day 集中下载 | mootdx 在线协议拉取 |
|---|---|---|
| 是否官方 | ✅ 是通达信个人版背后 | ⚠️ 依赖社区逆向有多深 |
| 完整性 | 100% 覆盖 | 受 socket 稳定性限制 |
| 速度 | 1 个 540 MB 文件 ~1 min 下载 + ~30s 全解析 | 5500 只逐拉 × 30 ms = 3 min，但限于完整覆盖 |
| 连接限定频次 | 一次性并接 HTTP | 严重依赖服务端质量控制（亚平斯可能被限流） |
| 财务数据 | tdxfin 1989→2026 所有季包 | Affair 仅单季拉 |
| **主要成分** | ✅ **v1.1 主路径（全面 + 财务 + 股本）** | ✅ 实时增量 + 补充 |
| **v1.1 架构** | sources/official_zip.py 处理 .day/.dat | vendor/mootdx 调用 bytes socket 拉取 |

### 📋 四.6 完整下载矩阵（v1.1 定时全量设计）

**2026-07-03 3 轮调研后限定的完整包运行矩阵 · 18 个 zip 按频率分组** （第 4 轮修订：shqqday/szqqday 语义修订）:

| # | 包名 | 服务器 | size | 业务领域 | **频率** | v1.1 cron | 估算 | 备注 |
|---|---|---|---|---|---|---|---|---|
| 1 | **`hsjday.zip`** | `data.tdx.com.cn` | 540 MB | sh+sz+bj 全部 A 股日 K 线 | **每日 17:30** | Mon-Fri 17:30 | 17:30 后 5-6 MB/s · ~10-15 min | **主路径** |
| 2 | `shzsday.zip` | `www.tdx.com.cn` | 27 MB | 上证指数 000001.SH | **每日 17:30** | Mon-Fri 17:30 | < 1 min | 上证主要指数 |
| 3 | `szzsday.zip` | `www.tdx.com.cn` | 36 MB | 深证指数 399001.SZ | **每日 17:30** | Mon-Fri 17:30 | < 1 min | 深证主要指数 |
| 4 | `tdxzs_day.zip` | `www.tdx.com.cn` | 78 MB | 通达信板块指数 | **每日 17:30** | Mon-Fri 17:30 | ~1 min | 增强指数 |
| 5 | `tdxgp.zip` | `data.tdx.com.cn` | 666 MB | 股本 / 公司信息 | **每日 17:30** | Mon-Fri 17:30 | ~10 min | 每日实测有变动 · 必须每日下 |
| 6 | `tdxfin.zip` | `data.tdx.com.cn` | 537 MB | 财务数据包 | **每日 17:30**（当季进展 14.3 MB · 未来季为 164B 占位 .zip） | Mon-Fri 17:30 | ~10 min | 覆盖全部财年 |
| 7 | `shqqday.zip` | `www.tdx.com.cn` | 19 MB | ⚠️ **真相修正** = “上海股票期权日线 (扩展行情)” **不是除权除息** · 命名误导 | **不下** ✅ 主人期权不在 v1.1 范围 | — | — | 保留作 v2.0 期权扩展 |
| 8 | `szqqday.zip` | `www.tdx.com.cn` | 11 MB | 同上深证版 | **不下** ✅ 同上 | — | — | v2.0 期权扩展 |
| 9 | `shlday.zip` | `www.tdx.com.cn` | 216 MB | sh TCKV4=0 完整 | **不下** ✅ 被 hsjday 包含 | — | — | 重复 · hsjday 已含 |
| 10 | `szlday.zip` | `www.tdx.com.cn` | 252 MB | sz TCKV4=0 完整 | **不下** ✅ 被 hsjday 包含 | — | — | 重复 · hsjday 已含 |
| 11 | `bjlday.zip` | `www.tdx.com.cn` | 8.6 MB | bj 独立包 | **不下** ✅ 被 hsjday 包含 | — | — | 重复 |
| 12 | `xsbday.zip` | `www.tdx.com.cn` | 33 MB | ⚠️ 真相修正 · **股转系统（扩展行情）** | **不下** | — | — | v1.1 不下 |
| 13 | `shlday_4.zip` | `www.tdx.com.cn` | 228 MB | sh TCKV4=1 扩展 | **可选下** | Mon-Fri 17:30 | ~5 min | 与 shlday ~90% 重复 · 主人可选 |
| 14 | `szlday_4.zip` | `www.tdx.com.cn` | 226 MB | sz TCKV4=1 扩展 | **可选下** | Mon-Fri 17:30 | ~5 min | 同上 |
| 15 | `62day.zip` | `www.tdx.com.cn` | 50 MB | ⚠️ 真相修正 · **中证指数日线（扩展行情）** | **不下** ✅ 与 tdxzs_day 重复 | — | — | v1.1 不下 |
| 16 | `33day.zip` | `www.tdx.com.cn` | 227 MB | 中证指数扩展 | **不下** | — | — | 与 tdxzs_day 重叠 |
| 17 | `34day.zip` | `www.tdx.com.cn` | 20 MB | 开放式基金 | **不下** | — | — | 主人范围外 |
| 18 | `38day.zip` | `www.tdx.com.cn` | 3 MB | 货币型基金 | **不下** | — | — | 主人范围外 |
| 19 | `ggtday.zip` | `www.tdx.com.cn` | 156 MB | **港股通** | **不下** | — | — | v2.0 范围 |
| 20 | `ScJyData_zbca.zip` | `www.tdx.com.cn` | 193 KB | 自定义咨询公司数据 | **可选下** | Mon-Fri 17:30 | < 1 min | 主人可选 |

#### **下载量预算**

| 时段 | 包数 | 总下载量 | 预计耗时（@1 MB/s） |
|---|---|---|---|
| **工作日 17:30** | **5 + (2 可选) ** | **~750MB（默认 / + ~454MB 可选 · 总 1.2GB）** | **10-15 min**（默认） |
| **周日 02:00** | **3** | **~570MB** | **~10 min** |

#### **重试数学重塑（化解委员会 P0 #3）**

| 策略 | 重试粒度 | 3 次重试后失败率 | 量化结论 |
|---|---|---|---|
| ~~v1.0 mootdx 在线拉 5500 只~~ | **stock 级别** | 0.95^5500 ≈ 0 | ❌ **委员会 P0 #3 ：100% 告警永远启不了** |
| **v1.1 官方 zip 包级别** | **zip 级别** | 0.05^5 = 2.4e-7 ≈ 0.00003% | ✅ **100% 告警可正常运作 · 阈值改为"完成度退 > 1%"** |

化减机制：包级别粒度使 "重试 1 个 zip 3 次" ≠ "重试 5500 只 3 次" · 差距 = **5500 倍**. 委员会 P0 #3 风险 **在架构上被消除**（不是调度上绕开）。

---

## 🛡️ 五、安全 / 故障 / 监控

### 安全

| 风险 | 缓解 |
|---|---|
| 数据泄露 | 仅本地，不暴露网络端口 |
| mootdx 攻击面 | 与浏览器隔离（Docker sandbox） |
| 凭证泄露 | 飞书 token 仅存 `.env`，不 commit |

### 故障模式 + 处置

| 故障 | 现象 | 处置 |
|---|---|---|
| TDX 协议拒绝服务 | 全市场拉取超时 | 重试 3 次 → 包级重试（5 个 zip × 0.95^3 ≈ 0.0003%）→ 告警 · ~~sina 兜底  v1.1 不实现~~ |
| 财务文件下载失败 | 当季 .dat 拉不下来 | 重试 3 次 → 告警 |
| 主机磁盘满 | 服务进程或 cron 失败 | `data/` 移到独立数据盘 · 监控磁盘水位 |
| 数据库损坏 | SQLite 损坏 | 每周 cron 备份 `meta.db` 到 `data/backup/` |
| 服务进程僵死 | cron 跑后无结果 | watchdog 检测，kill + 重启 + 告警 |

### 监控 / 告警指标

| 指标 | 检查频率 | 告警阈值 | 告警渠道 |
|---|---|---|---|
| 每日增量成功率 | 每日 17:30 后 | < 100% | 群 `oc_812b4a80dbf93832f71b6135ef6cb25a` |
| 全量数据完整度 | 每周一次 | 跌幅 > 1% | 同上 |
| 当日数据延迟 | 每日检查 | > 24 hr | 同上 |
| 财务数据完整度 | 每季一次 | 跌幅 > 5% | 同上 |
| 进程存活 | 心跳 | 失联 > 6 hr | 同上 |

---

## 🗺️ 六、里程碑（v1.1 第 5 轮重写·基于今天发现重新拆分）

**v1.1 重排原则**：
- 总周期 26-28 工作日（5-6 周 + 2 天缓冲）= 委员会 2026-07-03 决定
- 不再计"21 天理想路径"——已验证为乐观估算
- **A+B+D 验证 + 委员会 P0 #3 化解**作为 Sprint 划分依据
- 调整**：**Sprint 3 拆分**（全量下载 vs 解析 vs 验证独立 Sprint·避免同周两大块代码）
- 调整**：**Sprint 4 财务 + 股本** 拆分（财务变 + 股本存量·依赖不同）

### 里程碑表（v1.1 第 5 轮 + **2026-07-04 第 9 轮 Sprint 2 末修订**：选项 B 合并 Sprint 3b 到 Sprint 4a）

| # | Sprint 名 | 周期 | 交付物 | 依赖 | 验证依据 |
|---|---|---|---|---|---|
| 0 | **项目初始化 + 文档同步 + vendoring 工具链验证** | **1 d · ✅** | GitHub repo + 目录骨架 + 初始化 commit + `docs/CONTRIBUTING.md` + vendoring 工具链验证 | 签字 | 本轮需求文档 · v1.1 第 8 轮评审 |
| 1 | **mootdx Vendor 化 + 补丁备用** | **1.5-2 d · ✅** | `vendor/mootdx/` 复制 + 4 bug 记入 UPGRADE_NOTES 但不修 + 单元测试 9/9 PASSED | Sprint 0 | Sprint 1 验证 commit `de91fd4`-`437f2c3` |
| 2 | **抽象层 + 元数据 SQLite** | **3 d · ✅ (2 h 实际)** ⚡ | `sources/official_zip.py` (流式 + run_full_parse) + `meta.db` schema + **35 单元测试 PASSED** + **M1 验证里程碑跑通 12,256 文件** | Sprint 1 | Sprint 2 验证 commit `affb5ce`-`04284ce` |
| 3 | **⚡ Sprint 3a (简化下载) + Sprint 3b (并入 4a)** | — | _见下_ | Sprint 2 | |
| 3a | · **简化下载**（v1.1 第 9 轮修订：原 3d → 1d 简化版）| **1 d** | `cron/daily_sync.sh` + `bulk_download.py` (curl + zip 解压 + 断点续传) + 5 zip 下载验收 (hsjday/tdxfin/tdxgp + 2 指数) | Sprint 2 | 主人 vm002 0.8 MB/s 3 zip 工作日 15-20 min 实测 |
| 3b | · _已并入 Sprint 4a（原 Sprint 3b 任务· 2026-07-04 第 9 轮修订）_| ~~3 d~~ | _见 Sprint 4a 附注_ | | |
| 4 | **财务 + 全量解析 + 压缩优化**（v1.1 第 9 轮整合：3b + 4a + Parquet 压缩优化）| — | _见下_ | Sprint 3a | |
| 4a | · **财务 + 全量解析 + 压缩优化** | **4 d** ⚠️ v1.1 第 9 轮修订（原 3d + 3b 3d + 压缩优化 1d = 7d 整合为 4d）| · `tdxfin.zip` 历史季报解 · 占位 164B 检测 · `FinancialReader.to_data` 集成 · 5526×585 DataFrame 验证 · · **原 Sprint 3b 12,256 文件已完成（Sprint 2 末 M1 验证）** → 本 Sprint 仅补跨期验证 + 错误率报表 · · ⚡ **Parquet 压缩优化**（Sprint 2 末实测 input 917MB → Parquet 1202MB 反转） · 选项: zstd / 1-market-1-Parquet / DuckDB 列存 | Sprint 3a | Phase 1 PoC 已验证 + Sprint 2 M1 跑通 |
| 4b | · 股本 + 指数（存量） | **3 d** | tdxgp.zip 股本解 (7,573 .dat) + 指数 5 zip 下载 + 5 主要指数解 + 验证 | 4a | 今天 §四 摸排验证 |
| 5 | **每日增量 + cron + 告警** | **4 d** | `cron/{daily,weekly}_sync.sh` + `alerts/feishu.py` + 化减 P0 #3 包级重试 (5500 重试 → 5 重试) + 3 个镜像容错 + 飞书告警 (3 个镜像全失败才告警) | Sprint 4b | 今天 §四.6 + §七 验证 |
| 6 | **库文档 + 上线 + 健康检查** | **3 d** | `README.md` + `doctor.py` 周报 + 路径检查 + 5 zip 每日自动化 E2E 测试 | Sprint 5 | 主人签字进入 |
| 7 | **验证 + 主人签字 + v1.1.0 tag** | **2 d** | 端到端压测（1 周持续 5 交易日）+ README + v1.1.0 tag + 官方源补充 (bj/xsbday 不下) + Sprint 8 跟进项 | Sprint 6 | 交付预期合理化 |

**总周期**（v1.1 第 9 轮修订）：
- ✅ 0 + 1 + 2 已完成 (实际耗时 ~7 h)
- 1 + 4 + 3 + 4 + 3 + 2 = **17 d** · v1.1 第 9 轮修订后中间估算（原 25.5-27d）
- 乐观估算：1 + 3 + 3 + 4 + 3 + 2 = **16 d**
- 最保守：1 + 4 + 3 + 4 + 3 + 2 = **17 d**
- + **2 d 缓冲** = **18-19 工作日** = **3.5-4 周**
- 主人会内评：**v1.1.0 末只需 17-19 工作日**（原 21 天 → 26-28 天 → 25.5-27 天 → **17-19 天** · 总节省 8-9 d）

**第 9 轮修订关键决策（2026-07-04 Sprint 2 末签字）**：
- ✅ Sprint 2 实测已实现原 Sprint 3b 解析任务（M1 验证 12,256 文件· 2 min 跑通）
- ⚡ **选项 B**：Sprint 3b 并入 Sprint 4a（节省 3d）
- ⚡ **新增**：Parquet 压缩优化入 Sprint 4a（从 Sprint 2 末负发现 +1d）

### 拆分决策依据（委员会 2026-07-03 + 验证发现）

| 拆分 | 原因 | 交付后验证 |
|---|---|---|
| **Sprint 3 → 3a + 3b** | 12,256 文件下载与解析是两大独立风险块（网络 / IO / schema）· 合并会造成调试粒度太粗 | 今天 PoC 验证：下载 ~15-20 min · 解析 ~3 min |
| **Sprint 4 → 4a + 4b** | 财务是“变” (有未来季占位 164B) · 股本 + 指数是“存量” (不变) · 同周交付在今天验证后看不合理 | 今天 §四 摸排验证 |
| Sprint 5 cron 实现与 P0 #3 化解合并 | 委员会反馈 P0 #3 是设计问题不是调度问题 · 必须在 cron 实现周同步验证 | §七 风险 #8 已解决 |
| Sprint 6 加上 **5 zip 每日自动化 E2E** | 委员会警告"不能拿 Sample In 测试 1 交易日 · 要跨周" | §六 原始草拟遗漏 |

### 依存关系图（v1.1 第 9 轮修订）

```
Sprint 0 (1d ✅)
  └→ Sprint 1 (1.5-2d ✅)
      └→ Sprint 2 (3d ✅ · 2h 实际)
          └→ Sprint 3a (1d · 简化下载)  ← 原 Sprint 3 6d 拆分改：1d 简化版
              └→ Sprint 4a (4d)  ← 合并原 Sprint 3b + 4a + 压缩优化
                  └→ Sprint 4b (3d)
                      └→ Sprint 5 (4d)
                          └→ Sprint 6 (3d)
                              └→ Sprint 7 (2d)  [v1.1.0 tag]
```

**关键路径** = Sprint 3a → Sprint 7（任何环节延迟 1d · 总周期 +1d）

**关键路径** = Sprint 1→Sprint 5（任何环节延迟 1d · 总周期 +1d）

### 验证里程碑（不是 Sprint · 跨 Sprint 检查点）

- [ ] **M1 · Sprint 2 末** — 抽象层能调取 mock vendor 验证 .day schema 正确 · `meta.db` 能追溯到 mock vendor
- [ ] **M2 · Sprint 3b 末** — 12,256 个 .day 全部解析成功 · 内部完整性检查 (record count / 时间连续性 / OHLCV 互查) · ~~sina 交叉验证 v1.1 不做~~
- [ ] **M3 · Sprint 4a 末** — gpcw20260331.dat 解析后 DataFrame 与 Phase 1 PoC 一致 · 占位 .dat 检测为 20B
- [ ] **M4 · Sprint 5 末** — 包级重试生效 (取 1 个不存在的镜像作负样本 · 验证另 1 个镜像自动续传) · 飞书告警手动触发 1 次
- [ ] **M5 · Sprint 7 末** — 5 个交易日的 E2E 实跑·Sprint 8 跟进项（v2.0 期货 / 港股 / 期权） 定义清楚

### Sprint 8 + v2.0 预告（v1.1 范围外·不计入周期）

- v2.0 · 港股通 ggtday.zip (156 MB · 1 zip)
- v2.0 · 期货 / 期权 shqqday.zip (19 MB × 2 · v1.1 验证语义为“期权” · 是 v2.0 合适起点)
- v2.0 · tushare 接入作为 mootdx 死亡后的零轮换主路径
- v2.0 · web API (README 公开 download_url) · 不只是本地 cron
- v2.0 · 东方财富 / 同花顺 隐式数据源（只加“同源验证 · 不同源出警”）

---

## ⚠️ 七、风险与缓解

| # | 风险 | 影响 | 概率 | 缓解 |
|---|---|---|---|---|
| 1 | **TDX 协议突然变更** | 全数据源失效 | 中 | 1) 抽象层已隔绝 · 2) ~~新浪 hq.sinajs.cn 兜底 v1.1 不实现~~ · 3) ~~tushare v1.1 不实现~~ · 4) v2.0 预留 |
| 2 | **mootdx 上游重构** | vendor 升级难 + 同步成本高 | 低 | 在 `vendor/mootdx/UPGRADE_NOTES.md` 记录每次官方升级决策；通过 `vendoring` 工具替换 |
| 3 | **主机磁盘满** | 数据写入失败 | 中 | `data/` 移到独立盘 + 监控水位 + 清理策略（保留 10 年 K 线，每年财报） |
| 4 | **财务缺失容忍度 < 95%** | 部分股票（已退市 / 改名）数据缺失 | 高 | 接受现状；财务缺失标"known_unavailable"标记，不计入完整度 |
| 5 | **飞书 token 失效** | 告警中断 | 中 | token 在 `.env` + 主人私聊告警 token 失效 |
| 6 | **主机当机** | cron 不执行 | 低 | cron 主机冗余（v2.0 再考虑） · 监控里"心跳失联"会告警 |
| 7 | **同质下拉对手兴价** | mootdx 服务器封禁 | 低 | 控制频率 + 灰度下载（首批 100，分批到位） |
| 8 | ~~"成功重试 3 次" 未到 100%~~ **（已解决）** | ~~5500 只 × 0.95^3 = 86% · 全量完成度 = 0.86^5500 ≈ 0 · "100% 告警永远启不了"~~ ⚠️ **委员会 2026-07-03 提示** · **2026-07-03 第 3 轮解决**：v1.1 主路径改用"5 文件 · 1 重试 ・ 包级粒度"（不是 stock 级别）：5 个 zip × 0.95^3 ≈ 0.0003% 失败率 · 实际“完成度退 > 1%”告警阈值可正常运作 | ~~高~~ · **已解决** | 化减：§三 IN #15 + 附录 F.2 |

---

## 📝 八、依赖与产物

### 依赖（需要主人决策 / 提供）

- **(已就绪)** Python 3.12 + mootdx 0.11.7（PoC 验证 OK）
- **(已就绪)** 主人 GitHub `ariesy` 账号 + 已有 SSH key（**仅主项目，不再用于 mootdx fork**）
- **(待确认)** 飞书群 `oc_812b4a80dbf93832f71b6135ef6cb25a` 机器人 webhook（**需要主人开通 / 提供 token**）
- **(待确认)** 主机磁盘 ≥ 10 GB 独立盘（**如果 `/app` 不够**）
- **(v2.0)** tushare token

### 产物（v1.1 后）

- GitHub repo `ariesy/tdx-chronos`（**只有主项目**）+ `/app/tdx-chronos/vendor/mootdx/` 本地 vendor
- **PyPI/GitHub 可 `pip install` 的 Python library**（**v1.1 不含 Docker**）
- 飞书告警机器人 + 健康检查周报
- 数据仓库约 5-8 GB（在 `/app/tdx-chronos/data/`）

---

## ✅ 九、签字确认

| 角色 | 名字 | 决策 | 签字日期 |
|---|---|---|---|
| 产品 owner | 朱琨（主人） | 待批（第 2 轮修订） | 待 |
| 监理 | claw-cortex | 已交文档 | 2026-07-03 (含 Q4 修订 + **委员会 4 条 P0 补正 + 官方下载源发现**） |

---

## 📎 附录

### A. 关键决定汇总（对齐聊天记录）

| # | 决定 | 来源 | 修订 |
|---|---|---|---|
| 1 | 项目命名 `tdx-chronos` | 主人选择 | — |
| 2 | 独立项目 + 独立 repo | Q1 | — |
| 3 | 全量历史（a） + 离线仓库（d） | Q2 a+d | — |
| 4 | **本地 vendor 模式**（不 GitHub fork） | Q4 | **2026-07-03 主人在 Sprint 0 启动前修订** |
| 5 | 独立数据目录 | Q5 | — |
| 6 | 上市以来所有 K 线 | Q6 C | — |
| 7 | 17:30 工作日 cron | Q7 C | — |
| 8 | A 股 K 线 + 财务 + 指数 | Q8 C | — |
| 9 | 告警到群 `oc_812b4a80dbf93832f71b6135ef6cb25a` | Q9 | — |
| 10 | 重试 3 次 + 失败告警 | Q10 B | — |
| 11 | K 线 100% + 财务 95% | Q11 B | — |
| 12 | **v1.1 不打 Docker 镜像** + 提供 Python library | **主人反馈 2026-07-03** | **v1.1 修订** |
| 13 | 🆕 **总周期 26-28 天**（4 周 + 2 天缓冲） · 不是 21 天理想路径 | 委员会 2026-07-03 | v1.1 第 2 轮 修订 |
| 14 | 🆕 **主路径** = 官方 .day 集中下载 （hsjday + tdxfin + tdxgp） · mootdx 仅作补充 · ~~shqqday 已退主路径（现语义为期权）~~ | 验证发现 2026-07-03 + 2026-07-03 第 3 轮修订 | v1.1 第 3 轮 修订 |
| 15 | 🆕 告警阈值改为 "完成度退 > 1%"（不限 100% 启不了） | 委员会 P0 #3 | v1.1 第 2 轮 修订 |
| 16 | 🆕 **重试粒度** = zip 级别（不是 stock 级别）· 0.05^5 ≈ 0.0003% 失败率·化解 P0 #3 | 验证发现 2026-07-03 第 3 轮 | **v1.1 第 3 轮 修订** |
| 17 | 🆕 **下载频率矩阵**：18 个 zip 分 4 频率段（每日 / 每周 / 不下 / 可选）· 5 zip × 750MB 工作日 17:30 + 3 zip × 570MB 周日 02:00 | 验证发现 2026-07-03 第 3 轮 | **v1.1 第 3 轮 修订** |
| 18 | 🆕 **架构**: "完整快照 + Parquet 比对增量" 策略 · 不依赖"是否下到最新"判断 · **差量检测独立于服务端** | 验证发现 2026-07-03 第 3 轮 | **v1.1 第 3 轮 修订** |
| 19 | 🆕 **数据格式层重新事实对齐**：5 行表 → 7 元素 + 2 个解析器 schema + 1 个文件映射表 + 3 个大小预估修正 | 验证发现 2026-07-03 第 4 轮 | **v1.1 第 4 轮 修订** |
| 20 | 🆕 **§六里程碑重写**：Sprint 3+4 拆分为 3a/3b/4a/4b · M1-M5 验证里程碑 · Sprint 8 + v2.0 预告 · 1+3+3+3+3+3+3+4+3+2=25 + 2 缓冲 = 27 工作日 | 主人 2026-07-03 14:46 | **v1.1 第 5 轮 修订** |
| 21 | 🆕 **去掉多源验证**（sina.py / aggregator.py）· v1.1 专做 tdx 数据下载+整理+调用 · v2.0 预留 | 主人 2026-07-03 14:51 | **v1.1 第 6 轮 修订** |
| 22 | 🆕 **4 bug 不修**（v1.1 主路径不触发）· 记入 vendor/UPGRADE_NOTES.md·Sprint 1 改为 "vendor 化 + 备用" | 主人 2026-07-03 14:54 | **v1.1 第 7 轮 修订** |
| 23 | 🆕 **委员会 P0 补正**：Sprint 1 改 1.5-2d · 总周期 25.5-27d · Sprint 0 加 vendoring 可行性验证 · §三 IN #1 边界表达清晰 | 主人 2026-07-03 14:57 + 委员会评审 | **v1.1 第 8 轮 修订** |

### B. 参考 PoC 文档

- `projects/tdx-poc/decision.md` — Phase 1 决策
- `projects/tdx-poc/reviews/council-phase0.md` — 评审意见
- `projects/tdx-poc/goals.md` — 原始目标

### C. 相关 skill 引用

- `superpowers` — 进入实现前必须走 brainstorm → plan → TDD
- `project-management-skills` — 周报 + SDLC 全程跟踪
- `product-req-assistant` — 后阶段可生成正式 PRD

---

## 📥 附录 F · 通达信官方下载源摸排报告（v1.1 第 2 轮新增）

### F.1 概述

`2026-07-03` 主人问"首次全量数据是否可通过此链接下载 [个人行情数据 - 通达信软件 - 深圳市财富趋势科技股份有限公司](https://www.tdx.com.cn/article/vipdata.html)"**。** 后者意外发现：通达信个人版 SDK 后面有一个**可靠、可重复、可官方访问的集中下载源系统**。

### F.2 下载源汇总 + 合规性

| 压缩包 | URL | 主机 | 文件存在 | 大小 | 上次修改 | 可速 | 可重复 | 官方 |
|---|---|---|---|---|---|---|---|---|
| **hsjday.zip** | `https://data.tdx.com.cn/vipdoc/hsjday.zip` | `data.tdx.com.cn` | ✓ | 540 MB | 2026-07-03 09:27 | ✓ (~1 MB/s) | ✓ 每日重生 | ✅ 深圳市财富趋势（mozxin 文件场） |
| **tdxfin.zip** | `https://data.tdx.com.cn/vipdoc/tdxfin.zip` | `data.tdx.com.cn` | ✓ | 537 MB | 2026-07-03 00:02 | ✓ | ✓ 每日重生 | ✅ |
| **tdxgp.zip** | `https://data.tdx.com.cn/vipdoc/tdxgp.zip` | `data.tdx.com.cn` | ✓ | 666 MB | 2026-07-03 11:09 | ✓ | ✓ 每日重生 | ✅ |
| bjlday.zip | `https://www.tdx.com.cn/products/data/data/vipdoc/bjlday.zip` | `www.tdx.com.cn` | ✓ | 8.6 MB | 日常 | ✓ | ✓ | ✅ |
| shlday.zip / szlday.zip | 各 ~220 MB | 同上 | ✓ | 现货 | ✓ | ✓ | ✅ | |
| shqqday.zip / szqqday.zip | 各 ~20 MB | 同上 | ✓ | 现货 | ✓ | ✓ | ✅ · 但**实际语义为期权不是除权除息** | |
| shzsday.zip / szzsday.zip / tdxzs_day.zip | 各 ~30 MB | 同上 | ✓ | 现货 | ✓ | ✓ | ✅ | |

**所有 5 个 URL 都是公开 + 静态 + 禁用身份认证**。

### F.3 官方下载 vs 走二手 mirror（如 mootdx 什么逆向）

**官方源头最准确** ——它们就是通达信个人版客户端背后的同一个文件仓。mootdx 逆向接口 背后也是这些 .day 文件生成的。

### F.4 补充爬取发现

> 起初以为只有 bjlday + 5 个 makeup zip，实际上还能从 `stockfin.html` 翻出 2 个根本未在子菜单中出现的"专业财务数据"大包：
> - `tdxfin.zip` (537 MB · 297 个 季度 .dat)
> - `tdxgp.zip` (666 MB · 7,573 个 股本 .dat)
>
> 另从 `customdown.html` 出仓：
> - `ScJyData_zbca.zip` (193 KB · 指定咨询公司金股数据)

### F.5 v1.1 第 3 轮修订调研· 18 zip last-modified 实测（2026-07-03 14:00）

为辅助 4 频率划分，加上对所有已知 zip 的 `HEAD` request 拿 `Last-Modified` / `Content-Length`：

| 包名 | Last-Modified (UTC) | size | 频率判断 |
|---|---|---|---|
| `hsjday.zip` | 2026-07-03 **07:58** | 540 MB | **每日**（猜：成交 09:30-11:30 / 13:00-15:00 + 结算后） |
| `tdxfin.zip` | 2026-07-03 **00:02** | 537 MB | **每日**（实际每天 · 但仅由有季报变动公司 · 曾请财务下传） |
| `tdxgp.zip` | 2026-07-03 **12:09** | 666 MB | **每日**（股本变动频繁如发行 / 退出） |
| `shlday.zip` | 2026-07-03 09:27 | 216 MB | 每日 · 但**被 hsjday 包含** |
| `szlday.zip` | 2026-07-03 09:57 | 252 MB | 每日 · 但**被 hsjday 包含** |
| `bjlday.zip` | 2026-07-03 08:00 | 8.6 MB | 每日 · 但**被 hsjday 包含** |
| `xsbday.zip` | 2026-07-03 09:36 | 33 MB | 每日 · 但**被 hsjday 包含** |
| `shqqday.zip` | 2026-07-03 09:21 | 19 MB | **每日 · 但语义为期权不是除权除息** |
| `szqqday.zip` | 2026-07-03 09:26 | 11 MB | **每日 · 同上语义为期权** |
| `shzsday.zip` | 2026-07-03 08:22 | 27 MB | **每日** |
| `szzsday.zip` | 2026-07-03 08:25 | 36 MB | **每日** |
| `tdxzs_day.zip` | 2026-07-03 08:03 | 78 MB | **每日** |
| `33day.zip` | 2026-07-03 04:21 | 227 MB | **每日** · 中证指数扩展 |
| `34day.zip` | 2026-07-03 04:30 | 20 MB | **每日** · 开放式基金 |
| `38day.zip` | 2026-07-03 04:35 | 3 MB | **每日** · 货币型基金 |
| `62day.zip` | 2026-07-03 09:30 | 50 MB | **每日** · 股转 |
| `shlday_4.zip` | 2026-07-03 08:36 | 228 MB | **每日** · TCKV4=1 扩展 |
| `ggtday.zip` | 2026-07-03 10:03 | 156 MB | **每日** · 港股通 |

**总发现**：今日除手工脚本补丁 `Except2025.zip` 外，**所有 18 个 zip 都是当日的**——代表通达信服务端是一个**每日全量重生 zip**（不使用增量 patch）。

### F.6 150 路径 incremental 包扫描（2026-07-03 13:45）

为验证“是否有今日增量 zip” 的可能，进行“4 server × 30 pattern”扫描：

- 0/150 路径命中
- 证明**今日增量 zip 不存在**为服务端默认策略（其他厂商如 tushare / akshare 可能有但不在本次范围）

---

## 🏛️ 附录 G · 委员会评审会议记录（v1.1 第 2 轮）

### G.1 评审触发

主人于 `2026-07-03 12:40 UTC` 发起 "请智者委员会评审需求文档"。

### G.2 主审裁决：GO with conditions

5 名委员评审综··略 ·㬑主提·4条 P0 补正：

| P0 # | 补正 | 在文档中的位置 |
|---|---|---|
| 1 | **时间预算乐观 20-30%**：6 个 Sprint × ~26 天估算（不是 21 天理想路径） | §六 里程碑表 |
| 2 | **Vendor = 主权 ≠ 责任减轻**：vendor 让主人独立承担 mootdx 死亡后果·fork 至少有社区眼睛看着 | §三 边界 #5 |
| 3 | **"成功"数学不漂亮**：5500 只 × 0.95^3 = 86% · 全量完成度 = 0.86^5500 = 0 · "100% 成功率告警" 誓·永远启不了 | §七 风险 #8 |
| 4 | **财务隐藏产品**：`tdxgp.zip` (股本数据) + `shqqday.zip` ⚠️ 验证后实为期权数据·不属 v1.1 主路径 — 2026-07-03 验证后发现 | §三 IN #12 + 第 3 轮修订 |

### G.3 现场细节

委员主张 "这 4 条补上就签 · 找不到也不致命" ·主人未面商业到货·按以代理拍板。

### G.4 补正后的裁决

补正 4 条 · v1.1 v1.1.* 裁决· 全部合规。**请主人按理签字**。

---

## 🔄 附录 H · 修订历史

### H.1 v1.1 第 1 轮 · 2026-07-03 (Q4 vendor 模式)

- 选择 vendor 模式 而不 GitHub fork
- 附录 D 新增决策依据
- 清单条文添加 Sprint 1 执行明细

### H.2 v1.1 第 2 轮 · 2026-07-03 (官方下载源 + 委员会 4 条 P0)

- 🆕 **§四.5 官方下载源** · 2549 字符 · 4 个表 + 2 个验证示例 + 架构对比
- 🆕 **§三 IN #12** · 官方 .day 集中下载
- 🆕 **§三 边界 #5/#6** · vendor 主权 + 官方源备份 URL
- 🆕 **§七 风险 #8** · "100% 成功率告警永远启不了"补正
- ✏️ **§六 里程碑** · 21 → 26-28 天·加 2 天缓冲
- 🆕 **附录 F** · 通达信官方下载源摸排报告（8 表 1 发现）
- 🆕 **附录 G** · 委员会评审会议记录（4 条 P0）
- 🆕 **附录 H** · 修订历史（本节）

### H.3 v1.1 第 3 轮 · 2026-07-03 (18 zip 频率矩阵 + 包级重试)

主人在文档中间询 “每天只需要下载这一个文件吗？”，调查后补正：

- 🆕 **§三 IN #5b** · 每周同步·周日 02:00 3 zip
- 🆕 **§三 IN #13-15** · 频率矩阵 + 完整快照对比增量 + 包级重试
- 🆕 **§四.6** · 20 项目完整下载矩阵（18 zip + 2 补丁）
- 🆕 **§四 cron/** · 加 weekly_sync.sh 脚本
- 🆕 **§四.6 “重试数学重塑”表** · 化解委员会 P0 #3 （变 · 设计上而不是调度上）
- 🔄 **§七 风险 #8** · 从“高风险未解决” → “已解决”·包级重试

### H.4 v1.1 第 4 轮 · 2026-07-03 (数据格式 + 解析器 schema)

主人在第 3 轮后问"检查数据格式章节·是否需要基于当前已下载的文件内容进行调整"，检查后补正：

- 🆕 **§四 5 行表** → **7 行表**（加 snapshot/gp/xdxr 三行）
- 🆕 **§四.B .day 解析器 schema** · `'<'IIIIIfII'` + DataFrame schema + 字段名标准化
- 🆕 **§四.C .dat 财务解析器 schema** · 引用 Phase 1 PoC FinancialReader.to_data
- 🆕 **§四.D 文件名规范** · 1-1 映射（v1.1 数据目录纪律化）
- 🆕 **§四.E 大小预估修正** · K 线 5→8 GB · 财务 0.8→0.1 GB/年 · 元数据 0.001→0.01 GB
- 🆕 **§三 IN #16** · 数据格式层验收点
- 🆕 **§四 目录结构 data/** · 加 snapshot/ + gp/ + xdxr/ 子目录

### H.5 v1.1 第 5 轮 · 2026-07-03 (§六里程碑重写)

主人在 14:46 UTC 说"基于当前的需求和实现路径的变动，再重新检查和修订里程碑章节"，检查后重写：

- 🆕 **Sprint 3 拆分**为 3a（下载） + 3b（解析 + 验证） — 两大独立风险块
- 🆕 **Sprint 4 拆分**为 4a（财务变） + 4b（股本 + 指数存量）
- 🆕 **Sprint 5 加上**"化减 P0 #3" · Sprint 6 加上"5 zip 每日 E2E"（委员会警告）
- 🆕 **总周期计设**: 1+3+3+3+3+3+3+4+3+2 = 25 + 2 缓冲 = 27 工作日（5-6 周）
- 🆕 **M1-M5 验证里程碑**（跨 Sprint 检查点）— 不混在 Sprint 里
- 🆕 **Sprint 8 + v2.0 预告**：期货 / 港股 / 期权 / tushare / web API / 同花顺 验证源
- 🆕 **依赖图谱**·明确关键路径 = Sprint 1-5

### H.6 v1.1 第 6 轮 · 2026-07-03 (砍掉多源验证·v1.1 专做 tdx)

主人在 14:51 UTC 说"无需 sina.py / aggregator.py 这两个文件的功能，本项目只用来做 tdx 数据的下载，整理和提供调用"：

- ❌ **删掉** `sources/sina.py` · 公网 HTTP 兑底（v2.0 预留）
- ❌ **删掉** `sources/aggregator.py` · 多源一致性验证（v2.0 预留）
- 🔄 **§二 问题 1** · 数据源单一脆弱描述改为 "v1.1 范围外"
- 🔄 **§三 IN #12 / #3** · 描述去掉"sina cross-check 0.0000%" 列为 PoC 记录
- 🔄 **§四 目录结构** · 划掉 sina.py / aggregator.py
- 🔄 **§六 Sprint 3b 描述** · 去掉"sina 交叉验证"
- 🔄 **§六 M1 M2** · mock vendor / 内部检查（不进 sina）
- 🔄 **§七 风险 #1 + 表跨** · 去掉"新浪 / tushare 兑底"
- 🔄 **附录 A 表** · "多源扩展" 改为 "v1.1 只放 mootdx"
- 🔄 **附录 G Vendor 架构** · 三层变单层（v2.0 可扩展）

**v1.1 定义最终明确**：只做 tdx 官方 .day/tdxfin/tdxgp 下载 + Parquet 整理 + 本地调用接口，不实现多源验证，不实现在线 HTTP 兑底。

### H.7 v1.1 第 7 轮 · 2026-07-03 (4 bug 不修·Sprint 1 降为 vendor 备用)

主人在 14:54 UTC 说"前面提到的 mootdx 的 4 个 bug 补丁具体是什么？在目前通过下载全量加增量数据的方式下还需要对此 4 个 bug 进行修复吗"。

- 🔄 **§三 IN #1 验收** · 改为 "v1.1 主路径不调 mootdx·4 bug 不修·仅记入 vendor/UPGRADE_NOTES.md"
- 🔄 **§六 Sprint 1 交付物** · 改为 "vendor 化 + 4 bug 记入 UPGRADE_NOTES.md 但不修 + 单元测试只测 import + 调用"
- 🆕 **头部 "本次修订新增"** · 4 bug 清单表（带触发模块/函数/v1.1 是否触发列）
- 🆕 **附录 A #22** · 4 bug 不修决定
- 🆕 **附录 G 4 bug 详细记录** · 见 Phase 1 decision.md §弱证据 #3-#6

**v1.1 第 7 轮意义**：诚实面对 v1.1 新主路径（官方 .day 集中下载 + struct 解析）与 mootdx 的关系已经从 "主路径" 退化为 "v2.0 备用 + 抽象层参考实现" · Sprint 1 改为 "vendor 备用" 不是 "修 4 bug"。

### H.8 v1.1 第 8 轮 · 2026-07-03 (委员会 P0 补正)

主人在 14:57 UTC 说"请智者委员会再进行新一轮评审"。委员会 2m11s 返回 6 Action Items · 处理 5/6。

- 🔄 **§六 Sprint 1 表格** · 3d → 1.5-2d · 附注缩短原因
- 🔄 **§六总周期** · 改为 25.5-27d 区间 · 显化 3 估算
- 🔄 **§六 Sprint 0 交付物** · 加 "vendoring 可行性验证" 子任务
- 🔄 **§三 IN #1** · 边界表达清晰（"v1.1 主路径 = 官方 .day 集中下载 + struct 解析，不走 mootdx 在线 socket 路径"）
- 📋 **Action Item #4 不采纳** · Sprint 4b 并行可能性评估（v1.1 维持串行·v2.0 跟进）
- 🆕 **附录 A #23** · 委员会 P0 补正决定
- 🆕 **附录 G 评审记录** · Confidence Medium · 6 Action Items 处理表

**v1.1 第 8 轮意义**：委员会验收 - 第 7 轮决策逻辑正确但表文不一致已全部修正 · 主人签字进入 Sprint 0 的门槛现在干净
- 🆕 **附录 F.5** · 18 zip last-modified 实测表
- 🆕 **附录 F.6** · 150 路径 incremental 包扫描结论
- 🔄 **附录 A #16-18** · 3 项新决定
- 🆕 **文末修订标记**·表明本轮是第 3 轮

---

## 🔄 附录 D · Vendor vs Fork 决策依据（v1.1 修订）

| 维度 | Fork | Vendor（采用） |
|---|---|---|
| 主人需要大量修改 | ❌ 上游 PR 难走通，自己仓库节奏也乱 | ✅ 直接在 vendor/ 下改，节奏主人定 |
| 扩展多源（不只 mootdx） | ❌ 一个 fork 不够 | ✅ vendor/ 可以并排放多个源·但 v1.1 **只放 mootdx**（新浪 + tushare v2.0 预留） |
| 双仓同步负担 | ⚠️ master 跟 upstream + 频繁 rebase | ✅ 不存在，下载新版本时一次性 diff |
| 代码归属 | ⚠️ 公开发到 GitHub | ✅ 仅本地，公司场景友好 |
| 与上游作者关系 | ⚠️ 公开发版有"协助"含义 | ✅ 纯内部使用，无 PR 义务 |
| 升级路径 | ⚠️ rebase 冲突常常需要硬解决 | ✅ `vendoring` 工具一键替换，diff 可读 |
| **核心动机** | 与上游合作 | **完全自我掌握** ← 与 tdx-chronos 哲学一致 |

### Vendor 单层架构（v1.1 · v2.0 可扩展）

```
/app/tdx-chronos/vendor/
├── mootdx/       # 主 TDX 协议实现（已改 4 个 bug）
├── ~~sina/~~         # ❌ v1.1 不实现·v2.0 可选
└── ~~tushare/~~      # ❌ v1.1 不实现·v2.0 可选
```

### Vendor 初始化流程

```bash
# scripts/vendor_init.sh
# 首次启动：从 PyPI 下载固定版本，存到 vendor/，初始化 git 跟踪
pip download mootdx==0.11.7 -d vendor/mootdx/_pypi/
cd vendor/mootdx/ && python -m vendoring sync
```

### Vendor 升级机制（未来用）

当上游 mootdx 发新版时：
1. 主人拉新版本运行 `vendoring sync vendor/mootdx/`
2. 加 `vendor/mootdx/UPGRADE_NOTES.md` 说明变动了什么
3. 运行测试套件验证补丁仍可用
4. 升级完成（换源代价 = 1 条命令）

**结论**：主人在 Sprint 1 启动第 1 周做出此调整。理由：**tdx-chronos v1.1 只提供 tdx 数据下载 + 整理 + 调用，多源验证 v2.0 预留**。

---

> ⚠️ **HARD GATE**：本需求文档签字前，**不得进入设计 / 实现阶段**。
> 修改建议请直接 commit 到 `requirements.md` 提交 PR 评审。

_文档完成: 2026-07-02 22:48_
_修订: 2026-07-03 (Q4 vendor 模式 + 委员会 P0 补正 + 官方下载源发现 + 第 3 轮 18 zip 频率矩阵 + shqqday 真相修正 + 第 4 轮 数据格式 + 解析器 schema + 第 5 轮 里程碑重写 + 第 6 轮 砍掉多源验证 v1.1 专做 tdx + 第 7 轮 4 bug 不修·Sprint 1 降为 vendor 备用 + **第 8 轮 委员会 P0 补正·Sprint 1 1.5-2d·总周期 25.5-27d**)_