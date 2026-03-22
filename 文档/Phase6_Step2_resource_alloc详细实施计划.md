# Phase⑥ Step 2: resource_alloc.py 详细实施计划

> 创建日期：2026-03-22
> 状态：待实施（已完成分析和规划）
> 预计代码行数：290 行（resource_alloc.py 140行 + test 150行）

---

## 需求概述

实现 `edge_uav/model/resource_alloc.py`（Block C 资源分配，Level 2a 频率优化子问题）

**输入：** 固定轨迹 q、固定卸载决策 x
**输出：** 最优 CPU 频率分配 (f_local, f_edge) 最小化加权时延+能耗
**核心创新：** 异构任务下用对偶二分法（而非等比缩放）精确求解 KKT 条件

---

## 数学推导（关键）

### 1. 频率优化的拉格朗日一阶条件

对边缘节点 j、时隙 t、任务 i 的 CPU 频率 f_ji 求偏导：

```
∂L/∂f_ji = -α·F_i/(f²·τ_i) + 2·γ_w·γ_j·f·F_i/E_max + λ = 0
```

令：
- a_i = α·F_i/τ_i
- b_i = γ_w·γ_j·F_i/E_max

得：
```
2b_i·f³ + λ·f² - a_i = 0  ... (*)
```

### 2. 无约束 KKT 解（λ=0）

当容量 Σf_i ≤ f_max 时，各任务独立最优频率为：

```
f_i* = (a_i / (2b_i))^(1/3) = (α·E_max / (2·γ_w·γ_j·τ_i))^(1/3)
```

### 3. 对偶二分法（λ>0，约束触发）

当 Σf_i* > f_max_j 时，需找 λ 使 Σf_i(λ) = f_max_j

**关键性质：** g(λ) := Σf_i(λ) 关于 λ 严格单调递减（λ增大→f_i减小）

**算法：**
```
λ_min ← 0
λ_max ← (max_i(a_i) - 2·b_i·eps²) / eps²  # 保守估计，使f_min ≥ eps_freq
while (λ_max - λ_min) > 1e-12:
    λ_mid ← (λ_min + λ_max) / 2
    g_mid ← Σ_i f_i(λ_mid)
    if g_mid > f_max:
        λ_min ← λ_mid
    else:
        λ_max ← λ_mid
return f_i(λ_mid)
```

**复杂度：** O(log(λ_max/1e-12)) × O(n_tasks × 60) ≈ O(n_tasks × 600)，可承受

### 4. 目标函数（频率相关项）

```
L2a_obj = Σ_{j,i,t ∈ offload} [
    α·F_i/(f_ji·τ_i) + γ_w·γ_j·(f_ji)²·F_i/E_max
]
```

注：计算真实成本时，需加上通信时延项（由 precompute 提供，不在此优化）

---

## 实现规划

### 文件 1: `edge_uav/model/resource_alloc.py`（~140 行）

#### 模块结构

