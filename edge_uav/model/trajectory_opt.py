"""Block D trajectory optimization — Level 2b SCA + CVXPY SOCP.

Given fixed offloading decisions x and resource allocation f_edge, solve for
optimal UAV trajectories q that minimize propulsion energy subject to:
  - Map boundary, initial/final position, and velocity constraints (convex)
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
        objective_value: True total propulsion energy (J) — evaluated post-SCA.
        per_uav_energy: Energy per UAV (J), dict[j] -> float
        sca_iterations: Number of SCA iterations performed (1 <= k <= max_sca_iter)
        converged: True if relative gap <= eps_sca, False if max_sca_iter reached
        solver_status: Final CVXPY solver status (e.g., 'optimal', 'optimal_inaccurate')
        max_safe_slack: Largest safety constraint slack at final iteration (m²)
                       > 0 indicates initial trajectory was unsafe
        diagnostics: dict with keys:
            - 'true_objective_history': list[float] — true energy per SCA iteration
            - 'surrogate_history': list[float] — CVXPY objective values
            - 'solver_status_history': list[str]
            - 'max_slack_history': list[float]
            - 'sca_times': list[float] — wall time per iteration (s)
    """
    q: Trajectory2D
    objective_value: float
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
) -> TrajectoryResult:
    """Solve trajectory optimization via SCA + SOCP.

    Args:
        scenario: EdgeUavScenario with map, UAVs, tasks, and meta parameters
        offloading_decisions: dict (not used directly here, kept for API consistency)
        f_fixed: dict[j][i][t] -> float, edge CPU frequency (Hz) from Step 2
        q_init: Initial trajectory dict[j][t] = (x, y)
        params: PrecomputeParams (distances, rates, time slot duration δ)
        traj_params: TrajectoryOptParams (η_1..η_4, v_tip, v_max, d_safe)
        max_sca_iter: Max SCA iterations (default 100)
        eps_sca: Relative convergence tolerance (default 1e-3)
        safe_slack_penalty: Penalty weight for safe distance slack (default 1e3)
        solver_fallback: Solvers to try in order (default CLARABEL → ECOS → SCS)

    Returns:
        TrajectoryResult with optimized trajectory, energy, and diagnostics.

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
    active_offloads = _extract_active_offloads(scenario, f_fixed)

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
                active_offloads, safe_slack_penalty
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
        obj_true = _evaluate_true_objective(
            scenario, q_new_dict, traj_params, params
        )

        # Check max safe slack
        max_slack = float(np.max([sv.value for sv in slack_safe.values()])) \
                    if slack_safe else 0.0

        # Record history
        obj_history.append(obj_true)
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
        per_uav_energy=per_uav_energy,
        sca_iterations=len(obj_history),
        converged=converged,
        solver_status=solver_status_history[-1] if solver_status_history else "unknown",
        max_safe_slack=slack_history[-1] if slack_history else 0.0,
        diagnostics={
            "true_objective_history": obj_history,
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

    # Check safe distance (only interim slots, not endpoints)
    if traj_params.d_safe > 0:
        for j in scenario.uavs:
            for k in scenario.uavs:
                if j >= k:
                    continue
                q_j = q_init[j]
                q_k = q_init[k]
                # Check only 0 < t < T-1
                for t in range(1, T - 1):
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
    f_fixed: dict,
) -> list[tuple[int, int, int]]:
    """Extract (j, i, t) triples where task i is offloaded to UAV j at slot t.

    Returns:
        List of (j, i, t) tuples for which f_edge[j][i][t] is assigned.
    """
    active = []
    for j in f_fixed:
        for i in f_fixed[j]:
            for t in f_fixed[j][i]:
                active.append((j, i, t))
    return active


def _add_communication_delay_socp_constraint(
    constraints: list,
    pos_diff: cp.Expression,
    H: float,
    rate_safe: cp.Expression,
    tau_comm_budget: float,
    *,
    name_suffix: str = "",
) -> None:
    """Add DCP-compliant SOCP communication delay constraints.

    Rewrite
        2 * sqrt(H^2 + ||pos_diff||_2^2) / rate_safe <= tau_comm_budget
    into the SOCP-friendly form
        ||[H, pos_diff[0], pos_diff[1]]||_2 <= s
        2 * s <= tau_comm_budget * rate_safe

    The helper appends constraints directly to the mutable ``constraints`` list
    because the CVXPY Problem object is assembled only after all constraints
    have been collected.
    """
    s_var = cp.Variable(
        nonneg=True,
        name=f"comm_dist_aux_{name_suffix}" if name_suffix else None,
    )

    # SOCP distance epigraph:
    # sqrt(H^2 + ||pos_diff||_2^2) = ||[H, dx, dy]||_2 <= s
    dist_vec = cp.hstack([H, pos_diff[0], pos_diff[1]])
    constraints.append(cp.norm(dist_vec, 2) <= s_var)

    # Keep the rate lower bound strictly positive so the delay surrogate
    # remains well-defined in the SOCP reformulation.
    constraints.append(rate_safe >= 1e-12)

    # Delay inequality:
    # 2 * distance / rate <= tau  <=>  2 * distance <= tau * rate.
    constraints.append(2.0 * s_var <= tau_comm_budget * rate_safe)


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

    # (4e) Communication delay constraint
    # Get communication parameters from meta or use defaults
    H = float(scenario.meta.get('H', 100.0))  # Height (m)
    B_up = float(scenario.meta.get('B_up', 1e6))  # Uplink bandwidth (Hz)
    SNR_default = 100.0  # Default SNR ratio

    for j, i, t in active_offloads:
        tau_i = tasks[i].tau
        F_i = tasks[i].F

        f_edge_jit = f_fixed[j][i][t]
        tau_comm_budget = tau_i - F_i / f_edge_jit

        # Communication delay ≤ τ_comm_budget
        # Delay = 2√(H² + ||q_j - w_i||²) / r(H² + ||q_j - w_i||²)
        # Use lower bound on rate + inv_pos

        # Position of central base station
        w_i = scenario.meta.get('depot_pos', (x_max / 2, y_max / 2))
        if isinstance(w_i, (list, tuple)):
            w_i = tuple(w_i)
        else:
            w_i = (x_max / 2, y_max / 2)

        # Horizontal position difference from UAV j to base station for task i
        pos_diff = q_var[j][t] - np.array(w_i, dtype=float)

        # Rate lower bound (using pre-computed reference from q_ref)
        z_ref = np.sum(
            (np.array(q_ref[j][t], dtype=float) - np.array(w_i, dtype=float)) ** 2
        ) + H ** 2
        z_ref = max(z_ref, 1e-12)

        rate_safe = _rate_lower_bound_expr(
            cp.sum_squares(pos_diff) + H ** 2,
            z_ref,
            H,
            B_up,
            SNR_default,
        )

        # Rewrite the communication delay constraint in SOCP form to avoid
        # the non-DCP product sqrt(z) * inv_pos(rate_safe).
        _add_communication_delay_socp_constraint(
            constraints, pos_diff, H, rate_safe, tau_comm_budget,
            name_suffix=f"{j}_{i}_{t}"
        )

    # (4f) Safe distance constraint (SCA linearization, only 0 < t < T-1)
    if traj_params.d_safe > 0:
        for j in uavs:
            for k in uavs:
                if j >= k:
                    continue
                for t in range(1, T - 1):  # interim only
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

    # Objective: minimize propulsion energy + safe distance slack penalty
    obj_slack = cp.sum(cp.hstack(objective_terms)) if objective_terms else 0.0
    objective = cp.Minimize(obj_propulsion + obj_slack)

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
        CVXPY expression upper bound for 1/z (i.e., lower bound on rate)
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
) -> float:
    """Evaluate true propulsion energy using propulsion.total_flight_energy().

    Args:
        scenario: EdgeUavScenario
        q: Optimized trajectory dict[j][t] = (x, y)
        traj_params: TrajectoryOptParams
        params: PrecomputeParams

    Returns:
        Total propulsion energy (J) summed over all UAVs.
    """
    delta = float(scenario.meta.get('delta', 0.5))
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
    total_energy = sum(per_uav_energy.values())

    return total_energy
