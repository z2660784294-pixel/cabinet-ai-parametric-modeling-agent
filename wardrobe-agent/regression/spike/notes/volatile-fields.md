# Phase 0 Spike 结论：易变字段与比较器策略

本文件结论直接决定 Phase 1 `json_semantic_compare.py` 的默认行为。

## Case 信息

| 项 | 值 |
| --- | --- |
| case_id | `3FO3ENTUXJQB` |
| spike 日期 | 2026-06-12 |
| 执行人 | yaoshi / Claude |
| parameditor URL | `http://localhost:7764/sse` |
| param-editor-data URL | `http://localhost:7765/sse` |

## 0a. editData 链路一致性

- [x] `clear_scene` → `execute_script` → `get_current_editor_data` 链路跑通
- [x] 导出 editData 反映本次脚本执行结果（非历史 stale 数据）

备注：

```text
使用 regressionCases/3FO3ENTUXJQB/source/abd.json 与 design.json，通过现有 generate_pm_script.py 生成 cabinet_script.js。
run1/run2 均成功调用 parameditor.clear_scene、parameditor.execute_script(srcInput=<cabinet_script.js 绝对路径>)、param-editor-data.get_current_editor_data(destOutput=<editData.json 绝对路径>)。
两次 output.log 均显示 editData 写入对应 run 目录，导出 JSON 可解析。
```

## 0b. 两次 run 对比

| 对比项 | run1 路径 | run2 路径 |
| --- | --- | --- |
| editData | `regression/spike/output/run1/editData.json` | `regression/spike/output/run2/editData.json` |
| diff | | `regression/spike/output/diff/editData-diff.json` |

两次 run 是否语义一致：**部分一致**

## 发现的易变字段

| JSON 路径 | 类型 | 示例差异 | 建议处理 |
| --- | --- | --- | --- |
| `$.inputs[*].id` | 自增 id | `25` → `42`、`26` → `43` | `ignorePaths` |
| `$.modelInstances[*].uniqueId` | 随机/运行时 id | `k5a13ij1nc` → `ahmi5nm2kj` | `ignorePaths` |

未发现时间戳、环境字段、数组顺序不稳定或浮点抖动。两次 diff 共 25 处，全部集中在上述运行时标识字段。

## Phase 1 比较器策略建议

```json
{
  "objectKeyOrderSensitive": false,
  "arrayOrderStrict": true,
  "ignorePaths": [
    "$.inputs[*].id",
    "$.modelInstances[*].uniqueId"
  ],
  "numericTolerance": 0,
  "notes": "Phase 0 仅发现运行时自增/随机 id 易变；对象 key 顺序不敏感，数组顺序保持严格，数值精确比较。"
}
```

### 数组顺序

- [x] 保持严格（默认）
- [ ] 改为按稳定 key 排序后比较（说明 key：）

### 其他说明

```text
Phase 1 MVP 比较器应最小支持 ignorePaths，先覆盖 $.inputs[*].id 与 $.modelInstances[*].uniqueId。
不需要默认 numericTolerance，也不需要数组稳定 key 排序策略。
```
