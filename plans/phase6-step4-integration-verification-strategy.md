# Phase⑥ Step4 集成验证策略
## Day 1 准备文档

**日期**: 2026-03-26
**状态**: 🗂️ 历史验收策略文档（未执行状态仅对应 2026-03-26）
**版本**: 1.0 Final
**受众**: Agent 协同、单元测试执行、集成测试执行

> 说明：本文记录 Step4 集成验证启动前的策略设计。后续实现推进请以
> `CLAUDE.md` 和 `文档/70_工作日记/2026-03-27.md` 为准；正文保留原策略语义。

---

## 概述

Phase⑥ Step4 的目标是将已完成的 3 个 Level-2 子求解器（propulsion、resource_allocation、trajectory_opt）集成到 BCD（块坐标下降）迭代框架中，并通过 Harmony Search 驱动。

本策略文档规定了集成验证的 4 个阶段、每阶段的检查点、通过/失败标准，以及诊断路径。

---

## 前置状态（Phase⑥ Step3 完成后）

### 现有模块状态

| 模块 | 文件 | 状态 | API |
|------|------|------|-----|
| **Propulsion** | `edge_uav/model/propulsion.py` | ✅ 完成 | `solve_propulsion(scenario, q, params)` → `PropulsionResult` |
| **Resource Allocation** | `edge_uav/model/resource_alloc.py` | ✅ 完成 | `solve_resource_allocation(scenario, offload_decisions, params, alpha, gamma_w)` → `ResourceAllocResult` |
| **Trajectory Opt** | `edge_uav/model/trajectory_opt.py` | ✅ SOCP 修复完成 | `solve_trajectory_sca(scenario, offload, f_fixed, params, sca_iter)` → `TrajectoryResult` |
| **BCD Loop** | `edge_uav/model/bcd_loop.py` | ❌ 待实现 | 规范见下 |
| **HS Individual** | `heuristics/hsIndividualEdgeUav.py` | ⚠️ 待修改 L311-320 | 调用 BCD Loop 代替 OffloadingModel |

### 测试框架

| 测试集 | 文件 | 状态 |
|--------|------|------|
| 单元测试 | `tests/test_bcd_loop.py` | ✅ 框架完成，5 个测试待通过 |
| Propulsion 测试 | `tests/test_propulsion.py` | ✅ 14 个通过 |
| Resource Alloc 测试 | `tests/test_resource_alloc.py` | ✅ 14 个通过 |
| Trajectory Opt 测试 | `tests/test_trajectory_opt.py` | ✅ 10/12 通过 |
| HS Individual 测试 | `tests/test_hs_individual_edge_uav.py` | ⚠️ 待修改以覆盖 BCD 路径 |

---

## 阶段 1：代码审视检查点（30 min）

**目标**: 在单元测试运行前，验证代码结构兼容性。

### 1.1 BCD Loop 导入兼容性

**检查清单**：
- [ ] `bcd_loop.py` 正确导入 3 个 Level-2 求解器（propulsion, resource_alloc, trajectory_opt）
- [ ] 导入路径符合项目结构：`from edge_uav.model.xxx import yyy`
- [ ] 不存在循环导入（Level-2 求解器 ← BCD Loop ← offloading）

**验证方式（Codex read-only）**:
```bash
# 伪代码，实际由 Codex 执行
1. 打开 bcd_loop.py
2. 检查导入语句是否包含：
   - from edge_uav.model.propulsion import solve_propulsion, PropulsionResult
   - from edge_uav.model.resource_alloc import solve_resource_allocation, ResourceAllocResult
   - from edge_uav.model.trajectory_opt import solve_trajectory_sca, TrajectoryResult
   - from edge_uav.model.precompute import Level2Snapshot
3. 交叉验证：这些模块是否真实存在且公开这些符号
```

**通过标准**: 所有导入语句都能在代码中找到定义，无 ImportError 迹象。

---

### 1.2 clone_snapshot() 深拷贝逻辑

