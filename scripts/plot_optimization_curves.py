"""绘制实验目标函数收敛曲线与 UE sweep 折线图。

用法:
    uv run python scripts/plot_optimization_curves.py
    uv run python scripts/plot_optimization_curves.py --exp-dir discussion/experiment_results/20260402_214943
    uv run python scripts/plot_optimization_curves.py --mode ue-sweep-by-group --metric best_cost --num-uavs 3
    uv run python scripts/plot_optimization_curves.py --mode ue-sweep-by-uavs --metric best_cost --group A
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GROUP_COLORS = {
    "A": "#2196F3",
    "D1": "#F44336",
    "B": "#4CAF50",
    "C1": "#FF9800",
    "C2": "#9C27B0",
}
DEFAULT_COLOR = "#607D8B"
METRIC_LABELS = {
    "best_cost": "Best Cost",
    "mean_cost": "Mean Cost",
    "std_cost": "Cost Std",
    "feasible_rate": "Feasible Rate",
    "wall_time_sec": "Wall Time (s)",
    "llm_calls": "LLM Calls",
}
SWEEP_MODES = {"ue-sweep-by-group", "ue-sweep-by-uavs", "comparison-json", "csv-ablation-bars"}


# ─── 数据层：收敛图复用 ────────────────────────────────────────────────────────

def scan_experiment_dirs(base_dir: Path):
    """返回所有含 run_seed_*.json 的非空实验目录。"""
    dirs = []
    for exp_dir in sorted(base_dir.glob("20*_*")):
        if not exp_dir.is_dir():
            continue
        if any(exp_dir.glob("*/run_seed_*.json")):
            dirs.append(exp_dir)
    return dirs


def load_experiment_data(exp_dir: Path):
    """加载单个实验目录的所有数据。

    Returns:
        {seed: {group: RunData}}
        RunData = {scenario, group, label, best_so_far, history_by_gen}
    """
    by_seed = defaultdict(dict)
    for path in sorted(exp_dir.glob("*/run_seed_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARN: skip {path}: {exc}", file=sys.stderr)
            continue
        if not isinstance(payload, dict):
            continue

        group = payload.get("group", path.parent.name)
        seed = payload.get("seed")
        if seed is None:
            continue

        best_so_far = payload.get("metrics", {}).get("best_so_far", [])

        history_by_gen = defaultdict(list)
        for entry in payload.get("history", []):
            gen = entry.get("generation")
            score = entry.get("score")
            if gen is not None and score is not None:
                history_by_gen[gen].append(float(score))

        by_seed[seed][group] = {
            "scenario": payload.get("scenario", {}),
            "group": group,
            "label": payload.get("label", group),
            "best_so_far": best_so_far,
            "history_by_gen": dict(history_by_gen),
        }
    return dict(by_seed)


# ─── 数据层：sweep 图新增 ──────────────────────────────────────────────────────

def resolve_experiment_dirs(exp_dir_arg: str | None, base_dir: Path) -> list[Path]:
    """解析实验目录。

    - 未提供 exp_dir 时：扫描 base_dir 下所有 timestamp 目录
    - 提供 exp_dir 且其本身含 run_seed_*.json 时：返回该目录
    - 提供 exp_dir 且其下是多个 timestamp 目录时：扫描其子目录
    """
    if exp_dir_arg:
        path = Path(exp_dir_arg)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_dir():
            raise FileNotFoundError(f"experiment_dir not found: {path}")
        if any(path.glob("*/run_seed_*.json")):
            return [path]
        exp_dirs = scan_experiment_dirs(path)
        if exp_dirs:
            return exp_dirs
        raise FileNotFoundError(f"no experiment directories found under: {path}")

    exp_dirs = scan_experiment_dirs(base_dir)
    if not exp_dirs:
        raise FileNotFoundError(f"no experiment directories found under: {base_dir}")
    return exp_dirs


def load_run_payloads(exp_dirs: list[Path]):
    """跨多个实验目录读取所有 run_seed_*.json。"""
    payloads = []
    for exp_dir in exp_dirs:
        for path in sorted(exp_dir.glob("*/run_seed_*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                print(f"WARN: skip {path}: {exc}", file=sys.stderr)
                continue
            if not isinstance(payload, dict):
                continue
            payload = dict(payload)
            payload["__exp_dir__"] = str(exp_dir)
            payload["__exp_name__"] = exp_dir.name
            payload["__run_path__"] = str(path)
            payloads.append(payload)
    return payloads


def normalize_run_record(payload: dict):
    """将 run_seed JSON 转为扁平记录。"""
    scenario = payload.get("scenario", {})
    metrics = payload.get("metrics", {})
    search = payload.get("search", {})
    history = payload.get("history", [])

    group = payload.get("group")
    seed = payload.get("seed")
    num_tasks = scenario.get("numTasks")
    num_uavs = scenario.get("numUAVs")
    if group is None or seed is None or num_tasks is None or num_uavs is None:
        return None

    scores = [float(entry["score"]) for entry in history if entry.get("score") is not None]
    best_cost = metrics.get("best_cost")
    best_matches_history_min = None
    if best_cost is not None and scores:
        best_matches_history_min = abs(float(best_cost) - min(scores)) < 1e-9

    eval_budget_used = search.get("eval_budget_used")
    history_len = len(history)
    budget_match_ok = None
    if eval_budget_used is not None:
        budget_match_ok = history_len == int(eval_budget_used)

    return {
        "schema_version": payload.get("schema_version"),
        "exp_dir": payload.get("__exp_dir__"),
        "exp_name": payload.get("__exp_name__"),
        "run_path": payload.get("__run_path__"),
        "group": str(group),
        "label": payload.get("label", group),
        "seed": int(seed),
        "numTasks": int(num_tasks),
        "numUAVs": int(num_uavs),
        "T": scenario.get("T"),
        "use_bcd_loop": scenario.get("use_bcd_loop"),
        "pop_size": search.get("pop_size"),
        "iterations": search.get("iterations"),
        "eval_budget_target": search.get("eval_budget_target"),
        "eval_budget_used": eval_budget_used,
        "llm_calls": search.get("llm_calls"),
        "best_cost": metrics.get("best_cost"),
        "mean_cost": metrics.get("mean_cost"),
        "std_cost": metrics.get("std_cost"),
        "feasible_rate": metrics.get("feasible_rate"),
        "wall_time_sec": payload.get("wall_time_sec"),
        "source_run_dir": payload.get("source_run_dir"),
        "history_len": history_len,
        "best_so_far_len": len(metrics.get("best_so_far", [])),
        "budget_match_ok": budget_match_ok,
        "best_matches_history_min": best_matches_history_min,
    }


def parse_optional_bool(value: str | None):
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected one of: true, false")


def filter_sweep_records(
    records,
    *,
    fixed_num_uavs=None,
    fixed_group=None,
    fixed_use_bcd=None,
    fixed_T=None,
    seeds=None,
):
    filtered = []
    allowed_seeds = set(seeds) if seeds else None
    for record in records:
        if fixed_num_uavs is not None and record["numUAVs"] != fixed_num_uavs:
            continue
        if fixed_group is not None and record["group"] != fixed_group:
            continue
        if fixed_use_bcd is not None and record["use_bcd_loop"] != fixed_use_bcd:
            continue
        if fixed_T is not None and record["T"] != fixed_T:
            continue
        if allowed_seeds is not None and record["seed"] not in allowed_seeds:
            continue
        filtered.append(record)
    return filtered


def _sorted_unique(values):
    unique = {value for value in values if value is not None}
    return sorted(unique)


def _require_singleton(records, field, description):
    values = _sorted_unique(record[field] for record in records)
    if len(values) > 1:
        joined = ", ".join(str(v) for v in values)
        raise ValueError(f"mixed {description}: {joined}. Add filters before drawing sweep plots.")
    return values[0] if values else None


def validate_sweep_records(records, mode: str, *, fixed_num_uavs=None, fixed_group=None):
    if not records:
        raise ValueError("no records remain after filtering")

    _require_singleton(records, "T", "T")
    _require_singleton(records, "use_bcd_loop", "use_bcd_loop")
    _require_singleton(records, "pop_size", "pop_size")
    _require_singleton(records, "iterations", "iterations")

    if mode == "ue-sweep-by-group":
        if fixed_num_uavs is None:
            _require_singleton(records, "numUAVs", "numUAVs")
    elif mode == "ue-sweep-by-uavs":
        if fixed_group is None:
            _require_singleton(records, "group", "group")



def aggregate_sweep_series(records, *, series_field: str, metric: str):
    grouped = defaultdict(list)
    for record in records:
        metric_value = record.get(metric)
        if metric_value is None:
            continue
        grouped[(record[series_field], record["numTasks"])].append(record)

    series_map = defaultdict(list)
    for (series_key, x_value), rows in grouped.items():
        metric_values = [float(row[metric]) for row in rows if row.get(metric) is not None]
        if not metric_values:
            continue
        series_map[series_key].append(
            {
                "x": int(x_value),
                "mean": statistics.fmean(metric_values),
                "std": statistics.pstdev(metric_values) if len(metric_values) > 1 else 0.0,
                "n_runs": len(rows),
                "seeds": sorted({int(row["seed"]) for row in rows}),
                "exp_names": sorted({row["exp_name"] for row in rows if row.get("exp_name")}),
                "metric_values": metric_values,
                "feasible_rate_mean": statistics.fmean(
                    float(row["feasible_rate"]) for row in rows if row.get("feasible_rate") is not None
                ) if any(row.get("feasible_rate") is not None for row in rows) else None,
            }
        )

    output = []
    for series_key in sorted(series_map):
        output.append(
            {
                "series_key": series_key,
                "label": _format_series_label(series_field, series_key),
                "points": sorted(series_map[series_key], key=lambda item: item["x"]),
            }
        )
    return output


def compute_sweep_coverage(records, *, series_field: str, metric: str):
    x_values = _sorted_unique(record["numTasks"] for record in records)
    series_values = _sorted_unique(record[series_field] for record in records)
    cell_rows = defaultdict(list)
    for record in records:
        if record.get(metric) is None:
            continue
        cell_rows[(record[series_field], record["numTasks"])].append(record)

    cells = {}
    missing = []
    for series_value in series_values:
        for x_value in x_values:
            rows = cell_rows.get((series_value, x_value), [])
            key = f"{series_value}|{x_value}"
            if rows:
                cells[key] = {
                    "series": series_value,
                    "x": x_value,
                    "n_runs": len(rows),
                    "seeds": sorted({int(row["seed"]) for row in rows}),
                    "exp_names": sorted({row["exp_name"] for row in rows if row.get("exp_name")}),
                    "metric_values": [float(row[metric]) for row in rows if row.get(metric) is not None],
                }
            else:
                missing.append({"series": series_value, "x": x_value})

    return {
        "metric": metric,
        "series_field": series_field,
        "x_field": "numTasks",
        "x_values": x_values,
        "series_values": series_values,
        "cells": cells,
        "missing": missing,
    }



def print_coverage_summary(report: dict):
    print(
        f"[coverage] metric={report['metric']} x={report['x_field']} "
        f"series={report['series_field']}"
    )
    for series_value in report["series_values"]:
        covered = []
        for x_value in report["x_values"]:
            cell = report["cells"].get(f"{series_value}|{x_value}")
            if cell:
                seeds = ",".join(str(seed) for seed in cell["seeds"])
                covered.append(f"{x_value}(n={cell['n_runs']},seeds={seeds})")
        line = "; ".join(covered) if covered else "no points"
        print(f"  - {report['series_field']}={series_value}: {line}")
    if report["missing"]:
        print("  missing cells:")
        for item in report["missing"]:
            print(f"    * {report['series_field']}={item['series']} x={item['x']}")



def _unique_or_mixed(records, field):
    values = _sorted_unique(record[field] for record in records)
    if not values:
        return "?"
    if len(values) == 1:
        return values[0]
    return "mixed"



def _format_series_label(series_field: str, series_key):
    if series_field == "numUAVs":
        return f"UAVs={series_key}"
    return str(series_key)



def _series_color(series_field: str, series_key, index: int):
    if series_field == "group":
        return GROUP_COLORS.get(series_key, DEFAULT_COLOR)
    cmap = plt.get_cmap("tab10")
    return matplotlib.colors.to_hex(cmap(index % 10))



def _make_sweep_title(mode: str, metric: str, records, *, fixed_group=None, fixed_num_uavs=None):
    title = "UE Sweep by Group" if mode == "ue-sweep-by-group" else "UE Sweep by numUAVs"
    t_value = _unique_or_mixed(records, "T")
    bcd_value = _unique_or_mixed(records, "use_bcd_loop")
    subtitle_parts = [
        f"Metric={METRIC_LABELS.get(metric, metric)}",
        f"T={t_value}",
        f"BCD={bcd_value}",
        f"Runs={len(records)}",
    ]
    if fixed_num_uavs is not None:
        subtitle_parts.insert(1, f"Fixed numUAVs={fixed_num_uavs}")
    if fixed_group is not None:
        subtitle_parts.insert(1, f"Fixed group={fixed_group}")
    return title, " | ".join(str(part) for part in subtitle_parts)



def _make_sweep_stem(mode: str, metric: str, *, fixed_group=None, fixed_num_uavs=None, fixed_t=None, fixed_bcd=None, scope="all"):
    parts = [mode.replace("-", "_"), metric, scope]
    if fixed_group is not None:
        parts.append(f"group_{fixed_group}")
    if fixed_num_uavs is not None:
        parts.append(f"uavs_{fixed_num_uavs}")
    if fixed_t is not None:
        parts.append(f"T_{fixed_t}")
    if fixed_bcd is not None:
        parts.append(f"bcd_{str(fixed_bcd).lower()}")
    return "__".join(parts)


# ─── matplotlib 静态图：收敛图 ─────────────────────────────────────────────────

def _make_title(exp_dir: Path, seed, scenario: dict) -> tuple[str, str]:
    """生成主标题和副标题。"""
    title = f"Exp: {exp_dir.name} | Seed: {seed}"
    params = (
        f"Tasks={scenario.get('numTasks', '?')}, "
        f"UAVs={scenario.get('numUAVs', '?')}, "
        f"T={scenario.get('T', '?')}, "
        f"BCD={scenario.get('use_bcd_loop', '?')}"
    )
    return title, params


def plot_experiment_seed_mpl(seed, group_data: dict, exp_dir: Path, output_path: Path):
    """生成 2-subplot matplotlib 图并保存 PNG。"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax_conv, ax_box = axes

    scenario = next(iter(group_data.values()))["scenario"]
    title, params = _make_title(exp_dir, seed, scenario)
    fig.suptitle(f"{title}\n{params}", fontsize=11)

    ax_conv.set_title("Convergence Curve")
    ax_conv.set_xlabel("Evaluation Index")
    ax_conv.set_ylabel("Best Cost")

    for group in sorted(group_data.keys()):
        run = group_data[group]
        bsf = run["best_so_far"]
        if not bsf:
            continue
        xs = [e["evaluation_index"] for e in bsf]
        ys = [e["best_cost"] for e in bsf]
        color = GROUP_COLORS.get(group, DEFAULT_COLOR)
        label = f"{group}: {run['label']}"
        ax_conv.plot(xs, ys, color=color, label=label, linewidth=1.8, marker=".", markersize=3)

    ax_conv.legend(fontsize=8, loc="upper right")
    ax_conv.grid(True, alpha=0.3)

    ax_box.set_title("Score Distribution by Generation")
    ax_box.set_xlabel("Generation")
    ax_box.set_ylabel("Score")

    groups = sorted(group_data.keys())
    n_groups = len(groups)

    all_gens = set()
    for run in group_data.values():
        all_gens.update(run["history_by_gen"].keys())
    all_gens = sorted(all_gens)

    if all_gens and n_groups > 0:
        width = 0.7 / n_groups
        for gi, group in enumerate(groups):
            run = group_data[group]
            color = GROUP_COLORS.get(group, DEFAULT_COLOR)
            offsets = [g + (gi - (n_groups - 1) / 2) * width for g in all_gens]
            data_per_gen = [run["history_by_gen"].get(g, []) for g in all_gens]
            valid = [(o, d) for o, d in zip(offsets, data_per_gen) if d]
            if not valid:
                continue
            pos, data = zip(*valid)
            ax_box.boxplot(
                data,
                positions=pos,
                widths=width * 0.9,
                patch_artist=True,
                boxprops=dict(facecolor=color, alpha=0.5),
                medianprops=dict(color="black", linewidth=1.5),
                whiskerprops=dict(color=color),
                capprops=dict(color=color),
                flierprops=dict(marker=".", markersize=3, color=color, alpha=0.4),
                manage_ticks=False,
            )
            ax_box.plot([], [], color=color, linewidth=6, alpha=0.5, label=f"{group}: {run['label']}")

        ax_box.set_xticks(all_gens)
        ax_box.set_xticklabels([str(g) for g in all_gens])
        ax_box.legend(fontsize=8, loc="upper right")
        ax_box.grid(True, axis="y", alpha=0.3)
    else:
        ax_box.text(0.5, 0.5, "No history data", ha="center", va="center", transform=ax_box.transAxes)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


