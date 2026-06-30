# 回归测试平台

回归代码集中在此目录，与 `workspace/` 解耦。只允许 regression 调用 workspace，不允许 workspace 反向依赖 regression。

设计文档：`yaoshi/regressionDesign.md`  
任务拆解：`yaoshi/regressionTask.md`

## 目录结构

```text
regression/
  README.md                 # 本文件
  run_regression.py         # 统一 CLI 入口（Phase 1+）
  case_manager.py           # case 管理（Phase 3）
  spike/                    # Phase 0 可行性验证（临时，不纳入最终 runner）
  runners/                  # design2edit / abd2edit runner
  compare/                  # JSON 语义比较、实例/bbox 比较
  workspace_bridge/         # case <-> workspace/tmp、MCP 封装
  report/                   # Markdown 报告与批量汇总
  schemas/                  # case manifest schema
  .tmp/                     # 每次 run 的隔离临时目录

RegressionCases/            # 回归 case 根目录（可自定义路径）
  <case_id>/
    source/                 # 稳定输入与 baseline
    result/                 # 每次运行覆盖的输出
```

## 当前能力

| 阶段 | 状态 | 目标 |
| --- | --- | --- |
| Phase 0 | 已完成 | spike 验证 editData 链路一致性和 baseline 确定性 |
| Phase 1 | 已完成 | design2edit MVP：`design.json` → `cabinet_script.js` → editData → baseline compare |
| Phase 2 | 已完成 | abd2edit MVP：`abd.json` → design → editData → 实例/bbox 校验 → Report.md |
| Phase 3 | 进行中 | add-case、rebaseline、run-all、批量 Summary、测试与示例 case |

spike 结论写入 `spike/notes/volatile-fields.md`，决定design2edit比较器的默认 `ignorePaths` / `numericTolerance` / 数组顺序策略。

## 常用命令

```bash
python regression/run_regression.py list-cases --cases regressionCases
python regression/run_regression.py run-design2edit --cases regressionCases --case <case_id>
python regression/run_regression.py run-abd2edit --cases regressionCases --case <case_id> --design-backend existing-design
python regression/run_regression.py run-abd2edit --cases regressionCases --stage full --design-backend claude-code
python regression/run_regression.py run-all --cases regressionCases --design-backend existing-design
```

`run-abd2edit` 只保留 `abd.json` 文件存在和 JSON 语法校验，不在回归前置阶段调用 `validate_abd_layout.py` 做 ABD 内容校验；`invalid_size`、`missing_cells`、`invalid_cabinet_size` 等不会作为前置校验阻断回归。`--stage validate` 也只表示基础输入检查和 workspace 输入同步检查。

新增手动 case：

```bash
python regression/run_regression.py add-case \
  --cases regressionCases \
  --case-id <case_id> \
  --abd <abd.json> \
  --preview <previewImage.png> \
  --design <design.json> \
  --baseline <editData.json>
```

人工 Review 后更新 baseline：

```bash
python regression/run_regression.py rebaseline --cases regressionCases --case <case_id>
```

## data-tools 辅助导入

回归运行时不访问线上接口，也不读取登录态。需要从线上或收藏夹样本准备 case 时，先用 data-tools 在本地导出文件，再通过 `add-case` 加入 RegressionCases。

可用的辅助工具：

- `data-tools/utils/fetch_favorite_assembly/generate_assembly_abd.py`
  - 适合从收藏夹/装配数据导出 `abd.json`、封面图和相关参数文件。
- `data-tools/utils/model_info_utils/fetch_combo_case_data.py`
  - 适合抓取组合柜样本的 `editorData.json`、`paramModel.json`、`previewImage.png`，再人工整理为回归 case 输入。

推荐流程：

1. 在 data-tools 中导出或整理本地文件目录。
2. 确认至少有 `abd.json`。
3. 如果要跑design2edit，补齐 `design.json` 和 `baseline.json`。
4. 用 `add-case` 复制到标准 case 目录。
5. 之后的 `run-design2edit` / `run-abd2edit` / `run-all` 只读取本地 RegressionCases。

## 示例

最小示例 case 位于：

```text
regression/examples/minimal-case/source/
  abd.json
  design.json
  baseline.json
```

示例 case 只用于校验目录结构和纯 Python 逻辑，不代表真实 PMBuilder 可执行模型。

## 前置环境

- Python 3.x
- `workspace/skills/parametric-model-design/scripts/generate_pm_script.py`
- `parameditor` MCP（默认 `http://localhost:7764/sse`）
- `param-editor-data` MCP（默认 `http://localhost:7765/sse`）
- KooMaster client 已连接，参数化编辑器已打开模型
