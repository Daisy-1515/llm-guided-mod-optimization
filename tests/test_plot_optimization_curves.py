import json
from pathlib import Path

from scripts import plot_optimization_curves as poc



def _write_run_payload(exp_dir: Path, group: str, seed: int, *, num_tasks: int, num_uavs: int, t: int = 40, use_bcd_loop: bool = True, best_cost: float = 10.0, mean_cost: float = 12.0, feasible_rate: float = 1.0, history_scores=None, best_so_far=None):
    group_dir = exp_dir / group
    group_dir.mkdir(parents=True, exist_ok=True)
    history_scores = history_scores or [best_cost]
    best_so_far = best_so_far or [
        {"evaluation_index": idx, "best_cost": score}
        for idx, score in enumerate(sorted(history_scores, reverse=True), start=1)
    ]
    payload = {
        "schema_version": "experiment-run-v1",
        "group": group,
        "label": group,
        "seed": seed,
        "scenario": {
            "numTasks": num_tasks,
            "numUAVs": num_uavs,
            "T": t,
            "use_bcd_loop": use_bcd_loop,
        },
        "search": {
            "pop_size": 20,
            "iterations": 8,
            "eval_budget_target": len(history_scores),
            "eval_budget_used": len(history_scores),
            "llm_calls": 0 if group == "D1" else len(history_scores),
        },
        "wall_time_sec": 5.0,
        "metrics": {
            "best_cost": best_cost,
            "mean_cost": mean_cost,
            "std_cost": 0.0,
            "feasible_rate": feasible_rate,
            "best_so_far": best_so_far,
        },
        "history": [
            {"evaluation_index": idx + 1, "generation": idx, "score": score}
            for idx, score in enumerate(history_scores)
        ],
    }
    path = group_dir / f"run_seed_{seed}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path



def test_load_experiment_data_groups_runs_by_seed_and_group(tmp_path):
    exp_dir = tmp_path / "20260418_120000"
    _write_run_payload(exp_dir, "A", 42, num_tasks=15, num_uavs=3, history_scores=[15.0, 12.0])
    _write_run_payload(exp_dir, "D1", 42, num_tasks=15, num_uavs=3, history_scores=[18.0])
    _write_run_payload(exp_dir, "A", 43, num_tasks=20, num_uavs=3, history_scores=[14.0, 11.0])

    data = poc.load_experiment_data(exp_dir)

    assert set(data.keys()) == {42, 43}
    assert set(data[42].keys()) == {"A", "D1"}
    assert data[42]["A"]["history_by_gen"] == {0: [15.0], 1: [12.0]}
    assert data[43]["A"]["scenario"]["numTasks"] == 20



def test_resolve_experiment_dirs_supports_root_and_single_dir(tmp_path):
    root = tmp_path / "experiment_results"
    exp_a = root / "20260418_120000"
    exp_b = root / "20260418_130000"
    _write_run_payload(exp_a, "A", 42, num_tasks=15, num_uavs=3)
    _write_run_payload(exp_b, "A", 43, num_tasks=20, num_uavs=3)

    all_dirs = poc.resolve_experiment_dirs(str(root), root)
    single_dir = poc.resolve_experiment_dirs(str(exp_a), root)

    assert all_dirs == [exp_a, exp_b]
    assert single_dir == [exp_a]



def test_normalize_run_record_extracts_core_fields(tmp_path):
    exp_dir = tmp_path / "20260418_120000"
    run_path = _write_run_payload(exp_dir, "A", 42, num_tasks=15, num_uavs=3, history_scores=[15.0, 12.0], best_cost=12.0, mean_cost=13.5)
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    payload["__exp_dir__"] = str(exp_dir)
    payload["__exp_name__"] = exp_dir.name
    payload["__run_path__"] = str(run_path)

    record = poc.normalize_run_record(payload)

    assert record["group"] == "A"
    assert record["seed"] == 42
    assert record["numTasks"] == 15
    assert record["numUAVs"] == 3
    assert record["best_cost"] == 12.0
    assert record["mean_cost"] == 13.5
    assert record["history_len"] == 2
    assert record["budget_match_ok"] is True
    assert record["best_matches_history_min"] is True



def test_aggregate_sweep_series_by_group_computes_mean_and_std():
    records = [
        {
            "group": "A", "seed": 42, "numTasks": 15, "numUAVs": 3,
            "T": 40, "use_bcd_loop": True, "pop_size": 20, "iterations": 8,
            "best_cost": 10.0, "mean_cost": 11.0, "feasible_rate": 1.0, "exp_name": "exp1",
        },
        {
            "group": "A", "seed": 43, "numTasks": 15, "numUAVs": 3,
            "T": 40, "use_bcd_loop": True, "pop_size": 20, "iterations": 8,
            "best_cost": 14.0, "mean_cost": 15.0, "feasible_rate": 1.0, "exp_name": "exp2",
        },
        {
            "group": "D1", "seed": 42, "numTasks": 15, "numUAVs": 3,
            "T": 40, "use_bcd_loop": True, "pop_size": 20, "iterations": 8,
            "best_cost": 20.0, "mean_cost": 20.0, "feasible_rate": 1.0, "exp_name": "exp1",
        },
    ]

    series = poc.aggregate_sweep_series(records, series_field="group", metric="best_cost")

    assert [item["series_key"] for item in series] == ["A", "D1"]
    a_point = series[0]["points"][0]
    assert a_point["x"] == 15
    assert a_point["mean"] == 12.0
    assert a_point["std"] == 2.0
    assert a_point["seeds"] == [42, 43]



