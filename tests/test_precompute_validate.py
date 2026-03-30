"""S4 单元测试 — Level2Snapshot.validate() 方法。

覆盖 5 项检查 × 正常/异常场景，以及多错误累积行为。
"""

import pytest

from edge_uav.data import ComputeTask, UAV, EdgeUavScenario
from edge_uav.model.precompute import Level2Snapshot, _build_diagnostics


# =====================================================================
# Fixture: 最小场景（1 UAV × 2 task × 3 时隙）
# =====================================================================

def _make_scenario(*, x_max=1000.0, y_max=1000.0) -> EdgeUavScenario:
    """构造最小可用场景。"""
    tasks = {
        0: ComputeTask(
            index=0, pos=(100.0, 200.0),
            D_l=1e6, D_r=5e5, F=1e9, tau=10.0,
            active={0: True, 1: True, 2: True}, f_local=1e9,
        ),
        1: ComputeTask(
            index=1, pos=(300.0, 400.0),
            D_l=1e6, D_r=5e5, F=1e9, tau=10.0,
            active={0: True, 1: True}, f_local=1e9,
        ),
    }
    uavs = {
        0: UAV(
            index=0, pos=(500.0, 500.0), pos_final=(500.0, 500.0),
            E_max=100.0, f_max=4e9,
        ),
    }
    meta = {"x_max": x_max, "y_max": y_max}
    return EdgeUavScenario(
        tasks=tasks, uavs=uavs, time_slots=[0, 1, 2], seed=42, meta=meta,
    )


def _make_valid_snapshot(scenario: EdgeUavScenario) -> Level2Snapshot:
    """构造完全合法的 dense 快照。"""
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
    return Level2Snapshot(q=q, f_edge=f_edge, source="init")


# =====================================================================
# 测试：合法快照
# =====================================================================

class TestValidSnapshot:
    def test_valid_dense_snapshot_passes(self):
        """合法 dense 快照，validate 无异常。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        snap.validate(scenario)  # 不应 raise

    def test_valid_snapshot_without_bounds(self):
        """meta 不含 x_max/y_max 时跳过边界检查。"""
        scenario = _make_scenario()
        scenario.meta = {}
        snap = _make_valid_snapshot(scenario)
        snap.validate(scenario)

    def test_valid_snapshot_require_dense_false(self):
        """require_dense=False 时允许 f_edge 稀疏。"""
        scenario = _make_scenario()
        snap = Level2Snapshot(
            q={0: {t: (500.0, 500.0) for t in scenario.time_slots}},
            f_edge={0: {0: {0: 1e9}}},  # 稀疏
            source="custom",
        )
        snap.validate(scenario, require_dense=False)


# =====================================================================
# 测试：检查 1 — q 覆盖
# =====================================================================

class TestQCoverage:
    def test_missing_single_timeslot(self):
        """缺 q[0][2] → 报 1 个错误。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        del snap.q[0][2]

        with pytest.raises(ValueError, match=r"q missing key \(j=0, t=2\)"):
            snap.validate(scenario)

    def test_missing_entire_uav(self):
        """缺整个 q[0] → 报 len(time_slots) 个错误。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        del snap.q[0]

        with pytest.raises(ValueError) as exc_info:
            snap.validate(scenario)
        msg = str(exc_info.value)
        for t in scenario.time_slots:
            assert f"q missing key (j=0, t={t})" in msg


# =====================================================================
# 测试：检查 2 — f_edge 覆盖（require_dense）
# =====================================================================

class TestFEdgeCoverage:
    def test_missing_single_entry(self):
        """缺 f_edge[0][1][2] → 报错。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        del snap.f_edge[0][1][2]

        with pytest.raises(ValueError, match=r"f_edge missing key \(j=0, i=1, t=2\)"):
            snap.validate(scenario)

    def test_missing_entire_task(self):
        """缺整个 f_edge[0][1] → 报 len(time_slots) 个错误。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        del snap.f_edge[0][1]

        with pytest.raises(ValueError) as exc_info:
            snap.validate(scenario)
        msg = str(exc_info.value)
        for t in scenario.time_slots:
            assert f"f_edge missing key (j=0, i=1, t={t})" in msg


# =====================================================================
# 测试：检查 3 — f_edge 值 > 0
# =====================================================================

class TestFEdgePositive:
    def test_negative_frequency(self):
        """负频率 → 报错。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        snap.f_edge[0][0][0] = -1.0

        with pytest.raises(ValueError, match=r"f_edge\[0\]\[0\]\[0\] = -1\.0 <= 0"):
            snap.validate(scenario)

    def test_zero_frequency(self):
        """零频率 → 报错。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        snap.f_edge[0][1][1] = 0.0

        with pytest.raises(ValueError, match=r"<= 0"):
            snap.validate(scenario)


# =====================================================================
# 测试：检查 4 — 位置边界
# =====================================================================

class TestBoundsCheck:
    def test_negative_x(self):
        """x < 0 → 越界。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        snap.q[0][0] = (-10.0, 500.0)

        with pytest.raises(ValueError, match=r"out of bounds"):
            snap.validate(scenario)

    def test_exceeds_x_max(self):
        """x > x_max → 越界。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        snap.q[0][1] = (1500.0, 500.0)

        with pytest.raises(ValueError, match=r"out of bounds"):
            snap.validate(scenario)

    def test_negative_y(self):
        """y < 0 → 越界。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        snap.q[0][2] = (500.0, -5.0)

        with pytest.raises(ValueError, match=r"out of bounds"):
            snap.validate(scenario)

    def test_boundary_exactly_at_max(self):
        """恰好在边界上（x=x_max, y=y_max）→ 合法。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        snap.q[0][0] = (1000.0, 1000.0)
        snap.validate(scenario)  # 不应 raise

    def test_boundary_at_origin(self):
        """恰好在原点（0, 0）→ 合法。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        snap.q[0][0] = (0.0, 0.0)
        snap.validate(scenario)  # 不应 raise