**检查清单**：
- [ ] `clone_snapshot(snapshot: Level2Snapshot) -> Level2Snapshot` 函数存在
- [ ] 实现逻辑：使用 `copy.deepcopy()` 或等价方式
- [ ] 深拷贝覆盖范围：snapshot.q（2D 嵌套 dict）、snapshot.f_edge（3D 嵌套 dict）、source 字段
- [ ] 返回值创建新的 Level2Snapshot 对象（而非返回原对象）

**验证方式（Codex read-only）**:
```python
# 预期伪代码形式
def clone_snapshot(snapshot: Level2Snapshot) -> Level2Snapshot:
    from copy import deepcopy

    new_q = deepcopy(snapshot.q)
    new_f_edge = deepcopy(snapshot.f_edge)
    new_source = f"{snapshot.source}_cloned"

    return Level2Snapshot(
        q=new_q,
        f_edge=new_f_edge,
        source=new_source
    )

# 检查点：
# 1. deepcopy() 调用存在 ✓
# 2. 新对象创建明确（不是简单赋值）✓
# 3. source 字段被赋予新值（便于追踪来源）✓
```

**通过标准**: 函数实现满足上述 3 个检查点。

---

### 1.3 BCDResult 数据类与 hsIndividualEdgeUav 接口兼容性

**检查清单**：
- [ ] `BCDResult` dataclass 包含字段：
  - `q: dict` (轨迹优化结果)
  - `f_local: dict` (本地计算频率)
  - `f_edge: dict` (边缘计算频率)
  - `total_cost: float` (总目标函数值)
  - `feasible: bool` (可行性标志)
  - `bcd_iterations: int` (实际迭代轮数)
  - `diagnostics: dict` (诊断信息，用于 promptHistory)

**与 hsIndividualEdgeUav.runOptModel() 的兼容性检查**:
```python
# 现有代码（L311-320）会被修改为：
# 原：result = OffloadingModel(...).solve()
# 新：result = run_bcd_loop(scenario, snapshot, params)
#     snapshot = clone_snapshot(prev_snapshot)  # 热启动

# hsIndividualEdgeUav 期望从 result 中读取的字段：
# 1. result.total_cost  → 用于 hsPopulation 排序（seek minimum）
# 2. result.feasible    → 用于可行性过滤
# 3. result.diagnostics → 追加到 self.promptHistory["simulation_steps"][step_name]
```

**验证方式（Codex read-only）**:
```bash
# 检查 BCDResult 定义
1. 查找 class BCDResult 的声明
2. 确认包含 total_cost, feasible, diagnostics 三个关键字段
3. 在 hsIndividualEdgeUav 中查找访问这些字段的代码（修改后）
4. 验证访问模式（如 result.total_cost）与字段名一致
```

**通过标准**:
- BCDResult 包含全部 7 个字段
- 字段类型与使用位置兼容（如 `total_cost: float` 可用于数值比较）
- diagnostics 能转为 JSON（不含非序列化对象）

---

### 1.4 五个 Snippet 函数的签名与计划一致性

**预期的 5 个内部函数**（来自 CodeX MCP 设计输出）:

| # | 函数名 | 签名 | 用途 |
|---|--------|------|------|
| 1 | `_check_feasibility` | `(result: PropulsionResult) -> bool` | 检查能量约束 |
| 2 | `_compute_cost_from_blocks` | `(prop_r, res_r, traj_r) -> float` | 聚合 3 个求解器的成本 |
| 3 | `_prepare_trajectory_input` | `(scenario, f_fixed, offload) -> dict` | 格式化 trajectory_opt 的输入 |
| 4 | `_rollback_and_revert` | `(snapshot, iter_num) -> Level2Snapshot` | 回滚机制 |
| 5 | `_update_progress_diagnostic` | `(bcd_iter, prev_cost, curr_cost) -> dict` | 诊断信息更新 |

**验证方式（Codex read-only）**:
```bash
# 对每个函数逐一检查：
for func_name in [_check_feasibility, _compute_cost_from_blocks, ...]:
    1. 搜索函数定义
    2. 提取函数签名（参数列表和返回类型注解）
    3. 与表格第 3 列对比
    4. 检查函数体是否与第 4 列用途一致
```

