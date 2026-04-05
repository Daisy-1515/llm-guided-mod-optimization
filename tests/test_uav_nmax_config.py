import pytest

pytest.importorskip("gurobipy")

from config.config import configPara
from edge_uav.data import ComputeTask, UAV
from edge_uav.model.offloading import OffloadingModel
from edge_uav.scenario_generator import EdgeUavScenarioGenerator


def test_config_reads_optional_n_max_values():
    cfg = configPara(None, None)
    cfg.config["edgeUavHardware"]["N_max"] = "3"
    cfg.getConfigInfo()
    assert cfg.N_max == 3

    cfg_none = configPara(None, None)
    cfg_none.config["edgeUavHardware"]["N_max"] = "none"
    cfg_none.getConfigInfo()
    assert cfg_none.N_max is None


def test_scenario_generator_injects_default_n_max():
    cfg = configPara(None, None)
    cfg.getConfigInfo()

    scenario = EdgeUavScenarioGenerator().getScenarioInfo(cfg)

    assert scenario.uavs
    assert all(uav.N_max == cfg.N_max for uav in scenario.uavs.values())


def test_offloading_respects_per_slot_n_max():
    tasks = {
        0: ComputeTask(
            index=0,
            pos=(0.0, 0.0),
            D_l=1e6,
            D_r=1e5,
            F=1e9,
            tau=10.0,
            active={0: True},
            f_local=1e9,
        ),
        1: ComputeTask(
            index=1,
            pos=(1.0, 0.0),
            D_l=1e6,
            D_r=1e5,
            F=1e9,
            tau=10.0,
            active={0: True},
            f_local=1e9,
        ),
    }
    capped_uavs = {
        0: UAV(
            index=0,
            pos=(0.0, 0.0),
            pos_final=(0.0, 0.0),
            E_max=1e6,
            f_max=2e9,
            N_max=1,
        )
    }
    uncapped_uavs = {
        0: UAV(
            index=0,
            pos=(0.0, 0.0),
            pos_final=(0.0, 0.0),
            E_max=1e6,
            f_max=2e9,
            N_max=None,
        )
    }

    d_hat_local = {0: {0: 10.0}, 1: {0: 10.0}}
    d_hat_offload = {0: {0: {0: 1.0}}, 1: {0: {0: 1.0}}}
    e_hat_comp = {0: {0: {0: 0.1}, 1: {0: 0.1}}}

    capped_model = OffloadingModel(
        tasks=tasks,
        uavs=capped_uavs,
        time_list=[0],
        D_hat_local=d_hat_local,
        D_hat_offload=d_hat_offload,
        E_hat_comp=e_hat_comp,
    )
    feasible_capped, _ = capped_model.solveProblem()
    capped_outputs = capped_model.getOutputs()

    assert feasible_capped is True
    assert sum(len(v) for v in capped_outputs[0]["offload"].values()) == 1
    assert len(capped_outputs[0]["local"]) == 1

    uncapped_model = OffloadingModel(
        tasks=tasks,
        uavs=uncapped_uavs,
        time_list=[0],
        D_hat_local=d_hat_local,
        D_hat_offload=d_hat_offload,
        E_hat_comp=e_hat_comp,
    )
    feasible_uncapped, _ = uncapped_model.solveProblem()
    uncapped_outputs = uncapped_model.getOutputs()

    assert feasible_uncapped is True
    assert sum(len(v) for v in uncapped_outputs[0]["offload"].values()) == 2
    assert len(uncapped_outputs[0]["local"]) == 0
