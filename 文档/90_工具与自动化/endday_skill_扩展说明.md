# endday skill 扩展：项目级 CLAUDE.md 自动维护

## 功能概述

已为 `/endday` skill 添加**自动维护项目级 CLAUDE.md** 的功能。现在每次运行 `/endday` 时，脚本会自动：

1. ✅ **自动检测项目状态**
   - 从 git log 识别 Phase（Phase⑤/⑥）
   - 提取最新 commit 信息
   - 找到最新的运行数据

2. ✅ **自动更新配置信息**
   - 读取 `config/setting.cfg` 的 LLM 模型和 HS 参数
   - 显示当前 endpoint

3. ✅ **自动生成项目级 CLAUDE.md**
   - 如果不存在，则创建新文件
   - 如果存在，只更新"当前状态"部分
   - 保留手动编辑的其他内容（快速命令、常见任务等）

## 文件清单

### 新建文件
- **`scripts/update_project_claude.py`** (302 行)
  - 独立脚本，可单独运行或被 endday 调用
  - 自动生成/更新项目级 CLAUDE.md

- **`.endday.env`** (新配置文件)
  - endday skill 的项目级配置
  - 控制行为和集成点

### 修改的全局文件
- **endday skill**: `~/.cc-switch/skills/endday/scripts/endday_main.py`
  - 添加新的配置选项支持
  - 集成 `update_project_claude()` 步骤

### 自动生成文件
- **`CLAUDE.md`** (项目根目录)
  - 项目级快速参考文档
  - 自动部分 + 手动部分

## 快速使用

### 默认行为（已启用）

```bash
# 运行 endday，自动维护项目级 CLAUDE.md
/endday
```

会自动：
1. 审视变更 ✓
2. 更新 MEMORY.md ✓
3. 生成工作日记 ✓
4. **更新项目级 CLAUDE.md** ✅（新功能）
5. 检查敏感文件 ✓
6. 提交 ✓

### 禁用项目 CLAUDE.md 维护

编辑 `.endday.env`:
```bash
UPDATE_PROJECT_CLAUDE=false
```

或临时禁用：
```bash
# 不自动更新项目 CLAUDE.md
UPDATE_PROJECT_CLAUDE=false /endday
```

### 单独运行更新脚本

```bash
# 生成或更新项目级 CLAUDE.md
python scripts/update_project_claude.py

# 预览（不实际写入）
python scripts/update_project_claude.py --dry-run

# 指定项目根目录
python scripts/update_project_claude.py --project-root /path/to/project
```

## 配置文件说明

### `.endday.env` 配置项

```bash
# 项目级 CLAUDE.md 维护配置
UPDATE_PROJECT_CLAUDE=true              # 启用项目 CLAUDE.md 自动更新
PROJECT_CLAUDE_FILE=CLAUDE.md           # 项目 CLAUDE.md 文件路径
PROJECT_ROOT=.                          # 项目根目录

# 日记和进度文件
DIARY_DIR=文档/70_工作日记               # 日记存储目录
MEMORY_FILE=MEMORY.md                   # 全局进度文件

# 提交范围（包含项目 CLAUDE.md）
STAGE_PATTERNS=CLAUDE.md,MEMORY.md,文档/70_工作日记,...

# 安全性
CHECK_SENSITIVE=true                    # 敏感文件检查
AUTO_COMMIT=true                        # 自动提交
```

## 项目级 CLAUDE.md 结构

### 自动更新部分
```markdown
## 当前状态（自动更新）

**更新时间**: 2026-03-25 16:15:52

### 项目进度
- Phase Status: 🟡 Phase⑥ in progress
- Latest Commit: dddde3c refactor: ...

### 最新运行结果
- Latest Run: `20260325_152149/` (10 generations)

### LLM 配置
- LLM Model: qwen3.5-plus
- HS Parameters: popSize=5, iteration=10
```

### 手动维护部分（保留）
```markdown
## 快速命令
## 文件地图
## 常见任务
## 详细文档
## 下一步里程碑
```

