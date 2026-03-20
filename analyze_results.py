"""Phase⑤ 首跑结果分析 — S1-S4 成功判据检测。

用法:
    .venv/Scripts/python analyze_results.py
    .venv/Scripts/python analyze_results.py --run-dir discussion/20260320_143012
    .venv/Scripts/python analyze_results.py --expected-pop-size 3 --expected-iterations 3
"""

import argparse
import json
import re
import sys
from pathlib import Path


GEN_FILE_RE = re.compile(r"population_result_(\d+)\.json$")


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

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


# ─── 主函数 ──────────────────��────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Phase⑤ 首跑结果分析")
    parser.add_argument("--run-dir", help="结果目录（默认取最新）")
    parser.add_argument("--expected-pop-size", type=int, default=3)
    parser.add_argument("--expected-iterations", type=int, default=3)
    args = parser.parse_args()

    try:
        run_dir = _resolve_run_dir(args.run_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    gen_files = _collect_generation_files(run_dir)
    print(f"run_dir={run_dir}  json_files={len(gen_files)}")
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


if __name__ == "__main__":
    raise SystemExit(main())
