# Evaluator Drop 兼容性修复计划

> **状态**: 待执行
> **优先级**: P0（阻塞实验）
> **创建日期**: 2026-03-31
> **来源**: Codex MCP 代码审查 + 人工分析

---

## 1. 问题概述

`evaluator.py` 存在两个结构性 bug，导致当前参数下 **HS 种群评分全部失效**（所有解均返回 1e12）。

---

## 2. 发现的问题

### Bug 1（Critical）：`_index_outputs` 键粒度错误

**现象**: assignments 以 `i`（任务 ID）为键，但同一任务在多个时隙都活跃（当前 active_window=30=T）。第二个时隙就触发 "duplicate assignment" → ValueError → 返回 1e12。

**影响**: **当前参数下所有解都被判为 1e12**，HS 排序完全失效。

**位置**: `edge_uav/model/evaluator.py:39-74`

```python
# 当前（错误）：以 i 为键
assignments[i] = ("local", None, t)  # t=0 写入
assignments[i] = ("local", None, t)  # t=1 → "duplicate assignment for task i"

# 应改为：以 (i, t) 为键
assignments[(i, t)] = ("local", None)
```

### Bug 2（High）：不识别 drop 字段

**现象**: `_index_outputs` 只处理 `slot["local"]` 和 `slot["offload"]`，忽略 `slot["drop"]`。drop 的任务在完备性检查中报 "task not assigned" → 1e12。

**影响**: 任何含 drop 的解一律垫底，无法区分"drop 1 个任务的好解"和"完全崩溃的无效输出"。

**位置**: `edge_uav/model/evaluator.py:46-74`（缺少 drop 处理段）

### Issue 3（High）：`offloading.py` drop 创建条件过窄

**现象**: `setupVars()` 仅在任务**完全无可行选项**时创建 `drop[i,t]`。当任务单独看可行，但因 N_max 容量限制装不下时，不创建 drop → 模型可能 INFEASIBLE。

**两类失败场景**:
- **可行性失败**（已处理）：`D_local > tau` 且所有 `D_offload > tau`
- **容量失败**（未处理）：单独可行，但 N_max=1 无法容纳所有需卸载的任务

**位置**: `edge_uav/model/offloading.py:225-266`

---

## 3. 修复方案

### Phase A：修复 evaluator（阻塞性，必须先做）

#### A1. 键粒度修正

`_index_outputs` 返回类型从 `dict[int, ...]` 改为 `dict[tuple[int, int], ...]`：

```python
# 修改前
assignments: dict[int, tuple[str, int | None, int]] = {}
# ...
assignments[i] = ("local", None, t)

# 修改后
assignments: dict[tuple[int, int], tuple[str, int | None]] = {}
# ...
assignments[(i, t)] = ("local", None)
```

#### A2. 添加 drop 处理段

在 `_index_outputs` 的 local/offload 遍历后添加：

```python
# 失败分配
for i in slot.get("drop", []):
    key = (i, t)
    if i not in valid_tasks:
        raise ValueError(f"unknown task_id={i} in drop at t={t}")
    if key in assignments:
        raise ValueError(f"duplicate assignment for task ({i}, {t})")
    if not scenario.tasks[i].active.get(t, False):
        raise ValueError(f"inactive task ({i}, {t}) incorrectly assigned")
    assignments[key] = ("drop", None)
```

#### A3. 修正完备性检查

```python
# 修改前：只检查 i 维度
for i in scenario.tasks:
    if i not in assignments:
        raise ValueError(f"task {i} not assigned")

# 修改后：检查 (i, t) 维度
for i, task in scenario.tasks.items():
    for t in scenario.time_slots:
        if task.active.get(t, False) and (i, t) not in assignments:
            raise ValueError(f"task ({i}, {t}) not assigned")
```

#### A4. `_compute_score` 适配 (i, t) 粒度和 drop

```python
# 修改前
for i, task in scenario.tasks.items():
    tau = float(task.tau)
    mode, j, t = assignments[i]
    # ...

# 修改后
drop_term = 0.0
for i, task in scenario.tasks.items():
    tau = float(task.tau)
    for t in scenario.time_slots:
        if not task.active.get(t, False):
            continue
        mode, j = assignments[(i, t)]
        if mode == "drop":
            drop_term += drop_penalty
            continue
        elif mode == "local":
            delay = precompute_result.D_hat_local[i][t]
        elif mode == "offload":
            delay = precompute_result.D_hat_offload[i][j][t]
            energy_term += precompute_result.E_hat_comp[j][i][t] / scenario.uavs[j].E_max
            offload_counts[j] += 1
        # ... delay_term, deadline_term 不变
```