def test_compute_sweep_coverage_reports_missing_cells():
    records = [
        {
            "group": "A", "seed": 42, "numTasks": 15, "numUAVs": 3,
            "T": 40, "use_bcd_loop": True, "pop_size": 20, "iterations": 8,
            "best_cost": 10.0, "feasible_rate": 1.0, "exp_name": "exp1",
        },
        {
            "group": "D1", "seed": 42, "numTasks": 20, "numUAVs": 3,
            "T": 40, "use_bcd_loop": True, "pop_size": 20, "iterations": 8,
            "best_cost": 20.0, "feasible_rate": 1.0, "exp_name": "exp1",
        },
    ]

    report = poc.compute_sweep_coverage(records, series_field="group", metric="best_cost")

    assert report["x_values"] == [15, 20]
    assert report["series_values"] == ["A", "D1"]
    assert {tuple(item.values()) for item in report["missing"]} == {("A", 20), ("D1", 15)}



def test_validate_sweep_records_rejects_mixed_configurations():
    records = [
        {
            "group": "A", "seed": 42, "numTasks": 15, "numUAVs": 3,
            "T": 40, "use_bcd_loop": True, "pop_size": 20, "iterations": 8,
        },
        {
            "group": "A", "seed": 43, "numTasks": 20, "numUAVs": 3,
            "T": 80, "use_bcd_loop": True, "pop_size": 20, "iterations": 8,
        },
    ]

    try:
        poc.validate_sweep_records(records, "ue-sweep-by-group", fixed_num_uavs=3)
    except ValueError as exc:
        assert "mixed T" in str(exc)
    else:
        raise AssertionError("expected ValueError for mixed T")



def test_filter_sweep_records_applies_group_and_num_uavs_constraints():
    records = [
        {
            "group": "A", "seed": 42, "numTasks": 15, "numUAVs": 3,
            "T": 40, "use_bcd_loop": True, "pop_size": 20, "iterations": 8,
        },
        {
            "group": "A", "seed": 43, "numTasks": 20, "numUAVs": 5,
            "T": 40, "use_bcd_loop": True, "pop_size": 20, "iterations": 8,
        },
        {
            "group": "D1", "seed": 44, "numTasks": 20, "numUAVs": 3,
            "T": 40, "use_bcd_loop": True, "pop_size": 20, "iterations": 8,
        },
    ]

    filtered = poc.filter_sweep_records(records, fixed_num_uavs=3, fixed_group="A")

    assert filtered == [records[0]]



def test_run_convergence_mode_writes_png(tmp_path):
    exp_dir = tmp_path / "20260418_120000"
    _write_run_payload(exp_dir, "A", 42, num_tasks=15, num_uavs=3, history_scores=[15.0, 12.0])
    _write_run_payload(exp_dir, "D1", 42, num_tasks=15, num_uavs=3, history_scores=[18.0])

    output_dir = tmp_path / "plots"
    rc = poc.run_convergence_mode([exp_dir], output_dir)

    assert rc == 0
    assert (output_dir / exp_dir.name / "seed_42.png").exists()



def test_run_sweep_mode_writes_outputs(tmp_path):
    exp_dir = tmp_path / "20260418_120000"
    _write_run_payload(exp_dir, "A", 42, num_tasks=15, num_uavs=3, best_cost=10.0)
    _write_run_payload(exp_dir, "A", 43, num_tasks=20, num_uavs=3, best_cost=12.0)
    _write_run_payload(exp_dir, "D1", 42, num_tasks=15, num_uavs=3, best_cost=20.0)
    _write_run_payload(exp_dir, "D1", 43, num_tasks=20, num_uavs=3, best_cost=22.0)

    class Args:
        mode = "ue-sweep-by-group"
        metric = "best_cost"
        num_uavs = 3
        group = None
        t = None
        use_bcd_loop = None
        seeds = None

    output_dir = tmp_path / "plots"
    rc = poc.run_sweep_mode(Args(), [exp_dir], output_dir)

    assert rc == 0
    sweep_dir = output_dir / "sweeps"
    assert any(path.suffix == ".png" for path in sweep_dir.iterdir())
    assert any(path.name.endswith(".coverage.json") for path in sweep_dir.iterdir())
