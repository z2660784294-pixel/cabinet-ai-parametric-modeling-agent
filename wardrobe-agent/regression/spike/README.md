# Phase 0：闭环可行性 Spike

在投入 CLI 与 runner 脚手架前，用最小脚本验证 editData 链路与 baseline 确定性。

## 验证目标

### 0a. editData 链路一致性

确认 `parameditor` 与 `param-editor-data` 跨服务调用后，导出的 editData 反映**本次**脚本执行结果。

```text
source/abd.json + source/design.json
  -> generate_pm_script.py
  -> cabinet_script.js
  -> clear_scene
  -> execute_script(srcInput=<cabinet_script.js 本地完整路径>)
  -> get_current_editor_data(destOutput=<editData.json 本地完整路径>)
```

**注意**：`execute_script` 传的是脚本文件的本地路径（`srcInput`），不是脚本正文。

### 0b. baseline 确定性

同一 case **连跑两次**，比较两次导出的 editData，记录差异字段类型：

- 自增 id
- 时间戳
- 环境字段
- 数组顺序不稳定
- 浮点抖动

结论写入 [`notes/volatile-fields.md`](notes/volatile-fields.md)。

## 目录说明

```text
spike/
  README.md              # 本文件
  scripts/               # 临时 spike 脚本（手动编写，不要求纳入最终 runner）
  notes/
    volatile-fields.md   # spike 结论：易变字段清单与比较器策略建议
  output/
    run1/                # 第一次运行产物
    run2/                # 第二次运行产物
    diff/                # 两次 editData 的 diff 结果
```

## 建议产出（每次 run）

将以下文件放入对应 `output/run1/` 或 `output/run2/`：

| 文件 | 说明 |
| --- | --- |
| `cabinet_script.js` | `generate_pm_script.py` 生成 |
| `editData.json` | `get_current_editor_data` 导出 |
| `output.log` | 各步骤 stdout/stderr |

`output/diff/` 建议放置：

| 文件 | 说明 |
| --- | --- |
| `editData-diff.json` | 两次 editData 的结构化 diff |
| `summary.md` | 人工可读摘要 |

## 手动步骤参考

### 1. 准备 case

在 `RegressionCases/caseA/source/` 放入：

- `abd.json`
- `design.json`
- `baseline.json`（可选，spike 阶段主要用于后续 Phase 1；0b 可与两次 run 互比）

### 2. 生成脚本

```bash
python workspace/skills/parametric-model-design/scripts/generate_pm_script.py \
  --abd RegressionCases/caseA/source/abd.json \
  --design RegressionCases/caseA/source/design.json \
  -o regression/spike/output/run1/cabinet_script.js
```

（第二次运行改用 `run2/` 目录。）

### 3. MCP 执行与导出

通过 MCP 客户端或 Cursor 内置 MCP 工具依次调用：

1. `parameditor` → `clear_scene`
2. `parameditor` → `execute_script`，`srcInput` = `cabinet_script.js` 的**绝对路径**
3. `param-editor-data` → `get_current_editor_data`，`destOutput` = `editData.json` 的**绝对路径**

### 4. 重复 run2 并 diff

将 run1 与 run2 的 `editData.json` 做 diff，把结论填入 `notes/volatile-fields.md`。

## 验收标准

- [ ] 单次 run 能成功导出可解析的 `editData.json`
- [ ] 导出内容与本次脚本执行相关（非 stale 数据）
- [ ] 连跑两次并完成 diff
- [ ] `volatile-fields.md` 已填写，含 Phase 1 比较器策略建议
