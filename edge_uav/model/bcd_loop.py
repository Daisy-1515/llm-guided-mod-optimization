"""Block A+B+D integration — BCD (Block Coordinate Descent) main loop for Phase⑥ Step4.

Implements the three-layer iterative optimization framework:
  Level 1 (Offloading): Task offloading decisions (binary)
  Level 2a (Resource Allocation): CPU frequency optimization
  Level 2b (Trajectory Optimization): UAV trajectory via SCA

The BCD loop alternates between these three blocks until convergence.

Design document: plans/phase6-step3-socp-fix-plan.md (overall Phase⑥ structure)
"""

from __future__ import annotations

import logging
import math
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from config.config import configPara
from edge_uav.data import EdgeUavScenario
from edge_uav.model.offloading import OffloadingModel
from edge_uav.model.precompute import (
    InitPolicy,
    Level2Snapshot,
    PrecomputeParams,
    PrecomputeResult,
    Scalar2D,
    Scalar3D,
    Trajectory2D,
    make_initial_level2_snapshot,
    precompute_offloading_inputs,
)
from edge_uav.model.resource_alloc import (
    ResourceAllocResult,
    solve_resource_allocation,
)
from edge_uav.model.trajectory_opt import (
    TrajectoryOptParams,
    TrajectoryResult,
    solve_trajectory_sca,
)

logger = logging.getLogger(__name__)

__all__ = [
    "clone_snapshot",
    "BCDResult",
    "validate_offloading_outputs",
    "check_trajectory_monotonicity",
    "adapt_f_edge_for_snapshot",
    "validate_resource_allocation_feasibility",
    "run_bcd_loop",
]


# =====================================================================
# Snippet 1: Deep copy for Level2Snapshot
# =====================================================================


def clone_snapshot(
    snapshot: Level2Snapshot,
    source: str = "unknown",
) -> Level2Snapshot:
    """Deep copy Level2Snapshot to protect nested dicts from in-place mutations.

    Because Level2Snapshot is frozen=True (immutable), we must create a new
    instance with deeply copied field values. This prevents BCD iterations from
    polluting each other's state.

    Args:
        snapshot: Original Level2Snapshot to clone
        source: Diagnostic tag (e.g., "initialization", "iteration_3", "rollback_1")
                for tracking snapshot origin in logs/debugging

    Returns:
        New Level2Snapshot with deeply copied fields and updated source tag

    Raises:
        TypeError: If snapshot is not a Level2Snapshot
    """
    if not isinstance(snapshot, Level2Snapshot):
        raise TypeError(
            f"clone_snapshot expects Level2Snapshot, got {type(snapshot).__name__}"
        )

    return Level2Snapshot(
        q=deepcopy(snapshot.q),  # [j][t] -> (x, y)
        f_edge=deepcopy(snapshot.f_edge),  # [j][i][t] -> Hz
        f_local_override=(
            deepcopy(snapshot.f_local_override)
            if snapshot.f_local_override is not None
            else None
        ),  # [i][t] -> Hz (optional)
        source=source,  # Diagnostic tag
    )


# =====================================================================
# BCDResult data class
# =====================================================================


@dataclass(frozen=True)
class BCDResult:
    """BCD loop output snapshot at convergence (or max iterations reached).

    Attributes:
        snapshot: Optimal Level2Snapshot (q, f_edge, f_local_override) found
        offloading_outputs: Final offloading decisions dict from Level 1 solver.
                            Format: {t: {"local": [i...], "offload": {j: [i...]}}}
        total_cost: True system cost at convergence (scalar value in units matching config)
        bcd_iterations: Actual number of BCD outer loop iterations performed (>= 1)
        converged: True if relative cost change < eps_bcd, False if max_bcd_iter reached
        cost_history: List of best_cost at each iteration [cost_0, cost_1, ..., cost_k]
        solution_details: Dict with diagnostic info:
            - 'sca_converged': bool — did trajectory SCA converge?
            - 'max_safe_slack': float — largest safety constraint slack (m²)
            - 'resource_binding_slots': int — slots with binding capacity
            - 'total_rollbacks': int — how many times cost rollback triggered
            - 'final_sca_iterations': int — SCA iterations on final solution
    """

    snapshot: Level2Snapshot
    offloading_outputs: dict
    total_cost: float
    bcd_iterations: int
    converged: bool
    cost_history: List[float]
    solution_details: Dict[str, Any] = field(default_factory=dict)
    offloading_error_message: str = ""
    used_default_obj: bool = True
    objective_acceptance_status: str = "default_obj"