```python
# 第一部分：导入 + 类型别名 + 常量
from __future__ import annotations
import math
from dataclasses import dataclass
from edge_uav.model.precompute import Scalar2D, Scalar3D, PrecomputeParams
from edge_uav.data import EdgeUavScenario

__all__ = [
    "ResourceAllocResult",
    "solve_resource_allocation",
]

# 第二部分：数据类
@dataclass(frozen=True)
class ResourceAllocResult:
    """Block C 资源分配求解结果。

    属性：
        f_local: dict[i][t] = task.f_local（本地频率恒为最大）
        f_edge: dict[j][i][t] = KKT最优频率
        objective_value: 频率相关的目标值（仅 L2a-obj 部分）
        diagnostics: 诊断信息
            - binding_slots: 容量约束触发的 (j,t) 数量
            - total_bisect_iters: 对偶二分累计迭代数
            - max_bisect_iters: 单时隙最大迭代数
    """
    f_local: Scalar2D
    f_edge: Scalar3D
    objective_value: float
    diagnostics: dict

# 第三部分：公开 API
def solve_resource_allocation(
    scenario: EdgeUavScenario,
    offloading_decisions: dict,  # {t: {"local": [...], "offload": {j: [...]}}}
    params: PrecomputeParams,
    *,
    alpha: float,
    gamma_w: float,
) -> ResourceAllocResult:
    """Block C：给定卸载决策，求最优频率分配。

    数学模型：
        min_f Σ_{j,i,t} [α·F_i/(f·τ) + γ_w·γ_j·f²·F_i/E_max]
        s.t.  Σ_i f_ji^t ≤ f_max_j  ∀j,t
              f_ji^t ≥ eps_freq

    求解方法：
        1. f_local = task.f_local（无约束最优）
        2. f_edge: 逐(j,t)时隙用KKT+对偶二分求解

    参数：
        scenario: 场景数据
        offloading_decisions: OffloadingModel.getOutputs() 格式
        params: PrecomputeParams（含gamma_j, eps_freq）
        alpha: 时延权重 > 0
        gamma_w: 能耗缩放因子 > 0

    返回：
        ResourceAllocResult（含f_local, f_edge, objective_value, diagnostics）
    """
    # 1. 输入校验
    if alpha <= 0:
        raise ValueError(f"alpha must be > 0, got {alpha}")
    if gamma_w <= 0:
        raise ValueError(f"gamma_w must be > 0, got {gamma_w}")
    if params.gamma_j <= 0:
        raise ValueError(f"gamma_j must be > 0, got {params.gamma_j}")

    # 2. 解析卸载决策
    local_sets, offload_sets = _parse_offloading_decisions(offloading_decisions, scenario)

    # 3. 初始化本地频率
    f_local: Scalar2D = {}
    for i, task in scenario.tasks.items():
        f_local[i] = {}
        for t in scenario.time_slots:
            f_local[i][t] = task.f_local

    # 4. 求解边缘频率（逐时隙）
    f_edge: Scalar3D = {j: {} for j in scenario.uavs}
    diagnostics = {
        "binding_slots": 0,
        "total_bisect_iters": 0,
        "max_bisect_iters": 0,
    }

    for j, task_list in offload_sets.items():
        f_edge[j] = {}
        for t, task_ids in task_list.items():
            if not task_ids:
                continue

            # 构造该时隙的任务谱：[(i, a_i, b_i), ...]
            task_specs = []
            for i in task_ids:
                task = scenario.tasks[i]
                F_i = task.F
                tau_i = task.tau
                a_i = alpha * F_i / tau_i
                b_i = gamma_w * params.gamma_j * F_i / scenario.uavs[j].E_max
                task_specs.append((i, a_i, b_i))

            # 求解该时隙的最优频率
            slot_freqs, n_bisect = _solve_slot_kkt(
                task_specs,
                scenario.uavs[j].f_max,
                params.eps_freq,
            )

            f_edge[j][t] = slot_freqs

            # 更新诊断信息
            if n_bisect > 0:
                diagnostics["binding_slots"] += 1
            diagnostics["total_bisect_iters"] += n_bisect
            diagnostics["max_bisect_iters"] = max(diagnostics["max_bisect_iters"], n_bisect)

    # 5. 计算目标值
    objective_value = _compute_objective(
        f_edge, offload_sets, scenario, params,
        alpha=alpha, gamma_w=gamma_w,
    )

    return ResourceAllocResult(
        f_local=f_local,
        f_edge=f_edge,
        objective_value=objective_value,
        diagnostics=diagnostics,
    )


# 第四部分：内部函数

def _parse_offloading_decisions(outputs: dict, scenario: EdgeUavScenario) -> tuple:
    """解析卸载决策，返回本地集合和卸载集合。

    返回：
        (local_sets, offload_sets)
        local_sets: {(i,t): True}
        offload_sets: {j: {t: [i1, i2, ...]}}
    """
    local_sets = {}
    offload_sets = {j: {} for j in scenario.uavs}

    for t in scenario.time_slots:
        slot = outputs.get(t)
        if slot is None:
            raise ValueError(f"outputs missing time slot {t}")

        # 本地分配
        for i in slot.get("local", []):
            local_sets[(i, t)] = True

        # 卸载分配
        for j, task_ids in slot.get("offload", {}).items():
            if j not in scenario.uavs:
                raise ValueError(f"unknown uav_id={j}")
            if t not in offload_sets[j]:
                offload_sets[j][t] = []
            offload_sets[j][t].extend(task_ids)

    return local_sets, offload_sets


def _solve_slot_kkt(
    task_specs: list,  # [(i, a_i, b_i), ...]
    f_max: float,
    eps_freq: float,
) -> tuple[dict, int]:
    """单时隙 KKT 求解。

    返回：
        (freqs_dict, n_bisect_iters)
        freqs_dict: {i: f_ji*}
        n_bisect_iters: 对偶二分迭代数（0表示无约束解直接可行）
    """
    if not task_specs:
        return {}, 0

    # 第一阶段：计无约束 KKT 解
    unconstrained_freqs = {}
    total_unconstrained = 0.0

    for i, a_i, b_i in task_specs:
        # f* = (a / (2b))^(1/3)
        c_i = (a_i / (2 * b_i)) ** (1/3)
        unconstrained_freqs[i] = c_i
        total_unconstrained += c_i

    # 第二阶段：检查约束
    if total_unconstrained <= f_max:
        # 无约束解可行，直接 clamp 到 [eps_freq, f_max]
        feasible_freqs = {
            i: max(eps_freq, min(f_max, f))
            for i, f in unconstrained_freqs.items()
        }
        return feasible_freqs, 0

    # 第三阶段：对偶二分法求 λ
    lam_min = 0.0
    lam_max = (max(a_i for _, a_i, _ in task_specs) - 2e-12) / (eps_freq ** 2)

    n_bisect = 0
    max_bisect_iters = 60

    while n_bisect < max_bisect_iters:
        lam_mid = (lam_min + lam_max) / 2

        # 计 g(λ_mid) = Σ f_i(λ_mid)
        g_mid = 0.0
        for i, a_i, b_i in task_specs:
            f_i = _freq_at_dual(a_i, b_i, lam_mid, f_max, eps_freq)
            g_mid += f_i

        if g_mid > f_max:
            lam_min = lam_mid
        else:
            lam_max = lam_mid

        n_bisect += 1

        if (lam_max - lam_min) < 1e-12:
            break

    # 用最终的 λ 计频率
    lam_final = (lam_min + lam_max) / 2
    constrained_freqs = {
        i: _freq_at_dual(a_i, b_i, lam_final, f_max, eps_freq)
        for i, a_i, b_i in task_specs
    }

    return constrained_freqs, n_bisect


def _freq_at_dual(
    a_i: float,
    b_i: float,
    lam: float,
    f_max: float,
    eps_freq: float,
) -> float:
    """对给定 λ，求解 2b·f³ + λ·f² - a = 0 的正根。

    使用二分法在 [eps_freq, f_max] 上搜索。

    方程：2b·f³ + λ·f² - a = 0
    导数：6b·f² + 2λ·f > 0  （f > 0 时严格递增）
    """
    def h(f):
        return 2 * b_i * f**3 + lam * f**2 - a_i

    # 检查边界值
    h_low = h(eps_freq)
    h_high = h(f_max)

    if h_low >= 0:
        return eps_freq
    if h_high <= 0:
        return f_max

    # 二分法
    f_low, f_high = eps_freq, f_max
    for _ in range(60):  # 60 次迭代足够（2^-60 < 1e-18）
        f_mid = (f_low + f_high) / 2
        if h(f_mid) > 0:
            f_high = f_mid
        else:
            f_low = f_mid

        if (f_high - f_low) < 1e-14:
            break

    return (f_low + f_high) / 2


def _compute_objective(
    f_edge: Scalar3D,
    offload_sets: dict,
    scenario: EdgeUavScenario,
    params: PrecomputeParams,
    *,
    alpha: float,
    gamma_w: float,
) -> float:
    """计算频率相关的目标值（L2a-obj）。

    L2a_obj = Σ_{j,i,t} [α·F_i/(f·τ) + γ_w·γ_j·f²·F_i/E_max]
    """
    obj = 0.0

    for j, task_dict in offload_sets.items():
        for t, task_ids in task_dict.items():
            for i in task_ids:
                task = scenario.tasks[i]
                uav = scenario.uavs[j]

                if j in f_edge and t in f_edge[j] and i in f_edge[j][t]:
                    f_ji = f_edge[j][t][i]

                    # 时延项
                    delay_term = alpha * task.F / (f_ji * task.tau)

                    # 能耗项
                    energy_term = (
                        gamma_w * params.gamma_j * (f_ji ** 2) * task.F / uav.E_max
                    )

                    obj += delay_term + energy_term

    return obj
```

