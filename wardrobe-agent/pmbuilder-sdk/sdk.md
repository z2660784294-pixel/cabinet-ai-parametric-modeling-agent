# PMBuilder SDK 参考

参数化脚本在宿主环境中以 **JavaScript** 运行，仅可使用下文 **5 个 API**。`PMBuilder` 为全局常量，无需也无法 `new`。

## 表达式与字面量（括号）

- 传入**表达式**时须用圆括号整体包裹，例如 `'(#H-#T)'`、`'(#W+#D)'`；仅单个 `#` 引用且无运算符时可写作 `'#W'`（与下文示例一致）。
- **纯数字等字面量**不要使用圆括号，例如 `'18.0'`、`'600'`。

适用于 `createParam` 的 `value`、`setParam` 的 `paramValue`，以及 `setPosition` / `setRotation` 中可作为表达式传入的坐标或角度。

---

## `1. PMBuilder.createParam(name, value, valueType, displayName, paramTypeId, options?)`

创建顶层参数化模型（父模型）参数。

### `name`

- 参数名，**必须以 `#` 开头**，例如 `#W`、`#D`、`#H`。

### `value`

当前取值形态由 `**paramTypeId`** 决定，常见形态如下：


| 形态               | 说明                                                                                                          |
| ---------------- | ----------------------------------------------------------------------------------------------------------- |
| **single**       | 浮点/整数**字符串**或布尔字符串，如 `'18.0'`、`'600'`、`'true'`、`'false'`                                                    |
| **constant**     | 与 single 同形态的**固定字面量**（随 `valueType`），**不含** `#` |
| **interval**     | 与 single 同形态的**当前数值字符串**；宜落在 `options.min`～`options.max` 之间，如 `'1500'`，**不含** `#`                           |
| **enum**         | 枚举；valueType为`float`|`int`|`string`时，枚举值在 `options.editorOptions` 中定义；valueType为 `style`| `shape`|`material`时时，枚举值以link和linkForm体现    |
| **fixedFormula** | 表达式字符串，**必须用圆括号包裹**，如 `'(#W+#D)'`、`'(#W/2+#WX)'` |
| **formula**      | 复合公式|
| **formulaEnum**  | 公式+可选|

### `valueType`

字符串枚举，常用值：


| 值           | 含义          |
| ----------- | ----------- |
| `'float'`   | 浮点数（多数尺寸参数） |
| `'int'`     | 整数          |
| `'string'`  | 字符串         |
| `'boolean'` | 布尔          |
| `'material'` | 材质          |
| `'style'` | 样式          |
| `'shape'` | 轮廓          |
| `'booleanlist'` | 多布尔类型          |

### `valueType` × `paramTypeId` 常见搭配

表中数字为 `**paramTypeId**`。


| valueType           | 可用的 paramTypeId                                                                             |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `'float'` / `'int'` | **1** interval，**2** enum，**4** formula，**5** fixedFormula，**6** constant，**7** formulaEnum |
| `'string'`          | **2**，**4**，**5**，**6**，**7**（string 时 `**options` 勿传 `min`/`max`**）                        |
| `'boolean'`         | **0** single，**6** constant   |
| `'material'`| **0** single，**2** enum，**4** formula，**5** fixedFormula，**6** constant |
| `'style'`| **0** single，**2** enum，**4** formula，**5** fixedFormula，**6** constant |
| `'shape'`| **0** single，**2** enum，**4** formula，**5** fixedFormula，**6** constant |
| `'booleanlist'`| **0** single，**6** constant|

### `displayName`
- 参数显示名；

### `paramTypeId`


| ID    | 名称           | 含义                                                                                                                      |
| ----- | ------------ | ----------------------------------------------------------------------------------------------------------------------- |
| **0** | single       | 无限制                                                                                                                     |
| **1** | interval     | 区间数值. **必须**配合 `options.min`、`options.max`                                                                               |
| **2** | enum         | 可选. `value` 为当前枚举值，仅当valueType为`float`|`int`|`string`时，`options.editorOptions` 内为所有枚举值列；        |
| **4** | formula      | 复合公式. 由`options.status`字段决定当前值为值还是公式； **float/int** 须同时传 `min`/`max`；**string** 时 **禁止**在 `options` 中出现 `min`/`max` |
| **5** | fixedFormula | 公式. `value` 含 `#` 的公式，如 `'(#W/2+#WX)'`                                                                                      |
| **6** | constant     | 固定值                                                                                                                     |
| **7** | formulaEnum  | 复合公式+可选.  `value` 为当前枚举值, `options.editorOptions`内为所有枚举值列表，`options.formula`内为公式                      |


### `options`（可选）

不传可省略该参数，或传入 `{}`。常用字段：


