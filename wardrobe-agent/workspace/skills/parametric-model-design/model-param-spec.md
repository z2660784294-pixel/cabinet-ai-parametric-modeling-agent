# 模型参数规则模板
本文档说明在生成 `design.json` 时，父模型（组合柜）与子模型（单元柜）参数的定义和关联规则。请仔细阅读并遵守以下约定，以确保生成的 `design.json` 正确绑定参数并实现预期功能。

## 文档列说明

| 列名 | 含义 |
| --- | --- |
| **值范围** | **interval** 写 `min-max`；**enum** 写 `取值1/取值2/…`；**formula** / **fixedFormula** / **single** 等写 `—` |
| **出现条件** | `必配` = 所有组合柜都创建；`含边柜` = 存在名称含「边柜」的单元柜（须同时创建 `#BGW`、`#ZBGYS`、`#YBGYS`） |
| **子模型绑定** | 见「规则 A/B」 |
| **参数规则** | 位置、`#ignore`、尺寸公式等；镜像场景见「镜像排布」 |

## 父模型参数列表

#### 基础变量

1.子模型排布宽度之和 + 收口 + 边柜 = 父级 `#W` 默认值。
2.子模型基础材质统一引用父级 `#CZ`。在 `design.json` 中：`parentParams` 声明 `#CZ`；每个 `units[]` 通过 `paramOverrides` 绑定（见「#CZ 特例」）。

#### 自定义变量

| 引用名 | 名称 | valueType | paramTypeId | 值范围 | 当前值 | 出现条件 | 子模型绑定 | 参数规则 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `#WGJX` | 外观镜像 | string | enum | 左/右 | 左 | 必配 | — | 见「镜像排布」 |
| `#BGW` | 边柜宽 | float | interval | 200-600 | 450 | 含边柜 | 规则 B | 见「镜像排布」 |
| `#QYW1…N` | N 号柜宽 | float | formula | 200-1200 | 按门数 | 必配 | 规则 B | 净宽=`#W-#SK_L-#SK_R-#BGW`；按门数比例分配；X 见镜像表 |
| `#ZBGYS` | 左边柜样式 | style | enum | 3FO4K6WK7T8S | 3FO3G6FC18UH | 含边柜 | 规则 B | 见镜像表 |
| `#YBGYS` | 右边柜样式 | style | enum | 3FO4K6WK7PVR | 3FO3G6IVO2QA | 含边柜 | 规则 B | 见镜像表 |
| `#ST` | 柜体板厚 | float | interval | 3-100 | 18 | 必配 | 规则 A | — |
| `#TH` | 脚线高度 | int | interval | 0-1000 | 80 | 必配 | 规则 A + TH 特例 | — |
| `#CZ` | 基础材质 | material | single | — | 取 ABD 子模型当前值 | 必配 | 规则 B + CZ 特例 | — |
| `#GMCZ` | 柜门材质 | material | single | — | 3FO446UKPKPA | 必配 | 规则 A |  — |
| `#SK_T` | 顶收口高度 | float | interval | 0-300 | 50 | 必配 | 规则 A/B | 顶收口 Z=`(#H-#SK_T)`；其余见规则 B |
| `#SKYS_L` | 左收口样式 | string | enum | 无/有/见光板/侧收口 | 有 | 必配 | 规则 A | `#ignore`：`#SKYS_L=="无"`；含边柜加 `or #WGJX=="右"` |
| `#SKYS_R` | 右收口样式 | string | enum | 无/有/见光板/侧收口 | 见光板 | 必配 | 规则 A | `#ignore`：`#SKYS_R=="无"`；含边柜加 `or #WGJX=="左"` |
| `#SK_L` | 左收口宽度 | float | fixedFormula | — | — | 必配 | 规则 A/B | 含边柜：`#SKYS_L=="无" or #WGJX=="右"?0:#SKYS_L=="有"?50:18`；无边柜：`#SKYS_L=="无"?0:#SKYS_L=="有"?50:18` |
| `#SK_R` | 右收口宽度 | float | fixedFormula | — | — | 必配 | 规则 A/B | 含边柜：`#SKYS_R=="无" or #WGJX=="左"?0:#SKYS_R=="有"?50:18`；无边柜：`#SKYS_R=="无"?0:#SKYS_R=="有"?50:18` |