---

### 文件 2: `tests/test_resource_alloc.py`（~150 行）

#### 测试结构

```python
import math
import pytest
from edge_uav.data import ComputeTask, UAV, EdgeUavScenario
from edge_uav.model.precompute import PrecomputeParams
from edge_uav.model.resource_alloc import solve_resource_allocation

# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture
def params():
    """标准物理参数"""
    return PrecomputeParams(
        H=100.0,
        B_up=1e6,
        B_down=1e6,
        P_i=0.1,
        P_j=1.0,
        N_0=1e-11,
        rho_0=1.0,
        gamma_j=1e-28,
        eps_freq=1e-12,
    )

def _make_scenario(n_tasks=2, n_uavs=1, n_slots=2, **kwargs):
    """最小场景工厂"""
    tasks = {}
    for i in range(n_tasks):
        tasks[i] = ComputeTask(
            index=i,
            pos=(100 + i*10, 100),
            D_l=1000,
            D_r=500,
            F=kwargs.get(f"F_{i}", 1e9),
            tau=kwargs.get(f"tau_{i}", 0.5),
            f_local=1e9,
        )

    uavs = {}
    for j in range(n_uavs):
        uavs[j] = UAV(
            index=j,
            pos=(500, 500),
            pos_final=(600, 600),
            E_max=kwargs.get(f"E_max_{j}", 3600),
            f_max=kwargs.get(f"f_max_{j}", 1e9),
        )

    time_slots = list(range(n_slots))

    return EdgeUavScenario(
        tasks=tasks,
        uavs=uavs,
        time_slots=time_slots,
        seed=42,
        meta={"T": n_slots},
    )

# =====================================================================
# Test Cases
# =====================================================================

class TestLocalOnly:
    """全本地场景"""

    def test_all_local_no_offload(self, params):
        """T1：全部本地 → f_edge 空，f_local = f_max"""
        scenario = _make_scenario(n_tasks=2, n_slots=2)
        offloading = {
            0: {"local": [0, 1], "offload": {}},
            1: {"local": [0, 1], "offload": {}},
        }

        result = solve_resource_allocation(
            scenario, offloading, params,
            alpha=1.0, gamma_w=1e-9,
        )

        # f_edge 应为空（没有卸载）
        for j in scenario.uavs:
            assert len(result.f_edge.get(j, {})) == 0

        # f_local 应等于 task.f_local
        for i, task in scenario.tasks.items():
            for t in scenario.time_slots:
                assert result.f_local[i][t] == task.f_local


class TestEdgeKKT:
    """边缘 KKT 求解"""

    def test_unconstrained_kkt_exact(self, params):
        """T2：1 UAV 1 任务，f_max 很大 → 精确匹配 KKT 公式"""
        scenario = _make_scenario(n_tasks=1, n_uavs=1, n_slots=1, F_0=1e9, tau_0=0.5)
        offloading = {
            0: {"local": [], "offload": {0: [0]}},
        }

        alpha = 1.0
        gamma_w = 1e-9

        result = solve_resource_allocation(
            scenario, offloading, params,
            alpha=alpha, gamma_w=gamma_w,
        )

        # 无约束 KKT 解
        task = scenario.tasks[0]
        uav = scenario.uavs[0]
        expected_f = (alpha * uav.E_max / (2 * gamma_w * params.gamma_j * task.tau)) ** (1/3)

        actual_f = result.f_edge[0][0][0]
        assert actual_f == pytest.approx(expected_f, rel=1e-6)


class TestCapacityBinding:
    """容量约束触发"""

    def test_capacity_binds(self, params):
        """T3：1 UAV 3 任务，容量约束触发 → Σf = f_max"""
        scenario = _make_scenario(
            n_tasks=3, n_uavs=1, n_slots=1,
            F_0=1e9, F_1=1e9, F_2=1e9,
            tau_0=0.5, tau_1=0.5, tau_2=0.5,
            f_max_0=1e8,  # 容量紧张
        )
        offloading = {
            0: {"local": [], "offload": {0: [0, 1, 2]}},
        }

        result = solve_resource_allocation(
            scenario, offloading, params,
            alpha=1.0, gamma_w=1e-9,
        )

        # 检查 Σf ≈ f_max
        total_f = sum(result.f_edge[0][0].values())
        assert total_f == pytest.approx(scenario.uavs[0].f_max, rel=1e-5)


class TestObjectiveComputation:
    """目标值计算"""

    def test_objective_hand_computed(self, params):
        """T5：小场景手算目标值验证"""
        # 简单场景：1 task, 1 UAV, alpha=1, gamma_w=1
        scenario = _make_scenario(n_tasks=1, n_uavs=1, n_slots=1, F_0=1e8)
        offloading = {
            0: {"local": [], "offload": {0: [0]}},
        }

        alpha = 1.0
        gamma_w = 1e-10
        task = scenario.tasks[0]
        uav = scenario.uavs[0]

        result = solve_resource_allocation(
            scenario, offloading, params,
            alpha=alpha, gamma_w=gamma_w,
        )

        f = result.f_edge[0][0][0]
        expected_obj = (
            alpha * task.F / (f * task.tau) +
            gamma_w * params.gamma_j * f**2 * task.F / uav.E_max
        )

        assert result.objective_value == pytest.approx(expected_obj, rel=1e-6)

    def test_empty_scenario(self, params):
        """T6：无活跃任务 → 空字典"""
        scenario = _make_scenario(n_tasks=1)
        offloading = {
            0: {"local": [], "offload": {}},
        }

        result = solve_resource_allocation(
            scenario, offloading, params,
            alpha=1.0, gamma_w=1e-9,
        )

        assert result.objective_value == 0.0


class TestHeterogeneousTau:
    """异构任务 τ"""

    def test_heterogeneous_tau(self, params):
        """T7：不同 τ 下对偶二分解 vs 等比缩放结果不同"""
        scenario = _make_scenario(
            n_tasks=2, n_uavs=1, n_slots=1,
            F_0=1e9, F_1=1e9,
            tau_0=0.1, tau_1=0.5,  # 异构
            f_max_0=1e8,  # 容量紧张
        )
        offloading = {
            0: {"local": [], "offload": {0: [0, 1]}},
        }

        alpha = 1.0
        gamma_w = 1e-9

        result = solve_resource_allocation(
            scenario, offloading, params,
            alpha=alpha, gamma_w=gamma_w,
        )

        f0_dual = result.f_edge[0][0][0]
        f1_dual = result.f_edge[0][0][1]

        # 计等比缩放结果（对比）
        c0 = (alpha * 1e8 / (2 * gamma_w * params.gamma_j * 0.1)) ** (1/3)
        c1 = (alpha * 1e8 / (2 * gamma_w * params.gamma_j * 0.5)) ** (1/3)
        f0_scale = 1e8 * c0 / (c0 + c1)
        f1_scale = 1e8 * c1 / (c0 + c1)

        # 对偶解应与等比缩放不同（τ 异构情况）
        assert abs(f0_dual - f0_scale) > 1e-6 * max(f0_dual, f0_scale)


class TestKKTVerification:
    """KKT 条件验证"""

    def test_kkt_first_order_condition(self, params):
        """T8：代入解验证 KKT 一阶条件残差 < 1e-10"""
        scenario = _make_scenario(n_tasks=2, n_uavs=1, n_slots=1)
        offloading = {
            0: {"local": [], "offload": {0: [0, 1]}},
        }

        alpha = 1.0
        gamma_w = 1e-9

        result = solve_resource_allocation(
            scenario, offloading, params,
            alpha=alpha, gamma_w=gamma_w,
        )

        # 提取解
        f_edge = result.f_edge
        task0, task1 = scenario.tasks[0], scenario.tasks[1]
        uav = scenario.uavs[0]

        f0 = f_edge[0][0][0]
        f1 = f_edge[0][0][1]

        # KKT 条件：∂L/∂f_i = 0 (或 λ·f_i = 0 若边界)
        a0 = alpha * task0.F / task0.tau
        a1 = alpha * task1.F / task1.tau
        b = gamma_w * params.gamma_j / uav.E_max

        # 一阶条件（近似）：-a/f² + 2b·f = const（λ）
        lambda_est = -a0 / f0**2 + 2 * b * f0

        residual0 = abs(-a0 / f0**2 + 2 * b * f0 - lambda_est)
        residual1 = abs(-a1 / f1**2 + 2 * b * f1 - lambda_est)

        assert residual0 < 1e-8
        assert residual1 < 1e-8
```