**通过标准**:
- 5 个函数都存在
- 签名与计划表一致
- 函数体涵盖注释中提到的操作（如能量检查、成本聚合）

---

## 阶段 2：单元测试（快照隔离 + 回滚机制）（15 min）

**目标**: 验证 BCD 循环的核心机制（深拷贝隔离、回滚限制）。

### 2.1 T1：深拷贝隔离测试（CRITICAL）

**测试名**: `test_bcd_deepcopy_isolation`
**文件**: `tests/test_bcd_loop.py`

**预期行为**:
```python
# 初始快照：q[0] = (500, 500)
snapshot_0 = Level2Snapshot(q={0: {0: (500.0, 500.0), ...}}, ...)

# 克隆并修改
snapshot_1 = clone_snapshot(snapshot_0)
snapshot_1.q[0][0] = (600.0, 600.0)  # 修改克隆副本

# 验证原快照未变化
assert snapshot_0.q[0][0] == (500.0, 500.0)  ✓
assert snapshot_1.q[0][0] == (600.0, 600.0)  ✓
```

**运行命令**:
```bash
uv run pytest tests/test_bcd_loop.py::TestBCDDeepCopyIsolation -v
```

**预期输出**:
```
tests/test_bcd_loop.py::TestBCDDeepCopyIsolation::test_bcd_deepcopy_isolation PASSED
```

**通过标准**: 测试返回 PASSED，无 AssertionError。

**失败排查**:
| 症状 | 根因 | 排查步骤 |
|------|------|--------|
| `AssertionError: original snapshot was modified` | `clone_snapshot()` 未做深拷贝，只做了浅拷贝 | 检查 clone_snapshot() 是否使用 `deepcopy()` 或等价递归复制 |
| `AttributeError: snapshot has no attribute 'q'` | Level2Snapshot 的数据结构与测试预期不符 | 查看 Level2Snapshot 的实际定义（precompute.py）|
| `TypeError: unhashable type` | 嵌套 dict 的键类型不一致 | 确认 q 的键为 int 而非 tuple |

**耗时**: <1 min

---

### 2.2 T5：回滚限制测试（CRITICAL）

**测试名**: `test_bcd_rollback_limit`
**文件**: `tests/test_bcd_loop.py`

**预期行为**:
```python
# 模拟 BCD 循环中成本不下降，需要回滚
# 设置 MAX_ROLLBACK=2

iter_1: cost = 100.0, snapshot_1
iter_2: cost = 150.0  # 成本上升，触发回滚 1
        → 恢复到 snapshot_1
iter_3: cost = 120.0  # 仍上升，触发回滚 2
        → 恢复到 snapshot_init
iter_4: cost = 130.0  # 再次上升，但回滚次数已达上限
        → 不再回滚，直接返回最佳历史解

最终返回: best_iter=1, best_cost=100.0, rollback_count=2
```

**运行命令**:
```bash
uv run pytest tests/test_bcd_loop.py::TestBCDRollbackLimit -v
```

**预期输出**:
```
tests/test_bcd_loop.py::TestBCDRollbackLimit::test_bcd_rollback_limit PASSED
```

**通过标准**:
- 测试返回 PASSED
- 结果的 `rollback_count == 2`（达到上限）
- 最终成本对应 iter_1 而非 iter_4

**失败排查**:
| 症状 | 根因 | 排查步骤 |
|------|------|--------|
| `AssertionError: rollback_count != 2` | 回滚逻辑未实现或实现错误 | 检查 `_rollback_and_revert()` 的计数逻辑 |
| `AssertionError: final_cost != 100.0` | 未保存最佳历史快照 | 检查是否在每次迭代保存 `best_snapshot` |
| 无异常但测试超时 | 回滚逻辑陷入死循环 | 检查回滚数计数是否正确递增 |

**耗时**: <1 min

---

### 2.3 Test Dependency 与置信度判断

