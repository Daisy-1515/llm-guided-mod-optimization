"""绘制实验目标函数收敛曲线 + 箱线图。

用法:
    uv run python scripts/plot_optimization_curves.py
    uv run python scripts/plot_optimization_curves.py --exp-dir discussion/experiment_results/20260402_214943
    uv run python scripts/plot_optimization_curves.py --output-dir discussion/plots_custom
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GROUP_COLORS = {
    "A":  "#2196F3",
    "D1": "#F44336",
    "B":  "#4CAF50",
    "C1": "#FF9800",
    "C2": "#9C27B0",
}
DEFAULT_COLOR = "#607D8B"


# ─── 数据层 ──────────────────────────────────────────────────────────────────

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


# ─── matplotlib 静态图 ────────────────────────────────────────────────────────

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

    # 取任意一组的 scenario（同一实验目录下相同）
    scenario = next(iter(group_data.values()))["scenario"]
    title, params = _make_title(exp_dir, seed, scenario)
    fig.suptitle(f"{title}\n{params}", fontsize=11)

    # ── 左图：收敛曲线 ──────────────────────────────────────────────────────
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

    # ── 右图：箱线图 ────────────────────────────────────────────────────────
    ax_box.set_title("Score Distribution by Generation")
    ax_box.set_xlabel("Generation")
    ax_box.set_ylabel("Score")

    groups = sorted(group_data.keys())
    n_groups = len(groups)

    # 收集所有代号
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
            # 过滤空代
            valid = [(o, d) for o, d in zip(offsets, data_per_gen) if d]
            if not valid:
                continue
            pos, data = zip(*valid)
            bp = ax_box.boxplot(
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
            # 图例用代理 patch
            ax_box.plot([], [], color=color, linewidth=6, alpha=0.5,
                        label=f"{group}: {run['label']}")

        ax_box.set_xticks(all_gens)
        ax_box.set_xticklabels([str(g) for g in all_gens])
        ax_box.legend(fontsize=8, loc="upper right")
        ax_box.grid(True, axis="y", alpha=0.3)
    else:
        ax_box.text(0.5, 0.5, "No history data", ha="center", va="center",
                    transform=ax_box.transAxes)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


# ─── plotly 交互图 ────────────────────────────────────────────────────────────

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

    # ── 左图：收敛曲线 ──────────────────────────────────────────────────────
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

    # ── 右图：箱线图 ────────────────────────────────────────────────────────
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


# ─── 主程序 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="绘制实验目标函数收敛曲线")
    parser.add_argument(
        "--exp-dir",
        help="单个实验目录（默认全量扫描 discussion/experiment_results/）",
    )
    parser.add_argument(
        "--output-dir",
        default="discussion/plots",
        help="输出目录（默认 discussion/plots）",
    )
    args = parser.parse_args()

    base_dir = ROOT / "discussion" / "experiment_results"
    output_base = ROOT / args.output_dir

    if args.exp_dir:
        exp_dir = Path(args.exp_dir)
        if not exp_dir.is_absolute():
            exp_dir = ROOT / exp_dir
        if not exp_dir.is_dir():
            print(f"ERROR: exp_dir not found: {exp_dir}", file=sys.stderr)
            return 1
        exp_dirs = [exp_dir]
    else:
        exp_dirs = scan_experiment_dirs(base_dir)

    if not exp_dirs:
        print("ERROR: no experiment directories found", file=sys.stderr)
        return 1

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


if __name__ == "__main__":
    raise SystemExit(main())
