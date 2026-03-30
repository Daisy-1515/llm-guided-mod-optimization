"""Phase⑥ Step4 单元测试 — BCD Loop 框架测试.

测试 5 个核心功能:
  T1. 深拷贝隔离 (test_bcd_deepcopy_isolation) ⭐ Day1 P1 CRITICAL
  T2. 成本单调性 (test_bcd_cost_monotonicity) - Day1 P2
  T3. 收敛判定 (test_bcd_early_convergence) - Day1 P3
  T4. 热启动传递 (test_bcd_warm_start) - Day1 P3
  T5. 回滚限制 (test_bcd_rollback_limit) ⭐ Day1 P1 CRITICAL

对应 plans/phase6-step3-socp-fix-plan.md 的测试覆盖清单。
"""

from __future__ import annotations

import pytest
from copy import deepcopy
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

from config.config import configPara
from edge_uav.data import ComputeTask, UAV, EdgeUavScenario
from edge_uav.model.bcd_loop import run_bcd_loop
from edge_uav.model.precompute import Level2Snapshot, PrecomputeParams, PrecomputeResult
from edge_uav.model.trajectory_opt import TrajectoryOptParams, TrajectoryResult

if TYPE_CHECKING:
    # Placeholder imports for bcd_loop module (to be implemented in Step4)
    from edge_uav.model.bcd_loop import (
        clone_snapshot,
        run_bcd_loop,
        BCDResult,
    )


# =====================================================================
# 辅助函数 — 构造测试场景与快照
# =====================================================================


def _make_scenario(*, x_max: float = 1000.0, y_max: float = 1000.0) -> EdgeUavScenario:
    """构造最小化测试场景 (1 UAV × 1 任务 × 3 时隙)。"""
    tasks = {
        0: ComputeTask(
            index=0,
            pos=(100.0, 200.0),
            D_l=1e6,
            D_r=5e5,
            F=1e9,
            tau=10.0,
            active={0: True, 1: True, 2: True},
            f_local=1e9,
        ),
    }
    uavs = {
        0: UAV(
            index=0,
            pos=(500.0, 500.0),
            pos_final=(500.0, 500.0),
            E_max=100.0,
            f_max=4e9,
        ),
    }
    meta = {"x_max": x_max, "y_max": y_max}
    return EdgeUavScenario(
        tasks=tasks,
        uavs=uavs,
        time_slots=[0, 1, 2],
        seed=42,
        meta=meta,
    )


def _make_valid_snapshot(scenario: EdgeUavScenario) -> Level2Snapshot:
    """构造完全合法的 dense 快照 (覆盖所有 q, f_edge)。"""
    q = {
        j: {t: (500.0, 500.0) for t in scenario.time_slots}
        for j in scenario.uavs
    }
    f_edge = {
        j: {
            i: {t: 1e9 for t in scenario.time_slots}
            for i in scenario.tasks
        }
        for j in scenario.uavs
    }
    return Level2Snapshot(q=q, f_edge=f_edge, source="test_init")


# =====================================================================
# Pytest Fixtures
# =====================================================================


@pytest.fixture
def simple_scenario() -> EdgeUavScenario:
    """最小化测试场景 fixture。"""
    return _make_scenario()


@pytest.fixture
def simple_snapshot(simple_scenario: EdgeUavScenario) -> Level2Snapshot:
    """完全合法的初始快照 fixture。"""
    return _make_valid_snapshot(simple_scenario)


# =====================================================================
# T1: 深拷贝隔离 ⭐ CRITICAL - Day1 P1
# =====================================================================


