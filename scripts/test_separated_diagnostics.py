#!/usr/bin/env python3
"""
快速测试脚本：验证分离统计指标是否正确计算
"""

import sys
from pathlib import Path
import json

project_root = Path(__file__).parent.parent

def test_separated_diagnostics():
    """查看最新运行中的分离统计数据"""

    # 从最新运行加载一个预计算结果
    discussion_dir = project_root / "discussion"
    runs = sorted(discussion_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not runs:
        print("No previous runs found in discussion/")
        return False

    latest_run = runs[0]
    print(f"Checking run: {latest_run.name}\n")

    pop_result_files = sorted(latest_run.glob("population_result_*.json"))

    if not pop_result_files:
        print(f"No population_result_*.json found in {latest_run}")
        return False

    # 加载第一个种群结果
    with open(pop_result_files[0]) as f:
        pop_data = json.load(f)

    # pop_data 可能是列表或字典，检查结构
    print(f"  pop_data type: {type(pop_data)}")
    if isinstance(pop_data, list):
        if not pop_data:
            print("  ERROR: pop_data is empty list")
            return False
        pop_data = pop_data[0]  # 取第一个元素
        print(f"  Extracted first element, type: {type(pop_data)}")

    # 尝试找诊断数据（在 solution_details.final_precompute_diagnostics 中）
    diag = None
    if isinstance(pop_data, dict) and "solution_details" in pop_data:
        solution_details = pop_data.get("solution_details", {})
        if isinstance(solution_details, dict):
            diag = solution_details.get("final_precompute_diagnostics", None)

    if diag is None and isinstance(pop_data, dict) and "precompute_diagnostics" in pop_data:
        diag = pop_data["precompute_diagnostics"]

    if diag and isinstance(diag, dict):
        print("\n" + "="*80)
        print("PRECOMPUTE DIAGNOSTICS")
        print("="*80)
        print(f"【原始统计】")
        print(f"  candidate_offload_pairs: {diag.get('candidate_offload_pairs', 'N/A')}")
        print(f"  deadline_feasible_pairs: {diag.get('deadline_feasible_pairs', 'N/A')}")
        print(f"  offload_feasible_ratio: {diag.get('offload_feasible_ratio', 'N/A'):.4f}")

        print(f"\n【分离统计（新增）】")
        assigned_pairs = diag.get('assigned_pairs', 'N/A')
        assigned_feasible = diag.get('assigned_feasible_pairs', 'N/A')
        assigned_ratio = diag.get('assigned_feasible_ratio', 'N/A')
        unassigned_pairs = diag.get('unassigned_pairs', 'N/A')
        assigned_pair_ratio = diag.get('assigned_pair_ratio', 'N/A')

        if isinstance(assigned_pairs, int):
            print(f"  已分配对: {assigned_pairs}")
            if isinstance(assigned_feasible, int):
                print(f"    ├─ 可行: {assigned_feasible}")
                print(f"    └─ 可行率: {assigned_ratio:.4f}")
            print(f"  未分配对: {unassigned_pairs}")
            print(f"  分配率: {assigned_pair_ratio:.4f}")

            # 诊断结论
            print(f"\n【诊断结论】")
            if isinstance(assigned_ratio, float) and assigned_ratio > 0.5:
                print(f"  OK 已分配对的可行率较高 ({assigned_ratio:.4f})，deadline 压力在平衡范围内")
            elif isinstance(assigned_ratio, float):
                print(f"  WARNING 已分配对的可行率较低 ({assigned_ratio:.4f})，deadline 压力较大")

            return True
        else:
            print(f"  WARNING Separated statistics not available, code may not be fully deployed")
            print(f"    assigned_pairs={assigned_pairs} (type: {type(assigned_pairs)})")
            return False
    else:
        print("WARNING No precompute diagnostics found")
        if isinstance(pop_data, dict):
            print(f"  Keys in pop_data: {list(pop_data.keys())}")
            if 'solution_details' in pop_data:
                sd = pop_data.get('solution_details')
                if isinstance(sd, dict):
                    print(f"  Keys in solution_details: {list(sd.keys())}")
        return False

if __name__ == "__main__":
    success = test_separated_diagnostics()
    sys.exit(0 if success else 1)