#### A5. `evaluate_solution` 接口扩展

新增 `drop_penalty` 可选参数，默认从 `scenario.meta["penalty_drop"]` 读取，缺失时回退 `1e4`：

```python
DEFAULT_DROP_PENALTY: float = 1e4

def evaluate_solution(..., drop_penalty: float | None = None) -> float:
    # ...

def _resolve_drop_penalty(scenario, drop_penalty):
    if drop_penalty is not None:
        return float(drop_penalty)
    meta = getattr(scenario, "meta", None) or {}
    return float(meta.get("penalty_drop", DEFAULT_DROP_PENALTY))
```

### Phase B：扩展 offloading.py drop 创建（优化质量）

将 `drop[i,t]` 从"仅完全不可行时创建"扩展为"所有 active (i,t) 都创建"：

```python
# 修改前：仅在无可行选项时
if not has_local and not has_offload:
    self.drop[i, t] = self.model.addVar(...)

# 修改后：所有 active (i,t) 都有 drop 变量
# 约束保证 x_local + Σ x_offload + drop == 1
# 目标函数的大罚分确保 drop 只在必要时使用
self.drop[i, t] = self.model.addVar(
    vtype=gb.GRB.BINARY, lb=0, ub=1,
    name=f"drop_{i}_{t}",
)
```

**效果**：容量溢出时，优化器可以选择哪些任务 drop（选罚分最低的），而不是 INFEASIBLE。

**联动更新**：
- `objectives.py:35` 文档措辞需更新（删除"仅当全部不可行时"）
- `objectives.py` CONSTRAINT_REFERENCE 的 L1-C1 说明需更新

---

## 4. 验证计划

| 步骤 | 验证内容 | 命令 |
|------|---------|------|
| 1 | 单元测试通过 | `uv run pytest tests/test_evaluator.py -v` |
| 2 | 现有测试不回归 | `uv run pytest tests/ -v` |
| 3 | Smoke test（单次求解） | `uv run python scripts/run_edge_uav.py`（1 iteration） |
| 4 | 验证 evaluator 不再全员 1e12 | 检查 HS 日志中 evaluation_score 分布 |
| 5 | 验证 drop 解被正确评分 | 含 drop 的解 score < 1e12 且 > 无 drop 的解 |

---

## 5. 风险与注意事项

1. **罚分尺度**：`drop_penalty=1e4` 需与 Gurobi 目标函数的 `penalty_drop` 一致，否则 evaluator 排序和 Gurobi 求解的偏好可能不同
2. **Phase B 变量膨胀**：为所有 active (i,t) 创建 drop 变量会增加 Gurobi 变量数（约 +15×30=450 个二进制变量），对求解时间影响需验证
3. **下游兼容性**：`resource_alloc.py` 和 `bcd_loop.py` 是否假设所有 active 任务都已被 local/offload 消化，需检查
4. **测试用例更新**：`tests/test_evaluator.py` 现有用例基于旧的 `i` 键粒度，需全部适配 `(i, t)` 粒度

---

## 6. 受影响文件

| 文件 | Phase A | Phase B |
|------|---------|---------|
| `edge_uav/model/evaluator.py` | **主要修改** | — |
| `edge_uav/model/offloading.py` | — | **主要修改** |
| `edge_uav/model/objectives.py` | — | 文档更新 |
| `tests/test_evaluator.py` | **测试适配** | — |
| `heuristics/hsIndividualEdgeUav.py` | 检查调用点 | — |
| `heuristics/hsIndividualRandom.py` | 检查调用点 | — |
| `scripts/diagnose_edge_uav_bcd.py` | 检查调用点 | — |
| `scripts/run_all_experiments.py` | 检查调用点 | — |
| `edge_uav/model/resource_alloc.py` | — | 检查兼容性 |
| `edge_uav/model/bcd_loop.py` | — | 检查兼容性 |

---

## 7. 执行顺序建议

```
Phase A（阻塞性修复，约 30 分钟）
  A1. 键粒度 i → (i, t)
  A2. 添加 drop 处理段
  A3. 完备性检查适配
  A4. _compute_score 适配
  A5. 接口扩展 + drop_penalty 参数
  → 更新 tests/test_evaluator.py
  → 运行验证步骤 1-5

Phase B（优化质量，约 20 分钟）
  B1. offloading.py setupVars 扩展 drop 创建
  B2. objectives.py 文档更新
  B3. 检查下游兼容性
  → 运行完整测试 + smoke test
```