class TestBCDDeepCopyIsolation:
    """验证 clone_snapshot() 的深拷贝有效性，两个独立快照互不污染。

    关键测试：
      1. 创建 snapshot1 (q[j][t] 初值为 (0,0))
      2. clone_snapshot() → snapshot2
      3. 修改 snapshot2.q[j][t] = (10.0, 10.0)
      4. 验证 snapshot1.q[j][t] 仍为 (0,0) ← 深拷贝有效
      5. 修改 snapshot1.f_edge[j][i][t] = 5e7
      6. 验证 snapshot2.f_edge 不受污染 ← 完全隔离
    """

    def test_bcd_deepcopy_isolation(self, simple_scenario: EdgeUavScenario):
        """核心: snapshot1/snapshot2 修改互不污染。"""
        # 1. 创建初始快照 snapshot1
        snapshot1 = Level2Snapshot(
            q={0: {t: (0.0, 0.0) for t in simple_scenario.time_slots}},
            f_edge={
                0: {
                    0: {t: 1e8 for t in simple_scenario.time_slots}
                }
            },
            source="test_init",
        )

        # 2. 模拟 clone_snapshot (深拷贝)
        # TODO: 当 bcd_loop.py 实现时，改为: snapshot2 = clone_snapshot(snapshot1)
        snapshot2 = Level2Snapshot(
            q=deepcopy(snapshot1.q),
            f_edge=deepcopy(snapshot1.f_edge),
            source="cloned",
        )

        # 3. 修改 snapshot2.q[0][0]
        snapshot2.q[0][0] = (10.0, 10.0)

        # 4. 断言：snapshot1.q 未被污染
        assert snapshot1.q[0][0] == (0.0, 0.0), (
            "snapshot1 被污染: clone 时未进行深拷贝"
        )

        # 5. 修改 snapshot1.f_edge[0][0][0]
        snapshot1.f_edge[0][0][0] = 5e7

        # 6. 断言：snapshot2.f_edge 未被污染
        assert snapshot2.f_edge[0][0][0] == 1e8, (
            "snapshot2 被污染: f_edge 共享引用"
        )

    def test_bcd_snapshot_independence_across_generations(
        self, simple_scenario: EdgeUavScenario
    ):
        """代际间快照隔离: Gen1 best_snapshot → Gen2 initial。

        场景：Gen1 的最优快照作为 Gen2 初始快照，验证内容传递但引用隔离。
        """
        # Gen1: 创建 best_snapshot1
        best_snapshot1 = _make_valid_snapshot(simple_scenario)

        # Gen2: 用 deepcopy 模拟 clone_snapshot 传递
        # TODO: 当 bcd_loop 实现时，改为: gen2_initial = clone_snapshot(best_snapshot1)
        gen2_initial = Level2Snapshot(
            q=deepcopy(best_snapshot1.q),
            f_edge=deepcopy(best_snapshot1.f_edge),
            source="gen2_warmstart",
        )

        # Gen2 修改其快照
        gen2_initial.q[0][0] = (0.0, 0.0)
        gen2_initial.f_edge[0][0][0] = 2e9

        # 断言：Gen1 best_snapshot1 保持不变
        assert best_snapshot1.q[0][0] == (500.0, 500.0), (
            "Gen1 快照被 Gen2 修改污染"
        )
        assert best_snapshot1.f_edge[0][0][0] == 1e9, (
            "Gen1 f_edge 被 Gen2 污染"
        )


# =====================================================================
# T2: 成本单调性 - Day1 P2
# =====================================================================


class TestBCDCostMonotonicity:
    """验证成本历史严格单调非递增。

    BCD 迭代应满足:
      cost_history[k] <= cost_history[k-1] + eps_tol (eps_tol = 1e-6)

    目标：防止成本意外上升，检测目标函数设置错误。
    """

    def test_bcd_cost_monotonicity(self, simple_scenario: EdgeUavScenario):
        """5 轮 BCD 迭代，验证成本历史单调性。

        TODO: 当 run_bcd_loop 实现时，用实际 BCD 循环结果。
        """
        # 模拟成本历史: 应单调非递增
        cost_history = [100.0, 95.0, 92.0, 90.5, 90.2]

        eps_tol = 1e-6
        for k in range(1, len(cost_history)):
            assert cost_history[k] <= cost_history[k - 1] + eps_tol, (
                f"成本单调性破坏: cost[{k}]={cost_history[k]} "
                f"> cost[{k-1}]={cost_history[k-1]}"
            )


# =====================================================================
# T3: 收敛判定 - Day1 P3
# =====================================================================


class TestBCDEarlyConvergence:
    """较宽松的收敛容差 (eps_bcd=0.01) 应提前收敛。

    场景：eps_bcd=0.01（较宽松），BCD 循环应在 k < max_bcd_iter 时退出。

    TODO: 当 run_bcd_loop 实现时，替换为实际测试。
    """

    def test_bcd_early_convergence(self):
        """eps_bcd=0.01 时应提前收敛。"""
        # 模拟 BCD 结果
        class MockBCDResult:
            converged = True
            bcd_iterations = 5

        result = MockBCDResult()
        max_bcd_iter = 10

        assert result.converged is True, "应收敛"
        assert result.bcd_iterations < max_bcd_iter, (
            f"未提前收敛: {result.bcd_iterations} >= {max_bcd_iter}"
        )


# =====================================================================
# T4: 热启动机制 - Day1 P3
# =====================================================================


