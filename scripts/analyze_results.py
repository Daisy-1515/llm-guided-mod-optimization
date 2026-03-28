"""Phase⑤ 首跑结果分析 — S1-S4 成功判据检测。

用法:
    .venv/Scripts/python scripts/analyze_results.py
    .venv/Scripts/python scripts/analyze_results.py --run-dir discussion/20260320_143012
    .venv/Scripts/python scripts/analyze_results.py --expected-pop-size 3 --expected-iterations 3

如果不指定 --expected-iterations，脚本会尝试从 config/setting.cfg 读取。
"""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from configparser import ConfigParser

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


GEN_FILE_RE = re.compile(r"population_result_(\d+)\.json$")


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

def _read_config_iteration():
    """从 config/setting.cfg 读取 iteration 值，失败则返回 None。"""
    config_path = Path("config/setting.cfg")
    if not config_path.exists():
        return None
    try:
        parser = ConfigParser()
        parser.read(config_path)
        return parser.getint("hsSettings", "iteration")
    except Exception:
        return None


def _resolve_run_dir(run_dir_arg):
    """定位结果目录：显式指定 > 自动取最新 discussion/YYYYMMDD_*/。"""
    if run_dir_arg:
        path = Path(run_dir_arg)
    else:
        candidates = sorted(
            p for p in Path("discussion").glob("20*_*") if p.is_dir()
        )
        if not candidates:
            raise FileNotFoundError("no discussion/YYYYMMDD_* directories found")
        path = candidates[-1]
    if not path.is_dir():
        raise FileNotFoundError(f"run_dir not found: {path}")
    return path


def _collect_generation_files(run_dir):
    """收集并按代号排序的 population_result_N.json 文件。"""
    files = []
    for p in run_dir.glob("population_result_*.json"):
        m = GEN_FILE_RE.match(p.name)
        if m:
            files.append((int(m.group(1)), p))
    return sorted(files)