| 字段            | 说明                                                                                                                                                        |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `min` / `max` | 与 **float/int** 一致的数字字符串（如 `'0'`、`'6000'`）。**paramTypeId = 1** 时必填；**paramTypeId = 4** 且 **float/int** 时必填（约束 interval 一侧）。**valueType 为 string 时一律不要传。** |
| `group`       | 分组名，用于归类展示，其中：inner(内部变量)、report(报告变量)、system(系统变量)为内置group名                                                                                              |
| `ignore`      | 条件公式（含 `#` 须括号包裹，同 fixedFormula）；参数**隐藏条件**|
| `formulaForm` | 复合公式中的公式类型，**paramTypeId = 4** 时必填，0=公式，1=条件(casesJSON)，默认为0; |
| `status`      | 复合公式状态，**paramTypeId = 4** 时必填，status: 0=当前生效为值侧, `value` 为当前值；status: 1=当前生效为公式侧; status 默认 1 |
| `valueDisplayNames` | 多布尔参数补充属性，**valueType=booleanlist**时，必填，内容为：`["name1","name2"]`|
| `editorOptions` | 枚举类型补充属性，**valueType为`float`|`int`|`string`并且paramTypeId=2**或**paramTypeId=7**时，必填，内容示例：`[{ name: '20', value: '20' }, { name: '30', value: '30' }]`|
| `link` | 轮廓/材质/样式类型补充属性，**valueType为shape/material/style并且paramTypeId为2或4**时，必填，内容示例为：`"3FO4K5T6QLJ2"` 或 `'{"cases":[{"condition":"#W==50","value":"3FO4K5T6QLJ2"}],"defaultValue":"3FO4K5T67V6G"}'` |
| `linkForm` | 轮廓/材质/样式类型补充属性，**valueType为shape/material/style并且paramTypeId为2或4**时，必填，内容为：`"0"` 或 `"1"`，其中 `"0"` 表示 link 是指定文件夹 id，`"1"` 表示 link 是条件文件夹 JSON (含 cases/defaultValue) |
| `formula` | 公式属性， formulaForm=0 为 spel 字符串, formulaForm=1 为 {cases, defaultValue} 对象, 内容示例为 `{ cases: [{ condition: '#W==200', value: '{"obsBrandGoodId":"3FO3NGURA302","versionId":10}' }, { condition: '#W==300', value: '{"obsBrandGoodId":"3FO3K04GWD9L","versionId":6}' }], defaultValue: '{"obsBrandGoodId":"3FO3NGTYT0MM","versionId":5}' } }` |

---

## `2. PMBuilder.createModelInstance(obsBrandGoodId)`

创建指定商品的子模型实例，**返回子模型实例 id**。


| 参数               | 说明    |
| ---------------- | ----- |
| `obsBrandGoodId` | 商品 ID |


---

## `3. PMBuilder.setParam(modelInstanceId, paramName, paramValue, options?)`

设置子模型实例的参数值。


| 参数                | 说明                                   |
| ----------------- | ------------------------------------ |
| `modelInstanceId` | 模型实例 id                              |
| `paramName`       | 参数名，须 `#` 开头，如 `#W`。                  |
| `paramValue`      | 数值字符串如 `'18.0'`，或表达式字符串如 `'(#W+#D)'`，或者其他字符串 |
| `options`         | 可选项，常用字段：`status`, 复合公式参数 (paramTypeId 4/7) 的当前生效侧, 0=值侧, 1=公式侧; `formulaForm`, 显式指定公式类型 (0=spel, 1=condition);|

#### 内置参数名

以下参数名具有特殊含义，可在 `setParam` 中使用：

- `#materialBrandGoodId`：材质变量，用于设置模型材质
- `#ignore`：隐藏条件，用于控制模型可见性
- `#invokedPosType`: 调用点类型，0（原点），2（左后下）
- `#functionName`: 模型样式，其值通常关联样式变量
- `#name`: 模型名称，显示在参数化编辑器画布右侧结构导航栏
- `#refName`: 模型引用名，用于在兄弟模型的参数表达式中引用，例如 `#refName` 的值为 `A5`，则同级模型的参数表达式中可以通过 `@A5.Z_TMHD` 来引用该模型的 `Z_TMHD` 参数值
---

## `4. PMBuilder.setPosition(id, position_x, position_y, position_z)`

设置子模型实例在 3D 空间中的**位置**（一般为定位点，多见**左后下**，具体以商品为准）。


| 参数                                         | 说明                                          |
| ------------------------------------------ | ------------------------------------------- |
| `id`                                       | 模型实例 id                                     |
| `position_x` / `position_y` / `position_z` | 坐标；可为数字字符串或含 `#` 的表达式（括号约定见上文「表达式与字面量（括号）」） |


---

## `5. PMBuilder.setRotation(id, rotation_x, rotation_y, rotation_z)`

设置子模型实例绕各轴**旋转角度**。


| 参数                                         | 说明             |
| ------------------------------------------ | -------------- |
| `id`                                       | 模型实例 id        |
| `rotation_x` / `rotation_y` / `rotation_z` | 角度；可为数字字符串或表达式 |


**说明：** `setPosition` / `setRotation` 的坐标与角度参数均可写 `'800'` 这类字面量，或 `'#W'`、`'(#W+#D)'` 等表达式（括号约定见上文「表达式与字面量（括号）」）。

## 参数化脚本编写规范
1. 赋值到子实例身上的参数和表达式的默认取值，需要满足该子实例参数定义的min/max/enum要求
2. `createParam` 的 `displayName` 字段必须使用中文，且能清晰表达参数意图

## 参数化脚本常见语法错误

1. 使用了console.log, return语句, 尽管这些语句符合JavaScript语法, 但仍然会使脚本执行失败
2. 错误地将PMBuilder创建的参数和JavaScript参数混用, 注意PMBuilder创建的参数引用只有PMBuilder能够解析, 必须以字符串表达式的形式传入;相对的, 如果想要在参数表达式中使用JavaScript变量, 请使用模板字符串
3. 使用模板字符串时使用了普通的单引号或双引号, 而不是反引号
4. 修改模型参数、位置、旋转时未传入模型名称, 或调用setPosition时未传入模型id或错误地传入模型名称
5. 调用SDK中未定义的函数,如getSceneInfo, PMBuilder.addFeedback等
6. 试图创建PMBuilder实例, 注意PMBuilder是脚本执行环境下的全局常量, 无需创建
7. 使用参数时未加上#前缀