**如果 T1 + T5 都 PASSED**:
- ✅ 深拷贝隔离已验证 → 代际热启动的快照传递安全
- ✅ 回滚限制已验证 → 约束循环时能及时停止并返回最优历史解
- **置信度提升**: 其他 3 个测试（T2、T3、T4）的框架可信任，失败多为参数调整问题，非架构问题

**如果 T1 或 T5 失败**:
- ❌ 暂停阶段 3、4
- 修复源问题并重新运行 T1 + T5
- 仅在两个都 PASSED 后继续

---

## 阶段 3：冒烟测试（3-5 min）

**目标**: 验证 BCD 循环能在最小配置下完整执行（不追求最优解，仅验证无 crash）。

### 3.1 参数配置（单代单体）

**配置**:
```bash
export HS_POP_SIZE=1        # 种群大小：1 个个体
export HS_ITERATION=1       # HS 迭代：1 轮
export MAX_BCD_ITER=2       # BCD 迭代：2 轮（足以验证循环）
export SOLVER_TIMEOUT=60    # 单个求解器超时：60 sec
```

### 3.2 运行脚本

**命令**:
```bash
cd /e/aaa_dev/llm-guided-mod-optimization

# 烟雾测试：运行单代 HS 管道
uv run python testEdgeUav.py \
    --popsize=1 \
    --iteration=1 \
    --run-dir discussion/smoke_test_phase6_step4/ \
    --seed=42
```

**预期输出** (stdout):
```
[2026-03-26 HH:MM:SS] Harmony Search iteration 1/1 starting...
[2026-03-26 HH:MM:SS] Population size: 1
[2026-03-26 HH:MM:SS] BCD iteration 1 starting...
[2026-03-26 HH:MM:SS] Propulsion solver completed
[2026-03-26 HH:MM:SS] Resource allocation solver completed
[2026-03-26 HH:MM:SS] Trajectory optimization (SCA) iteration 1...
[2026-03-26 HH:MM:SS] BCD iteration 2 starting...
...
[2026-03-26 HH:MM:SS] Harmony Search completed.
[2026-03-26 HH:MM:SS] Results saved to discussion/smoke_test_phase6_step4/
```

**预期文件结构** (关键):
```
discussion/smoke_test_phase6_step4/
├── population_result_0_0.json      # 第 1 代第 1 个体（唯一）
├── solver_diagnostics_gen_0.json   # 诊断信息
└── summary.txt                     # 运行摘要
```

### 3.3 验收标准

**通过标准** (ALL 必须):
- [ ] 无异常抛出（returncode == 0）
- [ ] 输出日志包含 "BCD iteration" 至少 2 次（验证循环执行）
- [ ] 生成 1 个 population_result JSON 文件
- [ ] JSON 文件包含字段：`feasible`, `used_default_obj`, `llm_status`, `obj_value`
- [ ] 运行耗时 < 5 分钟

**失败排查**:
| 症状 | 根因 | 排查步骤 |
|------|------|--------|
| `ImportError: cannot import name 'run_bcd_loop'` | BCD Loop 模块未正确导入 | 确认 `edge_uav/model/bcd_loop.py` 存在且 `run_bcd_loop` 符号已导出 |
| `TypeError: run_bcd_loop() missing required argument` | BCD Loop 函数签名不匹配 | 检查调用位置（hsIndividualEdgeUav.py L311-320）的参数列表 |
| 求解器超时（status == "unknown"） | 某个 Level-2 求解器（propulsion/resource_alloc/trajectory_opt）超时 | 逐个求解器运行单元测试定位 |
| `Infeasible` 异常 | 约束集矛盾（通常来自 trajectory_opt） | 检查 trajectory_opt 的 SCA 迭代次数、slack 权重 |
| Memory 溢出 | 快照克隆未正确回收，内存积累 | 检查 clone_snapshot() 和 snapshot 生命周期管理 |

**耗时**: 3-5 min

---

## 阶段 4：HS 集成改动清单（准备，不执行）

**目标**: 记录 HS Individual 修改的确切位置和内容，便于执行时参考。

### 4.1 修改位置与内容

