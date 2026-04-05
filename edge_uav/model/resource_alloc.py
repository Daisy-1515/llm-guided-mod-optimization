"""Block C 资源分配 — Level 2a 频率优化.

给定固定的卸载决策 x 和无人机轨迹 q，求解最优 CPU 频率 (f_local, f_edge)，以最小化加权延迟和能量之和。

目标函数 (Eq. 3-20):
    min_f  Σ_{j,i,t} [ α·F_i/(f·τ_i) + γ_w·γ_j·f²·F_i/E_max ]
    s.t.   Σ_i f_ji^t ≤ f_max_j   ∀ j, t
           f_ji^t ≥ eps_freq

求解器：闭式 KKT + 容量受限时的对偶二分法。
"""

from __future__ import annotations

from dataclasses import dataclass

from edge_uav.data import EdgeUavScenario
from edge_uav.model.precompute import PrecomputeParams, Scalar2D, Scalar3D

__all__ = [
    "ResourceAllocResult",
    "solve_resource_allocation",
]

_MAX_OUTER_BISECT = 200   # 对偶变量范围可能跨越 30 多个数量级
_MAX_INNER_BISECT = 60    # 频率范围 [eps_freq, f_max] — 60 次二分足够
_G_REL_TOL = 1e-10        # 外部收敛条件: |g(ν) - f_max| / f_max < tol


@dataclass(frozen=True)
class ResourceAllocResult:
    """Block C 求解器输出。

    属性:
        f_local: dict[i][t] — 本地 CPU 频率 (Hz)，始终为 task.f_local。
        f_edge:  dict[j][i][t] — 边缘 CPU 频率 (Hz)，KKT 最优解。
        objective_value: L2a目标值 (已卸载任务的延迟 + 能量项)。
        total_comp_energy: {j: float} — 每架无人机的总计算能量 (J)，
            用于 BCD 循环中检查能量预算约束 (Eq. 3-25)。
        diagnostics: binding_slots, total_bisect_iters, max_bisect_iters 用于记录诊断信息。
    """

    f_local: Scalar2D
    f_edge: Scalar3D
    objective_value: float
    total_comp_energy: dict
    diagnostics: dict


# ------------------------------------------------------------------
# 公共 API
# ------------------------------------------------------------------

def solve_resource_allocation(
    scenario: EdgeUavScenario,
    offloading_decisions: dict,
    params: PrecomputeParams,
    *,
    alpha: float,
    gamma_w: float,
    N_act: int = 1,
) -> ResourceAllocResult:
    """求解 Block C：针对给定的卸载决策进行最优频率分配。

    参数:
        scenario: 边缘无人机场景数据。
        offloading_decisions: OffloadingModel.getOutputs() 的返回格式 —
            ``{t: {"local": [i...], "offload": {j: [i...]}}}``。
        params: 物理参数 (此处使用 gamma_j, eps_freq)。
        alpha: 延迟权重 (> 0, 仅限关键字参数)。
        gamma_w: 能量缩放因子 (> 0, 仅限关键字参数)。
        N_act: 聚合归一化因子（active task-slot 总数），默认 1。

    返回:
        带有 f_local, f_edge, objective, diagnostics 的 ResourceAllocResult 对象。

    抛出:
        ValueError: 当 alpha / gamma_w / gamma_j 无效时。
    """
    if alpha <= 0:
        raise ValueError(f"alpha must be > 0, got {alpha}")
    if gamma_w <= 0:
        raise ValueError(f"gamma_w must be > 0, got {gamma_w}")
    if params.gamma_j <= 0:
        raise ValueError(f"gamma_j must be > 0, got {params.gamma_j}")

    offload_sets = _parse_offload_sets(offloading_decisions, scenario)

    # f_local: 始终为 task.f_local (无本地能量项 ⇒ 最大频率即为最优)
    f_local: Scalar2D = {
        i: {t: task.f_local for t in scenario.time_slots}
        for i, task in scenario.tasks.items()
    }

    # f_edge: 存储为 [j][i][t]；针对每个 (j, t) 时隙使用 KKT + 对偶二分法求解
    f_edge: Scalar3D = {j: {i: {} for i in scenario.tasks} for j in scenario.uavs}
    diag = {"binding_slots": 0, "total_bisect_iters": 0, "max_bisect_iters": 0}

    for j, slot_map in offload_sets.items():
        uav = scenario.uavs[j]
        for t, task_ids in slot_map.items():
            if not task_ids:
                continue
            # Eq. 3-20 系数: a_i = α·F_i/τ_i, b_i = γ_w·γ_j·F_i/E_max
            specs = []
            for i in task_ids:
                task = scenario.tasks[i]
                a_i = alpha * task.F / task.tau
                b_i = gamma_w * params.gamma_j * task.F / uav.E_max
                specs.append((i, a_i, b_i))

            freqs, n_bisect = _solve_slot_kkt(specs, uav.f_max, params.eps_freq)
            for i, f in freqs.items():
                f_edge[j][i][t] = f

            if n_bisect > 0:
                diag["binding_slots"] += 1
            diag["total_bisect_iters"] += n_bisect
            diag["max_bisect_iters"] = max(diag["max_bisect_iters"], n_bisect)

    obj = _compute_objective(f_edge, offload_sets, scenario, params,
                             alpha=alpha, gamma_w=gamma_w, N_act=N_act)

    # Eq. 3-25: 计算每架无人机的总计算能量，用于验证 BCD 可行性
    comp_energy = _compute_comp_energy(f_edge, offload_sets, scenario, params)

    return ResourceAllocResult(
        f_local=f_local, f_edge=f_edge,
        objective_value=obj, total_comp_energy=comp_energy,
        diagnostics=diag,
    )