# ─── plotly 交互图：收敛图 ──────────────────────────────────────────────────────

def plot_experiment_seed_plotly(seed, group_data: dict, exp_dir: Path, output_path: Path):
    """生成 2-subplot plotly 图并保存 HTML。"""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print("WARN: plotly not installed, skipping HTML output", file=sys.stderr)
        return

    scenario = next(iter(group_data.values()))["scenario"]
    title, params = _make_title(exp_dir, seed, scenario)

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Convergence Curve", "Score Distribution by Generation"),
    )

    groups = sorted(group_data.keys())
    n_groups = len(groups)

    for group in groups:
        run = group_data[group]
        bsf = run["best_so_far"]
        if not bsf:
            continue
        xs = [e["evaluation_index"] for e in bsf]
        ys = [e["best_cost"] for e in bsf]
        color = GROUP_COLORS.get(group, DEFAULT_COLOR)
        fig.add_trace(
            go.Scatter(
                x=xs, y=ys, mode="lines+markers",
                name=f"{group}: {run['label']}",
                line=dict(color=color, width=2),
                marker=dict(size=4),
                legendgroup=group,
            ),
            row=1, col=1,
        )

    all_gens = set()
    for run in group_data.values():
        all_gens.update(run["history_by_gen"].keys())
    all_gens = sorted(all_gens)

    width = 0.7 / max(n_groups, 1)
    for gi, group in enumerate(groups):
        run = group_data[group]
        color = GROUP_COLORS.get(group, DEFAULT_COLOR)
        offset = (gi - (n_groups - 1) / 2) * width

        for gen in all_gens:
            scores = run["history_by_gen"].get(gen, [])
            if not scores:
                continue
            fig.add_trace(
                go.Box(
                    y=scores,
                    x=[gen + offset] * len(scores),
                    name=f"{group}: {run['label']}",
                    marker_color=color,
                    width=width * 0.85,
                    legendgroup=group,
                    showlegend=(gen == all_gens[0]),
                    boxpoints="outliers",
                ),
                row=1, col=2,
            )

    fig.update_layout(
        title_text=f"{title}<br><sup>{params}</sup>",
        height=500,
        width=1200,
        legend=dict(orientation="v"),
    )
    fig.update_xaxes(title_text="Evaluation Index", row=1, col=1)
    fig.update_yaxes(title_text="Best Cost", row=1, col=1)
    fig.update_xaxes(title_text="Generation", row=1, col=2)
    fig.update_yaxes(title_text="Score", row=1, col=2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(output_path))