**文件**: `heuristics/hsIndividualEdgeUav.py`
**行号范围**: L300-330（runOptModel 方法内部）

**原代码** (当前):
```python
# L300-320（伪代码，简化版）
def runOptModel(self, parent, way):
    parent, way = self._normalize_inputs(parent, way)

    # Step 1: LLM 生成或使用默认目标函数
    if way == "default":
        obj_code = self._synthesize_llm_response()
    else:
        obj_code = self._ensure_api().call_llm(self.prompt, ...)

    # Step 2: 使用 OffloadingModel 求解 Level-1
    offloading_model = OffloadingModel(
        scenario=self.scenario,
        obj_code=obj_code,
        params=self.config
    )
    offload_result = offloading_model.solve()  # ← 需要替换

    # Step 3: 评估
    score = evaluate_solution(offload_result, ...)

    # Step 4: 记录
    self.promptHistory["evaluation_score"] = score
    return score
```

**新代码** (修改后):
```python
def runOptModel(self, parent, way):
    parent, way = self._normalize_inputs(parent, way)

    # Step 1: LLM 生成或使用默认目标函数（保持不变）
    if way == "default":
        obj_code = self._synthesize_llm_response()
    else:
        obj_code = self._ensure_api().call_llm(self.prompt, ...)

    # Step 2: 使用 BCD 循环代替 OffloadingModel
    # 导入新增 (在文件头部 add)
    from edge_uav.model.bcd_loop import run_bcd_loop, clone_snapshot
    from edge_uav.model.precompute import make_initial_level2_snapshot

    # 获取或创建初始快照
    if not hasattr(self, '_bcd_snapshot') or self._bcd_snapshot is None:
        self._bcd_snapshot = make_initial_level2_snapshot(self.scenario)

    # 为本代创建热启动快照（克隆上代快照）
    current_snapshot = clone_snapshot(self._bcd_snapshot)

    # 调用 BCD 循环（替代 OffloadingModel）
    bcd_result = run_bcd_loop(
        scenario=self.scenario,
        snapshot=current_snapshot,
        params=self.params,  # PrecomputeParams
        max_iterations=10,   # BCD 迭代上限
        tolerance=1e-3,      # 成本改进容差
    )

    # 更新快照，为下一代热启动准备
    self._bcd_snapshot = bcd_result.snapshot_final  # ← 追踪中间快照

    # Step 3: 评估（改为使用 BCD 结果）
    # 注意：bcd_result 包含 q, f_local, f_edge，评估逻辑需调整
    score = evaluate_solution(bcd_result, ...)  # 可能需要适配器

    # Step 4: 诊断信息追加
    self.promptHistory["simulation_steps"]["bcd_loop"] = {
        "bcd_iterations": bcd_result.bcd_iterations,
        "total_cost": bcd_result.total_cost,
        "feasible": bcd_result.feasible,
        "diagnostics": bcd_result.diagnostics,
    }

    # Step 5: 记录
    self.promptHistory["evaluation_score"] = score
    return score
```

### 4.2 详细改动清单

**改动 1**: 新增导入语句（文件顶部）

```python
# 在现有导入后添加
from edge_uav.model.bcd_loop import run_bcd_loop, clone_snapshot
from edge_uav.model.precompute import make_initial_level2_snapshot
```

**检查点**:
- [ ] 不破坏现有导入顺序（按 from/import、stdlib/third-party/local 分组）
- [ ] 避免循环导入（bcd_loop 不应导入 hsIndividualEdgeUav）

---

**改动 2**: 初始化快照存储字段（__init__ 方法）

```python
def __init__(self, configPara, scenario, *, shared_precompute=None):
    # ... 现有代码 ...

    # 新增：用于跨代热启动的快照存储
    self._bcd_snapshot = None  # 延迟初始化
```

**检查点**:
- [ ] 字段名为 `_bcd_snapshot`（下划线前缀表示内部）
- [ ] 初始值为 None（在首次 runOptModel 调用时初始化）

---

**改动 3**: 替换 OffloadingModel 为 BCD 循环（runOptModel 方法）

**关键步骤**:

