# Sprint 6 Implementation Plan · 股本 type 1-48 字段语义映射

**Design**: [2026-07-05-sprint6-type-semantics-design.md](2026-07-05-sprint6-type-semantics-design.md)
**执行模式**: 直接动手 (1 文件 + 1 测试 · lean)

---

## T1 · `src/tdx_chronos/fin/tdxgp_types.py`

**目标**: type 1-48 → 字段语义映射 + 4 category 桶

### 步骤

1. 写 `src/tdx_chronos/fin/tdxgp_types.py`:
   - `TYPE_CATEGORY_MAPPING: Dict[int, Tuple[str, str]]` (type → (name, confidence))
   - `TYPE_NAME: Dict[int, str]` (type → name · 反向映射)
   - `CATEGORY_BUCKETS: Dict[str, List[int]]` (5 类)
   - `CATEGORY_COLUMNS: Dict[str, List[str]]` (category → 字段名)
2. 写 `tests/unit/test_tdxgp_types.py` (5 测试):
   - mapping 完整性
   - buckets disjoint
   - name lookup
   - category 边界
   - confidence 合法值

### Verify
- 5/5 PASSED
- 真跑茅台 4 categories → 行数与 type 1-48 摸排一致

---

## T2 · `TdxGpRecordReader.to_categorized(category)` + sprint6-report

**目标**: 在 tdxgp_record.py 加 to_categorized 方法 + 真验收 + 报告

### 步骤

1. 在 `tdxgp_record.py` 加:
   ```python
   def to_categorized(records_path: Path, category: str) -> pd.DataFrame:
       """按 category 过滤 + 重命名 columns"""
       from tdx_chronos.fin.tdxgp_types import CATEGORY_BUCKETS
       types = CATEGORY_BUCKETS.get(category, [])
       table = pq.read_table(records_path, columns=['code','date','value_1','value_2','market'])
       mask = pc.is_in(table.column('type'), value_set=types)
       filtered = table.filter(mask)
       return filtered.to_pandas()
   ```

2. 写 `tests/unit/test_tdxgp_categorized.py` (3 测试):
   - capital_share / circulating_share / shareholder_structure

3. 真跑 4 categories on clean data:
   - 茅台 (600519) 验证
   - 全市场验证

4. 写 `logs/sprint6-report.md`:
   - 2 commits (T1 + T2)
   - 5 + 3 = 8 测试 PASSED
   - 真验收 4 categories 行数
   - 摸排真相 (type 1-48 推测)

5. commit + push

### Verify
- 8/8 PASSED
- 真跑结果与 design 表格一致
- 远端 29 commits

---

Co-Authored-By: claw-cortex 🦞 <ariesy.bleiben@gmail.com>