def _load_generation(path):
    """安全加载单代 JSON，损坏时返回 None。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARN: skip unreadable JSON {path}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, list):
        print(f"WARN: skip non-list JSON {path}", file=sys.stderr)
        return None
    return data


def _get_step(individual):
    """提取 simulation_steps 中第 0 步（兼容字符串/整数 key）。"""
    steps = individual.get("simulation_steps") or {}
    return steps.get("0") or steps.get(0) or {}


def _summarize_generation(data):
    """计算单代个体的关键统计。"""
    ok = 0
    custom_obj_ok = 0
    feasible = 0
    scores = []

    for ind in data:
        if not isinstance(ind, dict):
            continue
        step = _get_step(ind)
        status = step.get("llm_status", "unknown")
        used_default = bool(step.get("used_default_obj", True))

        if status == "ok":
            ok += 1
            if not used_default:
                custom_obj_ok += 1
        if bool(step.get("feasible", False)):
            feasible += 1

        try:
            scores.append(float(ind["evaluation_score"]))
        except (KeyError, TypeError, ValueError):
            pass

    return {
        "n": len(data),
        "ok": ok,
        "custom_obj_ok": custom_obj_ok,
        "feasible": feasible,
        "best_evaluation_score": min(scores) if scores else None,
    }


def _resolve_experiment_dir(path_arg):
    if path_arg:
        path = Path(path_arg)
    else:
        base = Path("discussion/experiment_results")
        candidates = sorted(p for p in base.glob("20*_*") if p.is_dir())
        if not candidates:
            raise FileNotFoundError("no discussion/experiment_results/YYYYMMDD_* found")
        path = candidates[-1]
    if not path.is_dir():
        raise FileNotFoundError(f"experiment_dir not found: {path}")
    return path


def load_experiment_runs(experiment_dir):
    runs = []
    for path in sorted(Path(experiment_dir).glob("*/run_seed_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARN: skip unreadable JSON {path}: {exc}", file=sys.stderr)
            continue
        if isinstance(payload, dict):
            runs.append(payload)
    return runs


def summarize_experiment_runs(runs):
    grouped = {}
    for run in runs:
        grouped.setdefault(run["group"], []).append(run)

    summary = {}
    for group, group_runs in grouped.items():
        best_costs = [float(run["metrics"]["best_cost"]) for run in group_runs]
        feasible_rates = [float(run["metrics"]["feasible_rate"]) for run in group_runs]
        wall_times = [float(run["wall_time_sec"]) for run in group_runs]
        llm_calls = [int(run["search"]["llm_calls"]) for run in group_runs]
        summary[group] = {
            "runs": len(group_runs),
            "seeds": [run["seed"] for run in group_runs],
            "best_cost_mean": statistics.fmean(best_costs),
            "best_cost_std": statistics.pstdev(best_costs) if len(best_costs) > 1 else 0.0,
            "best_cost_min": min(best_costs),
            "feasible_rate_mean": statistics.fmean(feasible_rates),
            "wall_time_mean_sec": statistics.fmean(wall_times),
            "llm_calls_mean": statistics.fmean(llm_calls),
        }
    return summary


def _analyze_experiment_dir(experiment_dir_arg):
    try:
        experiment_dir = _resolve_experiment_dir(experiment_dir_arg)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    runs = load_experiment_runs(experiment_dir)
    if not runs:
        print(f"ERROR: no run_seed_*.json found under {experiment_dir}", file=sys.stderr)
        return 1

    summary = summarize_experiment_runs(runs)
    print(f"experiment_dir={experiment_dir}  run_files={len(runs)}")
    print("=" * 72)
    for group in sorted(summary):
        row = summary[group]
        print(
            f"{group:>2}  runs={row['runs']}  seeds={row['seeds']}  "
            f"best_mean={row['best_cost_mean']:.4f}  "
            f"best_std={row['best_cost_std']:.4f}  "
            f"best_min={row['best_cost_min']:.4f}  "
            f"feasible_mean={row['feasible_rate_mean']:.3f}  "
            f"llm_calls_mean={row['llm_calls_mean']:.1f}  "
            f"time_mean={row['wall_time_mean_sec']:.2f}s"
        )
    return 0


# ─── 主函数 ──────────────────��────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Phase⑤ 首跑结果分析")
    parser.add_argument("--run-dir", help="结果目录（默认取最新）")
    parser.add_argument("--expected-pop-size", type=int, default=None)
    parser.add_argument("--expected-iterations", type=int, default=None)
    args = parser.parse_args()

    # 如果未指定 expected_iterations，尝试从 config 读取
    if args.expected_iterations is None:
        config_iter = _read_config_iteration()
        if config_iter is not None:
            args.expected_iterations = config_iter
        else:
            args.expected_iterations = 3  # 默认备选值

    try:
        run_dir = _resolve_run_dir(args.run_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    gen_files = _collect_generation_files(run_dir)
    print(f"run_dir={run_dir}  json_files={len(gen_files)} expected_iterations={args.expected_iterations}")
    print("=" * 72)

    # ---- 每代摘要 ----
    summaries = {}
    for gen, path in gen_files:
        data = _load_generation(path)
        if data is None:
            continue
        s = _summarize_generation(data)
        summaries[gen] = s
        best = s["best_evaluation_score"]
        best_text = "N/A" if best is None else f"{best:.4f}"
        print(
            f"Gen {gen:>2}: "
            f"n={s['n']}/{args.expected_pop_size}  "
            f"ok={s['ok']}  "
            f"custom_obj={s['custom_obj_ok']}  "
            f"feasible={s['feasible']}  "
            f"best={best_text}"
        )

    print("=" * 72)

    # ---- S1-S4 判定 ----
    final_gen = max((g for g, _ in gen_files), default=None)
    final = summaries.get(final_gen)

    # S1: JSON 文件数 == expected_iterations
    s1 = "PASS" if len(gen_files) == args.expected_iterations else "FAIL"
    print(f"S1 {s1}: json_files={len(gen_files)} expected={args.expected_iterations}")

    if final is None:
        print("S2 UNKNOWN: no readable generation data")
        print("S3 UNKNOWN: no readable generation data")
        print("S4 UNKNOWN: baseline unavailable")
        return 0

    # S2: ≥1 个体 llm_status=ok 且 used_default_obj=false
    s2 = "PASS" if final["custom_obj_ok"] >= 1 else "FAIL"
    print(f"S2 {s2}: final gen {final_gen} custom_obj_ok={final['custom_obj_ok']}")

    # S3: ≥1 个体 feasible=true
    s3 = "PASS" if final["feasible"] >= 1 else "FAIL"
    print(f"S3 {s3}: final gen {final_gen} feasible={final['feasible']}")

    # S4: 记录基线 evaluation_score
    if final["best_evaluation_score"] is not None:
        print(f"S4 PASS: baseline best_evaluation_score={final['best_evaluation_score']:.4f}")
    else:
        print(f"S4 UNKNOWN: final gen {final_gen} best_evaluation_score unavailable")

    return 0


def main_cli():
    if "--experiment-dir" in sys.argv:
        try:
            exp_index = sys.argv.index("--experiment-dir")
            experiment_dir = sys.argv[exp_index + 1]
        except IndexError:
            print("ERROR: --experiment-dir requires a path", file=sys.stderr)
            return 1
        return _analyze_experiment_dir(experiment_dir)
    return main()


if __name__ == "__main__":
    raise SystemExit(main_cli())
