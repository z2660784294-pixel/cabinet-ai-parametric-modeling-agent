---
name: parametric-model-design
description: >-
  基于组合柜描述 tmp/input/abd.json, 推断出合理的 design.json, 并生成参数化脚本 tmp/output/cabinet_script.js。
  注意一定要调用 generate_pm_script.py 生成 cabinet_script.js，不可自行生成
  disable-model-invocation: true
---

## 输入 / 输出

| 输入 | 路径 | 必需 |
|------|------|------|
| abd.json | `tmp/input/abd.json` | 是 |

| 输出 | 路径 |
|------|------|
| cabinet_script.js | `tmp/output/cabinet_script.js` |

## 流程

### 1. 生成组合柜布局设计 design.json
根据组合柜描述 abd.json，结合 `skills/parametric-model-design/model-param-spec.md` 中的说明，生成组合柜父模型参数和父子模型参数关联规则。 按照 `skills/parametric-model-design/designjson-schema/schema.md`中定义的**格式**, 生成 design.json, 写到`tmp/output/design.json`. 

注意：
- `designjson-schema/example.json`仅作为格式参考，**禁止照搬**任何参数到 `design.json` 中。
- `design.json` 的 `units[]` 必须包含 `abd.json` 的 `units[]` 中的**每一个**实例，（按 `id` + `obsBrandGoodId` 匹配）。**不得**因「摆件」「电器」「软装」「挂件」等非柜体商品而省略。
- abd 中的 `position` / `rotate` / `size` **仅用于推断相对布局**（分列、叠放、总 WDH），勿照抄为子模型坐标
- abd 中的 `position` 一般是该单元柜实例的左后下点
- 标明”必配“的参数是必须生成的。 
- 当最外侧单元柜不对称结构单元柜时（如转角柜、边柜、多边形柜等），需要判断组合模型需要添加镜像条件，并增加一个与这个不对称单元柜相镜像的单元柜模型参与建模（如已有左转角柜，需要补充右转角柜模型）
- 按“备注”要求生成参数公式. 确保生成的子模型实例之间的相对位置关系正确，模型实例之间不互相干涉，但也不要完全孤立或存在间隙
- 在没有明确要求的旋转情况下不要对任何子模型进行任何方向上的旋转
- 单元柜深度一般应为 `#D` 或其它类似表达式。严禁使用 `18` 这样明显不合理的数值
- design.json 中的 `units[].id` 必须使用 `abd.json` 中对应单元的真实实例 id（`units[].id`）
- 所有在 `abd.json` 的 `parentParams` 中的参数都必须被包含在 `design.json`的 `parentParams` 中，参数取值以  `abd.json` 中为准

#### 利用 bbox 差异反馈修正（重试时）

当 `tmp/output/bbox_diff.json` 存在且包含 `status: "different"` 的条目时，说明上一轮生成的脚本执行后，场景中实际 bbox 与 abd.json 期望不符。需读取该文件并据此修正 `design.json`。

`bbox_diff.json` 中每个 `different` 条目的结构：

```json
{
  "obsBrandGoodId": "3FO3PVG4P0Y6",
  "name": "【2门断背高柜】V1",
  "status": "different",
  "scene_bbox": { "position": {...}, "size": {...} },
  "abd_bbox":   { "position": {...}, "size": {...} },
  "diff": {
    "position": { "x": 150, "y": 0, "z": -30 },
    "size":     { "x": 0, "y": 0, "z": 50 }
  }
}
```

> `diff` = `scene - abd_bbox`（`abd_bbox` 已由校验脚本将 abd 从中心原点变换到场景左后下坐标系），正值表示场景偏大/偏右，负值表示偏小/偏左。

**修正策略：**

- **size 差异**：说明子模型实际渲染尺寸与 design.json 中 W/D/H 表达式求值结果不符。检查对应 unit 的 `size.W/D/H` 表达式和 `parentParams` 的默认值，使默认值下的表达式求值等于 abd.json 中的 `size`。 修正时，要采取修正表达式的方式，不可为了追求数值相等，直接将表达式改为数值。保持表达式里的参数关联，优先于数值正确。
  仅修正有差异的条目对应的 unit 的 size ，不改动 `identical` 的 unit 的size。
- **position 差异**：说明子模型实际摆放位置与预期有偏移。检查对应 unit 的 `position` 表达式，确保默认参数值下的位置正确反映 abd.json 中各子模型的相对布局关系。

### 2. 生成脚本

```bash
python skills/parametric-model-design/scripts/generate_pm_script.py \
  --abd tmp/input/abd.json \
  --design tmp/output/design.json \
  -o tmp/output/cabinet_script.js
```

`generate_pm_script.py` 负责：
a. 为父模型创建一堆固定的工艺参数
b. 如果子模型上有任何参数名称和现有的父模型参数相同，那么把父模型参数的表达式设给该子模型参数
c. 对于子模型上其它的参数，从一个固定的参数描述json 文件里读取当前值，并设给这个参数


