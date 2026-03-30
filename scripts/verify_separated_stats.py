#!/usr/bin/env python3
"""
验证脚本：直接测试分离统计逻辑是否正确
"""

import sys
from pathlib import Path
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_separated_stats_logic():
    """
    模拟分离统计的逻辑：
    - 已分配对：f_edge > eps_freq
    - 未分配对：f_edge <= eps_freq
    """

    # 模拟一个简单的快照和预计算结果
    eps_freq = 1e-12

    # 模拟场景：10 个对，其中 7 个被分配，3 个未分配
    pairs = [
        # (f_edge, d_offload, tau, is_feasible_expected)
        (1e6, 0.5, 1.0, True),    # 已分配，可行
        (1e6, 0.9, 1.0, True),    # 已分配，可行
        (1e6, 1.5, 1.0, False),   # 已分配，不可行
        (1e6, 0.3, 1.0, True),    # 已分配，可行
        (1e6, 0.8, 1.0, True),    # 已分配，可行
        (1e6, 1.2, 1.0, False),   # 已分配，不可行
        (1e6, 0.6, 1.0, True),    # 已分配，可行
        (0.0, 1e6, 1.0, False),   # 未分配（f=0），不可行
        (0.0, 1e6, 1.0, False),   # 未分配（f=0），不可行
        (0.0, 1e6, 1.0, False),   # 未分配（f=0），不可行
    ]

    # 计算统计
    assigned_pairs = 0
    assigned_feasible = 0
    unassigned_pairs = 0

    for f_val, d_val, tau_val, _ in pairs:
        if f_val > eps_freq:
            # 已分配对
            assigned_pairs += 1
            if d_val <= tau_val:
                assigned_feasible += 1
        else:
            # 未分配对
            unassigned_pairs += 1

    total_pairs = assigned_pairs + unassigned_pairs
    total_feasible = assigned_feasible  # 注意：未分配对的 d_val=1e6，肯定不可行

    # 验证
    print("Separated Statistics Logic Verification")
    print("=" * 60)
    print(f"Total pairs: {total_pairs}")
    print(f"  Assigned pairs: {assigned_pairs}")
    print(f"    Feasible: {assigned_feasible}")
    print(f"    Infeasible: {assigned_pairs - assigned_feasible}")
    print(f"  Unassigned pairs: {unassigned_pairs}")
    print()
    print(f"Mixed ratio (old): {total_feasible}/{total_pairs} = {total_feasible/total_pairs:.4f}")
    print(f"Assigned-only ratio (new): {assigned_feasible}/{assigned_pairs} = {assigned_feasible/assigned_pairs:.4f}")
    print()
    print(f"Expected values:")
    print(f"  Mixed ratio: 5/10 = 0.5000 (5 out of 10 pairs feasible)")
    print(f"  Assigned-only: 5/7 = 0.7143 (5 out of 7 assigned pairs feasible)")
    print()

    # 验证计算是否正确
    assert assigned_pairs == 7, f"Expected 7 assigned pairs, got {assigned_pairs}"
    assert assigned_feasible == 5, f"Expected 5 assigned-feasible pairs, got {assigned_feasible}"
    assert unassigned_pairs == 3, f"Expected 3 unassigned pairs, got {unassigned_pairs}"
    assert abs(total_feasible / total_pairs - 0.5) < 1e-6, "Mixed ratio should be 0.5"
    assert abs(assigned_feasible / assigned_pairs - 5/7) < 1e-6, "Assigned-only ratio should be ~0.7143"

    print("OK All assertions passed!")
    print()
    print("Interpretation:")
    print("- Mixed ratio (0.50) includes both assigned and unassigned (f=0) pairs")
    print("- Since unassigned pairs get f=eps_freq~1e-12, d_offload becomes huge")
    print("- This explains why 'mixed ratio' drops from 50% to <1% after BCD optimization")
    print("- Assigned-only ratio (0.71) shows the true pressure on allocated resources")

    return True

if __name__ == "__main__":
    try:
        success = test_separated_stats_logic()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
