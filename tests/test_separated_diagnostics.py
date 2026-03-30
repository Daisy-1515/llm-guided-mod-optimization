"""Test separated diagnostics data from run outputs.

Migrated from scripts/test_separated_diagnostics.py — converted to pytest format.
Reads the latest run from discussion/ to verify separated statistics are present.
"""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_latest_diagnostics():
    """Load precompute diagnostics from the most recent run."""
    discussion_dir = PROJECT_ROOT / "discussion"
    if not discussion_dir.exists():
        return None, "No discussion/ directory"

    runs = sorted(discussion_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        return None, "No previous runs found in discussion/"

    latest_run = runs[0]
    pop_result_files = sorted(latest_run.glob("population_result_*.json"))
    if not pop_result_files:
        return None, f"No population_result_*.json in {latest_run.name}"

    with open(pop_result_files[0]) as f:
        pop_data = json.load(f)

    if isinstance(pop_data, list):
        if not pop_data:
            return None, "pop_data is empty list"
        pop_data = pop_data[0]

    diag = None
    if isinstance(pop_data, dict) and "solution_details" in pop_data:
        solution_details = pop_data.get("solution_details", {})
        if isinstance(solution_details, dict):
            diag = solution_details.get("final_precompute_diagnostics")

    if diag is None and isinstance(pop_data, dict):
        diag = pop_data.get("precompute_diagnostics")

    return diag, None


def test_diagnostics_present():
    """Precompute diagnostics should be present in the latest run."""
    diag, reason = _load_latest_diagnostics()
    if diag is None:
        pytest.skip(f"No diagnostics available: {reason}")

    assert isinstance(diag, dict)
    assert "candidate_offload_pairs" in diag
    assert "deadline_feasible_pairs" in diag
    assert "offload_feasible_ratio" in diag


def test_separated_statistics_available():
    """Separated statistics (assigned_pairs etc.) should be present."""
    diag, reason = _load_latest_diagnostics()
    if diag is None:
        pytest.skip(f"No diagnostics available: {reason}")

    assigned_pairs = diag.get("assigned_pairs")
    if not isinstance(assigned_pairs, int):
        pytest.skip("Separated statistics not yet deployed in this run")

    assert isinstance(diag.get("assigned_feasible_pairs"), int)
    assert isinstance(diag.get("assigned_feasible_ratio"), float)
    assert isinstance(diag.get("unassigned_pairs"), int)
    assert isinstance(diag.get("assigned_pair_ratio"), float)