1. **删除** OffloadingModel 创建与调用（行 311-318）
   ```python
   # ❌ 删除这段
   offloading_model = OffloadingModel(...)
   offload_result = offloading_model.solve()
   ```

2. **新增** BCD 循环调用（行 311-320，插入位置）
   ```python
   # ✅ 插入这段
   if not hasattr(self, '_bcd_snapshot') or self._bcd_snapshot is None:
       self._bcd_snapshot = make_initial_level2_snapshot(self.scenario)

   current_snapshot = clone_snapshot(self._bcd_snapshot)

   bcd_result = run_bcd_loop(
       scenario=self.scenario,
       snapshot=current_snapshot,
       params=self.params,
       max_iterations=10,
       tolerance=1e-3,
   )

   self._bcd_snapshot = bcd_result.snapshot_final
   ```

**检查点**:
- [ ] 参数 `params` 存在（应在 __init__ 中初始化为 PrecomputeParams）
- [ ] `bcd_result` 包含 `snapshot_final` 字段（用于热启动）
- [ ] 无语法错误（缩进、括号配对）

---

**改动 4**: 更新诊断信息记录

```python
# 在 Step 4 记录前添加
self.promptHistory["simulation_steps"]["bcd_loop"] = {
    "bcd_iterations": bcd_result.bcd_iterations,
    "total_cost": bcd_result.total_cost,
    "feasible": bcd_result.feasible,
    "diagnostics": bcd_result.diagnostics,
}
```

**检查点**:
- [ ] `promptHistory["simulation_steps"]` 是可变字典
- [ ] 键值（`bcd_iterations`, `total_cost` 等）与 BCDResult 字段名一致
- [ ] 所有字段都能序列化为 JSON（不含非标量对象）

---

**改动 5**: 调整评估逻辑适配器（可选）

**原**:
```python
score = evaluate_solution(offload_result, ...)
```

**新** (如果 evaluate_solution 签名要求 offloading 格式):
```python
# 可能需要包装 bcd_result 使其兼容 evaluate_solution
# 具体取决于 evaluate_solution 的实现
score = evaluate_solution(bcd_result, ...)
```

**检查点**:
- [ ] 确认 evaluate_solution 的输入签名
- [ ] 如需适配器，创建转换函数或修改 evaluate_solution
- [ ] 验证转换后的 score 仍为标量（用于排序）

---

### 4.3 改动验证清单（不执行，仅规划）

执行时应逐项验证：

- [ ] 文件保存无语法错误（`python -m py_compile hsIndividualEdgeUav.py`）
- [ ] 新增导入能成功（`from edge_uav.model.bcd_loop import ...` 不抛异常）
- [ ] 热启动逻辑正确（第一代初始化快照，后续代克隆并修改）
- [ ] 诊断信息追加不覆盖（promptHistory 为累积，不覆盖字段）
- [ ] 单元测试通过（test_hs_individual_edge_uav.py 中涉及 BCD 路径的测试）

---

## 整体时间表与通过标准

### 分阶段耗时估计

| 阶段 | 内容 | 预计耗时 | 串行/并行 |
|------|------|--------|---------|
| **1** | 代码审视 (5 个检查点) | 30 min | 串行（Codex） |
| **2** | 单元测试 (T1 + T5) | 15 min | 并行可能，但通常串行 |
| **3** | 冒烟测试 | 5 min | 串行（HS 管道） |
| **4** | HS 集成改动 | 0 min（仅规划，不执行） | N/A |

**总耗时**: 50 min（如果各阶段都通过）

---

### 整体通过/失败标准

**全部通过** (✅):
- [ ] 阶段 1：5 个检查点无重大问题（导入、深拷贝、接口、函数签名）
- [ ] 阶段 2：T1 和 T5 都 PASSED
- [ ] 阶段 3：冒烟测试无异常，生成结果文件，运行耗时 < 5 min

**进展卡住** (⚠️):
- 任何阶段失败 → 停止，诊断并修复
- 修复完成后，重新从失败的阶段开始