# ─── sweep 图后端 ─────────────────────────────────────────────────────────────

def plot_sweep_mpl(series_data, *, title: str, subtitle: str, x_label: str, y_label: str, output_path: Path, series_field: str):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    fig.suptitle(f"{title}\n{subtitle}", fontsize=11)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_title("Sweep Summary")

    for index, series in enumerate(series_data):
        points = series["points"]
        if not points:
            continue
        xs = [point["x"] for point in points]
        ys = [point["mean"] for point in points]
        yerr = [point["std"] for point in points]
        color = _series_color(series_field, series["series_key"], index)
        label = series["label"]
        if any(err > 0 for err in yerr):
            ax.errorbar(xs, ys, yerr=yerr, color=color, label=label, linewidth=1.8, marker="o", capsize=3)
        else:
            ax.plot(xs, ys, color=color, label=label, linewidth=1.8, marker="o")

    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="best")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)



def plot_sweep_plotly(series_data, *, title: str, subtitle: str, x_label: str, y_label: str, output_path: Path, series_field: str):
    try:
        import plotly.graph_objects as go
    except ImportError:
        print("WARN: plotly not installed, skipping HTML output", file=sys.stderr)
        return

    fig = go.Figure()
    for index, series in enumerate(series_data):
        points = series["points"]
        if not points:
            continue
        xs = [point["x"] for point in points]
        ys = [point["mean"] for point in points]
        customdata = [
            [
                point.get("std", 0.0),
                point.get("n_runs", 1),
                ",".join(str(seed) for seed in point.get("seeds", [])),
                ", ".join(point.get("exp_names", [])),
            ]
            for point in points
        ]
        color = _series_color(series_field, series["series_key"], index)
        error_y = dict(type="data", array=[point["std"] for point in points], visible=True)
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines+markers",
                name=series["label"],
                line=dict(color=color, width=2),
                marker=dict(size=7),
                error_y=error_y,
                customdata=customdata,
                hovertemplate=(
                    "UE=%{x}<br>mean=%{y:.4f}<br>std=%{customdata[0]:.4f}"
                    "<br>n_runs=%{customdata[1]}<br>seeds=%{customdata[2]}"
                    "<br>experiments=%{customdata[3]}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title_text=f"{title}<br><sup>{subtitle}</sup>",
        height=550,
        width=1000,
        xaxis_title=x_label,
        yaxis_title=y_label,
        legend=dict(orientation="v"),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(output_path))