## 工作流示例

### 典型会话结束流程

```bash
# 1. 完成代码工作
$ git add -A && git commit -m "feature: add X"

# 2. 更新各类文档和进度
$ /endday

# 自动执行：
# [REVIEW] 审视变更 → +10 -5 (5 files)
# [UPDATE] MEMORY.md 已更新 ✓
# [DIARY]  日记已生成 ✓
# [PROJECT-CLAUDE] 项目 CLAUDE.md 已更新 ✓
# [SECURE] 敏感文件检查通过 ✓
# [COMMIT] 提交成功 (abc1234)
# [DONE] 日常工作流完成

# 3. 推送（手动）
$ git push origin master
```

## 自动检测规则

### Phase 状态识别

- **Phase⑤ complete**: 在 git log 中扫描 "Phase⑤"
- **Phase⑥ in progress**: 在 git log 中扫描 "Phase⑥"、"Step1"、"Step2"、"Step3"
- **Step1/2/3**: 如果 git log 包含 "trajectory" 或 "Step3"

### 运行数据识别

- 扫描 `discussion/` 目录找最新的时间戳目录
- 统计该目录下的 `population_result_*.json` 文件数

### 配置识别

- 读取 `config/setting.cfg`：
  - `[llmSettings] model`
  - `[hsSettings] popSize, iteration`

## 故障排除

### 问题 1：脚本找不到 update_project_claude.py

**症状**：`/endday` 时显示 `WARN: update_project_claude.py not found`

**解决**：确保 `scripts/update_project_claude.py` 存在
```bash
ls -la scripts/update_project_claude.py
# 如果不存在，从备份恢复或重新创建
```

### 问题 2：编码错误（Windows）

**症状**：`UnicodeEncodeError: 'gbk' codec can't encode...`

**解决**：脚本已配置了 UTF-8 编码处理，应该自动解决。如果仍有问题：
```bash
# 运行脚本时指定编码
PYTHONIOENCODING=utf-8 python scripts/update_project_claude.py
```

### 问题 3：项目 CLAUDE.md 内容重复或异常

**症状**：多个"当前状态"部分，或内容丢失

**解决**：
```bash
# 删除项目 CLAUDE.md 并重新生成
rm CLAUDE.md
python scripts/update_project_claude.py
```

## 扩展功能建议

### 可选扩展 1：自定义模板

编辑 `scripts/update_project_claude.py` 的 `_generate_claude_content()` 方法来自定义项目 CLAUDE.md 的格式。

### 可选扩展 2：更多自动检测

添加更多启发式规则来检测：
- 代码质量指标（测试覆盖率、CI 状态）
- 待办项（从 git 标签或注释）
- 性能基准（缓存的 benchmark 结果）

### 可选扩展 3：多项目支持

配置多个 `PROJECT_ROOT` 来管理多个项目的 CLAUDE.md：
```bash
PROJECT_CLAUDE_FILE_1=./CLAUDE.md
PROJECT_ROOT_1=.

PROJECT_CLAUDE_FILE_2=../other-project/CLAUDE.md
PROJECT_ROOT_2=../other-project
```

## 许可证与引用

- **endday skill**: 全局可用的项目自动化工具
- **update_project_claude.py**: 本项目特化脚本
- **修改的 endday_main.py**: 向后兼容，所有项目都可受益

## 验证

运行以下命令验证功能工作正常：

```bash
# 1. 检查项目级 CLAUDE.md 存在
ls -la CLAUDE.md

# 2. 检查 .endday.env 配置正确
cat .endday.env | grep UPDATE_PROJECT_CLAUDE

# 3. 运行 dry-run 预览
/endday --dry-run

# 4. 实际运行一次
/endday

# 5. 检查更新时间戳
grep "更新时间" CLAUDE.md
```

---

**最后更新**: 2026-03-25
**维护者**: endday skill + update_project_claude.py
**状态**: ✅ 可用（已测试）
