"""Unit tests for BCD offloading model initialization fix.

Verifies that OffloadingModel.solveProblem() correctly initializes
the Gurobi model without requiring explicit setupVars() calls.
"""

import pytest
from edge_uav.model.offloading import OffloadingModel
from edge_uav.data import ComputeTask, UAV
import numpy as np


def create_simple_scenario():
    """Create a minimal scenario for testing."""
    tasks = {
        0: ComputeTask(
            index=0,
            pos=(0.0, 0.0),
            D_l=1e6,
            D_r=1e5,
            F=1e9,
            tau=10.0,
        )
    }
    uavs = {
        0: UAV(
            index=0,
            pos=(0.0, 0.0),
            pos_final=(0.0, 0.0),
            E_max=1e6,
            f_max=2e9,
        )
    }

    class SimpleScenario:
        def __init__(self, tasks, uavs):
            self.tasks = tasks
            self.uavs = uavs
            self.time_slots = [0]

    return SimpleScenario(tasks, uavs)


def create_precompute_params(scenario):
    """Create minimal precompute parameters."""
    n_tasks = len(scenario.tasks)
    n_uavs = len(scenario.uavs)
    n_time = len(scenario.time_slots)

    class Params:
        def __init__(self):
            self.D_hat_local = np.ones((n_tasks, n_time)) * 5.0
            self.D_hat_offload = np.ones((n_tasks, n_uavs, n_time)) * 3.0
            self.E_hat_comp = np.ones((n_tasks, n_time)) * 1.0

    return Params()


def test_offloading_model_initialization():
    """Verify solveProblem() correctly initializes Gurobi model."""
    scenario = create_simple_scenario()
    params = create_precompute_params(scenario)

    offloading_model = OffloadingModel(
        tasks=scenario.tasks,
        uavs=scenario.uavs,
        time_list=scenario.time_slots,
        D_hat_local=params.D_hat_local,
        D_hat_offload=params.D_hat_offload,
        E_hat_comp=params.E_hat_comp,
    )

    # Verify initial state
    assert offloading_model.model is None

    # Call solveProblem
    feasible, cost = offloading_model.solveProblem()

    # Verify model was created
    assert offloading_model.model is not None
    assert feasible is True
    assert cost >= 0


def test_offloading_model_idempotent():
    """Verify solveProblem() can be called multiple times."""
    scenario = create_simple_scenario()
    params = create_precompute_params(scenario)

    offloading_model = OffloadingModel(
        tasks=scenario.tasks,
        uavs=scenario.uavs,
        time_list=scenario.time_slots,
        D_hat_local=params.D_hat_local,
        D_hat_offload=params.D_hat_offload,
        E_hat_comp=params.E_hat_comp,
    )

    feasible1, cost1 = offloading_model.solveProblem()
    feasible2, cost2 = offloading_model.solveProblem()

    assert feasible1 == feasible2
    assert abs(cost1 - cost2) < 1e-3