##### 自定义变量说明
- valueType=string|int|float，且paramTypeId=enum时，`值范围`需写成name|value形式，无明确说明，则name=value，如`"editorOptions": [{ "name": "无", "value": "无" }]`

## 父子参数关联

对每个子模型实例，先 `query_param_list` 得到 **paramName** 列表，再绑定。

### 规则 A：允许绑定

将下列父级参数表达式写入`design.json` 对应 `units[]` 中的 WDH 参数以及 `paramOverrides` 中；参数格式参考 `designjosn-param-fields.md`。

| 场景 | 写法 |
| --- | --- |
| N 号柜净宽 | 子 `#W` ← `#QYWk` |
| 左/右收口条宽 | 子 `#W` ← `#SK_L` / `#SK_R` |
| 顶收口宽 | 子 `#W` ← `(#W-#SK_L-#SK_R-#BGW)`（无边柜则减 `#SK_R` 即可） |
| 顶收口高 | 子 `#H` ← `#SK_T` |
| 下柜净高 | 名称含「下柜」：`#H` ← `(#H-#SK_T)` |
| 边柜高 | 名称含「边柜」：`#H` ← `#H`（不减 `#SK_T`） |
| 边柜样式/宽 | `#functionName` ← `#ZBGYS`/`#YBGYS`；`#W` ← `#BGW` |

写法示例：
```json
"paramOverrides": {
  "functionName": "#ZBGYS"
}
```

### 规则 B：禁止绑定
未出现在规则 A 中的父级变量，**不要** 写入到子模型。例如：
1. **禁止**绑 `tjgd` 到 `TH`
2. **不要**将 `#CZ` 绑到门板/背板类参数（如 `Z_YMCZ`、`Z_BBCZDY`、`Z_TMCZ`）；那些由子模型自身或 `#GMCZ` 控制。

### 镜像排布（含边柜 + `#WGJX` 时必读）

在 **中间单元区**（`#SK_L` ～ `#W-#SK_R`）内水平翻转。`#WGJX=="左"` 为 ABD 默认；`#WGJX=="右"` 时中间区首位↔末位互换，1…N 号柜视觉顺序 N…1。

**左右收口不参与镜像**（恒 `X=0` / `X=#W-#SK_R`，仅 `#ignore` 显隐）。参与镜像者（边柜、下柜、顶收口）：

```text
X = #WGJX=="左" ? X左 : (#W - #SK_R - (X左 - #SK_L) - W柜)
```

右分支**只减 `#SK_R`，不减 `#SK_L`**；禁止写 `#W-#SK_L-…`，禁止用平移代替翻转。

| 实例 | 镜像 | 左镜像 `X左` | `W柜` | `#ignore` |
| --- | --- | --- | --- | --- |
| 左收口 | 否 | `0` | `#SK_L` | `#SKYS_L=="无" or #WGJX=="右"` |
| 左边柜 | 是 | `0` | `#BGW` | `#WGJX=="左"` |
| k 号柜 | 是 | `#SK_L+#QYW1+…+#QYW(k-1)` | `#QYWk` | — |
| 右边柜 | 是 | `#SK_L+#QYW1+…+#QYWn` | `#BGW` | `#WGJX=="右"` |
| 右收口 | 否 | `#W-#SK_R` | `#SK_R` | `#SKYS_R=="无" or #WGJX=="左"` |
| 顶收口 | 是 | `#SK_L` | `(#W-#SK_L-#SK_R-#BGW)` | — |

示例（3 号柜）：`(#WGJX=="左"?(#SK_L+#QYW1+#QYW2):(#W-#SK_R-#QYW1-#QYW2-#QYW3))`。

## 生成后 Checklist
- 父模型参数已全部出现在`design.json`的`parentParams`中；
- 逐实例查 `query_param_list`，按规则 A/B 补全绑定（含两侧边柜、全部下柜）
- `#ST` 未绑异名；`#TH` 已绑全部下柜/边柜
- 顶收口 `#W`=`(#W-#SK_L-#SK_R-#BGW)`；边柜 `#H`=`#H`；
- 镜像符合「镜像排布」（收口不参与、右分支不减 `#SK_L`）
