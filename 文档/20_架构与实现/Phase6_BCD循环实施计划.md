# Phase⑥ Level-2 BCD 循环实施计划

> 创建日期：2026-03-22
> 状态：待实施

## Context

Phase⑤ 已完成（S1-S4 全 PASS），当前系统仅运行 Level-1 单层优化（固定轨迹+频率，只求解卸载决策）。需要实现 Level-2（资源分配+轨迹规划）并通过 BCD 交替迭代与 Level-1 耦合，实现联合优化。

数学规范已完整定义于 `文档/10_模型与公式/公式20_两层解耦.md`。

---

## 关键设计决策

| 问题 | 决策 | 理由 |
|------|------|------|
| Level 2a 求解器 | **解析 KKT + 水填充投影** | 可分离凸结构，闭式解，微秒级，无需额外依赖 |
| Level 2b 求解器 | **CVXPY + ECOS（SOCP）** | SCA 每轮需重建问题，CVXPY DPP 自然支持；免费；可后换 Gurobi 后端 |
| 文件组织 | **每块一个文件** | propulsion.py / resource_alloc.py / trajectory_opt.py / bcd_loop.py |
| 实现顺序 | **自底向上** | 最快反馈：推进力 → 资源 → 轨迹 → BCD → HS接入 |

---

## Step 1: `edge_uav/model/propulsion.py`（~80行）

推进力功率与飞行能耗计算（公式18）。

```python
propulsion_power(v_sq, *, eta_1, eta_2, eta_3, eta_4, v_tip) → float
flight_energy_per_slot(q_j, delta, prop_params) → dict[int, float]  # E_fly[t]
total_flight_energy(q, delta, prop_params) → dict[int, float]       # per-UAV total
```

测试：`tests/test_propulsion.py`（~5 个）— 已知速度 → 已知功率

---

## Step 2: `edge_uav/model/resource_alloc.py`（~120行）

Level 2a 解析解。

```python
@dataclass(frozen=True)
class ResourceAllocResult:
    f_local: Scalar2D       # [i][t] = f_max
    f_edge: Scalar3D        # [j][i][t] = KKT最优
    objective_value: float

solve_resource_allocation(scenario, offloading_decisions, q_fixed, params,
                          *, alpha, gamma_w) → ResourceAllocResult
```

核心逻辑：
1. `f_local[i][t] = f_max`（无本地能耗项，最大化频率）
2. `f_ji* = (α·E_max / (2·γ_w·γ_j·τ_i))^(1/3)`（KKT 无约束解）
3. 若 `Σ_i f_ji* > f_max`，水填充等比缩放

测试：`tests/test_resource_alloc.py`（~8 个）— 无约束/有约束/空集/单任务

---

## Step 3: `edge_uav/model/trajectory_opt.py`（~350行）

Level 2b SCA 逐次凸近似。

```python
@dataclass(frozen=True)
class TrajectoryResult:
    q: Trajectory2D
    objective_value: float
    sca_iterations: int
    converged: bool

solve_trajectory_sca(scenario, offloading_decisions, f_fixed, q_init, params,
                     prop_params, *, alpha, lambda_w, max_sca_iter=5, eps_sca=1e-3)
    → TrajectoryResult
```

关键内部函数：
- `_build_sca_subproblem()` — 在线性化点构建 CVXPY SOCP 子问题
- `_taylor_comm_delay_upper_bound()` — 通信时延 1/r(q) 的一阶 Taylor 上界
- `_taylor_propulsion_convex_bound()` — 推进功率凸上界

约束实现（公式4a-4f）：
- (4a) 边界：`0 ≤ q_j^t ≤ (x_max, y_max)`
- (4b) 初始位置：`q_j^0 = UAV.pos`
- (4c) 终止位置：`q_j^{T-1} = UAV.pos_final`
- (4d) 速度：`‖q_j^{t+1} - q_j^t‖ ≤ v_max·δ`（SOC）
- (4f) 安全距离：`‖q_j - q_j'‖ ≥ d_safe`（非凸 → SCA 线性化）

依赖：`uv pip install cvxpy`

测试：`tests/test_trajectory_opt.py`（~6 个）— 固定位置/单 UAV/小规模收敛

---

## Step 4: `edge_uav/model/bcd_loop.py`（~200行）

BCD 外层循环编排。