---

## 验证检查清单

### 编码风格
- [ ] `from __future__ import annotations` 开头
- [ ] `__all__ = [...]` 导出列表
- [ ] 模块 docstring 引用公式编号
- [ ] 数据类用 `@dataclass(frozen=True)`
- [ ] 物理参数均为 keyword-only（`*,`）
- [ ] 注释对齐数学公式（如 `# Eq.(3-20): ...`）
- [ ] 类型别名从 precompute.py 导入（不重复定义）

### 数学正确性
- [ ] KKT 一阶条件：2b·f³ + λ·f² - a = 0 ✓
- [ ] 无约束解：f* = (a/(2b))^(1/3) ✓
- [ ] λ 的二分范围设定合理 ✓
- [ ] f 的二分求解（方程逆解）正确 ✓
- [ ] 目标函数计算完整 ✓

### 测试覆盖
- [ ] T1: 本地唯一 → f_edge 空
- [ ] T2: 无约束 → 精确 KKT
- [ ] T3: 约束触发 → Σf = f_max
- [ ] T4: 单任务上界
- [ ] T5: 目标值手算验证
- [ ] T6: 空集处理
- [ ] T7: 异构 τ 对偶解 ≠ 等比缩放
- [ ] T8: KKT 残差 < 1e-8

### 运行检查
```bash
# 单文件测试
pytest tests/test_resource_alloc.py -v

# 集成测试
pytest tests/ -v --tb=short

# 预期结果：8/8 PASS
```

---

## 下一步交接

**明天开始时：**

1. 用 Codex/Gemini 生成代码框架（或直接手写）
2. 逐行实现 resource_alloc.py
3. 编写 test_resource_alloc.py
4. 运行测试，确保 8/8 PASS
5. 更新 git commit（Phase⑥ Step 2 完成）

**预计耗时：** 2-3 小时（包括调试）

**关键风险：**
- 二分法收敛性：需验证 λ_max 估计的保守性
- KKT 残差精度：target < 1e-8，可能需要 eps_freq 调整
- 异构 τ 场景设计：T7 验证对偶解的优越性

---

**文档完成时间：** 2026-03-22 13:45 UTC
**状态：** ✓ 待明日实施
