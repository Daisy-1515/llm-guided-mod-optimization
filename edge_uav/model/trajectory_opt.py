"""Block D trajectory optimization — Level 2b SCA + CVXPY SOCP.

Given fixed offloading decisions x and resource allocation f_edge, solve for
optimal UAV trajectories q that jointly minimize communication delay + propulsion
energy subject to:
  - Map boundary, initial/final position, and velocity constraints (convex)
  - Endpoint reachability constraints (4e)
  - Communication delay constraints (convex via successive approximation)
  - Safe separation constraints (non-convex, linearized via SCA with slack)

Uses CVXPY with CLARABEL/ECOS/SCS solver fallback for robustness.
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
    """Trajectory optimization parameters — Step 3 specific.

    Attributes:
        eta_1, eta_2, eta_3, eta_4: Propulsion model coefficients (W, m, s, ...)
        v_tip: Rotor tip speed (m/s)
        v_max: Maximum UAV velocity (m/s)
        d_safe: Safe separation distance (m). If <= 0, safe distance check is skipped.
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
    """Trajectory optimization output.

    Attributes:
        q: Optimized trajectory dict[j][t] = (x, y) (m)
        objective_value: Complete L2b cost = alpha*total_comm_delay + lambda_w*total_prop_energy
        total_comm_delay: Total communication delay Σ D_l/r_up + D_r/r_down (s)
        total_prop_energy: Total propulsion energy Σ_j E_prop_j (J)
        per_uav_energy: Propulsion energy per UAV (J), dict[j] -> float
        sca_iterations: Number of SCA iterations performed (1 <= k <= max_sca_iter)
        converged: True if relative gap <= eps_sca, False if max_sca_iter reached
        solver_status: Final CVXPY solver status (e.g., 'optimal', 'optimal_inaccurate')
        max_safe_slack: Largest safety constraint slack at final iteration (m²)
                       > 0 indicates initial trajectory was unsafe
        diagnostics: dict with keys:
            - 'true_objective_history': list[float] — true L2b cost per SCA iteration
            - 'total_comm_delay_history': list[float] — comm delay per iteration (s)
            - 'total_prop_energy_history': list[float] — prop energy per iteration (J)
            - 'surrogate_history': list[float] — CVXPY objective values
            - 'solver_status_history': list[str]
            - 'max_slack_history': list[float]
            - 'sca_times': list[float] — wall time per iteration (s)
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
    safe_slack_penalty: float = 1e3,
    solver_fallback: tuple[str, ...] = ("CLARABEL", "ECOS", "SCS"),
    alpha: float = 1.0,
    lambda_w: float = 1.0,
) -> TrajectoryResult:
    """Solve trajectory optimization via SCA + SOCP.

    Args:
        scenario: EdgeUavScenario with map, UAVs, tasks, and meta parameters
        offloading_decisions: dict {t: {"local": [i...], "offload": {j: [i...]}}}
                             If non-empty, used as authority for active offload set.
                             If empty dict {}, falls back to f_fixed traversal.
        f_fixed: dict[j][i][t] -> float, edge CPU frequency (Hz) from Step 2
        q_init: Initial trajectory dict[j][t] = (x, y)
        params: PrecomputeParams (distances, rates, time slot duration δ)
        traj_params: TrajectoryOptParams (η_1..η_4, v_tip, v_max, d_safe)
        max_sca_iter: Max SCA iterations (default 100)
        eps_sca: Relative convergence tolerance (default 1e-3)
        safe_slack_penalty: Penalty weight for safe distance slack (default 1e3)
        solver_fallback: Solvers to try in order (default CLARABEL → ECOS → SCS)
        alpha: Communication delay objective weight (default 1.0)
        lambda_w: Propulsion energy objective weight (default 1.0)

    Returns:
        TrajectoryResult with optimized trajectory, combined L2b cost, and diagnostics.

    Raises:
        ValueError: If input is infeasible (endpoint distance > capacity, missing f_edge, etc.)
    """
    # ========== Step 0: Input validation ==========
    _validate_input_basic(scenario, q_init, traj_params, params)

    # Extract T and map dimensions from meta/scenario
    T = len(scenario.time_slots)
    x_max = float(scenario.meta.get('x_max', 1000.0))
    y_max = float(scenario.meta.get('y_max', 1000.0))
    delta = float(scenario.meta.get('delta', 0.5))

    # Quick feasibility check: endpoint distance vs available time
    for j in scenario.uavs:
        pos_j = scenario.uavs[j].pos
        pos_final_j = scenario.uavs[j].pos_final
        dist_max = np.linalg.norm(np.array(pos_final_j) - np.array(pos_j))
        max_dist_achievable = (T - 1) * traj_params.v_max * delta
        if dist_max > max_dist_achievable + 1e-9:
            raise ValueError(
                f"UAV {j}: endpoint distance {dist_max:.2f}m exceeds capacity "
                f"{max_dist_achievable:.2f}m at v_max={traj_params.v_max} m/s, "
                f"T={T}, delta={delta}s"
            )

    # Extract active offloads for communication constraints
    active_offloads = _extract_active_offloads(scenario, offloading_decisions, f_fixed)

    # Pre-check communication feasibility: ensure τ_comm > 0 for all active pairs
    for j, i, t in active_offloads:
        tau_i = scenario.tasks[i].tau
        F_i = scenario.tasks[i].F
        f_edge_jit = f_fixed.get(j, {}).get(i, {}).get(t)
        if f_edge_jit is None:
            raise ValueError(
                f"Missing f_fixed[{j}][{i}][{t}] for active offload (j={j}, i={i}, t={t})"
            )
        tau_comm = tau_i - F_i / f_edge_jit
        if tau_comm <= 0:
            raise ValueError(
                f"Infeasible communication budget for task {i} on UAV {j} at slot {t}: "
                f"tau_comm={tau_comm:.2e}s (τ_i={tau_i}s, F_i={F_i}, f_edge={f_edge_jit:.2e})"
            )

    # Validate initial trajectory: check boundary, endpoints, speed, optionally comm
    is_safe_init, safety_msg = _validate_initial_trajectory(
        q_init, scenario, traj_params, params, allow_unsafe=True
    )
    if not is_safe_init:
        print(f"[WARNING] Initial trajectory unsafe: {safety_msg}. Will use slack to handle.")

    # ========== Step 1: SCA loop ==========
    q_ref = q_init
    obj_history = []
    comm_history = []
    prop_history = []
    surrogate_history = []
    solver_status_history = []
    slack_history = []
    sca_times = []

    for sca_k in range(max_sca_iter):
        iter_start = time.time()

        # Build SOCP subproblem at reference point q_ref
        try:
            problem, q_var, slack_safe, obj_surrogate = _build_sca_subproblem(
                scenario, q_ref, f_fixed, params, traj_params,
                active_offloads, safe_slack_penalty,
                alpha=alpha, lambda_w=lambda_w,
            )
        except Exception as e:
            raise ValueError(f"Failed to build SOCP subproblem at SCA iter {sca_k}: {e}")

        # Solve with fallback
        solver_status = None
        for solver_name in solver_fallback:
            try:
                problem.solve(solver=getattr(cp, solver_name), verbose=False)
                solver_status = problem.status
                if problem.status in ["optimal", "optimal_inaccurate"]:
                    break
            except Exception:
                # Solver not available or failed; try next
                continue

        if solver_status not in ["optimal", "optimal_inaccurate"]:
            raise ValueError(
                f"All solvers failed at SCA iter {sca_k}. Tried: {solver_fallback}. "
                f"Last status: {solver_status}"
            )

        # Extract solution
        q_new_dict = {j: {} for j in scenario.uavs}
        for j in scenario.uavs:
            for t in range(T):
                x_val = q_var[j][t][0].value
                y_val = q_var[j][t][1].value
                if x_val is None or y_val is None:
                    raise ValueError(f"Solver failed to assign q[{j}][{t}]")
                q_new_dict[j][t] = (float(x_val), float(y_val))

        # Evaluate true objective at q_new
        obj_true, comm_true, prop_true = _evaluate_true_objective(
            scenario, q_new_dict, traj_params, params,
            active_offloads, alpha=alpha, lambda_w=lambda_w,
        )

        # Check max safe slack
        max_slack = float(np.max([sv.value for sv in slack_safe.values()])) \
                    if slack_safe else 0.0

        # Record history
        obj_history.append(obj_true)
        comm_history.append(comm_true)
        prop_history.append(prop_true)
        surrogate_history.append(problem.value if problem.value is not None else np.inf)
        solver_status_history.append(solver_status)
        slack_history.append(max_slack)
        sca_times.append(time.time() - iter_start)

        # Check convergence
        converged = False
        if sca_k > 0:
            rel_gap = abs(obj_history[sca_k] - obj_history[sca_k - 1]) / (
                abs(obj_history[sca_k - 1]) + 1e-12
            )
            converged = rel_gap <= eps_sca

        # Update reference and possibly break
        q_ref = q_new_dict
        if converged or sca_k == max_sca_iter - 1:
            break

    # ========== Step 2: Compute per-UAV energy ==========
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

    # ========== Step 3: Assemble result ==========
    result = TrajectoryResult(
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
        },
    )

    return result


# ============================================================================
# Auxiliary Functions
# ============================================================================

def _validate_input_basic(
    scenario: EdgeUavScenario,
    q_init: Trajectory2D,
    traj_params: TrajectoryOptParams,
    params: PrecomputeParams,
) -> None:
    """Quick sanity checks on scenario and parameters."""
    if not scenario.uavs or not scenario.tasks:
        raise ValueError("Scenario has no UAVs or tasks")
    if traj_params.v_max <= 0:
        raise ValueError(f"v_max must be > 0, got {traj_params.v_max}")
    delta = float(scenario.meta.get('delta', 0.5))
    if delta <= 0:
        raise ValueError(f"delta must be > 0, got {delta}")
    if len(q_init) != len(scenario.uavs):
        raise ValueError(
            f"Initial trajectory has {len(q_init)} UAVs but scenario has {len(scenario.uavs)}"
        )


def _validate_initial_trajectory(
    q_init: Trajectory2D,
    scenario: EdgeUavScenario,
    traj_params: TrajectoryOptParams,
    params: PrecomputeParams,
    allow_unsafe: bool = True,
) -> tuple[bool, str]:
    """Validate initial trajectory for boundary, endpoints, speed, safe distance.

    Returns:
        (is_safe, reason) — True if all checks pass; False + reason string otherwise.
    """
    T = len(scenario.time_slots)
    x_max = float(scenario.meta.get('x_max', 1000.0))
    y_max = float(scenario.meta.get('y_max', 1000.0))
    delta = float(scenario.meta.get('delta', 0.5))

    for j in scenario.uavs:
        if j not in q_init:
            return False, f"UAV {j} missing from q_init"

        q_j = q_init[j]
        if len(q_j) != T:
            return False, f"UAV {j} trajectory has {len(q_j)} slots but T={T}"

        # Check boundary
        for t in range(T):
            x, y = q_j[t]
            if not (0 <= x <= x_max) or not (0 <= y <= y_max):
                return False, f"UAV {j} at t={t}: position ({x:.2f}, {y:.2f}) outside map [0,{x_max}]×[0,{y_max}]"

        # Check initial and final position
        pos_j = scenario.uavs[j].pos
        pos_final_j = scenario.uavs[j].pos_final
        if not np.allclose(q_j[0], pos_j, atol=1e-6):
            return False, f"UAV {j}: q[{j}][0]={q_j[0]} != pos={pos_j}"
        if not np.allclose(q_j[T - 1], pos_final_j, atol=1e-6):
            return False, f"UAV {j}: q[{j}][T-1]={q_j[T-1]} != pos_final={pos_final_j}"

        # Check speed constraint
        for t in range(T - 1):
            delta_q = np.array(q_j[t + 1]) - np.array(q_j[t])
            dist = np.linalg.norm(delta_q)
            max_dist = traj_params.v_max * delta
            if dist > max_dist + 1e-9:
                return False, f"UAV {j} at t={t}: ||Δq||={dist:.2f}m > v_max·δ={max_dist:.2f}m"

    # Check safe distance — endpoint exemption (design assumption):
    # All UAVs share a common depot (takeoff and landing point), so t=0 and t=T-1
    # are intentionally exempt from the safe-distance check. Enforcing d_safe at
    # shared endpoints would make the problem artificially infeasible.
    # Effective domain: 0 < t < T-1 (interim slots only).
    if traj_params.d_safe > 0:
        for j in scenario.uavs:
            for k in scenario.uavs:
                if j >= k:
                    continue
                q_j = q_init[j]
                q_k = q_init[k]
                for t in range(1, T - 1):  # interim slots only; endpoints exempt
                    delta_q = np.array(q_j[t]) - np.array(q_k[t])
                    dist = np.linalg.norm(delta_q)
                    if dist < traj_params.d_safe - 1e-9:
                        return False, (
                            f"UAV {j},{k} at t={t}: ||q_j - q_k||={dist:.2f}m "
                            f"< d_safe={traj_params.d_safe}m"
                        )

    return True, "OK"


def _extract_active_offloads(
    scenario: EdgeUavScenario,
    offloading_decisions: dict,
    f_fixed: dict,
) -> list[tuple[int, int, int]]:
    """Extract (j, i, t) triples where task i is offloaded to UAV j at slot t.

    If offloading_decisions is non-empty, uses it as the authority for the active
    offload set and validates consistency with f_fixed. If offloading_decisions is
    an empty dict {}, falls back to traversing f_fixed directly.

    Args:
        scenario: EdgeUavScenario (unused, kept for API)
        offloading_decisions: {t: {"local": [i...], "offload": {j: [i...]}}}
                             Empty dict {} triggers fallback to f_fixed.
        f_fixed: dict[j][i][t] -> float, edge CPU frequency from Step 2

    Returns:
        List of (j, i, t) tuples for active offloads.

    Raises:
        ValueError: If offloading_decisions and f_fixed are inconsistent (when
                   offloading_decisions is non-empty).
    """
    # Fallback: empty offloading_decisions → use f_fixed as authority
    if not offloading_decisions:
        active = []
        for j in f_fixed:
            for i in f_fixed[j]:
                for t in f_fixed[j][i]:
                    if f_fixed[j][i][t] > 0:
                        active.append((j, i, t))
        return active

    # Build declared set from offloading_decisions
    declared: set[tuple[int, int, int]] = set()
    for t, t_dict in offloading_decisions.items():
        for j, task_list in t_dict.get("offload", {}).items():
            for i in task_list:
                declared.add((j, i, t))

    # Build f_fixed positive set
    f_fixed_positive: set[tuple[int, int, int]] = set()
    for j in f_fixed:
        for i in f_fixed[j]:
            for t in f_fixed[j][i]:
                if f_fixed[j][i][t] > 0:
                    f_fixed_positive.add((j, i, t))

    # Validate: every declared (j,i,t) must have f_fixed > 0
    missing_in_f_fixed = declared - f_fixed_positive
    if missing_in_f_fixed:
        raise ValueError(
            f"offloading_decisions declares offloads but f_fixed has no positive entry: "
            f"{sorted(missing_in_f_fixed)}"
        )

    # Validate: no residual allocation in f_fixed not covered by offloading_decisions
    residual = f_fixed_positive - declared
    if residual:
        raise ValueError(
            f"f_fixed has positive entries not declared in offloading_decisions (residual): "
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
    """Add DCP-compliant communication delay constraint.

    Constraint: (D_l + D_r) / rate_safe <= tau_comm_budget
    Equivalent linear form (rate_safe is affine from Taylor LB):
        payload_bits <= tau_comm_budget * rate_safe

    Args:
        constraints: Mutable list to append constraints to.
        pos_diff: Unused after refactor (kept for call-site compatibility).
        H: Unused after refactor (kept for call-site compatibility).
        rate_safe: Affine lower bound on Shannon rate (bps).
        tau_comm_budget: Communication time budget (s).
        payload_bits: Total payload D_l + D_r (bits).
        name_suffix: For debugging/identification.
    """
    # Keep the rate lower bound strictly positive as a safety guard.
    constraints.append(rate_safe >= 1e-12)

    # Direct linear constraint: payload / rate <= tau
    # <=> payload <= tau * rate  (DCP-compliant: affine <= affine)
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
    """Add the SCA safe-separation constraint with explicit slack penalty.

    This preserves the current SCA linearization
        2 * d_bar^T * delta_q - ||d_bar||^2 + delta >= d_safe^2
    while standardizing slack creation and objective penalization so the model
    aligns with the Phase 6 Step 3 plan form rho_k * sum(delta_{jk}^t).

    Note:
        This remains an affine SCA constraint inside the SOCP-compatible
        subproblem; it is not a new SOC reformulation.
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
    """Build CVXPY SOCP subproblem at reference point q_ref.

    Returns:
        (problem, q_var, slack_safe_dict, obj_expr) where:
        - problem: CVXPY Problem ready to solve()
        - q_var: dict[j][t][dim] — CVXPY Variable for position
        - slack_safe_dict: dict[(j,k,t)] → slack variable for safe distance
        - obj_expr: objective expression (CVXPY)
    """
    T = len(scenario.time_slots)
    x_max = float(scenario.meta.get('x_max', 1000.0))
    y_max = float(scenario.meta.get('y_max', 1000.0))
    delta = float(scenario.meta.get('delta', 0.5))
    uavs = scenario.uavs
    tasks = scenario.tasks

    # Decision variables
    q_var = {j: {t: cp.Variable(2) for t in range(T)} for j in uavs}
    speed_sq = {j: {t: cp.Variable() for t in range(T - 1)} for j in uavs}
    slack_safe = {}
    objective_terms = []

    constraints = []
    obj_propulsion = 0.0

    # ===== Constraints (4a)-(4f) =====

    # (4a) Map boundary
    for j in uavs:
        for t in range(T):
            constraints.append(q_var[j][t][0] >= 0)
            constraints.append(q_var[j][t][0] <= x_max)
            constraints.append(q_var[j][t][1] >= 0)
            constraints.append(q_var[j][t][1] <= y_max)

    # (4b) Initial position
    for j in uavs:
        pos_j = uavs[j].pos
        constraints.append(q_var[j][0][0] == pos_j[0])
        constraints.append(q_var[j][0][1] == pos_j[1])

    # (4c) Final position
    for j in uavs:
        pos_final_j = uavs[j].pos_final
        constraints.append(q_var[j][T - 1][0] == pos_final_j[0])
        constraints.append(q_var[j][T - 1][1] == pos_final_j[1])

    # (4d) Velocity constraint (SOC)
    for j in uavs:
        for t in range(T - 1):
            delta_q = q_var[j][t + 1] - q_var[j][t]
            # ||Δq||² = Δx² + Δy²
            norm_sq = cp.sum_squares(delta_q)
            # ||Δq|| ≤ v_max · δ
            max_dist = traj_params.v_max * delta
            constraints.append(norm_sq <= (max_dist ** 2))
            # DCP-compliant epigraph link:
            # speed_sq >= ||delta_q||^2 / delta^2
            # <=> ||delta_q||^2 <= delta^2 * speed_sq
            constraints.append(norm_sq <= (delta ** 2) * speed_sq[j][t])
            # speed_sq[j][t] >= 0
            constraints.append(speed_sq[j][t] >= 0)
            # Keep the epigraph variable physically bounded as v^2 <= v_max^2.
            # Without this upper bound, the secant-based propulsion surrogate
            # can become numerically unbounded for some parameter regimes.
            constraints.append(speed_sq[j][t] <= traj_params.v_max ** 2)

    # (4e) Endpoint reachability: ||q_j[t] - pos_final||² <= (v_max*(T-1-t)*delta)²
    for j in uavs:
        pos_final_j = np.array(uavs[j].pos_final, dtype=float)
        for t in range(T - 1):  # t=T-1 already covered by (4c), skip
            remaining = T - 1 - t
            max_dist = traj_params.v_max * remaining * delta
            diff = q_var[j][t] - pos_final_j
            constraints.append(cp.sum_squares(diff) <= max_dist ** 2)

    # Propulsion energy objective (from speed_sq)
    for j in uavs:
        for t in range(T - 1):
            # Power at this slot: P(v²) = η₁(1 + 3v²/v_tip²) + φ_ind(v²) + η₄v³
            # Using convex upper bound via secant method on [0, v_max²]
            v_sq = speed_sq[j][t]

            # Term 1: η₁(1 + 3v²/v_tip²) — linear in v²
            term1 = traj_params.eta_1 * (1.0 + 3.0 * v_sq / (traj_params.v_tip ** 2))

            # Term 2: φ_ind(v²) — upper bound via secant on interval [0, v_max²]
            # φ_ind(v²) = η₂ · √(√(η₃ + v⁴/4) - v²/2)
            term2_ub = _propulsion_upper_bound_expr(
                v_sq, traj_params.eta_2, traj_params.eta_3,
                v_max_sq=traj_params.v_max ** 2
            )

            # Term 3: η₄(v²)^(3/2) — upper bound via secant
            term3_ub = _propulsion_power_drag_ub(
                v_sq, traj_params.eta_4,
                v_max_sq=traj_params.v_max ** 2
            )

            # Power upper bound
            power_ub = term1 + term2_ub + term3_ub

            # Energy in this slot: Power × δ
            energy_contrib = power_ub * delta
            obj_propulsion += energy_contrib

    # Communication parameters from meta
    H       = float(scenario.meta.get('H',     100.0))
    B_up    = float(scenario.meta.get('B_up',    2e7))
    B_down  = float(scenario.meta.get('B_down',  2e7))
    P_i     = float(scenario.meta.get('P_i',     0.5))
    P_j     = float(scenario.meta.get('P_j',     1.0))
    rho_0   = float(scenario.meta.get('rho_0',  1e-5))
    N_0     = float(scenario.meta.get('N_0',   1e-10))
    beta      = P_i * rho_0 / N_0   # uplink SNR coefficient
    beta_down = P_j * rho_0 / N_0   # downlink SNR coefficient

    # Communication surrogate objective + deadline constraints
    obj_comm_surrogate = cp.Constant(0)

    for j, i, t in active_offloads:
        tau_i = tasks[i].tau
        F_i = tasks[i].F
        f_edge_jit = f_fixed[j][i][t]
        tau_comm_budget = tau_i - F_i / f_edge_jit

        # Position of task device on the ground
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
                    # Linearization at reference point
                    # 2 · d_bar^T · (q_j - q_k) - ||d_bar||² + slack ≥ d_safe²
                    d_bar = np.array(q_ref[j][t], dtype=float) - np.array(q_ref[k][t], dtype=float)

                    delta_q = q_var[j][t] - q_var[k][t]
                    slack_safe[(j, k, t)] = _add_safety_separation_socp_constraint(
                        constraints=constraints,
                        d_bar=d_bar,
                        delta_q=delta_q,
                        d_safe=traj_params.d_safe,
                        slack_penalty=safe_slack_penalty,
                        objective_terms=objective_terms,
                        name_suffix=f"{j}_{k}_{t}",
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
    """Evaluate true L2b objective: alpha*comm_delay + lambda_w*prop_energy.

    Args:
        scenario: EdgeUavScenario
        q: Optimized trajectory dict[j][t] = (x, y)
        traj_params: TrajectoryOptParams
        params: PrecomputeParams
        active_offloads: list of (j, i, t) active offload triples
        alpha: Communication delay weight
        lambda_w: Propulsion energy weight

    Returns:
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