# =====================================================================
# 测试：检查 5 — f_local_override 覆盖
# =====================================================================

class TestFLocalOverride:
    def test_valid_override_passes(self):
        """完整的 f_local_override → 无异常。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        f_override = {
            i: {t: 1e9 for t in scenario.time_slots}
            for i in scenario.tasks
        }
        snap2 = Level2Snapshot(
            q=snap.q, f_edge=snap.f_edge,
            f_local_override=f_override, source="init",
        )
        snap2.validate(scenario)

    def test_missing_override_entry(self):
        """f_local_override 缺 (i=1, t=2) → 报错。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        f_override = {
            i: {t: 1e9 for t in scenario.time_slots}
            for i in scenario.tasks
        }
        del f_override[1][2]
        snap2 = Level2Snapshot(
            q=snap.q, f_edge=snap.f_edge,
            f_local_override=f_override, source="init",
        )
        with pytest.raises(ValueError, match=r"f_local_override missing \(i=1, t=2\)"):
            snap2.validate(scenario)

    def test_none_override_skips_check(self):
        """f_local_override=None → 跳过检查 5。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        snap.validate(scenario)  # source 为 None 已在 _make_valid_snapshot 中


# =====================================================================
# 测试：多错误累积
# =====================================================================

class TestCodexReviewEdgeCases:
    """Codex review 指出的补充边界测试。"""

    def test_f_edge_entire_uav_missing(self):
        """f_edge 缺整个 j=0 → 报 len(tasks)*len(time_slots) 个错误。"""
        scenario = _make_scenario()
        snap = Level2Snapshot(
            q={0: {t: (500.0, 500.0) for t in scenario.time_slots}},
            f_edge={},  # 整个 j=0 缺失
            source="init",
        )
        with pytest.raises(ValueError) as exc_info:
            snap.validate(scenario)
        msg = str(exc_info.value)
        for i in scenario.tasks:
            for t in scenario.time_slots:
                assert f"f_edge missing key (j=0, i={i}, t={t})" in msg

    def test_f_local_override_entire_task_missing(self):
        """f_local_override 缺整个 i=1 → 报 len(time_slots) 个错误。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        f_override = {0: {t: 1e9 for t in scenario.time_slots}}  # 缺 i=1
        snap2 = Level2Snapshot(
            q=snap.q, f_edge=snap.f_edge,
            f_local_override=f_override, source="init",
        )
        with pytest.raises(ValueError) as exc_info:
            snap2.validate(scenario)
        msg = str(exc_info.value)
        for t in scenario.time_slots:
            assert f"f_local_override missing (i=1, t={t})" in msg

    def test_require_dense_false_still_rejects_negative_freq(self):
        """require_dense=False 时仍拒绝已有的负频率。"""
        scenario = _make_scenario()
        snap = Level2Snapshot(
            q={0: {t: (500.0, 500.0) for t in scenario.time_slots}},
            f_edge={0: {0: {0: -5.0}}},  # 稀疏但有负值
            source="custom",
        )
        with pytest.raises(ValueError, match=r"<= 0"):
            snap.validate(scenario, require_dense=False)


