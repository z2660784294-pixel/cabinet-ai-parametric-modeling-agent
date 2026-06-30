# 参数化模型参数字段说明

在design.json 里定义参数化模型的参数，需要提供如下字段

---

## 必选字段

创建顶层参数化模型（父模型）参数。

### `name`

- 参数名，**必须以 `#` 开头**，例如 `#W`、`#D`、`#H`。

### `value`

当前取值形态由 `**paramTypeId`** 决定，常见形态如下：

| 形态               | 说明                                                                                                          |
| ---------------- | ----------------------------------------------------------------------------------------------------------- |
| **single**       | 浮点/整数**字符串**或布尔字符串，如 `'18.0'`、`'600'`、`'true'`、`'false'`                                                    |
| **constant**     | 与 single 同形态的**固定字面量**（随 `valueType`），**不含** `#` |
| **interval**     | 与 single 同形态的**当前数值字符串**；宜落在 `min`～`max` 之间，如 `'1500'`，**不含** `#`                           |
| **enum**         | 枚举值；valueType为`float`|`int`|`string`时，枚举值在 `editorOptions` 中定义；valueType为 `style`| `shape`|`material`时时，枚举值以link和linkForm体现               |
| **formula**      | 表达式字符串，**必须用圆括号包裹**，如 `'(#W+#D)'`、`'(#W/2+#WX)'` |


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


### `displayName`
- 参数显示名，需使用中文

### `paramTypeId`
| ID    | 名称           | 含义                                                                                                                      |
| ----- | ------------ | ----------------------------------------------------------------------------------------------------------------------- |
| **0** | single       | 无限制                                                                                                                     |
| **1** | interval     | 区间数值. **必须**配合 `min`、`max`                                                                               |
| **2** | enum         | 可选. `value` 为当前枚举值，仅当valueType为`float`|`int`|`string`时，`editorOptions` 内为所有枚举值列；|
| **4** | formula      | 复合公式. 由`status`字段决定当前值为值还是公式； **float/int** 须同时传 `min`/`max`；**string** 时 **禁止**出现 `min`/`max` |
| **5** | fixedFormula | 公式. `value` 含 `#` 的公式，如 `'(#W/2+#WX)'`                                                                                      |
| **6** | constant     | 固定值                                                                                                                     |
| **7** | formulaEnum  | 复合公式+可选.  `value` 为当前枚举值, `editorOptions` 内为所有枚举值列表，`formula` 内为公式                      |


#### 备注：`valueType` × `paramTypeId` 常见搭配

表中数字为 `**paramTypeId**`。


| valueType           | 可用的 paramTypeId                                                                             |
| ------------------- | ------------------------------------------------------------------------------------------- |
| `'float'` / `'int'` | **1** interval，**2** enum，**4** formula，**5** fixedFormula，**6** constant，**7** formulaEnum |
| `'string'`          | **2**，**4**，**5**，**6**，**7**（string 时勿添加 `min`/`max`**）                        |
| `'boolean'`         | **0** single，**6** constant   |
| `'material'`| **0** single，**2** enum，**4** formula，**5** fixedFormula，**6** constant |
| `'style'`| **0** single，**2** enum，**4** formula，**5** fixedFormula，**6** constant |
| `'shape'`| **0** single，**2** enum，**4** formula，**5** fixedFormula，**6** constant |
| `'booleanlist'`| **0** single，**6** constant|

## 可选字段


| 字段            | 说明                                                                                                                                                        |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `min` / `max` | 与 **float/int** 一致的数字字符串（如 `'0'`、`'6000'`）。**paramTypeId = 1** 时必填；**paramTypeId = 4** 且 **float/int** 时必填（约束 interval 一侧）。**valueType 为 string 时一律不要传。** |
| `group`       | 分组名，用于归类展示，其中：inner(内部变量)、report(报告变量)、system(系统变量)为内置group名                                                                                              |
| `ignore`      | 条件公式（含 `#` 须括号包裹，同 fixedFormula）；参数**隐藏条件**|
| `formulaForm` | 复合公式中的公式类型，**paramTypeId = 4** 时必填，0=公式，1=条件(casesJSON)，默认为0; |
| `status`      | 复合公式状态，**paramTypeId = 4** 时必填，status: 0=当前生效为值侧, `value` 为当前值；status: 1=当前生效为公式侧; status 默认 1 |
| `valueDisplayNames` | 多布尔参数各选项显示名，**valueType=booleanlist**时，必填，内容示例：`["name1","name2"]`|
| `editorOptions` | 枚举选项列表，**valueType为`float`|`int`|`string`并且paramTypeId=2**或**paramTypeId=7**时，必填，内容示例：`[{ name: '20', value: '20' }, { name: '30', value: '30' }]`|
| `link` | 轮廓/材质/样式类型补充属性，**valueType为shape/material/style并且paramTypeId为2或4**时，必填，内容示例为：`"3FO4K5T6QLJ2"` 或 `'{"cases":[{"condition":"#W==50","value":"3FO4K5T6QLJ2"}],"defaultValue":"3FO4K5T67V6G"}'` |
| `linkForm` | 轮廓/材质/样式类型补充属性，**valueType为shape/material/style并且paramTypeId为2或4**时，必填，内容为：`"0"` 或 `"1"`，其中 `"0"` 表示 link 是指定文件夹 id，`"1"` 表示 link 是条件文件夹 JSON (含 cases/defaultValue) |
| `formula` | 公式属性， formulaForm=0 为 spel 字符串, formulaForm=1 为 {cases, defaultValue} 对象, 内容示例为 `{ cases: [{ condition: '#W==200', value: '{"obsBrandGoodId":"3FO3NGURA302","versionId":10}' }, { condition: '#W==300', value: '{"obsBrandGoodId":"3FO3K04GWD9L","versionId":6}' }], defaultValue: '{"obsBrandGoodId":"3FO3NGTYT0MM","versionId":5}' } }` |

---

# schema examples
- `skills/parametric-model-design/designjson-schema/example.json`
- `skills/parametric-model-design/designjson-schema/example-with-bgm.json` 
