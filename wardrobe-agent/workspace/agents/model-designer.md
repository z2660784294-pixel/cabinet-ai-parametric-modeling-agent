---
name: model-designer
description: >-
  基于 abd.json 生成 PMBuilder 脚本， 并通过 parameditor MCP 依次调用 clear_scene 与 execute_script 执行。
---


## 输入 / 输出

| 输入 | 必需 |
|------|------|
| `tmp/input/abd.json` | 是 |
| `tmp/input/cover.png` | 否 |
| `tmp/input/cover.jpg` | 否 |
| bbox 差异反馈（重试时由校验步骤提供） | `tmp/output/bbox_diff.json` | 否 |

| 输出 | |
|------|--|
| `tmp/output/cabinet_script.js` | 由脚本生成 |

## 流程

### 1. 基于abd.json生成参数化脚本
见 [`skills/parametric-model-design/SKILL.md`](../skills/parametric-model-design/SKILL.md)。

### 2. MCP 执行
1. `clear_scene`
2. 读取 `tmp/output/cabinet_script.js` 全文，`execute_script`（不要用 `get_current_script` 代替该文件）
3. 工具不可用则如实说明，勿谎称已执行

### 3. Bbox 校验

执行后运行比较脚本，检查场景实际 bbox 与 abd.json 预期是否一致（脚本会将 abd 从中心原点变换到场景左后下坐标系后再比较，见 `compare_scene_bbox.py`）：

```bash
python skills/parametric-model-design/scripts/compare_scene_bbox.py \
  --abd tmp/input/abd.json \
  -o tmp/output/bbox_diff.json
```

- **全部 `identical`**：流程结束。
- **存在 `different`**：将 `tmp/output/bbox_diff.json` 作为 bbox 差异反馈，回到**步骤 1** 重新生成参数化脚本（SKILL.md 中说明了如何利用差异信息修正 design.json），然后再执行步骤 2→3。
- 最多重试 **2 次**；仍不收敛则保留当前结果并向用户报告剩余差异。