# =====================================================================
# 测试：多错误累积
# =====================================================================

class TestMultipleErrors:
    def test_two_errors_accumulated(self):
        """同时缺 q key + 负频率 → 报 ≥2 个错误。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        del snap.q[0][2]
        snap.f_edge[0][0][0] = -1.0

        with pytest.raises(ValueError) as exc_info:
            snap.validate(scenario)
        msg = str(exc_info.value)
        assert "2 errors" in msg
        assert "q missing key (j=0, t=2)" in msg
        assert "f_edge[0][0][0] = -1.0 <= 0" in msg

    def test_three_different_types(self):
        """缺 q key + 负频率 + 越界 → 报 ≥3 个错误。"""
        scenario = _make_scenario()
        snap = _make_valid_snapshot(scenario)
        del snap.q[0][2]           # 检查 1
        snap.f_edge[0][0][0] = -1.0  # 检查 3
        snap.q[0][1] = (-10.0, 500.0)  # 检查 4

        with pytest.raises(ValueError) as exc_info:
            snap.validate(scenario)
        msg = str(exc_info.value)
        assert "q missing key" in msg
        assert "<= 0" in msg
        assert "out of bounds" in msg


class TestSeparatedDiagnostics:
    def test_assigned_feasible_ratio_is_none_when_no_pairs_are_assigned(self):
        """assigned_pairs == 0 should be reported as None, not 0.0."""
        scenario = _make_scenario()
        zero_snapshot = Level2Snapshot(
            q={0: {t: (500.0, 500.0) for t in scenario.time_slots}},
            f_edge={
                0: {
                    i: {t: 0.0 for t in scenario.time_slots}
                    for i in scenario.tasks
                }
            },
            source="zero_alloc",
        )

        diagnostics = _build_diagnostics(
            D_hat_local={0: {0: 1.0}, 1: {0: 1.0}},
            D_hat_offload={
                0: {0: {0: 2.0, 1: 2.0}},
                1: {0: {0: 2.0, 1: 2.0}},
            },
            E_hat_comp={0: {0: {0: 0.0, 1: 0.0}, 1: {0: 0.0, 1: 0.0}}},
            tasks=scenario.tasks,
            snapshot_source="custom",
            guard_hits={},
            active_task_slots=2,
            candidate_offload_pairs=4,
            deadline_feasible_pairs=0,
            uplink_rates=[1.0],
            downlink_rates=[1.0],
            tasks_all_uavs_infeasible=[],
            tasks_local_over_tau=[],
            snapshot=zero_snapshot,
            eps_freq=1e-12,
        )

        assert diagnostics["assigned_pairs"] == 0
        assert diagnostics["unassigned_pairs"] == 4
        assert diagnostics["assigned_feasible_ratio"] is None