# ------------------------------------------------------------------
# 内部辅助函数
# ------------------------------------------------------------------

def _parse_offload_sets(
    outputs: dict,
    scenario: EdgeUavScenario,
) -> dict[int, dict[int, list[int]]]:
    """从卸载决策中提取每架无人机每个时隙的任务列表。

    返回:
        {j: {t: [i, ...]}} — 时隙 t 卸载给无人机 j 的任务。
    """
    sets: dict[int, dict[int, list[int]]] = {j: {} for j in scenario.uavs}
    for t in scenario.time_slots:
        slot = outputs.get(t)
        if slot is None:
            continue
        for j, task_ids in slot.get("offload", {}).items():
            if j not in scenario.uavs:
                raise ValueError(f"unknown uav_id={j}")
            if task_ids:
                sets[j][t] = list(task_ids)
    return sets


def _solve_slot_kkt(
    specs: list[tuple[int, float, float]],
    f_max: float,
    eps_freq: float,
) -> tuple[dict[int, float], int]:
    """针对单个 (j, t) 时隙的 KKT 求解器。

    第 1 阶段: 求解无约束最优解 f_i* = (a_i / (2·b_i))^(1/3)。
    第 2 阶段: 如果 Σf_i* ≤ f_max，则直接返回该解。
    第 3 阶段: 针对容量受限，通过对偶二分法求解 ν，使得 Σ f_i(ν) = f_max。

    返回:
        ({i: f_i*}, n_bisect_iters)。
    """
    if not specs:
        return {}, 0

    # 第 1 阶段: 无约束 KKT — 即 Eq. 3-20 且 ν = 0
    unc = {}
    total = 0.0
    for i, a_i, b_i in specs:
        f_i = (a_i / (2.0 * b_i)) ** (1.0 / 3.0)
        unc[i] = f_i
        total += f_i

    # 第 2 阶段: 可行性检查
    if total <= f_max:
        clamped = {i: max(eps_freq, min(f_max, f)) for i, f in unc.items()}
        # 裁剪后的检查：由于 eps_freq 的下限限制，可能导致总和超出容量
        if sum(clamped.values()) <= f_max:
            return clamped, 0
        # 如果超出，则继续进入对偶二分法阶段

    # 第 3 阶段: 对偶二分法 — 寻找 ν > 0 使得 g(ν) = Σ f_i(ν) = f_max
    #   ν 范围可能跨越 30 多个数量级 (例如，当 gamma_j ≈ 1e-28 时，范围在 [0, 2e33])，
    #   因此，收敛条件基于相对于 f_max 的 g(ν) 变化，而不是 ν 的绝对公差。
    nu_lo = 0.0
    nu_hi = max(a for _, a, _ in specs) / (eps_freq ** 2)

    n_bisect = 0
    for _ in range(_MAX_OUTER_BISECT):
        nu_mid = 0.5 * (nu_lo + nu_hi)
        g = sum(
            _freq_at_dual(a_i, b_i, nu_mid, f_max, eps_freq)
            for _, a_i, b_i in specs
        )
        if g > f_max:
            nu_lo = nu_mid
        else:
            nu_hi = nu_mid
        n_bisect += 1
        if abs(g - f_max) < _G_REL_TOL * f_max:
            break

    nu_final = 0.5 * (nu_lo + nu_hi)
    freqs = {
        i: _freq_at_dual(a_i, b_i, nu_final, f_max, eps_freq)
        for i, a_i, b_i in specs
    }
    return freqs, n_bisect