```python
@dataclass
class BCDResult:
    snapshot: Level2Snapshot
    offloading_outputs: dict
    total_cost: float
    bcd_iterations: int
    converged: bool
    cost_history: list[float]

run_bcd_loop(scenario, config, *,
             dynamic_obj_func=None, initial_snapshot=None,
             max_bcd_iter=5, eps_bcd=1e-3,
             max_sca_iter=3, eps_sca=1e-3,
             max_inner_bcd=3, eps_inner=1e-3,
             cost_rollback_delta=0.05) → BCDResult
```

算法：
```
for k = 1..K:
  1. precompute(snapshot) → D̂, Ê
  2. Level-1: solve BLP (± LLM proxy obj) → x*
  3. Level-2 inner:
     for l = 1..L:
       2a: solve_resource_allocation(x*, q_current) → f*
       2b: solve_trajectory_sca(x*, f*, q_current) → q*
       check inner convergence
  4. compute_real_cost(x*, q*, f*) → Φ_total
  5. cost rollback check (LLM proxy 场景)
  6. check outer convergence
```

测试：`tests/test_bcd_loop.py`（~5 个）— 单轮有效/成本单调/回滚触发

---

## Step 5: Config 扩展（~20行改动）

`config/config.py` 新增 `[edgeUavBCD]` 节：

```python
self.max_bcd_iter = 5        # BCD 外层最大迭代
self.eps_bcd = 1e-3          # 外层收敛容差
self.max_inner_bcd = 3       # Level-2 内层最大迭代
self.eps_inner = 1e-3        # 内层收敛容差
self.max_sca_iter = 3        # SCA 最大迭代
self.eps_sca = 1e-3          # SCA 收敛容差
self.cost_rollback_delta = 0.05  # 代价回滚阈值
```

`config/setting.cfg` 新增对应节。

---

## Step 6: HS 接入（~50行改动）

修改 `heuristics/hsIndividualEdgeUav.py` 的 `runOptModel()`：

```
旧：snapshot(init) → precompute → Level-1 → evaluate
新：snapshot(init/warm-start) → run_bcd_loop(Level-1 ↔ Level-2) → evaluate with real cost
```

- 替换单次 Level-1 为 `run_bcd_loop()`
- 评估使用含飞行能耗的真实系统成本
- 更新 `self.snapshot` 用于下轮 HS warm-start

---

## 工作量估算

| 文件 | 新增行数 | 类型 |
|------|----------|------|
| `edge_uav/model/propulsion.py` | ~80 | 新建 |
| `edge_uav/model/resource_alloc.py` | ~120 | 新建 |
| `edge_uav/model/trajectory_opt.py` | ~350 | 新建 |
| `edge_uav/model/bcd_loop.py` | ~200 | 新建 |
| `config/config.py` + `setting.cfg` | ~20 | 改动 |
| `heuristics/hsIndividualEdgeUav.py` | ~50 | 改动 |
| 测试（4 文件） | ~200 | 新建 |
| **合计** | **~1020** | |

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| SCA Taylor 上界推导错误 → 发散 | 先在纸上推导验证，再用数值梯度检查 |
| 水填充投影饿死低优先级任务 | 强制最低频率下限 |
| SCA 初始轨迹（直线）离任务太远 | 后续可加任务感知初始化 |
| LLM proxy 导致 BCD 非单调 | cost rollback 机制（标准目标先验证） |
| Level 2b 运行时间长 | 默认 K=3, S=3（可调），总 SOCP ~135 次 |

---

## 验证方式

1. 每步独立单元测试（propulsion → resource → trajectory → bcd）
2. BCD 标准目标下成本单调不递增
3. 1×1 冒烟测试：`run_bcd_loop()` 端到端返回有效结果
4. 3×3 完整测试：HS + BCD 联合运行，S1-S4 仍通过
5. 对比 Level-1-only vs BCD：BCD 的真实系统成本应更低

---

## 关键参考文件

| 用途 | 路径 |
|------|------|
| Level-1 BLP | `edge_uav/model/offloading.py` |
| 预计算（Level2Snapshot） | `edge_uav/model/precompute.py` |
| 评估器 | `edge_uav/model/evaluator.py` |
| HS 个体 | `heuristics/hsIndividualEdgeUav.py` |
| 配置 | `config/config.py` + `config/setting.cfg` |
| 数学规范 | `文档/10_模型与公式/公式20_两层解耦.md` |
| 架构分析 | `文档/40_审查与诊断/解耦对比分析报告.md` |