**无法继续** (❌):
- 同一问题失败 3 次（per CLAUDE.md §2.6） → 停止，汇报现状
- BCD Loop 模块完全无法导入 → 需要 CodeX 重新实现整个模块
- trajectory_opt 出现新的 DCP 违规 → 需要回到 Step3 补充修复

---

## 诊断与排查指南

### 常见故障与排查树

```
问题：Stage 1 代码审视失败（导入错误）
├─ 症状："ModuleNotFoundError: No module named 'edge_uav.model.bcd_loop'"
├─ 原因：bcd_loop.py 未创建或路径错误
└─ 排查：
   1. 验证 bcd_loop.py 是否存在：ls edge_uav/model/bcd_loop.py
   2. 如果不存在，CodeX 需要创建整个模块
   3. 如果存在，检查 __init__.py 中是否导出

问题：Stage 2 T1 失败（深拷贝不隔离）
├─ 症状："AssertionError: original snapshot was modified"
├─ 原因：clone_snapshot() 未做深拷贝
└─ 排查：
   1. 查看 clone_snapshot() 实现是否有 deepcopy() 调用
   2. 检查嵌套 dict 的复制是否递归
   3. 确认 source 字段是否创建新字符串

问题：Stage 2 T5 失败（回滚逻辑错误）
├─ 症状："AssertionError: rollback_count != 2"
├─ 原因：回滚次数计数未正确递增
└─ 排查：
   1. 查看 _rollback_and_revert() 的计数逻辑
   2. 确认每次触发回滚时 rollback_count += 1
   3. 检查回滚上限 MAX_ROLLBACK 是否正确应用

问题：Stage 3 冒烟测试超时
├─ 症状："Timeout after 5 minutes"
├─ 原因：某个 Level-2 求解器卡死
└─ 排查：
   1. 独立运行 propulsion 求解器：pytest tests/test_propulsion.py -v
   2. 独立运行 resource_alloc 求解器：pytest tests/test_resource_alloc.py -v
   3. 独立运行 trajectory_opt 求解器：pytest tests/test_trajectory_opt.py -v
   4. 如果都通过但组合超时，问题可能在 BCD 循环的参数传递

问题：Stage 3 冒烟测试返回 "infeasible"
├─ 症状："Status: infeasible" in output
├─ 原因：约束集矛盾，通常来自 trajectory_opt
└─ 排查：
   1. 检查 trajectory_opt 的 τ_comm（通信时延预算）是否合理
   2. 增加 SCA 迭代次数（max_sca_iter → 20）
   3. 调整安全分离 slack 权重（ρ_0 → 更大的初值）
```

---

## 后续流程

### 验证完成后（所有阶段通过）

1. **等待确认** (按用户指示)
   - 用户审查验证策略输出
   - 确认是否执行 Stage 4（HS 集成改动）

2. **执行 HS 集成改动**（如用户确认）
   - 按照 Section 4 的清单逐项修改
   - 运行修改后的单元测试
   - 执行完整 E2E 管道验证（类似 Phase⑤）

3. **最终报告生成**
   - 汇总验证结果（Stage 1-4 通过标准）
   - 生成 Phase⑥ Step4 完成报告
   - 更新项目 MEMORY.md 与工作日记

---

## 文档维护

**版本历史**:
- v1.0 (2026-03-26): 初版，规划阶段

**更新规则**:
- 执行过程中如发现新的检查点或失败模式，即时更新此文档
- 执行完成后，添加"实际执行结果"章节

**关键链接**:
- 前序计划: `plans/phase6-step3-socp-fix-plan.md`
- 测试框架: `tests/test_bcd_loop.py`
- HS Individual: `heuristics/hsIndividualEdgeUav.py`
- 内存记录: (跨对话持久化)

---

**策略版本**: 1.0
**最后更新**: 2026-03-26 08:30
**状态**: 🗂️ 历史验收策略文档（规划阶段已完成，正文保留当时执行前状态）
**后续状态**: 该策略文档之后的实现推进请以 `CLAUDE.md` 和
`文档/70_工作日记/2026-03-27.md` 为准
