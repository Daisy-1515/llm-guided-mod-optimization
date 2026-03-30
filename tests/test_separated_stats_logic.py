"""Test separated statistics logic with synthetic data.

Migrated from scripts/verify_separated_stats.py — converted to pytest format.
Pure logic test — no external dependencies required.
"""


def test_separated_stats_logic():
    """Verify separated statistics computation on synthetic pairs."""
    eps_freq = 1e-12

    # (f_edge, d_offload, tau, is_feasible_expected)
    pairs = [
        (1e6, 0.5, 1.0, True),    # assigned, feasible
        (1e6, 0.9, 1.0, True),    # assigned, feasible
        (1e6, 1.5, 1.0, False),   # assigned, infeasible
        (1e6, 0.3, 1.0, True),    # assigned, feasible
        (1e6, 0.8, 1.0, True),    # assigned, feasible
        (1e6, 1.2, 1.0, False),   # assigned, infeasible
        (1e6, 0.6, 1.0, True),    # assigned, feasible
        (0.0, 1e6, 1.0, False),   # unassigned, infeasible
        (0.0, 1e6, 1.0, False),   # unassigned, infeasible
        (0.0, 1e6, 1.0, False),   # unassigned, infeasible
    ]

    assigned_pairs = 0
    assigned_feasible = 0
    unassigned_pairs = 0

    for f_val, d_val, tau_val, _ in pairs:
        if f_val > eps_freq:
            assigned_pairs += 1
            if d_val <= tau_val:
                assigned_feasible += 1
        else:
            unassigned_pairs += 1

    total_pairs = assigned_pairs + unassigned_pairs
    total_feasible = assigned_feasible

    assert assigned_pairs == 7
    assert assigned_feasible == 5
    assert unassigned_pairs == 3
    assert abs(total_feasible / total_pairs - 0.5) < 1e-6
    assert abs(assigned_feasible / assigned_pairs - 5 / 7) < 1e-6