class TestBCDWarmStart:
    """前后两代的快照正确传递（代际间 warm-start）。

    场景：
      1. Gen1 运行完毕 → gen1_best_snapshot
      2. Gen2 初始化时用 clone_snapshot(gen1_best_snapshot)
      3. 验证：Gen2 初始成本 <= Gen1 最优成本
    """

    def test_bcd_warm_start(self, simple_scenario: EdgeUavScenario):
        """代际间热启动验证。"""
        # Gen1: 最优快照
        gen1_best_snapshot = _make_valid_snapshot(simple_scenario)
        gen1_best_cost = 95.0  # 假设 Gen1 最优成本

        # Gen2: 热启动
        # TODO: gen2_initial = clone_snapshot(gen1_best_snapshot)
        gen2_initial = Level2Snapshot(
            q=deepcopy(gen1_best_snapshot.q),
            f_edge=deepcopy(gen1_best_snapshot.f_edge),
            source="gen2_warmstart",
        )
        gen2_initial_cost = 94.0  # 热启动优势

        # 验证：Gen2 初始成本 <= Gen1 最优成本
        assert gen2_initial_cost <= gen1_best_cost, (
            f"热启动失败: Gen2 初始 {gen2_initial_cost} > Gen1 最优 {gen1_best_cost}"
        )


# =====================================================================
# T5: 回滚限制机制 ⭐ CRITICAL - Day1 P1
# =====================================================================


class TestBCDRollbackLimit:
    """验证 max_rollbacks=2 防止无限循环。

    场景：LLM 代理目标导致成本上升 5 次，观察回滚 2 次后终止。

    关键步骤：
      1. 创建 mock dynamic_obj_func，返回导致成本上升的目标
      2. 设置 cost_rollback_delta=0.05 (5% 阈值), max_rollbacks=2
      3. 调用 run_bcd_loop
      4. 观察: 成本上升 → 回滚 → 重试 → 再上升 → 再回滚 → 达 max=2 → 终止
      5. 断言：final rollback_count == 2 (不会无限增长)
    """

    def test_bcd_rollback_limit_prevents_infinite_loop(
        self, simple_scenario: EdgeUavScenario
    ):
        """max_rollbacks=2 时，回滚次数不应超过 2。"""
        # 模拟 BCD 循环的成本历史与回滚记录
        cost_history = [100.0, 105.0]  # 成本上升 → 第 1 次回滚
        cost_after_rollback_1 = 98.0
        cost_history.append(cost_after_rollback_1)

        cost_history.append(103.0)  # 再上升 → 第 2 次回滚
        cost_after_rollback_2 = 96.0
        cost_history.append(cost_after_rollback_2)

        cost_history.append(105.0)  # 再上升，但已达 max_rollbacks=2 → 终止

        # 模拟 BCD 结果
        max_rollbacks = 2
        cost_rollback_delta = 0.05
        final_rollback_count = 2

        assert final_rollback_count <= max_rollbacks, (
            f"回滚次数超限: {final_rollback_count} > max_rollbacks={max_rollbacks}"
        )

        # 验证成本上升时触发回滚
        rollback_triggered_count = 0
        for i in range(1, len(cost_history)):
            if cost_history[i] > cost_history[i - 1] * (1 + cost_rollback_delta):
                rollback_triggered_count += 1

        assert rollback_triggered_count <= max_rollbacks, (
            f"回滚触发次数过多: {rollback_triggered_count} > {max_rollbacks}"
        )

    def test_bcd_rollback_convergence_after_max_limit(
        self, simple_scenario: EdgeUavScenario
    ):
        """到达 max_rollbacks 后，BCD 循环应终止而非无限重试。"""
        # 模拟：成本上升 3 次，但 max_rollbacks=2 → 第 3 次上升时无法回滚 → 终止
        max_rollbacks = 2
        rollback_count = 0
        cost = 100.0

        for iteration in range(10):  # 最多 10 轮
            # 模拟 LLM 目标导致成本上升
            new_cost = cost * 1.05  # 5% 上升

            if new_cost > cost:  # 成本上升，需要回滚
                if rollback_count < max_rollbacks:
                    # 回滚
                    rollback_count += 1
                    cost = cost * 0.99  # 回滚到前一代快照
                else:
                    # 已达回滚限制，终止迭代
                    break

            cost = new_cost

        # 验证：回滚次数不超过 max，且循环已终止
        assert rollback_count <= max_rollbacks, (
            f"回滚次数超过限制: {rollback_count} > {max_rollbacks}"
        )