# =====================================================================
# Snippet 2-5: Validation and adaptation functions
# =====================================================================


def validate_offloading_outputs(
    offloading_outputs: dict,
    scenario: EdgeUavScenario,
) -> dict:
    """Validate offloading decisions from Level 1 solver.

    Checks that:
      1. Every task i is assigned at time t (either local or offloaded)
      2. No task is assigned to multiple UAVs or both local+offload
      3. Offloading is only to UAVs in scenario.uavs

    Args:
        offloading_outputs: Format {t: {"local": [i...], "offload": {j: [i...]}}}
        scenario: EdgeUavScenario with tasks, uavs, time_slots

    Returns:
        offloading_outputs (unchanged if valid)

    Raises:
        ValueError: If validation fails
    """
    errors: List[str] = []
    all_tasks = set(scenario.tasks.keys())
    all_uavs = set(scenario.uavs.keys())
    all_time_slots = set(scenario.time_slots)

    # Check all time slots are present
    missing_slots = all_time_slots - set(offloading_outputs.keys())
    if missing_slots:
        errors.append(f"Missing time slots: {sorted(missing_slots)}")

    for t, t_dict in offloading_outputs.items():
        if not isinstance(t_dict, dict):
            errors.append(f"Time slot {t}: expected dict, got {type(t_dict).__name__}")
            continue

        local_tasks = set(t_dict.get("local", []))
        offload_dict = t_dict.get("offload", {})

        # Check local tasks are valid
        invalid_local = local_tasks - all_tasks
        if invalid_local:
            errors.append(
                f"Time slot {t}: invalid task IDs in 'local': {sorted(invalid_local)}"
            )

        # Check offload assignments
        offload_tasks = set()
        if not isinstance(offload_dict, dict):
            errors.append(
                f"Time slot {t}: 'offload' must be dict, got {type(offload_dict).__name__}"
            )
            continue

        for j, task_list in offload_dict.items():
            if j not in all_uavs:
                errors.append(f"Time slot {t}: unknown UAV {j} in offload")
                continue
            invalid_uav_tasks = set(task_list) - all_tasks
            if invalid_uav_tasks:
                errors.append(
                    f"Time slot {t}, UAV {j}: invalid task IDs {sorted(invalid_uav_tasks)}"
                )
            offload_tasks.update(task_list)

        # Check overlap between local and offload
        overlap = local_tasks & offload_tasks
        if overlap:
            errors.append(
                f"Time slot {t}: tasks {sorted(overlap)} assigned to both local and offload"
            )

    if errors:
        raise ValueError(
            f"validate_offloading_outputs failed ({len(errors)} errors):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return offloading_outputs


def check_trajectory_monotonicity(
    q_result: TrajectoryResult,
    scenario: EdgeUavScenario,
    config: configPara,
) -> Tuple[Trajectory2D, float]:
    """Verify trajectory satisfies boundary constraints and is "reasonable".

    Currently implements basic checks:
      1. All positions within map bounds (if meta contains x_max, y_max)
      2. No NaN or infinity values
      3. Velocity constraints respected (if max velocity in config)

    Args:
        q_result: TrajectoryResult from solve_trajectory_sca()
        scenario: EdgeUavScenario with map bounds (in meta)
        config: configPara with trajectory limits

    Returns:
        (q_checked, cost_checked): Trajectory dict and verified objective cost

    Raises:
        ValueError: If trajectory violates hard constraints
    """
    q = q_result.q
    meta = scenario.meta or {}
    x_max = float(meta.get("x_max", 1e6))
    y_max = float(meta.get("y_max", 1e6))
    delta_t = float(
        getattr(config, "delta", getattr(config, "delta_t", meta.get("delta", 1.0)))
    )  # time slot duration (s)
    v_max = float(getattr(config, "v_traj_max", getattr(config, "v_U_max", getattr(config, "v_max", 30.0))))  # m/s

    errors: List[str] = []

    for j in scenario.uavs:
        if j not in q:
            errors.append(f"Missing trajectory for UAV {j}")
            continue

        q_j = q[j]
        for t_idx, t in enumerate(scenario.time_slots):
            if t not in q_j:
                errors.append(f"UAV {j}: missing position at time slot {t}")
                continue

            x, y = q_j[t]

            # Allow small numerical drift from conic solvers near the map boundary.
            _eps = 1e-3
            if not (-_eps <= x <= x_max + _eps and -_eps <= y <= y_max + _eps):
                errors.append(f"UAV {j}, t={t}: position ({x}, {y}) out of bounds")

            # Check for invalid values
            if not (math.isfinite(x) and math.isfinite(y)):
                errors.append(f"UAV {j}, t={t}: position ({x}, {y}) is NaN or inf")

            # Check velocity constraint (if not first time slot)
            if t_idx > 0:
                t_prev = scenario.time_slots[t_idx - 1]
                if t_prev in q_j:
                    x_prev, y_prev = q_j[t_prev]
                    dist = math.sqrt((x - x_prev) ** 2 + (y - y_prev) ** 2)
                    velocity = dist / delta_t
                    if velocity > v_max * 1.01:  # 1% tolerance
                        errors.append(
                            f"UAV {j}, t={t}: velocity {velocity:.2f} m/s "
                            f"exceeds max {v_max} m/s"
                        )

    if errors:
        raise ValueError(
            f"check_trajectory_monotonicity failed ({len(errors)} errors):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    # Return verified trajectory and objective cost
    return q, q_result.objective_value


def adapt_f_edge_for_snapshot(
    scenario: EdgeUavScenario,
    snapshot: Level2Snapshot,
    ra_result: ResourceAllocResult,
    eps_freq: float = 1e-12,
) -> Scalar3D:
    """Adapt resource allocation result f_edge into snapshot format.

    ResourceAllocResult.f_edge may be sparse on the time-slot axis (only
    offloaded tasks have values). For snapshot compatibility, we densify to
    [j][i][t], filling missing keys with f_max/N_tasks fallback, and validate
    provided values.

    Args:
        scenario: EdgeUavScenario with tasks, uavs, time_slots
        snapshot: Current snapshot (used for structure reference only)
        ra_result: ResourceAllocResult from solve_resource_allocation()
        eps_freq: Minimum frequency threshold (Hz)

    Returns:
        f_edge_adapted: Scalar3D [j][i][t], missing keys filled with f_max/N_tasks fallback

    Raises:
        ValueError: If provided values are invalid (NaN/inf/negative)
    """
    f_edge = ra_result.f_edge
    tasks = scenario.tasks
    uavs = scenario.uavs
    time_slots = scenario.time_slots

    # Densify and validate values
    f_edge_adapted: Scalar3D = {}
    errors: List[str] = []

    for j in uavs:
        f_edge_adapted[j] = {}
        f_j = f_edge.get(j, {})

        for i in tasks:
            f_edge_adapted[j][i] = {}
            f_ji = f_j.get(i, {})

            for t in time_slots:
                v = f_ji.get(t)
                if v is None:
                    # Missing key means "not offloaded at this slot".
                    # Use f_max/N_tasks fallback so the edge remains a viable candidate
                    # in the next BCD iteration; 0.0 would cause big_m_delay in precompute.
                    f_edge_adapted[j][i][t] = uavs[j].f_max / max(len(tasks), 1)
                elif not math.isfinite(v):
                    errors.append(f"f_edge[{j}][{i}][{t}] = {v} is NaN/inf")
                elif v < 0:
                    errors.append(f"f_edge[{j}][{i}][{t}] = {v} < 0")
                else:
                    # Keep floor for existing positive allocations
                    f_edge_adapted[j][i][t] = max(v, eps_freq)

    if errors:
        raise ValueError(
            f"adapt_f_edge_for_snapshot failed ({len(errors)} errors):\n"
            + "\n".join(f"  - {e}" for e in errors[:10])  # Show first 10
        )

    return f_edge_adapted


def validate_resource_allocation_feasibility(
    ra_result: ResourceAllocResult,
    scenario: EdgeUavScenario,
) -> bool:
    """Check if resource allocation result is feasible.

    Verifies:
      1. f_local > 0 for all (i, t)
      2. f_edge >= 0 for all (j, i, t)
      3. Total computation energy per UAV is finite

    Args:
        ra_result: ResourceAllocResult from solve_resource_allocation()
        scenario: EdgeUavScenario (for reference)

    Returns:
        True if feasible, False otherwise (logs warnings without raising)
    """
    f_local = ra_result.f_local
    f_edge = ra_result.f_edge
    total_comp_energy = ra_result.total_comp_energy or {}

    # Check f_local
    for i, f_i in f_local.items():
        for t, v in f_i.items():
            if not (math.isfinite(v) and v > 0):
                logger.warning(f"f_local[{i}][{t}] = {v}, expected > 0")
                return False

    # Check f_edge
    for j, f_j in f_edge.items():
        for i, f_ji in f_j.items():
            for t, v in f_ji.items():
                if not (math.isfinite(v) and v >= 0):
                    logger.warning(f"f_edge[{j}][{i}][{t}] = {v}, expected >= 0")
                    return False

    # Check total_comp_energy
    for j, e_j in total_comp_energy.items():
        if not math.isfinite(e_j) or e_j < 0:
            logger.warning(f"total_comp_energy[{j}] = {e_j}, expected >= 0")
            return False

    return True


# =====================================================================
# Snippet 4: BCD main loop
# =====================================================================


def run_bcd_loop(
    scenario: EdgeUavScenario,
    config: configPara,
    params: PrecomputeParams,
    traj_params: TrajectoryOptParams,
    dynamic_obj_func: Optional[str] = None,
    initial_snapshot: Optional[Level2Snapshot] = None,
    max_bcd_iter: int = 5,
    eps_bcd: float = 1e-3,
    cost_rollback_delta: float = 0.05,
    max_rollbacks: int = 2,
    init_policy: InitPolicy = "greedy",
) -> BCDResult:
    """Run Block Coordinate Descent (BCD) outer loop for integrated optimization.

    Alternates between three optimization blocks:
      Block A (Level 1): Offloading decisions (binary)
      Block B (Level 2a): Resource allocation (frequency)
      Block D (Level 2b): Trajectory optimization (spatial + temporal)

    Each iteration (k) solves three fixed-point subproblems in sequence,
    updating the snapshot and cost. Terminates on convergence (relative cost gap)
    or max iterations reached.

    Args:
        scenario: EdgeUavScenario with tasks, UAVs, map, meta
        config: configPara with problem parameters (alpha, gamma_w, etc.)
        params: PrecomputeParams with physical parameters
        traj_params: TrajectoryOptParams for SCA solver
        dynamic_obj_func: LLM-generated objective function code (str) or None.
                          If provided, enables cost rollback mechanism.
        initial_snapshot: Level2Snapshot for warm start. If None, initializes with
                         default linear trajectory + uniform frequency.
        max_bcd_iter: Maximum number of outer loop iterations (default 5)
        eps_bcd: Relative convergence tolerance for cost (default 1e-3)
        cost_rollback_delta: Threshold for cost increase before rollback
                            (default 5%, i.e., 0.05)
        max_rollbacks: Maximum rollback attempts per iteration (default 2)

    Returns:
        BCDResult: Optimal snapshot, final offloading, cost history, diagnostics

    Raises:
        ValueError: On invalid scenario, config, or solver failures
        RuntimeError: If all rollback attempts exhausted
    """

    # -------- P1: Initialize warm start --------
    logger.info("BCD loop: Initializing warm start")
    if initial_snapshot is None:
        initial_snapshot = make_initial_level2_snapshot(
            scenario, policy=init_policy
        )
    initial_snapshot.validate(scenario)
    logger.debug(f"Initial snapshot source: {initial_snapshot.source}")

    best_snapshot = clone_snapshot(initial_snapshot, source="initialization")
    current_snapshot = clone_snapshot(best_snapshot, source="iteration_0")

    # Initialize best cost (placeholder, will be computed after first precompute)
    best_cost = float("inf")
    cost_history: List[float] = []
    rollback_count = 0
    solution_details: Dict[str, Any] = {
        "sca_converged": False,
        "max_safe_slack": 0.0,
        "min_inter_uav_distance": None,
        "min_inter_uav_distance_slot": None,
        "violated_safe_slots": [],
        "resource_binding_slots": 0,
        "total_rollbacks": 0,
        "final_sca_iterations": 0,
    }
    offloading_error_message = "None Obj. Using default obj."
    used_default_obj = dynamic_obj_func is None
    objective_acceptance_status = "default_obj" if dynamic_obj_func is None else "unknown"

    # -------- BCD outer loop --------
    converged_flag = False
    for k in range(max_bcd_iter):
        logger.info(f"BCD iteration {k + 1}/{max_bcd_iter}")

        # -------- P2: Precompute offloading inputs --------
        try:
            precompute_result: PrecomputeResult = precompute_offloading_inputs(
                scenario,
                params,
                current_snapshot,
                mu=None,  # Use default task.F
                active_only=True,
            )
            logger.debug(
                f"Precompute diagnostics: {precompute_result.diagnostics.keys()}"
            )
        except Exception as e:
            logger.error(f"Precompute failed at iteration {k}: {e}")
            raise

        # -------- P3: Level 1 — Offloading decisions --------
        try:
            offloading_model = OffloadingModel(
                tasks=scenario.tasks,
                uavs=scenario.uavs,
                time_list=scenario.time_slots,
                D_hat_local=precompute_result.D_hat_local,
                D_hat_offload=precompute_result.D_hat_offload,
                E_hat_comp=precompute_result.E_hat_comp,
                alpha=float(getattr(config, "alpha", 1.0)),
                gamma_w=float(getattr(config, "gamma_w", 1.0)),
                N_act=precompute_result.N_act,
                dynamic_obj_func=dynamic_obj_func,
            )
            offloading_model.solveProblem()
            offloading_outputs = validate_offloading_outputs(
                offloading_model.getOutputs(), scenario
            )
            offloading_error_message = offloading_model.error_message or ""
            used_default_obj = (
                offloading_error_message
                != "Your obj function is correct. Gurobi accepts your obj."
            )
            if offloading_error_message == "Your obj function is correct. Gurobi accepts your obj.":
                objective_acceptance_status = "accepted_custom_obj"
            elif dynamic_obj_func is None:
                objective_acceptance_status = "default_obj"
            else:
                objective_acceptance_status = "fallback_default_obj"
            logger.info(f"Level 1 offloading solved (gap={offloading_model.gap:.4%})")
        except Exception as e:
            logger.error(f"Level 1 offloading failed at iteration {k}: {e}")
            raise

        # -------- P4: Level 2a — Resource allocation --------
        try:
            ra_result = solve_resource_allocation(
                scenario,
                offloading_outputs,
                params,
                alpha=float(getattr(config, "alpha", 1.0)),
                gamma_w=float(getattr(config, "gamma_w", 1.0)),
                N_act=precompute_result.N_act,
            )
            if not validate_resource_allocation_feasibility(ra_result, scenario):
                logger.warning("Resource allocation may be infeasible, continuing...")
            solution_details["resource_binding_slots"] = int(
                ra_result.diagnostics.get("binding_slots", 0)
            )
            logger.info(f"Level 2a resource allocation solved")
        except Exception as e:
            logger.error(f"Level 2a resource allocation failed at iteration {k}: {e}")
            raise

        # -------- P5: Level 2b — Trajectory optimization --------
        try:
            q_init = current_snapshot.q
            traj_result = solve_trajectory_sca(
                scenario,
                offloading_outputs,
                ra_result.f_edge,
                q_init,
                params,
                traj_params,
                max_sca_iter=int(getattr(config, "max_sca_iter", 100)),
                eps_sca=float(getattr(config, "eps_sca", 1e-3)),
                safe_slack_penalty=float(getattr(config, "safe_slack_penalty", 1e6)),
                alpha=float(getattr(config, "alpha", 1.0)),
                lambda_w=float(getattr(config, "lambda_w", 1.0)),
                N_act=precompute_result.N_act,
                N_fly=precompute_result.N_fly,
            )
            q_new, cost_traj = check_trajectory_monotonicity(
                traj_result, scenario, config
            )
            solution_details["sca_converged"] = traj_result.converged
            solution_details["max_safe_slack"] = traj_result.max_safe_slack
            solution_details["min_inter_uav_distance"] = traj_result.diagnostics.get(
                "min_inter_uav_distance"
            )
            solution_details["min_inter_uav_distance_slot"] = traj_result.diagnostics.get(
                "min_inter_uav_distance_slot"
            )
            solution_details["violated_safe_slots"] = traj_result.diagnostics.get(
                "violated_safe_slots", []
            )
            solution_details["final_sca_iterations"] = traj_result.sca_iterations
            logger.info(
                f"  [BCD k={k}] L2b: cost_traj={cost_traj:.6f}, "
                f"comm_delay={traj_result.total_comm_delay:.6f}, "
                f"prop_energy={traj_result.total_prop_energy:.6f}, "
                f"sca_iter={traj_result.sca_iterations}, converged={traj_result.converged}"
            )
        except Exception as e:
            logger.error(f"Level 2b trajectory optimization failed at iteration {k}: {e}")
            raise

        # -------- P6: Update snapshot with new results --------
        try:
            current_snapshot = clone_snapshot(
                current_snapshot, source=f"before_adapt_iter{k}"
            )
            # Update trajectory
            current_snapshot = Level2Snapshot(
                q=q_new,
                f_edge=deepcopy(current_snapshot.f_edge),
                f_local_override=deepcopy(current_snapshot.f_local_override)
                if current_snapshot.f_local_override
                else None,
                source=f"iter{k}_post_trajectory",
            )
            # Adapt f_edge from resource allocation
            f_edge_adapted = adapt_f_edge_for_snapshot(
                scenario, current_snapshot, ra_result, params.eps_freq
            )
            current_snapshot = Level2Snapshot(
                q=current_snapshot.q,
                f_edge=f_edge_adapted,
                f_local_override=deepcopy(current_snapshot.f_local_override)
                if current_snapshot.f_local_override
                else None,
                source=f"iter{k}_post_adapt",
            )
            logger.debug(f"Snapshot updated: source={current_snapshot.source}")
        except Exception as e:
            logger.error(f"Snapshot update failed at iteration {k}: {e}")
            raise

        # -------- P7: Compute real system cost and cost rollback --------
        # Complete L2 objective: (L2a local delay + compute energy) + (L2b offload delay + flight energy)
        # = ra_result.objective_value + cost_traj
        # Corresponds to L2-obj terms: (1+3) + (2+4)
        cost_new = ra_result.objective_value + cost_traj
        logger.info(
            f"  [BCD k={k}] ra_obj={ra_result.objective_value:.6f}, "
            f"cost_traj={cost_traj:.6f}, total={cost_new:.6f}"
        )

        # Cost rollback mechanism (only if dynamic_obj_func is provided)
        if dynamic_obj_func is not None:
            threshold = best_cost * (1.0 + cost_rollback_delta)
            if cost_new > threshold:
                rollback_count += 1
                logger.warning(
                    f"Cost rollback #{rollback_count}: {cost_new:.4f} > "
                    f"{threshold:.4f} (best={best_cost:.4f})"
                )
                solution_details["total_rollbacks"] = rollback_count

                if rollback_count >= max_rollbacks:
                    logger.error(
                        f"Max rollbacks ({max_rollbacks}) reached, "
                        f"reverting to best snapshot"
                    )
                    current_snapshot = clone_snapshot(
                        best_snapshot, source=f"rollback_{rollback_count}_final"
                    )
                    break

                # Rollback to previous best snapshot
                current_snapshot = clone_snapshot(
                    best_snapshot, source=f"rollback_{rollback_count}"
                )
                continue

        # -------- P8: Update best solution if cost improved --------
        if cost_new < best_cost:
            best_cost = cost_new
            best_snapshot = clone_snapshot(current_snapshot, source=f"iteration_{k}")
            rollback_count = 0  # Reset rollback counter on improvement
            logger.info(f"Best cost improved: {best_cost:.6f}")
        else:
            logger.info(f"Cost did not improve: {cost_new:.6f} >= {best_cost:.6f}")

        cost_history.append(cost_new)

        # -------- P9: Convergence check --------
        if k > 0:
            relative_gap = abs(cost_history[-1] - cost_history[-2]) / abs(
                cost_history[-2]
            )
            logger.info(f"Relative cost gap: {relative_gap:.6e} (threshold: {eps_bcd})")
            if relative_gap < eps_bcd:
                logger.info(f"BCD converged at iteration {k + 1}")
                converged_flag = True
                break
        else:
            logger.debug("Skipping convergence check at iteration 0")

    # -------- Finalization --------
    logger.info(
        f"BCD loop completed: "
        f"{len(cost_history)} iterations, "
        f"final cost={best_cost:.6f}, "
        f"converged={converged_flag}"
    )

    # final_precompute_diagnostics must always describe the returned best_snapshot.
    # The per-iteration precompute_result only describes the snapshot at the start
    # of that iteration, so it cannot be exposed as the final diagnosis.
    final_precompute_fallback = False
    try:
        final_precompute_result = precompute_offloading_inputs(
            scenario,
            params,
            best_snapshot,
            mu=None,
            active_only=True,
        )
        solution_details["final_precompute_diagnostics"] = (
            final_precompute_result.diagnostics
        )
    except Exception as e:
        final_precompute_fallback = True
        logger.warning(
            f"Failed to compute final_precompute_diagnostics: {e}. "
            f"Falling back to last precompute_result if available."
        )
        if "precompute_result" in locals() and precompute_result is not None:
            solution_details["final_precompute_diagnostics"] = precompute_result.diagnostics
    solution_details["final_precompute_diagnostics_fallback"] = final_precompute_fallback

    return BCDResult(
        snapshot=best_snapshot,
        offloading_outputs=offloading_outputs,
        total_cost=best_cost,
        bcd_iterations=len(cost_history),
        converged=converged_flag,
        cost_history=cost_history,
        solution_details=solution_details,
        offloading_error_message=offloading_error_message,
        used_default_obj=used_default_obj,
        objective_acceptance_status=objective_acceptance_status,
    )
