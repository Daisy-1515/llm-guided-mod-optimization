"""UAV rotor-wing propulsion power and flight energy model.

Implements Eq.(18) propulsion power, Eq.(3') velocity derivation,
and Eq.(17) per-slot flight energy for the Edge UAV system.
"""

from __future__ import annotations

import math

# Type aliases — aligned with precompute.py naming convention:
#   Trajectory2D = dict[int, dict[int, tuple]]  (fleet level, [j][t])
# Here we define single-UAV level aliases only.
Position2D = tuple[float, float]
SingleTrajectory = dict[int, Position2D]          # q_j[t] = (x, y)
Trajectory2D = dict[int, SingleTrajectory]         # q[j][t] = (x, y)

__all__ = [
    "propulsion_power",
    "flight_energy_per_slot",
    "total_flight_energy",
]


def propulsion_power(
    v_sq: float,
    *,
    eta_1: float,
    eta_2: float,
    eta_3: float,
    eta_4: float,
    v_tip: float,
) -> float:
    """Eq.(18): propulsion power given squared speed v².

    P = η₁(1 + 3v²/v_tip²) + η₂√(√(η₃ + v⁴/4) - v²/2) + η₄v³

    Args:
        v_sq: Speed squared ‖Δq‖²/δ² (m²/s²). Must be >= 0.
        eta_1..eta_4, v_tip: Propulsion model parameters (keyword-only).

    Returns:
        Propulsion power in Watts.
    """
    # Term 1: blade profile power (convex)
    term1 = eta_1 * (1.0 + 3.0 * v_sq / (v_tip * v_tip))

    # Term 2: induced power (non-convex)
    # Rationalized form for numerical stability at high v_sq:
    #   sqrt(η₃ + v⁴/4) - v²/2 = η₃ / (sqrt(η₃ + v⁴/4) + v²/2)
    denom = math.sqrt(eta_3 + v_sq * v_sq / 4.0) + v_sq / 2.0
    inner = eta_3 / denom if denom > 0.0 else math.sqrt(eta_3)
    term2 = eta_2 * math.sqrt(inner)

    # Term 3: parasite drag power (convex), v³ = v_sq^(3/2)
    term3 = eta_4 * v_sq * math.sqrt(v_sq) if v_sq > 0.0 else 0.0

    return term1 + term2 + term3


def flight_energy_per_slot(
    q_j: SingleTrajectory,
    delta: float,
    *,
    eta_1: float,
    eta_2: float,
    eta_3: float,
    eta_4: float,
    v_tip: float,
) -> dict[int, float]:
    """Per-slot flight energy for a single UAV trajectory.

    Eq.(3'): v² = ‖q[t+1] - q[t]‖² / δ²
    Eq.(17): E_fly[t] = P_prop(v²) * δ

    The last time slot uses hover power (v=0) since no q[t+1] exists.

    Args:
        q_j: Trajectory {t: (x, y)} for UAV j, sorted by time slot.
        delta: Time slot duration in seconds.
        eta_1..eta_4, v_tip: Propulsion parameters.

    Returns:
        {t: E_fly} flight energy per slot in Joules.
    """
    slots = sorted(q_j)
    delta_sq = delta * delta
    prop_kw = dict(eta_1=eta_1, eta_2=eta_2, eta_3=eta_3,
                   eta_4=eta_4, v_tip=v_tip)
    energies: dict[int, float] = {}

    for idx, t in enumerate(slots):
        if idx + 1 < len(slots):
            x0, y0 = q_j[t]
            x1, y1 = q_j[slots[idx + 1]]
            v_sq = ((x1 - x0) ** 2 + (y1 - y0) ** 2) / delta_sq
        else:
            v_sq = 0.0  # last slot: hover

        energies[t] = propulsion_power(v_sq, **prop_kw) * delta

    return energies


def total_flight_energy(
    q: Trajectory2D,
    delta: float,
    *,
    eta_1: float,
    eta_2: float,
    eta_3: float,
    eta_4: float,
    v_tip: float,
) -> dict[int, float]:
    """Total flight energy for each UAV across all time slots.

    Args:
        q: Fleet trajectory {j: {t: (x, y)}}.
        delta: Time slot duration in seconds.
        eta_1..eta_4, v_tip: Propulsion parameters.

    Returns:
        {j: total_E_fly} total flight energy per UAV in Joules.
    """
    prop_kw = dict(eta_1=eta_1, eta_2=eta_2, eta_3=eta_3,
                   eta_4=eta_4, v_tip=v_tip)
    return {
        j: sum(flight_energy_per_slot(q[j], delta, **prop_kw).values())
        for j in sorted(q)
    }
