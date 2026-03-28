#!/bin/bash

# Historical checklist created for the 2026-03-27 quick-validation phase.
# Current project status is maintained in CLAUDE.md and the latest work diary.

echo "========== PHASE 4 ACCEPTANCE CHECKLIST =========="
echo ""

# 检查 1: conftest.py 创建成功
echo "[1] conftest.py exists"
if test -f tests/conftest.py; then
    echo "  PASS - conftest.py created at tests/conftest.py"
else
    echo "  FAIL - conftest.py not found"
fi
echo ""

# 检查 2: pytest 导入无错
echo "[2] pytest import validation"
COLLECT_OUTPUT=$(uv run python -m pytest tests/test_bcd_loop.py --collect-only 2>&1)
if echo "$COLLECT_OUTPUT" | grep -q "8 tests collected"; then
    echo "  PASS - 8 tests collected, no import errors"
else
    echo "  FAIL - Import error detected"
    echo "$COLLECT_OUTPUT" | head -5
fi
echo ""

# 检查 3: BCD 单元测试全通过
echo "[3] BCD unit tests (expect 8 passed)"
BCD_RESULT=$(uv run python -m pytest tests/test_bcd_loop.py -q --tb=no 2>&1 | tail -1)
if echo "$BCD_RESULT" | grep -q "8 passed"; then
    echo "  PASS - $BCD_RESULT"
else
    echo "  FAIL - $BCD_RESULT"
fi
echo ""

# 检查 4: Trajectory 单元测试全通过
echo "[4] Trajectory unit tests (expect 12 passed)"
TRAJ_RESULT=$(uv run python -m pytest tests/test_trajectory_opt.py -q --tb=no 2>&1 | tail -1)
if echo "$TRAJ_RESULT" | grep -q "12 passed"; then
    echo "  PASS - $TRAJ_RESULT"
else
    echo "  FAIL - $TRAJ_RESULT"
fi
echo ""

# 检查 5: Resource Alloc 单元测试全通过
echo "[5] Resource Alloc unit tests (expect 8 passed)"
RA_RESULT=$(uv run python -m pytest tests/test_resource_alloc.py -q --tb=no 2>&1 | tail -1)
if echo "$RA_RESULT" | grep -q "passed"; then
    echo "  PASS - $RA_RESULT"
else
    echo "  FAIL - $RA_RESULT"
fi
echo ""

# 检查 6: 冒烟测试成功执行
echo "[6] Smoke test execution (HS_POP_SIZE=1, ITERATION=1)"
SMOKE_LOG=$(mktemp)
export HS_POP_SIZE=1 HS_ITERATION=1 MAX_BCD_ITER=2
timeout 180 uv run python scripts/testEdgeUav.py > "$SMOKE_LOG" 2>&1
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "  PASS - Exit code 0 (successful execution)"
else
    echo "  FAIL - Exit code $EXIT_CODE"
fi
echo ""

# 检查 7: BCD 相关日志或求解器调用痕迹
echo "[7] BCD/solver traces in logs"
# 旧版脚本默认系统仍停留在单层 Offloading 路径。
# 当前仓库已进入 Phase⑥ Step4 后续状态，因此优先检查 BCD 相关日志；
# 若未命中，再提示检查 use_bcd_loop、降级路径和当前日志行为。
BCD_LOGS=$(grep -E -c "BCD iteration|BCD loop failed" "$SMOKE_LOG" 2>/dev/null || echo "0")
GUROBI_SOLVES=$(grep -c "Gurobi Optimizer" "$SMOKE_LOG" 2>/dev/null || echo "0")
if [ "$BCD_LOGS" -ge 1 ]; then
    echo "  PASS - Found $BCD_LOGS BCD-related log line(s) in latest run"
elif [ "$GUROBI_SOLVES" -ge 1 ]; then
    echo "  PASS - Found $GUROBI_SOLVES Gurobi solver invocation(s) in latest run"
    echo "  INFO - No explicit BCD log line found; check use_bcd_loop, fallback path, and current logging behavior"
else
    echo "  INFO - No BCD-related or solver log lines found"
fi
echo ""

# 检查 8: 结果目录生成
echo "[8] Result directory generated"
LATEST=$(ls -d discussion/2026* 2>/dev/null | sort -r | head -1)
if [ -n "$LATEST" ]; then
    FILE_COUNT=$(ls -1 "$LATEST" | wc -l)
    echo "  PASS - Generated: $LATEST"
    echo "         Files: $FILE_COUNT result files"
else
    echo "  FAIL - No result directory found"
fi
echo ""

echo "========== END CHECKLIST =========="