def _freq_at_dual(
    a: float,
    b: float,
    nu: float,
    f_max: float,
    eps_freq: float,
) -> float:
    """求解  2b·f³ + ν·f²  − a = 0，使得 f ∈ [eps_freq, f_max]。

    等式左侧 h(f) = 2b·f³ + ν·f² − a 在 f > 0 时严格单调递增，
    因此二分查找能够保证收敛。
    """
    def h(f: float) -> float:
        return 2.0 * b * f * f * f + nu * f * f - a

    if h(eps_freq) >= 0.0:
        return eps_freq
    if h(f_max) <= 0.0:
        return f_max

    lo, hi = eps_freq, f_max
    for _ in range(_MAX_INNER_BISECT):
        mid = 0.5 * (lo + hi)
        if h(mid) > 0.0:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-14:
            break
    return 0.5 * (lo + hi)


def _compute_objective(
    f_edge: Scalar3D,
    offload_sets: dict[int, dict[int, list[int]]],
    scenario: EdgeUavScenario,
    params: PrecomputeParams,
    *,
    alpha: float,
    gamma_w: float,
    N_act: int = 1,
) -> float:
    """L2a 目标函数: (1/N_act) × Σ [ α·F/(f·τ) + γ_w·γ_j·f²·F/E_max ]。

    仅包含与频率相关的项；通信延迟作为外部参数给定。
    """
    inv_N_act = 1.0 / N_act if N_act > 0 else 1.0
    obj = 0.0
    for j, slot_map in offload_sets.items():
        uav = scenario.uavs[j]
        task_freqs = f_edge.get(j, {})
        for t, task_ids in slot_map.items():
            for i in task_ids:
                f = task_freqs.get(i, {}).get(t)
                if f is None or f <= 0.0:
                    continue
                task = scenario.tasks[i]
                # Eq. 3-20: 延迟项 + 能量项（带聚合归一化）
                obj += inv_N_act * alpha * task.F / (f * task.tau)
                obj += inv_N_act * gamma_w * params.gamma_j * f * f * task.F / uav.E_max
    return obj


def _compute_comp_energy(
    f_edge: Scalar3D,
    offload_sets: dict[int, dict[int, list[int]]],
    scenario: EdgeUavScenario,
    params: PrecomputeParams,
) -> dict[int, float]:
    """计算每架无人机的总计算能量: Σ_{i,t} γ_j · f² · F_i。

    供 BCD 模型检查 Eq. 3-25 可行性: E_comp_j + E_fly_j ≤ E_max_j。
    """
    energy: dict[int, float] = {j: 0.0 for j in scenario.uavs}
    for j, slot_map in offload_sets.items():
        task_freqs = f_edge.get(j, {})
        for t, task_ids in slot_map.items():
            for i in task_ids:
                f = task_freqs.get(i, {}).get(t)
                if f is None or f <= 0.0:
                    continue
                task = scenario.tasks[i]
                # Eq. 3-24: E_comp = γ_j · f² · F_i
                energy[j] += params.gamma_j * f * f * task.F
    return energy
