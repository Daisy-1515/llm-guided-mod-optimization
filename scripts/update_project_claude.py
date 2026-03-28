#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新项目级 CLAUDE.md 中的"当前状态"部分
扫描 git log、config、讨论数据，自动生成和更新状态信息
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

# 设置 stdout 编码为 utf-8
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class ProjectClaudeUpdater:
    """维护项目级 CLAUDE.md"""

    def __init__(self, project_root: str = "."):
        self.root = Path(project_root)
        self.claude_file = self.root / "CLAUDE.md"
        self.config_file = self.root / "config" / "setting.cfg"
        self.discussion_dir = self.root / "discussion"

    def create_or_update(self) -> bool:
        """创建或更新项目级 CLAUDE.md"""
        if not self.claude_file.exists():
            return self._create_new()
        else:
            return self._update_existing()

    def _create_new(self) -> bool:
        """创建新的项目级 CLAUDE.md"""
        try:
            content = self._generate_claude_content()
            self.claude_file.write_text(content, encoding="utf-8")
            print(f"✅ 创建项目级 CLAUDE.md")
            return True
        except Exception as e:
            print(f"❌ 创建失败: {e}")
            return False

    def _update_existing(self) -> bool:
        """更新现有的项目级 CLAUDE.md"""
        try:
            content = self.claude_file.read_text(encoding="utf-8")
            # 更新"当前状态"部分
            updated = self._update_status_section(content)
            if updated != content:
                self.claude_file.write_text(updated, encoding="utf-8")
                print(f"✅ 更新项目级 CLAUDE.md")
                return True
            else:
                print(f"ℹ️  项目级 CLAUDE.md 无需更新")
                return True
        except Exception as e:
            print(f"❌ 更新失败: {e}")
            return False

    def _generate_claude_content(self) -> str:
        """生成新的项目级 CLAUDE.md"""
        status_info = self._get_status_info()
        config_info = self._get_config_info()
        latest_run = self._get_latest_run_info()

        return f"""# llm-guided-mod-optimization 项目 CLAUDE.md

## 当前状态（自动更新）

**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### 项目进度
{status_info['progress']}

### 最新运行结果
{status_info['latest_run']}

### LLM 配置
{config_info}

### 已知问题
| 问题 | 位置 | 状态 | 优先级 |
|------|------|------|--------|
| DCP 约束非凸 | edge_uav/model/trajectory_opt.py:527 | 🔴 阻断 | P0 |
| 参数约束可行性 | config/setting.cfg | 🟡 待决策 | P2 |

## 快速命令

```bash
uv sync                      # 环境设置
python scripts/testEdgeUav.py        # 运行 Edge UAV 管道
python scripts/analyze_results.py    # 验证结果
pytest tests/ -v             # 运行全部测试
```

## 文件地图

**原始 MoD 系统**:
- `legacy_mod/scenarioGenerator.py` — 场景生成
- `AssignmentModel.py`, `SequencingModel.py` — 优化模型
- `SimClass.py` — 仿真评估

**Edge UAV 系统** (Phase④-⑤ 已完成，⑥ 进行中):
- `edge_uav/model/` — 物理模型 (offloading / propulsion / resource_alloc / trajectory_opt)
- `edge_uav/prompt/` — 提示工程
- `heuristics/hsIndividualEdgeUav.py` — HS 个体评估

**LLM 接口**:
- `llmAPI/llmInterface_huggingface.py` — OpenAI 兼容接口

**测试套件**: `tests/test_*.py` (62 tests)

## 常见任务

### 切换 LLM 模型
编辑 `config/setting.cfg`:
```ini
[llmSettings]
model = qwen3.5-plus    # or deepseek-chat, gpt-4o, etc.
```

### 修改 HS 参数
编辑 `config/setting.cfg`:
```ini
[hsSettings]
popSize = 5
iteration = 10
```

### 运行完整管道
```bash
python scripts/testEdgeUav.py --popsize=5 --iteration=10
python scripts/analyze_results.py --run-dir discussion/LATEST_RUN/
```

## 详细文档

- **全局指导**: `.claude/CLAUDE.md` (深度设计、架构决策)
- **全局进度**: `MEMORY.md` (跨会话追踪)
- **数学模型**: `文档/10_模型与公式/公式.md`
- **工作日记**: `文档/70_工作日记/YYYY-MM-DD.md`
- **诊断报告**: `文档/40_审查与诊断/`

## 下一步里程碑

{status_info['milestones']}

---
*本文件由 `/endday` skill 自动维护（当前状态部分）。其他部分可手动编辑。*
"""

    def _update_status_section(self, content: str) -> str:
        """更新现有 CLAUDE.md 中的"当前状态"部分"""
        status_info = self._get_status_info()
        config_info = self._get_config_info()

        # 替换"当前状态"部分
        import re

        status_section = f"""## 当前状态（自动更新）

**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### 项目进度
{status_info['progress']}

### 最新运行结果
{status_info['latest_run']}

### LLM 配置
{config_info}"""

        # 找到并替换"当前状态"到下一个 ## 之间的内容
        pattern = r"## 当前状态.*?\n(?=## [^#]|\Z)"
        updated = re.sub(pattern, status_section + "\n\n", content, flags=re.DOTALL)

        return updated

    def _get_status_info(self) -> Dict[str, str]:
        """获取项目状态信息"""
        progress = self._get_phase_status()
        latest_run = self._get_latest_run_info()
        milestones = self._get_milestones()

        return {
            "progress": progress,
            "latest_run": latest_run,
            "milestones": milestones,
        }

    def _get_phase_status(self) -> str:
        """从 git log 推断 Phase 状态"""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-20"],
                cwd=str(self.root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )

            lines = result.stdout.strip().split("\n")

            # 简单启发式：扫描最近 20 条 commit
            phase5_done = any("Phase⑤" in line for line in lines)
            phase6_started = any("Phase⑥" in line or "Step1" in line or "Step2" in line or "Step3" in line for line in lines)

            if phase6_started:
                phase_text = "🟡 Phase⑥ in progress"
                if any("trajectory" in line or "Step3" in line for line in lines):
                    phase_text += " (Step1/2/3 in development)"
            elif phase5_done:
                phase_text = "✅ Phase⑤ complete (2026-03-22)"
            else:
                phase_text = "❓ Phase status unknown"

            return f"- **Phase Status**: {phase_text}\n- **Latest Commit**: {lines[0] if lines else 'N/A'}"

        except Exception as e:
            return f"- **Phase Status**: Unable to detect (git error: {str(e)[:30]})"

    def _get_latest_run_info(self) -> str:
        """获取最新 run 的信息"""
        try:
            if not self.discussion_dir.exists():
                return "- No runs found"

            # 找最新的 run 目录
            runs = sorted([d for d in self.discussion_dir.iterdir() if d.is_dir()])
            if not runs:
                return "- No runs found"

            latest = runs[-1]
            run_name = latest.name

            # 检查是否有 population_result_*.json 文件
            json_files = list(latest.glob("population_result_*.json"))
            if json_files:
                gen_count = len(json_files)
                return f"- **Latest Run**: `{run_name}/` ({gen_count} generations)\n- **Status**: Check with `python scripts/analyze_results.py --run-dir {latest.name}/`"
            else:
                return f"- **Latest Run**: `{run_name}/` (in progress)"

        except Exception:
            return "- Unable to read run info"

    def _get_config_info(self) -> str:
        """获取 LLM 和 HS 配置"""
        try:
            import configparser

            config = configparser.ConfigParser()
            config.read(str(self.config_file), encoding='utf-8')

            model = config.get("llmSettings", "model", fallback="unknown")
            pop_size = config.get("hsSettings", "popSize", fallback="5")
            iteration = config.get("hsSettings", "iteration", fallback="10")

            return f"""- **LLM Model**: `{model}` (config/setting.cfg:7)
- **HS Parameters**: popSize={pop_size}, iteration={iteration}
- **Endpoint**: CloseAI (api.openai-proxy.org)"""

        except Exception as e:
            return f"- Unable to read config: {str(e)[:50]}"

    def _get_milestones(self) -> str:
        """生成下一步里程碑"""
        return """- [ ] Phase⑥ Step3: 解决 DCP 约束非凸性问题
- [ ] 完整 HS + BCD 集成和验证
- [ ] 论文第 3 章完稿"""


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="更新项目级 CLAUDE.md")
    parser.add_argument("--project-root", default=".", help="项目根目录")
    parser.add_argument("--dry-run", action="store_true", help="仅显示将要做的操作")
    args = parser.parse_args()

    updater = ProjectClaudeUpdater(args.project_root)

    if args.dry_run:
        print("📋 [DRY-RUN] 将执行以下操作:")
        if updater.claude_file.exists():
            print(f"  - 更新 {updater.claude_file}")
        else:
            print(f"  - 创建 {updater.claude_file}")
        return 0

    success = updater.create_or_update()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
