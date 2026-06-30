---
name: image-to-abd
description: >-
  根据用户输入的图片和文字描述，分析组合柜结构，生成 abd_for_review.json 骨架。
disable-model-invocation: true
---
# image/text -> abd_for_review.json

## 输入 / 输出

输入
1. 用户需求，包含对于组合柜的文字描述
2. 用户上传图片（非必须）

| 输出 | 路径 | 必填 |
|------|------|------|
| abd_for_review.json | `../workspace/tmp/input/abd_for_review.json` | 是 |
| abd_analysis_audit.json | `../workspace/tmp/input/abd_analysis_audit.json` | 否，仅按需输出 |

## 流程

### 步骤 1. 生成 abd_for_review.json 骨架

读取用户输入与图片，结合领域知识 `skills/image-to-abd/references/domain.md`，分析组合柜结构，输出 `../workspace/tmp/input/abd_for_review.json`。

### 步骤 2. 记录推理轨迹（按需）

当用户的提示词中含有**记录推理过程、输出推理轨迹、审计分析、debug 推理**等类似意图时，将分析推理过程写入 `../workspace/tmp/input/abd_analysis_audit.json`。

## json 格式

### abd_for_review.json 结构

下面是一个完整的 JSON 示例（4 门衣柜场景：边柜 + 单门柜 + 双门带抽柜）：
- 模板：[`templates/abd_for_review.example.json`](templates/abd_for_review.example.json)

#### basic_info 字段

| 字段 | 类型 | 枚举 / 范围 | 必填 | 说明 |
|---|---|---|---|---|
| `W` | int (mm) | — | 必填 | 组合柜总宽 |
| `H` | int (mm) | — | 必填 | 组合柜总高 |
| `D` | int (mm) | — | 必填 | 组合柜总深 |
| `total_bay_count` | int | ≥1 | 必填 | 立面分格总数 |
| `unit_count_main` | int | ≥1 | 必填 | 单元柜总数 |

#### units[] 单项字段

| 字段 | 类型 | 枚举 / 范围 | 必填 | 说明 |
|---|---|---|---|---|
| `slot` | int | ≥1 | 必填 | 从左到右编号 |
| `type` | string | `高柜/下柜` / `边柜` / `开放柜` / `其他` | 必填 | 禁止写`高柜`单独一词 |
| `obsBrandGoodId` | string | `""` | 必填 | 骨架阶段留空字符串，由 agent 在选型阶段写入，不得编造 |
| `door_count` | int | 0 / 1 / 2 | 必填 | 0=开放柜；上下分段门板按可见独立门板数累计 |
| `bay_count` | int | 1 / 2 | 必填 | 1=独占1分格；2=合并2分格 |
| `drawer_count` | int | ≥0 | 必填 | 无抽屉填0 |
| `has_open_shelf` | bool | true / false | 必填 | 含开放区域则 true |
| `est_width` | int (mm) | — | 必填 | 单元柜估计宽度 |
| `est_height` | int (mm) | — | 必填 | 单元柜估计高度 |
| `position` | string | — | 选填 | 如"左数第1个（占第1-2分格）" |
| `handle_style` | string | — | 选填 | 自由文本描述，从图像推测拉手样式 |
| `summary` | string | — | 选填 | 综合描述 |

### abd_analysis_audit.json 结构

```json
{
  "source_info": "图片展示了一个一字到顶的三门衣柜，白门浅木纹柜体，左侧边柜上段开放...",
  "analysis_trace": {
    "step1_identify_modules": {
      "1_1_edge_cabinet": "可选；识别边柜/异形开放格模块的推导说明，没有可留空字符串",
      "1_2_open_cabinet": "可选；识别开放柜的推导说明，没有可留空字符串",
      "1_3_main_modules": "可选；识别主体高柜/下柜模块的推导说明，没有可留空字符串"
    },
    "step2_identify_attributes": "可选；识别每个单元柜属性的推导说明，没有可留空字符串",
    "step3_output_json": "可选；通常省略"
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `source_info` | 必填 | LLM 初步观察的自然语言描述 |
| `analysis_trace` | 可选 | 各分析步骤的推导轨迹（事后记录） |
| `analysis_trace.step1_identify_modules.1_1_edge_cabinet` | 可选 | 步骤 1.1 边柜/异形开放格识别过程 |
| `analysis_trace.step1_identify_modules.1_2_open_cabinet` | 可选 | 步骤 1.2 开放柜识别过程 |
| `analysis_trace.step1_identify_modules.1_3_main_modules` | 可选 | 步骤 1.3 主体高柜/下柜模块识别过程 |
| `analysis_trace.step2_identify_attributes` | 可选 | 步骤 2 各单元柜属性识别过程 |
| `analysis_trace.step3_output_json` | 可选 | 步骤 3 输出 JSON 说明，通常省略 |
