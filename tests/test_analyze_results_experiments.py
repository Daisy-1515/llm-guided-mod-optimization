import json

from scripts.analyze_results import load_experiment_runs, summarize_experiment_runs


def test_summarize_experiment_runs(tmp_path):
    run_root = tmp_path / "experiment_results"
    group_a = run_root / "A"
    group_b = run_root / "B"
    group_a.mkdir(parents=True)
    group_b.mkdir(parents=True)

    payload_a = {
        "group": "A",
        "seed": 42,
        "metrics": {"best_cost": 10.0, "feasible_rate": 1.0},
        "wall_time_sec": 5.0,
        "search": {"llm_calls": 50},
    }
    payload_b = {
        "group": "B",
        "seed": 43,
        "metrics": {"best_cost": 12.0, "feasible_rate": 0.8},
        "wall_time_sec": 6.0,
        "search": {"llm_calls": 50},
    }

    (group_a / "run_seed_42.json").write_text(json.dumps(payload_a), encoding="utf-8")
    (group_b / "run_seed_43.json").write_text(json.dumps(payload_b), encoding="utf-8")

    runs = load_experiment_runs(run_root)
    summary = summarize_experiment_runs(runs)

    assert set(summary) == {"A", "B"}
    assert summary["A"]["runs"] == 1
    assert summary["A"]["best_cost_mean"] == 10.0
    assert summary["A"]["feasible_rate_mean"] == 1.0
    assert summary["B"]["llm_calls_mean"] == 50
