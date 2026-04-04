"""Block D 轨迹优化 — Level 2b SCA + CVXPY SOCP.

给定固定的卸载决策 x 和资源分配 f_edge，求解联合极小化通信延迟与推进能量的
最优无人机轨迹 q，受限于：
  - 地图边界、初始/最终位置以及速度约束（凸集）
  - 终点可达性约束（4e）
  - 通信延迟约束（通过连续凸近似转化为凸约束）
  - 安全分隔约束（非凸，通过引入松弛变量的 SCA 进行线性化）

使用 CVXPY，并带有 CLARABEL/ECOS/SCS 求解器回退机制以保证稳健性。
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import cvxpy as cp
import numpy as np

from edge_uav.data import EdgeUavScenario
from edge_uav.model.precompute import PrecomputeParams, Trajectory2D
from edge_uav.model.propulsion import total_flight_energy

__all__ = [
    "TrajectoryOptParams",
    "TrajectoryResult",
    "solve_trajectory_sca",
]


@dataclass(frozen=True)
class TrajectoryOptParams:
    """轨迹优化参数 — 专属步骤 3。

    属性:
        eta_1, eta_2, eta_3, eta_4: 推进模型系数 (W, m, s, ...)
        v_tip: 旋翼叶尖速度 (m/s)
        v_max: UAV 最大飞行速度 (m/s)
        d_safe: 安全分隔距离 (m)。如果 <= 0，则跳过安全距离检查。
    """
    eta_1: float
    eta_2: float
    eta_3: float
    eta_4: float
    v_tip: float
    v_max: float
    d_safe: float


@dataclass(frozen=True)
class TrajectoryResult:
    """轨迹优化输出结果。

    属性:
        q: 优化后的轨迹 dict[j][t] = (x, y) (m)
        objective_value: 完整的 L2b 目标值 = alpha*total_comm_delay + lambda_w*total_prop_energy
        total_comm_delay: 总通信延迟 Σ D_l/r_up + D_r/r_down (s)
        total_prop_energy: 总推进能量 Σ_j E_prop_j (J)
        per_uav_energy: 每架无人机的推进能量 (J), dict[j] -> float
        sca_iterations: 执行的 SCA 迭代次数 (1 <= k <= max_sca_iter)
        converged: 如果相对间隙 <= eps_sca 则为 True，如果达到 max_sca_iter 则为 False
        solver_status: 最终的 CVXPY 求解器状态 (例如 'optimal', 'optimal_inaccurate')
        max_safe_slack: 最后一次迭代中的最大安全约束松弛量 (m²)
                       > 0 表示初始轨迹不满足安全距离
        diagnostics: 包含额外诊断信息的字典:
            - 'true_objective_history': list[float] — 每次 SCA 迭代的真实 L2b 目标值
            - 'total_comm_delay_history': list[float] — 每次迭代的通信延迟 (s)
            - 'total_prop_energy_history': list[float] — 每次迭代的推进能量 (J)
            - 'surrogate_history': list[float] — CVXPY 替代目标值
            - 'solver_status_history': list[str]
            - 'max_slack_history': list[float]
            - 'sca_times': list[float] — 每次迭代的计算耗时 (s)
    """
    q: Trajectory2D
    objective_value: float
    total_comm_delay: float
    total_prop_energy: float
    per_uav_energy: dict[int, float]
    sca_iterations: int
    converged: bool
    solver_status: str
    max_safe_slack: float
    diagnostics: dict[str, Any]


def solve_trajectory_sca(
    scenario: EdgeUavScenario,
    offloading_decisions: dict,
    f_fixed: dict,
    q_init: Trajectory2D,
    params: PrecomputeParams,
    traj_params: TrajectoryOptParams,
    *,
    max_sca_iter: int = 100,
    eps_sca: float = 1e-3,
    safe_slack_penalty: float = 1e6,
    solver_fallback: tuple[str, ...] = ("CLARABEL", "ECOS", "SCS"),
    alpha: float = 1.0,
    lambda_w: float = 1.0,
) -> TrajectoryResult:
    """Solve the trajectory SCA subproblem with safety-aware solution screening."""
    _validate_input_basic(scenario, q_init, traj_params, params)

    T = len(scenario.time_slots)
    delta = float(scenario.meta.get("delta", 0.5))

    for j in scenario.uavs:
        pos_j = scenario.uavs[j].pos
        pos_final_j = scenario.uavs[j].pos_final
        dist_max = np.linalg.norm(np.array(pos_final_j) - np.array(pos_j))
        max_dist_achievable = (T - 1) * traj_params.v_max * delta
        if dist_max > max_dist_achievable + 1e-9:
            raise ValueError(
                f"UAV {j}: endpoint distance {dist_max:.2f}m exceeds reachable "
                f"limit {max_dist_achievable:.2f}m under v_max={traj_params.v_max}m/s"
            )

    active_offloads = _extract_active_offloads(scenario, offloading_decisions, f_fixed)

    for j, i, t in active_offloads:
        tau_i = scenario.tasks[i].tau
        F_i = scenario.tasks[i].F
        f_edge_jit = f_fixed.get(j, {}).get(i, {}).get(t)
        if f_edge_jit is None:
            raise ValueError(
                f"Active offload (j={j}, i={i}, t={t}) is missing in f_fixed"
            )
        tau_comm = tau_i - F_i / f_edge_jit
        if tau_comm <= 0:
            raise ValueError(
                "Infeasible communication budget: "
                f"j={j}, i={i}, t={t}, tau_comm={tau_comm:.2e}"
            )

    is_safe_init, safety_msg = _validate_initial_trajectory(
        q_init, scenario, traj_params, params, allow_unsafe=True
    )
    if not is_safe_init:
        print(
            f"[WARNING] Initial trajectory unsafe: {safety_msg}. "
            "Will use slack penalties to handle."
        )

    q_ref = q_init
    obj_history: list[float] = []
    comm_history: list[float] = []
    prop_history: list[float] = []
    surrogate_history: list[float] = []
    solver_status_history: list[str] = []
    slack_history: list[float] = []
    sca_times: list[float] = []
    final_safety_diag = _compute_safety_diagnostics(q_ref, scenario, traj_params.d_safe)
    converged = False

    for sca_k in range(max_sca_iter):
        iter_start = time.time()

        try:
            problem, q_var, slack_safe, _ = _build_sca_subproblem(
                scenario,
                q_ref,
                f_fixed,
                params,
                traj_params,
                active_offloads,
                safe_slack_penalty,
                alpha=alpha,
                lambda_w=lambda_w,
            )
        except Exception as e:
            raise ValueError(f"SCA iteration {sca_k} failed to build subproblem: {e}")

        accepted_candidate = None
        fallback_inaccurate = None
        solver_status = None

        for solver_name in solver_fallback:
            try:
                problem.solve(solver=getattr(cp, solver_name), verbose=False)
            except Exception:
                continue

            solver_status = problem.status
            if solver_status not in {"optimal", "optimal_inaccurate"}:
                continue

            q_candidate = _extract_trajectory_solution(q_var, scenario, T)
            q_candidate = _project_trajectory_to_bounds(q_candidate, scenario)

            # Velocity constraint verification after projection
            velocity_ok = _verify_velocity_constraints(
                q_candidate, traj_params.v_max, delta, scenario
            )
            if not velocity_ok:
                # Reject candidate with velocity constraint violation
                continue

            obj_true, comm_true, prop_true = _evaluate_true_objective(
                scenario,
                q_candidate,
                traj_params,
                params,
                active_offloads,
                alpha=alpha,
                lambda_w=lambda_w,
            )
            max_slack = (
                float(np.max([sv.value for sv in slack_safe.values()]))
                if slack_safe
                else 0.0
            )
            safety_diag = _compute_safety_diagnostics(
                q_candidate, scenario, traj_params.d_safe
            )

            candidate = {
                "q": q_candidate,
                "objective_value": obj_true,
                "total_comm_delay": comm_true,
                "total_prop_energy": prop_true,
                "max_safe_slack": max_slack,
                "solver_status": solver_status,
                "surrogate_value": (
                    problem.value if problem.value is not None else float("inf")
                ),
                "safety_diag": safety_diag,
            }

            if solver_status == "optimal":
                accepted_candidate = candidate
                break

            if _safety_diagnostics_pass(safety_diag):
                if (
                    fallback_inaccurate is None
                    or candidate["objective_value"] < fallback_inaccurate["objective_value"]
                ):
                    fallback_inaccurate = candidate

        if accepted_candidate is None:
            accepted_candidate = fallback_inaccurate

        if accepted_candidate is None:
            raise ValueError(
                "SCA iteration "
                f"{sca_k} failed: all candidate solvers were infeasible or unsafe. "
                f"Last status={solver_status}"
            )

        q_ref = accepted_candidate["q"]
        final_safety_diag = accepted_candidate["safety_diag"]

        obj_history.append(accepted_candidate["objective_value"])
        comm_history.append(accepted_candidate["total_comm_delay"])
        prop_history.append(accepted_candidate["total_prop_energy"])
        surrogate_history.append(accepted_candidate["surrogate_value"])
        solver_status_history.append(accepted_candidate["solver_status"])
        slack_history.append(accepted_candidate["max_safe_slack"])
        sca_times.append(time.time() - iter_start)

        converged = False
        if sca_k > 0:
            rel_gap = abs(obj_history[sca_k] - obj_history[sca_k - 1]) / (
                abs(obj_history[sca_k - 1]) + 1e-12
            )
            converged = rel_gap <= eps_sca

        if converged or sca_k == max_sca_iter - 1:
            break

    per_uav_energy = total_flight_energy(
        q_ref,
        delta,
        eta_1=traj_params.eta_1,
        eta_2=traj_params.eta_2,
        eta_3=traj_params.eta_3,
        eta_4=traj_params.eta_4,
        v_tip=traj_params.v_tip,
        include_terminal_hover=False,
    )

    # Compute final trajectory velocity diagnostics
    max_velocity = 0.0
    for j in scenario.uavs:
        if j not in q_ref:
            continue
        q_j = q_ref[j]
        for t_idx in range(len(scenario.time_slots) - 1):
            t_curr = scenario.time_slots[t_idx + 1]
            t_prev = scenario.time_slots[t_idx]
            if t_curr in q_j and t_prev in q_j:
                x_curr, y_curr = q_j[t_curr]
                x_prev, y_prev = q_j[t_prev]
                dist = math.sqrt((float(x_curr) - float(x_prev)) ** 2 + (float(y_curr) - float(y_prev)) ** 2)
                velocity = dist / delta
                max_velocity = max(max_velocity, velocity)

    return TrajectoryResult(
        q=q_ref,
        objective_value=obj_history[-1],
        total_comm_delay=comm_history[-1],
        total_prop_energy=prop_history[-1],
        per_uav_energy=per_uav_energy,
        sca_iterations=len(obj_history),
        converged=converged,
        solver_status=solver_status_history[-1] if solver_status_history else "unknown",
        max_safe_slack=slack_history[-1] if slack_history else 0.0,
        diagnostics={
            "true_objective_history": obj_history,
            "total_comm_delay_history": comm_history,
            "total_prop_energy_history": prop_history,
            "surrogate_history": surrogate_history,
            "solver_status_history": solver_status_history,
            "max_slack_history": slack_history,
            "sca_times": sca_times,
            "min_inter_uav_distance": final_safety_diag["min_inter_uav_distance"],
            "min_inter_uav_distance_slot": final_safety_diag["min_inter_uav_distance_slot"],
            "violated_safe_slots": final_safety_diag["violated_safe_slots"],
            "final_safety_passed": _safety_diagnostics_pass(final_safety_diag),
            "velocity_check_enabled": True,
            "velocity_check_tolerance": 1.01,
            "final_max_velocity": max_velocity,
            "velocity_constraint_ratio": max_velocity / traj_params.v_max if traj_params.v_max > 0 else 0.0,
            "velocity_verified": max_velocity <= traj_params.v_max * 1.01,
        },
    )



# ============================================================================
# 辅助函数
# ============================================================================

def _validate_input_basic(
    scenario: EdgeUavScenario,
    q_init: Trajectory2D,
    traj_params: TrajectoryOptParams,
    params: PrecomputeParams,
) -> None:
    """对场景与参数进行基础性的合法验证。"""
    if not scenario.uavs or not scenario.tasks:
        raise ValueError("场景内未载入 UAV 或待处理任务群")
    if traj_params.v_max <= 0:
        raise ValueError(f"v_max 必须大于 0，当前传入值为 {traj_params.v_max}")
    delta = float(scenario.meta.get('delta', 0.5))
    if delta <= 0:
        raise ValueError(f"delta 必须大于 0，当前传入值为 {delta}")
    if len(q_init) != len(scenario.uavs):
        raise ValueError(
            f"初始轨迹共具备 {len(q_init)} 架无人机，而场景中规定只有 {len(scenario.uavs)} 架"
        )


def _validate_initial_trajectory(
    q_init: Trajectory2D,
    scenario: EdgeUavScenario,
    traj_params: TrajectoryOptParams,
    params: PrecomputeParams,
    allow_unsafe: bool = True,
) -> tuple[bool, str]:
    """验证初始轨迹对地图边线、起始终点、速度限值和基础防撞距的安全要求合规性。

    返回:
        (is_safe, reason) — 如果所有验证都通过则返回 True；否则返回 False 并附带具体文案。
    """
    T = len(scenario.time_slots)
    x_max = float(scenario.meta.get('x_max', 1000.0))
    y_max = float(scenario.meta.get('y_max', 1000.0))
    delta = float(scenario.meta.get('delta', 0.5))

    for j in scenario.uavs:
        if j not in q_init:
            return False, f"UAV {j} 未能在初始轨迹 q_init 中找寻到"

        q_j = q_init[j]
        if len(q_j) != T:
            return False, f"UAV {j} 的轨迹包含 {len(q_j)} 点位，而总时隙应为 T={T}"

        # 检查边界
        for t in range(T):
            x, y = q_j[t]
            if not (0 <= x <= x_max) or not (0 <= y <= y_max):
                return False, f"UAV {j} 在 t={t} 的位置 ({x:.2f}, {y:.2f}) 超越地图界线 [0,{x_max}]×[0,{y_max}]"

        # 检查起始终端点重合度
        pos_j = scenario.uavs[j].pos
        pos_final_j = scenario.uavs[j].pos_final
        if not np.allclose(q_j[0], pos_j, atol=1e-6):
            return False, f"UAV {j}: 初始轨迹点 q[{j}][0]={q_j[0]} 与出发坐标 pos={pos_j} 不吻合"
        if not np.allclose(q_j[T - 1], pos_final_j, atol=1e-6):
            return False, f"UAV {j}: 最终轨迹点 q[{j}][T-1]={q_j[T-1]} 与终点坐标 pos_final={pos_final_j} 不吻合"

        # 验证速度不能冲破限制
        for t in range(T - 1):
            delta_q = np.array(q_j[t + 1]) - np.array(q_j[t])
            dist = np.linalg.norm(delta_q)
            max_dist = traj_params.v_max * delta
            if dist > max_dist + 1e-9:
                return False, f"UAV {j} 于 t={t} 时刻点越阶位移: ||Δq||={dist:.2f}m > v_max·δ={max_dist:.2f}m"

    # 防撞检查约束安全屏障 — 端点豁免免查 (由于特定的场景设计):
    # 全部无人机均共同挂在同一个无人机集中收发平台 (起发和终端降落处全在一点)，所以出于特例给予两端豁免。
    # 把端点囊括在安全检查之内会导致问题直接失去数学解。
    # 其检测真正发生段在: 0 < t < T-1 (唯针对中途运转节点)。
    if traj_params.d_safe > 0:
        for j in scenario.uavs:
            for k in scenario.uavs:
                if j >= k:
                    continue
                q_j = q_init[j]
                q_k = q_init[k]
                for t in range(1, T - 1):  # 阶段性中间节点; 彻底豁免终端接头
                    delta_q = np.array(q_j[t]) - np.array(q_k[t])
                    dist = np.linalg.norm(delta_q)
                    if dist < traj_params.d_safe - 1e-9:
                        return False, (
                            f"UAV {j} 与 {k} 在 t={t} 发生越界接近: ||q_j - q_k||={dist:.2f}m "
                            f"<  d_safe={traj_params.d_safe}m"
                        )

    return True, "OK"


def _project_trajectory_to_bounds(
    q: Trajectory2D,
    scenario: EdgeUavScenario,
) -> Trajectory2D:
    """Clamp slight solver drift to the map box and restore exact endpoints."""
    x_max = float(scenario.meta.get('x_max', 1000.0))
    y_max = float(scenario.meta.get('y_max', 1000.0))
    first_t = scenario.time_slots[0]
    last_t = scenario.time_slots[-1]

    projected: Trajectory2D = {}
    for j, q_j in q.items():
        projected[j] = {}
        for t in scenario.time_slots:
            x, y = q_j[t]
            projected[j][t] = (
                float(np.clip(x, 0.0, x_max)),
                float(np.clip(y, 0.0, y_max)),
            )

        projected[j][first_t] = tuple(scenario.uavs[j].pos)
        projected[j][last_t] = tuple(scenario.uavs[j].pos_final)

    return projected


def _verify_velocity_constraints(
    q: Trajectory2D,
    v_max: float,
    delta: float,
    scenario: EdgeUavScenario,
    tolerance: float = 1.01,
) -> bool:
    """Verify that all UAVs satisfy velocity constraints after trajectory extraction/projection.

    Args:
        q: Trajectory dict[j][t] = (x, y)
        v_max: Maximum velocity (m/s)
        delta: Time step interval (s)
        scenario: EdgeUavScenario object
        tolerance: Allow up to 1% numerical error (default 1.01)

    Returns:
        bool: True if all velocity constraints satisfied, False otherwise.
    """
    if v_max <= 0:
        return True  # No velocity constraint

    for j in scenario.uavs:
        if j not in q:
            continue

        q_j = q[j]
        time_slots = scenario.time_slots

        for t_idx in range(len(time_slots) - 1):
            t_curr = time_slots[t_idx + 1]
            t_prev = time_slots[t_idx]

            if t_curr not in q_j or t_prev not in q_j:
                continue

            x_curr, y_curr = q_j[t_curr]
            x_prev, y_prev = q_j[t_prev]

            dx = float(x_curr) - float(x_prev)
            dy = float(y_curr) - float(y_prev)
            dist = math.sqrt(dx**2 + dy**2)
            velocity = dist / delta

            if velocity > v_max * tolerance:
                return False

    return True


def _extract_trajectory_solution(
    q_var: dict,
    scenario: EdgeUavScenario,
    T: int,
) -> Trajectory2D:
    """Read solver values from q_var into the project trajectory dict."""
    q_new_dict = {j: {} for j in scenario.uavs}
    for j in scenario.uavs:
        for t in range(T):
            x_val = q_var[j][t][0].value
            y_val = q_var[j][t][1].value
            if x_val is None or y_val is None:
                raise ValueError(f"Solver did not assign q[{j}][{t}]")
            q_new_dict[j][t] = (float(x_val), float(y_val))
    return q_new_dict


def _compute_safety_diagnostics(
    q: Trajectory2D,
    scenario: EdgeUavScenario,
    d_safe: float,
    *,
    tolerance: float = 1e-3,
) -> dict[str, Any]:
    """Compute true pairwise safety diagnostics on interim time slots."""
    diagnostics = {
        "min_inter_uav_distance": float("inf"),
        "min_inter_uav_distance_slot": None,
        "violated_safe_slots": [],
    }
    if d_safe <= 0 or len(scenario.uavs) < 2:
        return diagnostics

    for j in scenario.uavs:
        for k in scenario.uavs:
            if j >= k:
                continue
            for t in range(1, len(scenario.time_slots) - 1):
                dist = float(
                    np.linalg.norm(np.array(q[j][t], dtype=float) - np.array(q[k][t], dtype=float))
                )
                if dist < diagnostics["min_inter_uav_distance"]:
                    diagnostics["min_inter_uav_distance"] = dist
                    diagnostics["min_inter_uav_distance_slot"] = (j, k, t)
                if dist < d_safe - tolerance:
                    diagnostics["violated_safe_slots"].append((j, k, t, dist))

    return diagnostics


def _safety_diagnostics_pass(
    diagnostics: dict[str, Any],
) -> bool:
    """Return True when no material safe-distance violation remains."""
    return len(diagnostics.get("violated_safe_slots", [])) == 0


def _extract_active_offloads(
    scenario: EdgeUavScenario,
    offloading_decisions: dict,
    f_fixed: dict,
) -> list[tuple[int, int, int]]:
    """以 (j, i, t) 元组群集的形式提取指代任务 i 在位于 t 时区卸给 UAV j 处理的合集。

    当其下放了有效的决策指派便以它作为官方依准，而一旦遇到无参带离传的 {} 将会自动找寻调用 f_fixed 表数据用作补充。

    参数:
        scenario: EdgeUavScenario (当前闲置保留接口完整度)
        offloading_decisions: 卸配决策组 {t: {"local": [i...], "offload": {j: [i...]}}}
        f_fixed: dict[j][i][t] -> float, 取用于自接段步进 2 的资源规划分配成项

    返回:
        囊括在列表当中的所有积极卸分项参数对应单元。

    抛出:
        ValueError: 当它两两字典表数据间生化出现逻辑互驳异错之时报警制停
    """
    # 策略退缩回退线: 当拿到落空分配簿册的时候，调转向着 f_fixed 大力搜发引据用。
    if not offloading_decisions:
        active = []
        for j in f_fixed:
            for i in f_fixed[j]:
                for t in f_fixed[j][i]:
                    if f_fixed[j][i][t] > 0:
                        active.append((j, i, t))
        return active

    # 透过已有宣告项将相关条案拢收记录起来
    declared: set[tuple[int, int, int]] = set()
    for t, t_dict in offloading_decisions.items():
        for j, task_list in t_dict.get("offload", {}).items():
            for i in task_list:
                declared.add((j, i, t))

    # 去 f_fixed 中深挖有效活跃之正值群落
    f_fixed_positive: set[tuple[int, int, int]] = set()
    for j in f_fixed:
        for i in f_fixed[j]:
            for t in f_fixed[j][i]:
                if f_fixed[j][i][t] > 0:
                    f_fixed_positive.add((j, i, t))

    # 执行同一对应校验：但有挂接布派指令也势必对等地反映呈现于正数配置上
    missing_in_f_fixed = declared - f_fixed_positive
    if missing_in_f_fixed:
        raise ValueError(
            f"布定规划明确声称需要派收配包，但于对口的 f_fixed 段则落空缺少对应实际有功份额: "
            f"{sorted(missing_in_f_fixed)}"
        )

    # 追加残留废项检验过滤核对
    residual = f_fixed_positive - declared
    if residual:
        raise ValueError(
            f"residual f_fixed entries were found outside offloading_decisions: "
            f"{sorted(residual)}"
        )

    return sorted(declared)


def _add_communication_delay_socp_constraint(
    constraints: list,
    pos_diff: cp.Expression,
    H: float,
    rate_safe: cp.Expression,
    tau_comm_budget: float,
    *,
    payload_bits: float = 1.0,
    name_suffix: str = "",
) -> None:
    """追加服从对标于 DCP 标准格式约限规制的网络通信羁滞防越超卡线项。

    该原本的算式表现原型为: (D_l + D_r) / rate_safe <= tau_comm_budget
    透过下限直线牵引将之扳置呈合乎线状等式并排关系的形式：
        payload_bits <= tau_comm_budget * rate_safe

    参数:
        constraints: 支持推拉添加新限制条件。
        pos_diff: 回退重构处理后所余遗下来没在起效的存悬变量项。
        H: 废置没再应用。
        rate_safe: 提供对信号速率 r(z) 兜保线垫的单层下沿极限直向率度 (bps)。
        tau_comm_budget: 经费时限段额封量界限 (s)。
        payload_bits: 合起数据 D_l + D_r 传输内容总数定值 (bits)。
        name_suffix: 添加用于后缀调试追查标识志字。
    """
    # 让此通率保障维持在不坠超触底非零面以外以供护核计算系统跑脱轨道
    constraints.append(rate_safe >= 1e-12)

    # 向限制库灌写入递拉直线牵平后法则条律: 直接挂向负荷总宽 = 时间限制阈 * 安全线度率网宽
    # 等效作用为: payload <= tau * rate  (完美响应了凸限制下的正比例缩涨限定)
    constraints.append(payload_bits <= tau_comm_budget * rate_safe)


def _add_safety_separation_socp_constraint(
    constraints: list,
    d_bar: np.ndarray,
    delta_q: cp.Expression,
    d_safe: float,
    slack_penalty: float,
    objective_terms: list,
    name_suffix: str,
) -> cp.Variable:
    """挂结设置伴入责斥追扣变量作为安全避碰护垫容压区距项的 SCA 放行限。

    这使得公式保留一以贯之持续起效着的 SCA 线性切化表层:
        2 * d_bar^T * delta_q - ||d_bar||^2 + delta >= d_safe^2
    并兼并带把该留出的宽松弹性地带置挂进入了对于向向总体目标的抵扣损大盘面中以便响应落实期表为 rho_k * sum(delta_{jk}^t) 这个宏大策略。

    提醒:
        这依旧稳占属于是一条贴于在 SOCP 之从下的具像 SCA 等式规范限制范围；其这远还谈不上是对源结构大作重整颠置后的什么创新 SOC 重铸再改翻作。
    """
    slack_var = cp.Variable(nonneg=True, name=f"safe_slack_{name_suffix}")
    d_bar_norm_sq = float(np.sum(d_bar ** 2))
    lhs = 2.0 * d_bar @ delta_q - d_bar_norm_sq + slack_var
    constraints.append(lhs >= d_safe ** 2)
    objective_terms.append(slack_penalty * slack_var)
    return slack_var


def _build_sca_subproblem(
    scenario: EdgeUavScenario,
    q_ref: Trajectory2D,
    f_fixed: dict,
    params: PrecomputeParams,
    traj_params: TrajectoryOptParams,
    active_offloads: list[tuple[int, int, int]],
    safe_slack_penalty: float,
    alpha: float = 1.0,
    lambda_w: float = 1.0,
) -> tuple[cp.Problem, dict, dict, cp.Expression]:
    """围绕参照起点位 q_ref 来进行打桩和架置本趟回转的用以施行的 CVXPY SOCP 等效替代子命题方程组框架模型。

    返回:
        一套由 (problem, q_var, slack_safe_dict, obj_expr) 四分组合组成的产系结果：
        - problem: 已准备无误的 CVXPY .solve() 对象总管题集
        - q_var: dict[j][t][dim] — 囊括具体落标处参数 CVXPY Variable 决策数
        - slack_safe_dict: dict[(j,k,t)] → 提供对于相逼机队安全宽额变浮限让引用的字典表
        - obj_expr: 最后将交呈结算用之最终目的大合成函数组列表达
    """
    T = len(scenario.time_slots)
    x_max = float(scenario.meta.get('x_max', 1000.0))
    y_max = float(scenario.meta.get('y_max', 1000.0))
    delta = float(scenario.meta.get('delta', 0.5))
    uavs = scenario.uavs
    tasks = scenario.tasks

    # 决策变元组
    q_var = {j: {t: cp.Variable(2) for t in range(T)} for j in uavs}
    speed_sq = {j: {t: cp.Variable() for t in range(T - 1)} for j in uavs}
    slack_safe = {}
    objective_terms = []

    constraints = []
    obj_propulsion = 0.0

    # ===== 限定羁约框架限制阵 (4a)-(4f) =====

    # (4a) 图场限高边界线
    for j in uavs:
        for t in range(T):
            constraints.append(q_var[j][t][0] >= 0)
            constraints.append(q_var[j][t][0] <= x_max)
            constraints.append(q_var[j][t][1] >= 0)
            constraints.append(q_var[j][t][1] <= y_max)

    # (4b) 初始阵发起点定位
    for j in uavs:
        pos_j = uavs[j].pos
        constraints.append(q_var[j][0][0] == pos_j[0])
        constraints.append(q_var[j][0][1] == pos_j[1])

    # (4c) 终收末段结算点安位
    for j in uavs:
        pos_final_j = uavs[j].pos_final
        constraints.append(q_var[j][T - 1][0] == pos_final_j[0])
        constraints.append(q_var[j][T - 1][1] == pos_final_j[1])

    # (4d) 速位羁绊驱截约束条件表 (SOC)
    for j in uavs:
        for t in range(T - 1):
            delta_q = q_var[j][t + 1] - q_var[j][t]
            # ||Δq||² = Δx² + Δy²
            norm_sq = cp.sum_squares(delta_q)
            # ||Δq|| ≤ v_max · δ
            max_dist = traj_params.v_max * delta
            constraints.append(norm_sq <= (max_dist ** 2))
            # 纳入能通容 DCP 正合准纲规范的外显关联搭挂转扣延生桥接处:
            # speed_sq >= ||delta_q||^2 / delta^2
            # <=> ||delta_q||^2 <= delta^2 * speed_sq
            constraints.append(norm_sq <= (delta ** 2) * speed_sq[j][t])
            # speed_sq[j][t] >= 0
            constraints.append(speed_sq[j][t] >= 0)
            # 全身兜紧牢加定这属于伴衍引出的上探位外生面自身绝不许可溢顶溢破其固有防涨阈罩即限值限位 v^2 <= v_max^2。
            # 如无此项进行坚挺固位作保障的话，通过弦切接引入用来拉替代行代班的这个虚幻替模型运算过程中或有可能会令整个运算陷入暴量疯狂失控冲大跑散的境地中不受约束。
            constraints.append(speed_sq[j][t] <= traj_params.v_max ** 2)

    # (4e) 端局指向的触及触达保障项: ||q_j[t] - pos_final||² <= (v_max*(T-1-t)*delta)²
    for j in uavs:
        pos_final_j = np.array(uavs[j].pos_final, dtype=float)
        for t in range(T - 1):  # t=T-1 由于被 (4c) 大伞兜罩遮护盖下，便免在其中不再繁赘重述处理。
            remaining = T - 1 - t
            max_dist = traj_params.v_max * remaining * delta
            diff = q_var[j][t] - pos_final_j
            constraints.append(cp.sum_squares(diff) <= max_dist ** 2)

    # 发动机运转用功打耗推进飞移动气耗推向目引数项算量 (透过依托用伴生引产出列的属列阵元素 speed_sq 来转介构建代引结立生成这项目)
    for j in uavs:
        for t in range(T - 1):
            # 每每处于这时缝间区内该阶段产生的自身出力强弱功率算公式是: P(v²) = η₁(1 + 3v²/v_tip²) + φ_ind(v²) + η₄v³
            # 应用借着使用那向截弓直去弓拉打弦挂靠的刀手割手段于取用 [0, v_max²] 所覆包其定区间里建构生提出并盖覆搭罩上的包面防漏凸面大包盖拱面穹盖遮封层用来当作为这指标限向上限界定高界值
            v_sq = speed_sq[j][t]

            # 构件项元组分 1: η₁(1 + 3v²/v_tip²) — 指着自己对于 v² 因变参本身的表观正相关系就是一副平滑和善直条状条顺线属形貌结构态表现
            term1 = traj_params.eta_1 * (1.0 + 3.0 * v_sq / (traj_params.v_tip ** 2))

            # 构件项元组分 2: φ_ind(v²) — 此路则取从区间面展宽为 [0, v_max²] 拿借割引截线打面作出的拉切线顶限封堵向限界
            # φ_ind(v²) = η₂ · √(√(η₃ + v⁴/4) - v²/2)
            term2_ub = _propulsion_upper_bound_expr(
                v_sq, traj_params.eta_2, traj_params.eta_3,
                v_max_sq=traj_params.v_max ** 2
            )

            # 构件项元组分 3: η₄(v²)^(3/2) — 引正向弦截直截手段来找置给安铺定上那道包封面上截限界限线带
            term3_ub = _propulsion_power_drag_ub(
                v_sq, traj_params.eta_4,
                v_max_sq=traj_params.v_max ** 2
            )

            # 构成的这三连封防漏限越线大封护最高压限天顶极限高高拦截盖面
            power_ub = term1 + term2_ub + term3_ub

            # 置配入于当下此时期片段的本内局内阶段里将统括收揽去用支去耗用的引散流放能量消解花量结账: 单时刻至顶耗项数值乘附上跨步区跨幅时长标距标尺 δ
            energy_contrib = power_ub * delta
            obj_propulsion += energy_contrib

    # 参数定指常额号数值数据一并全从场景表抽取调唤调引入位收列接发供供入项支待命使用
    H       = float(scenario.meta.get('H',     100.0))
    B_up    = float(scenario.meta.get('B_up',    2e7))
    B_down  = float(scenario.meta.get('B_down',  2e7))
    P_i     = float(scenario.meta.get('P_i',     0.5))
    P_j     = float(scenario.meta.get('P_j',     1.0))
    rho_0   = float(scenario.meta.get('rho_0',  1e-5))
    N_0     = float(scenario.meta.get('N_0',   1e-10))
    beta      = P_i * rho_0 / N_0   # 上联发传递发送上挂上路路信噪配比联系基 β
    beta_down = P_j * rho_0 / N_0   # 回发顺溜往下走放引返回接向路道网络网接管信噪联向传送分配比基 β

    # 被构建被架置起来起假充指代替充打位假用临时替代包顶替代性表头用模型充数作建拟包指标充名代理功能模型大目标大引项
    obj_comm_surrogate = cp.Constant(0)

    for j, i, t in active_offloads:
        tau_i = tasks[i].tau
        F_i = tasks[i].F
        f_edge_jit = f_fixed[j][i][t]
        tau_comm_budget = tau_i - F_i / f_edge_jit

        # 下挂接收派发送回点源地标终归下接收归向目标在陆地面表面基板的扎标定位终端落标地点
        w_i = tuple(tasks[i].pos)
        pos_diff = q_var[j][t] - np.array(w_i, dtype=float)

        # z = ||q_j[t] - w_i||² + H²  (convex in q_var)
        z_expr = cp.sum_squares(pos_diff) + H ** 2
        z_ref = max(
            np.sum((np.array(q_ref[j][t], dtype=float) - np.array(w_i, dtype=float)) ** 2) + H ** 2,
            1e-12
        )

        # Uplink rate lower bound (first-order Taylor)
        r_up_lb = _rate_lower_bound_expr(z_expr, z_ref, H, B_up, beta)
        r_up_ref = max((B_up / np.log(2)) * np.log(1 + beta / z_ref), 1e-12)

        # Downlink rate lower bound (same form, different parameters)
        r_down_lb = _rate_lower_bound_expr(z_expr, z_ref, H, B_down, beta_down)
        r_down_ref = max((B_down / np.log(2)) * np.log(1 + beta_down / z_ref), 1e-12)

        # Communication delay surrogate objective (DCP: negative constant × concave = convex)
        # Proxy for minimizing D_l/r_up + D_r/r_down via SCA
        D_l_i = float(tasks[i].D_l)
        D_r_i = float(tasks[i].D_r)
        obj_comm_surrogate = obj_comm_surrogate \
            - (D_l_i / r_up_ref ** 2) * r_up_lb \
            - (D_r_i / r_down_ref ** 2) * r_down_lb

        # Deadline constraint: (D_l + D_r) / r_up <= tau_comm_budget
        payload_bits = D_l_i + D_r_i
        _add_communication_delay_socp_constraint(
            constraints, pos_diff, H, r_up_lb, tau_comm_budget,
            payload_bits=payload_bits,
            name_suffix=f"{j}_{i}_{t}",
        )

    # (4f) Safe distance constraint — endpoint exemption (design assumption):
    # All UAVs share a common depot (takeoff and landing point), so t=0 and t=T-1
    # are intentionally exempt from safe-distance enforcement. Including endpoint
    # slots would make the problem infeasible whenever UAVs share a depot.
    # Effective domain: 0 < t < T-1 (SCA linearization, interim slots only).
    if traj_params.d_safe > 0:
        for j in uavs:
            for k in uavs:
                if j >= k:
                    continue
                for t in range(1, T - 1):  # interim slots only; endpoints exempt
                    d_bar = np.array(q_ref[j][t], dtype=float) - np.array(q_ref[k][t], dtype=float)
                    delta_q = q_var[j][t] - q_var[k][t]
                    slack_safe[(j, k, t)] = _add_safety_separation_socp_constraint(
                        constraints,
                        d_bar,
                        delta_q,
                        traj_params.d_safe,
                        safe_slack_penalty,
                        objective_terms,
                        f"{j}_{k}_{t}",
                    )

    # Combined objective: alpha * comm_surrogate + lambda_w * propulsion + slack_penalty
    obj_slack = cp.sum(cp.hstack(objective_terms)) if objective_terms else 0.0
    objective = cp.Minimize(
        alpha * obj_comm_surrogate
        + lambda_w * obj_propulsion
        + obj_slack
    )

    problem = cp.Problem(objective, constraints)

    return problem, q_var, slack_safe, objective.args[0]


def _rate_lower_bound_expr(
    z: cp.Expression,
    z_ref: float,
    H: float,
    B: float,
    snr: float,
) -> cp.Expression:
    """Lower bound on Shannon rate r(z) = B·ln(1 + β/z) at z using first-order Taylor.

    Args:
        z: Distance-squared variable z = H² + ||q_j - w_i||²
        z_ref: Reference value for Taylor expansion
        H: Height parameter
        B: Bandwidth (Hz)
        snr: SNR ratio β

    Returns:
        CVXPY expression: affine lower bound on rate (bps)
    """
    beta = snr

    # r(z) = (B / ln2) · ln(1 + β/z)
    # r'(z) = -(B / ln2) · β / (z(z + β))

    # At z_ref:
    r_ref = (B / np.log(2)) * np.log(1.0 + beta / z_ref)
    r_prime_ref = -(B / np.log(2)) * beta / (z_ref * (z_ref + beta))

    # First-order lower bound:
    # r(z) ≥ r(z_ref) + r'(z_ref) · (z - z_ref)
    rate_lb = r_ref + r_prime_ref * (z - z_ref)

    return rate_lb


def _propulsion_upper_bound_expr(
    v_sq: cp.Expression,
    eta_2: float,
    eta_3: float,
    v_max_sq: float,
) -> cp.Expression:
    """Upper bound on induced power φ_ind(v²) using secant method.

    φ_ind(v²) = η₂ · √(√(η₃ + v⁴/4) - v²/2)

    Evaluate secant (chord) from v²=0 to v²=v_max² and return upper bound.
    """
    # Secant upper bound: a · v_sq + b
    v_sq_0 = 0.0
    v_sq_max = v_max_sq

    phi_0 = eta_2 * np.sqrt(max(np.sqrt(eta_3) - 0, 0))
    phi_max = eta_2 * np.sqrt(max(np.sqrt(eta_3 + (v_sq_max ** 2) / 4) - v_sq_max / 2, 0))

    if v_sq_max > 1e-12:
        a_coeff = (phi_max - phi_0) / v_sq_max
        b_coeff = phi_0
    else:
        a_coeff = 0.0
        b_coeff = phi_0

    ub = a_coeff * v_sq + b_coeff
    return ub


def _propulsion_power_drag_ub(
    v_sq: cp.Expression,
    eta_4: float,
    v_max_sq: float,
) -> cp.Expression:
    """Upper bound on drag power η₄ · v³ = η₄ · (v²)^(3/2) using secant.
    """
    v_sq_0 = 0.0
    v_sq_max = v_max_sq

    power_0 = eta_4 * (v_sq_0 ** 1.5)  # = 0
    power_max = eta_4 * (v_sq_max ** 1.5)

    if v_sq_max > 1e-12:
        a_coeff = power_max / v_sq_max
        b_coeff = 0.0
    else:
        a_coeff = 0.0
        b_coeff = 0.0

    ub = a_coeff * v_sq + b_coeff
    return ub


def _evaluate_true_objective(
    scenario: EdgeUavScenario,
    q: Trajectory2D,
    traj_params: TrajectoryOptParams,
    params: PrecomputeParams,
    active_offloads: list[tuple[int, int, int]],
    alpha: float = 1.0,
    lambda_w: float = 1.0,
) -> tuple[float, float, float]:
    """计算评估真实客观的 L2b 目标: alpha*comm_delay + lambda_w*prop_energy。

    参数:
        scenario: EdgeUavScenario 对象
        q: 轨迹数据字典 dict[j][t] = (x, y)
        traj_params: 参数字典
        params: 预置定标参数
        active_offloads: 活跃任务元组集
        alpha: 通讯目标权重
        lambda_w: 耗能目标权重

    返回:
        (total_obj, total_comm_delay, total_prop_energy)
        where total_obj = alpha * total_comm_delay + lambda_w * total_prop_energy
    """
    delta = float(scenario.meta.get('delta', 0.5))
    tasks = scenario.tasks

    # Propulsion energy
    per_uav_energy = total_flight_energy(
        q,
        delta,
        eta_1=traj_params.eta_1,
        eta_2=traj_params.eta_2,
        eta_3=traj_params.eta_3,
        eta_4=traj_params.eta_4,
        v_tip=traj_params.v_tip,
        include_terminal_hover=False,
    )
    E_prop = sum(per_uav_energy.values())

    # Communication parameters
    H       = float(scenario.meta.get('H',     100.0))
    B_up    = float(scenario.meta.get('B_up',    2e7))
    B_down  = float(scenario.meta.get('B_down',  2e7))
    P_i     = float(scenario.meta.get('P_i',     0.5))
    P_j     = float(scenario.meta.get('P_j',     1.0))
    rho_0   = float(scenario.meta.get('rho_0',  1e-5))
    N_0     = float(scenario.meta.get('N_0',   1e-10))
    beta      = P_i * rho_0 / N_0
    beta_down = P_j * rho_0 / N_0

    # Communication delay (true, not surrogate)
    total_comm = 0.0
    for j, i, t in active_offloads:
        w_i = np.array(tasks[i].pos, dtype=float)
        q_jt = np.array(q[j][t], dtype=float)
        z = float(np.sum((q_jt - w_i) ** 2)) + H ** 2
        z = max(z, 1e-12)

        r_up   = max(float((B_up   / np.log(2)) * np.log(1 + beta      / z)), 1e-12)
        r_down = max(float((B_down / np.log(2)) * np.log(1 + beta_down / z)), 1e-12)

        total_comm += float(tasks[i].D_l) / r_up + float(tasks[i].D_r) / r_down

    total_obj = alpha * total_comm + lambda_w * E_prop
    return float(total_obj), float(total_comm), float(E_prop)
