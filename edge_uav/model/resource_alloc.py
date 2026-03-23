"""Block C resource allocation — Level 2a frequency optimization.

Given fixed offloading decisions x and UAV trajectories q, solve for
optimal CPU frequencies (f_local, f_edge) that minimise weighted delay
plus energy.

Objective (Eq. 3-20):
    min_f  Σ_{j,i,t} [ α·F_i/(f·τ_i) + γ_w·γ_j·f²·F_i/E_max ]
    s.t.   Σ_i f_ji^t ≤ f_max_j   ∀ j, t
           f_ji^t ≥ eps_freq

Solver: closed-form KKT + dual bisection when capacity binds.
"""

from __future__ import annotations

from dataclasses import dataclass

from edge_uav.data import EdgeUavScenario
from edge_uav.model.precompute import PrecomputeParams, Scalar2D, Scalar3D

__all__ = [
    "ResourceAllocResult",
    "solve_resource_allocation",
]

_MAX_OUTER_BISECT = 200   # dual variable range can span 30+ orders of magnitude
_MAX_INNER_BISECT = 60    # frequency range [eps_freq, f_max] — 60 halves suffice
_G_REL_TOL = 1e-10        # outer convergence: |g(ν) - f_max| / f_max < tol


@dataclass(frozen=True)
class ResourceAllocResult:
    """Block C solver output.

    Attributes:
        f_local: dict[i][t] — local CPU frequency (Hz), always task.f_local.
        f_edge:  dict[j][t][i] — edge CPU frequency (Hz), KKT-optimal.
        objective_value: L2a-obj (delay + energy terms for offloaded tasks).
        total_comp_energy: {j: float} — per-UAV total computation energy (J),
            for BCD wrapper to check energy budget constraint (Eq. 3-25).
        diagnostics: binding_slots, total_bisect_iters, max_bisect_iters.
    """

    f_local: Scalar2D
    f_edge: Scalar3D
    objective_value: float
    total_comp_energy: dict
    diagnostics: dict


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def solve_resource_allocation(
    scenario: EdgeUavScenario,
    offloading_decisions: dict,
    params: PrecomputeParams,
    *,
    alpha: float,
    gamma_w: float,
) -> ResourceAllocResult:
    """Solve Block C: optimal frequency allocation for given offloading.

    Args:
        scenario: Edge UAV scenario data.
        offloading_decisions: OffloadingModel.getOutputs() format —
            ``{t: {"local": [i...], "offload": {j: [i...]}}}``.
        params: Physical parameters (gamma_j, eps_freq used here).
        alpha: Delay weight (> 0, keyword-only).
        gamma_w: Energy scaling factor (> 0, keyword-only).

    Returns:
        ResourceAllocResult with f_local, f_edge, objective, diagnostics.

    Raises:
        ValueError: On invalid alpha / gamma_w / gamma_j.
    """
    if alpha <= 0:
        raise ValueError(f"alpha must be > 0, got {alpha}")
    if gamma_w <= 0:
        raise ValueError(f"gamma_w must be > 0, got {gamma_w}")
    if params.gamma_j <= 0:
        raise ValueError(f"gamma_j must be > 0, got {params.gamma_j}")

    offload_sets = _parse_offload_sets(offloading_decisions, scenario)

    # f_local: always task.f_local (no local energy term ⇒ max freq optimal)
    f_local: Scalar2D = {
        i: {t: task.f_local for t in scenario.time_slots}
        for i, task in scenario.tasks.items()
    }

    # f_edge: solve per (j, t) slot via KKT + dual bisection
    f_edge: Scalar3D = {j: {} for j in scenario.uavs}
    diag = {"binding_slots": 0, "total_bisect_iters": 0, "max_bisect_iters": 0}

    for j, slot_map in offload_sets.items():
        uav = scenario.uavs[j]
        for t, task_ids in slot_map.items():
            if not task_ids:
                continue
            # Eq. 3-20 coefficients: a_i = α·F_i/τ_i, b_i = γ_w·γ_j·F_i/E_max
            specs = []
            for i in task_ids:
                task = scenario.tasks[i]
                a_i = alpha * task.F / task.tau
                b_i = gamma_w * params.gamma_j * task.F / uav.E_max
                specs.append((i, a_i, b_i))

            freqs, n_bisect = _solve_slot_kkt(specs, uav.f_max, params.eps_freq)
            f_edge[j][t] = freqs

            if n_bisect > 0:
                diag["binding_slots"] += 1
            diag["total_bisect_iters"] += n_bisect
            diag["max_bisect_iters"] = max(diag["max_bisect_iters"], n_bisect)

    obj = _compute_objective(f_edge, offload_sets, scenario, params,
                             alpha=alpha, gamma_w=gamma_w)

    # Eq. 3-25: per-UAV total computation energy for BCD feasibility check
    comp_energy = _compute_comp_energy(f_edge, offload_sets, scenario, params)

    return ResourceAllocResult(
        f_local=f_local, f_edge=f_edge,
        objective_value=obj, total_comp_energy=comp_energy,
        diagnostics=diag,
    )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _parse_offload_sets(
    outputs: dict,
    scenario: EdgeUavScenario,
) -> dict[int, dict[int, list[int]]]:
    """Extract per-UAV per-slot task lists from offloading decisions.

    Returns:
        {j: {t: [i, ...]}} — tasks offloaded to UAV j at slot t.
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
    """KKT solver for one (j, t) slot.

    Phase 1: unconstrained solution f_i* = (a_i / (2·b_i))^(1/3).
    Phase 2: if Σf_i* ≤ f_max, return directly.
    Phase 3: dual bisection on ν so that Σ f_i(ν) = f_max.

    Returns:
        ({i: f_i*}, n_bisect_iters).
    """
    if not specs:
        return {}, 0

    # Phase 1: unconstrained KKT — Eq. 3-20 with ν = 0
    unc = {}
    total = 0.0
    for i, a_i, b_i in specs:
        f_i = (a_i / (2.0 * b_i)) ** (1.0 / 3.0)
        unc[i] = f_i
        total += f_i

    # Phase 2: feasibility check
    if total <= f_max:
        clamped = {i: max(eps_freq, min(f_max, f)) for i, f in unc.items()}
        # Post-clamp check: eps_freq lift could violate capacity
        if sum(clamped.values()) <= f_max:
            return clamped, 0
        # Fall through to dual bisection

    # Phase 3: dual bisection — find ν > 0 s.t. g(ν) = Σ f_i(ν) = f_max
    #   ν range can span 30+ orders of magnitude (e.g. [0, 2e33] when
    #   gamma_j ≈ 1e-28), so converge on g(ν) relative to f_max instead
    #   of absolute ν tolerance.
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
    """Solve  2b·f³ + ν·f²  − a = 0  for f ∈ [eps_freq, f_max].

    The LHS h(f) = 2b·f³ + ν·f² − a is strictly increasing for f > 0,
    so binary search is guaranteed to converge.
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
) -> float:
    """L2a objective: Σ [ α·F/(f·τ) + γ_w·γ_j·f²·F/E_max ].

    Only frequency-dependent terms; communication delay is external.
    """
    obj = 0.0
    for j, slot_map in offload_sets.items():
        uav = scenario.uavs[j]
        for t, task_ids in slot_map.items():
            slot_freqs = f_edge.get(j, {}).get(t, {})
            for i in task_ids:
                f = slot_freqs.get(i)
                if f is None or f <= 0.0:
                    continue
                task = scenario.tasks[i]
                # Eq. 3-20: delay term + energy term
                obj += alpha * task.F / (f * task.tau)
                obj += gamma_w * params.gamma_j * f * f * task.F / uav.E_max
    return obj


def _compute_comp_energy(
    f_edge: Scalar3D,
    offload_sets: dict[int, dict[int, list[int]]],
    scenario: EdgeUavScenario,
    params: PrecomputeParams,
) -> dict[int, float]:
    """Per-UAV total computation energy: Σ_{i,t} γ_j · f² · F_i.

    For BCD wrapper to check Eq. 3-25: E_comp_j + E_fly_j ≤ E_max_j.
    """
    energy: dict[int, float] = {j: 0.0 for j in scenario.uavs}
    for j, slot_map in offload_sets.items():
        for t, task_ids in slot_map.items():
            slot_freqs = f_edge.get(j, {}).get(t, {})
            for i in task_ids:
                f = slot_freqs.get(i)
                if f is None or f <= 0.0:
                    continue
                task = scenario.tasks[i]
                # Eq. 3-24: E_comp = γ_j · f² · F_i
                energy[j] += params.gamma_j * f * f * task.F
    return energy