def write_coverage_report(report: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── 模式执行 ──────────────────────────────────────────────────────────────────

def run_convergence_mode(exp_dirs: list[Path], output_base: Path):
    total_png = 0
    total_html = 0

    for exp_dir in exp_dirs:
        seed_data = load_experiment_data(exp_dir)
        if not seed_data:
            print(f"SKIP: {exp_dir.name} — no run_seed_*.json files")
            continue

        out_dir = output_base / exp_dir.name

        for seed in sorted(seed_data.keys()):
            group_data = seed_data[seed]
            if not group_data:
                continue

            png_path = out_dir / f"seed_{seed}.png"
            html_path = out_dir / f"seed_{seed}.html"

            plot_experiment_seed_mpl(seed, group_data, exp_dir, png_path)
            total_png += 1

            plot_experiment_seed_plotly(seed, group_data, exp_dir, html_path)
            total_html += 1

            groups_str = ", ".join(sorted(group_data.keys()))
            print(f"  {exp_dir.name}/seed_{seed}  groups=[{groups_str}]  -> {png_path.name}")

    print(f"\nDone: {total_png} PNG + {total_html} HTML  -> {output_base}")
    return 0





def load_ablation_csv(csv_path: Path):
    rows = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"csv is empty: {csv_path}")
        required = {"numTasks", "all-local", "D1", "D1 feasible", "pure LLM(B)", "B feasible"}
        missing = required - set(reader.fieldnames)
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"csv missing columns: {missing_text}")
        for row in reader:
            rows.append(
                {
                    "x": int(float(row["numTasks"])),
                    "all_local": float(row["all-local"]),
                    "d1": float(row["D1"]),
                    "d1_feasible": float(row["D1 feasible"]),
                    "pure_llm": float(row["pure LLM(B)"]),
                    "b_feasible": float(row["B feasible"]),
                    "best_group": (row.get("最佳可行方案") or "").strip(),
                }
            )
    if not rows:
        raise ValueError(f"csv has no data rows: {csv_path}")
    return rows