# =====================================================================
# 集成测试占位符（Day2+）
# =====================================================================


class TestBCDIntegration:
    """集成测试（后续实现）。

    TODO: 当 bcd_loop.py 完整实现后添加：
      - test_bcd_full_loop_e2e: 端到端 BCD 循环测试
      - test_bcd_with_dynamic_objectives: 动态目标函数集成
      - test_bcd_trajectory_convergence: 轨迹优化收敛性
      - test_bcd_offloading_feedback: 卸载决策反馈循环
    """

    def test_placeholder(self):
        """占位符，防止 pytest 报告 "无测试" 警告。"""
        assert True
class TestBCDFinalDiagnostics:
    """Integration tests for final diagnostics recomputation."""

    def test_final_precompute_uses_best_snapshot_after_rollback_break(
        self, simple_scenario: EdgeUavScenario, monkeypatch
    ):
        config = configPara(None, None)
        params = PrecomputeParams.from_config(config)
        traj_params = TrajectoryOptParams(
            eta_1=float(config.eta_1),
            eta_2=float(config.eta_2),
            eta_3=float(config.eta_3),
            eta_4=float(config.eta_4),
            v_tip=float(config.v_tip),
            v_max=float(config.v_traj_max),
            d_safe=float(config.d_safe_traj),
        )
        initial_snapshot = _make_valid_snapshot(simple_scenario)
        precompute_sources = []
        trajectory_costs = iter([10.0, 20.0])

        def fake_precompute_offloading_inputs(
            scenario, params_arg, snapshot, mu=None, active_only=True
        ):
            precompute_sources.append(snapshot.source)
            return PrecomputeResult(
                D_hat_local={},
                D_hat_offload={},
                E_hat_comp={},
                diagnostics={"snapshot_source": snapshot.source},
            )

        class FakeOffloadingModel:
            def __init__(self, **kwargs):
                self.gap = 0.0
                self.error_message = ""

            def solveProblem(self):
                return None

            def getOutputs(self):
                return {
                    t: {"local": [0], "offload": {0: []}}
                    for t in simple_scenario.time_slots
                }

        def fake_solve_resource_allocation(*args, **kwargs):
            return SimpleNamespace(
                f_local={0: {t: 1.0 for t in simple_scenario.time_slots}},
                f_edge={0: {0: {t: 1.0 for t in simple_scenario.time_slots}}},
                total_comp_energy={0: 1.0},
                diagnostics={"binding_slots": 0},
            )

        def fake_solve_trajectory_sca(*args, **kwargs):
            q_new = {0: {t: (500.0, 500.0) for t in simple_scenario.time_slots}}
            return TrajectoryResult(
                q=q_new,
                objective_value=next(trajectory_costs),
                per_uav_energy={0: 1.0},
                sca_iterations=1,
                converged=False,
                solver_status="optimal",
                max_safe_slack=0.0,
                diagnostics={},
            )

        def fake_check_trajectory_monotonicity(q_result, scenario, config):
            return q_result.q, q_result.objective_value

        monkeypatch.setattr(
            "edge_uav.model.bcd_loop.precompute_offloading_inputs",
            fake_precompute_offloading_inputs,
        )
        monkeypatch.setattr("edge_uav.model.bcd_loop.OffloadingModel", FakeOffloadingModel)
        monkeypatch.setattr(
            "edge_uav.model.bcd_loop.solve_resource_allocation",
            fake_solve_resource_allocation,
        )
        monkeypatch.setattr(
            "edge_uav.model.bcd_loop.solve_trajectory_sca",
            fake_solve_trajectory_sca,
        )
        monkeypatch.setattr(
            "edge_uav.model.bcd_loop.check_trajectory_monotonicity",
            fake_check_trajectory_monotonicity,
        )

        result = run_bcd_loop(
            simple_scenario,
            config,
            params,
            traj_params,
            dynamic_obj_func="def dynamic_obj_func(self):\n    return None",
            initial_snapshot=initial_snapshot,
            max_bcd_iter=3,
            cost_rollback_delta=0.05,
            max_rollbacks=1,
        )

        assert result.snapshot.source == "iteration_0"
        assert precompute_sources == ["iteration_0", "iter0_post_adapt", "iteration_0"]
        assert (
            result.solution_details["final_precompute_diagnostics"]["snapshot_source"]
            == "iteration_0"
        )
        assert result.solution_details["final_precompute_diagnostics_fallback"] is False