def plot_ablation_bars_mpl(rows, *, title: str, x_label: str, y_label: str, output_path: Path):
    fig, ax = plt.subplots(figsize=(10, 5.6))
    x_positions = list(range(len(rows)))
    width = 0.24

    labels = [str(row["x"]) for row in rows]
    all_local = [row["all_local"] for row in rows]
    pure_llm = [row["pure_llm"] for row in rows]
    d1 = [row["d1"] for row in rows]

    ax.bar([x - width for x in x_positions], all_local, width=width, color="#FBC02D", edgecolor="black", linewidth=0.8, label="本地处理")
    ax.bar(x_positions, pure_llm, width=width, color="#1F77B4", edgecolor="black", linewidth=0.8, label="RIS辅助卸载")
    ax.bar([x + width for x in x_positions], d1, width=width, color="#E6550D", edgecolor="black", linewidth=0.8, label="失败")

    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 0.98), frameon=True, fancybox=False, edgecolor="black")
    ax.tick_params(direction="in", top=True, right=True)
    ax.set_axisbelow(True)
    ax.set_ylim(bottom=0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def run_comparison_json_mode(args, output_base: Path):
    if not args.summary_json:
        raise ValueError("comparison-json requires --summary-json")

    summary_path = Path(args.summary_json)
    if not summary_path.is_absolute():
        summary_path = ROOT / summary_path
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    title = payload.get("title", "Experiment Comparison")
    subtitle = payload.get("subtitle", "")
    x_label = payload.get("x_label", "UE Count")
    y_label = payload.get("y_label", "Score")
    series_data = payload.get("series", [])
    if not series_data:
        raise ValueError("summary json contains no series")

    out_dir = output_base / "sweeps"
    stem = summary_path.stem
    png_path = out_dir / f"{stem}.png"
    html_path = out_dir / f"{stem}.html"

    plot_sweep_mpl(
        series_data,
        title=title,
        subtitle=subtitle,
        x_label=x_label,
        y_label=y_label,
        output_path=png_path,
        series_field="group",
    )
    plot_sweep_plotly(
        series_data,
        title=title,
        subtitle=subtitle,
        x_label=x_label,
        y_label=y_label,
        output_path=html_path,
        series_field="group",
    )
    print(f"\nDone: 1 PNG + 1 HTML  -> {out_dir}")
    print(f"  png={png_path.name}")
    print(f"  html={html_path.name}")
    return 0


def run_csv_ablation_bars_mode(args, output_base: Path):
    if not args.csv_path:
        raise ValueError("csv-ablation-bars requires --csv-path")

    csv_path = Path(args.csv_path)
    if not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    rows = load_ablation_csv(csv_path)

    out_dir = output_base / "csv_bars"
    png_path = out_dir / f"{csv_path.stem}.png"
    title = args.title or "消融实验对比"
    x_label = args.x_label or "任务数"
    y_label = args.y_label or "目标值"

    plot_ablation_bars_mpl(rows, title=title, x_label=x_label, y_label=y_label, output_path=png_path)
    print(f"\nDone: 1 PNG  -> {out_dir}")
    print(f"  png={png_path.name}")
    return 0


def run_sweep_mode(args, exp_dirs: list[Path], output_base: Path):
    payloads = load_run_payloads(exp_dirs)
    records = [record for payload in payloads if (record := normalize_run_record(payload)) is not None]
    filtered = filter_sweep_records(
        records,
        fixed_num_uavs=args.num_uavs,
        fixed_group=args.group,
        fixed_use_bcd=args.use_bcd_loop,
        fixed_T=args.t,
        seeds=args.seeds,
    )
    validate_sweep_records(filtered, args.mode, fixed_num_uavs=args.num_uavs, fixed_group=args.group)

    series_field = "group" if args.mode == "ue-sweep-by-group" else "numUAVs"
    coverage = compute_sweep_coverage(filtered, series_field=series_field, metric=args.metric)
    print_coverage_summary(coverage)

    series_data = aggregate_sweep_series(filtered, series_field=series_field, metric=args.metric)
    if not series_data:
        raise ValueError(f"no series data available for metric={args.metric}")

    title, subtitle = _make_sweep_title(
        args.mode,
        args.metric,
        filtered,
        fixed_group=args.group,
        fixed_num_uavs=args.num_uavs,
    )
    scope = exp_dirs[0].name if len(exp_dirs) == 1 else "all_experiments"
    stem = _make_sweep_stem(
        args.mode,
        args.metric,
        fixed_group=args.group,
        fixed_num_uavs=args.num_uavs,
        fixed_t=args.t,
        fixed_bcd=args.use_bcd_loop,
        scope=scope,
    )
    out_dir = output_base / "sweeps"
    png_path = out_dir / f"{stem}.png"
    html_path = out_dir / f"{stem}.html"
    coverage_path = out_dir / f"{stem}.coverage.json"

    plot_sweep_mpl(
        series_data,
        title=title,
        subtitle=subtitle,
        x_label="UE Count",
        y_label=METRIC_LABELS.get(args.metric, args.metric),
        output_path=png_path,
        series_field=series_field,
    )
    plot_sweep_plotly(
        series_data,
        title=title,
        subtitle=subtitle,
        x_label="UE Count",
        y_label=METRIC_LABELS.get(args.metric, args.metric),
        output_path=html_path,
        series_field=series_field,
    )
    write_coverage_report(coverage, coverage_path)

    print(f"\nDone: 1 PNG + 1 HTML + 1 coverage JSON  -> {out_dir}")
    print(f"  png={png_path.name}")
    print(f"  html={html_path.name}")
    print(f"  coverage={coverage_path.name}")
    return 0


# ─── 主程序 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="绘制实验目标函数收敛曲线与 UE sweep 图")
    parser.add_argument(
        "--mode",
        default="convergence",
        choices=["convergence", *sorted(SWEEP_MODES)],
        help="绘图模式（默认 convergence）",
    )
    parser.add_argument(
        "--exp-dir",
        help="单个实验目录；不指定时扫描 discussion/experiment_results/ 下所有 timestamp 目录",
    )
    parser.add_argument(
        "--output-dir",
        default="discussion/plots",
        help="输出目录（默认 discussion/plots）",
    )
    parser.add_argument(
        "--metric",
        default="best_cost",
        choices=sorted(METRIC_LABELS.keys()),
        help="sweep 模式的纵轴指标（默认 best_cost）",
    )
    parser.add_argument(
        "--num-uavs",
        type=int,
        help="固定无人机数量（常用于 ue-sweep-by-group）",
    )
    parser.add_argument(
        "--group",
        help="固定算法组（常用于 ue-sweep-by-uavs）",
    )
    parser.add_argument(
        "--t",
        type=int,
        help="固定 T（可选）",
    )
    parser.add_argument(
        "--use-bcd-loop",
        type=parse_optional_bool,
        default=None,
        help="固定是否启用 BCD（true/false，可选）",
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        help="仅使用指定 seeds（可选）",
    )
    parser.add_argument(
        "--summary-json",
        help="comparison-json 模式使用的汇总 JSON 文件",
    )
    parser.add_argument(
        "--csv-path",
        help="csv-ablation-bars 模式使用的 CSV 文件",
    )
    parser.add_argument(
        "--title",
        help="自定义图标题",
    )
    parser.add_argument(
        "--x-label",
        help="自定义横轴标题",
    )
    parser.add_argument(
        "--y-label",
        help="自定义纵轴标题",
    )
    args = parser.parse_args()

    base_dir = ROOT / "discussion" / "experiment_results"
    output_base = ROOT / args.output_dir

    try:
        if args.mode == "comparison-json":
            return run_comparison_json_mode(args, output_base)
        if args.mode == "csv-ablation-bars":
            return run_csv_ablation_bars_mode(args, output_base)

        exp_dirs = resolve_experiment_dirs(args.exp_dir, base_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.mode == "ue-sweep-by-group" and args.num_uavs is None:
        print("ERROR: ue-sweep-by-group requires --num-uavs to avoid mixing scenarios", file=sys.stderr)
        return 1
    if args.mode == "ue-sweep-by-uavs" and not args.group:
        print("ERROR: ue-sweep-by-uavs requires --group to avoid mixing algorithms", file=sys.stderr)
        return 1

    try:
        if args.mode == "convergence":
            return run_convergence_mode(exp_dirs, output_base)
        return run_sweep_mode(args, exp_dirs, output_base)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
