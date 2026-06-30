# model_info_utils Python 脚本说明

`utils/model_info_utils/` 存放当前 buildAgent 项目中用于模型信息抓取和分析的 Python 脚本。当前稳定主入口是 `category_pipeline.py`，它会串联组合柜抓取、单元柜池构建、组合关系报告、自定义参数分析、装配参数模板、参数关系分析和树状参数关系报告；`generate_assembly_parameter_template.py` 也可单独基于已有 cases 生成实施可编辑的装配参数模板。

这些脚本主要依赖：

- `utils/fetch_model_library/api.py`：通过 HTTP 直接调用 `get_catalogue_tree`、`get_products_by_categories`、`get_model_data`、`get_product_preview_img_url` 等接口，需配置 `fetch_model_library/config.json` 并保持登录态。

运行前需确保：

- `fetch_model_library/config.json` 配置正确（`apiBaseUrl`、`toolType`、`toolTypePos` 等）。
- 登录态有效：在 `data-tools/` 下执行 `python utils/login/browser_login.py check`，返回 `ok: true` 方可继续。
- 如果中文目录路径在 shell 中传参不稳定，优先使用 `--category-id`。

---

## 推荐主入口：`category_pipeline.py`

### 职责

按一个模型库目录生成完整分析产物。输入目录 ID 或目录名称/路径，输出到指定 `output-root`，目录下会包含组合柜原始数据、单元柜池、组合柜-单元柜关系报告、自定义参数报告、装配参数模板、参数关系报告、树状参数关系报告和管线摘要。

### 执行步骤

1. 调用 `fetch_combo_case_data.py` 抓取组合柜数据到 `{output-root}/cases/`。
2. 调用 `fetch_combo_unit_pool.py` 解析可见单元柜并抓取数据到 `{output-root}/unit-pool/`。
3. 调用 `build_composition_report.py` 生成 `{output-root}/组合柜-单元柜关系.md`。
4. 调用 `analyze_custom_params.py` 生成 `{output-root}/custom-params-analysis.json` 和 `.md`。
5. 调用 `generate_assembly_parameter_template.py` 生成 `{output-root}/custom_params_template.json` 和 `.md`。
6. 调用 `analyze_param_relations.py` 生成 `{output-root}/paramRelation.json` 和 `.md`。
7. 调用 `analyze_param_relations_tree.py` 生成 `{output-root}/paramRelation_tree.md`。
8. 校验输出并生成 `{output-root}/pipeline-summary.json`。

### 输出结构

```text
{output-root}/
├── cases/
│   └── {comboBGID}/
│       ├── editorData.json
│       ├── paramModel.json
│       └── previewImage.png
├── unit-pool/
│   ├── bgid-list.json
│   ├── bgid-list.txt
│   └── {unitBGID}/
│       ├── editorData.json
│       ├── paramModel.json
│       └── previewImage.png
├── 组合柜-单元柜关系.md
├── custom-params-analysis.json
├── custom-params-analysis.md
├── custom_params_template.json
├── custom_params_template.md
├── paramRelation.json
├── paramRelation.md
├── paramRelation_tree.md
└── pipeline-summary.json
```

### 使用方法

按目录 ID 运行完整管线：

```bash
python utils/model_info_utils/category_pipeline.py \
  --category-id 3FO4JSCD6RYJ \
  --output-root temp/yaoshitempfolder \
  --strict
```

按目录名称/路径运行：

```bash
python utils/model_info_utils/category_pipeline.py \
  --category-name "柜体组合库/AI辅助建模-组合案例库/一字到底衣柜" \
  --output-root temp/category/topwardobe \
  --strict
```

覆盖已有输出并重新抓取：

```bash
python utils/model_info_utils/category_pipeline.py \
  --category-id 3FO4JSKQSLY2 \
  --output-root temp/category/topwardobe \
  --strict \
  --overwrite
```

只处理前 2 个组合柜做冒烟测试：

```bash
python utils/model_info_utils/category_pipeline.py \
  --category-id 3FO4JSKQSLY2 \
  --output-root temp/verify-topwardobe-limit2 \
  --strict \
  --overwrite \
  --limit 2
```

常用参数：

- `--category-id`：要分析的模型库目录 ID。
- `--category-name`：要分析的模型库目录名称或路径。
- `--output-root`：完整管线输出目录，默认 `temp/category`。
- `--batch-size`：目录商品查询批大小，默认 `20`。
- `--limit`：限制组合柜数量，适合冒烟测试。
- `--overwrite`：重新抓取已存在的模型数据和预览图。
- `--strict`：报告和校验步骤使用严格模式；有校验问题时返回非零退出码。

---

## `download_preview_image_bybgid.py`

### 职责

按单个 BGID 通过直连 `GET /editor/api/site/editordata` 获取商品 `previewImgUrl`，并下载商品预览图到指定目录。

### 能力

- 调用 `fetch_model_library.api.get_product_preview_img_url` 按 BGID 获取 `previewImgUrl`（不需要 MCP 服务）。
- 下载预览图到本地。
- 仅允许下载 `*.kujiale.com` 白名单域名下的图片，避免任意 URL 下载。
- 支持跳过已有图片或通过 `--overwrite` 覆盖重新下载。

### 使用方法

```bash
python utils/model_info_utils/download_preview_image_bybgid.py 3FO3JCVO58AE temp
```

指定输出文件名：

```bash
python utils/model_info_utils/download_preview_image_bybgid.py 3FO3JCVO58AE temp --output-name previewImage.png
```

覆盖已有文件：

```bash
python utils/model_info_utils/download_preview_image_bybgid.py 3FO3JCVO58AE temp --overwrite
```

常用参数：

- `bgid`：商品 BGID。
- `output_dir`：图片输出目录。
- `--output-name`：输出图片文件名，默认 `previewImage.png`。
- `--overwrite`：覆盖已有输出文件。

---

## `fetch_combo_case_data.py`

### 职责

按单个组合柜 BGID 或商品目录批量抓取组合柜原始数据，输出到 `temp/cases/{BGID}/`，或通过 `--output-root` 输出到指定 `cases` 目录。

### 能力

- 支持按 BGID、目录 ID、目录名称/路径三种方式运行。
- 调用 `fetch_model_library.api.get_model_data` 直连后端获取：
  - `editorData.json`（`GET /editor/api/site/editordata`）
  - `paramModel.json`（`POST /editor/api/site/3d`）
- 下载组合柜 `previewImage.png`：
  - 目录模式使用 `fetch_model_library.get_products_by_categories` 返回的 `previewImgUrl`。
  - 单 BGID 模式可通过 `--lookup-category-id` 加速定位商品；未指定时会扫描目录树商品列表查找 BGID。
- 支持 `--limit` 做小批量冒烟测试。
- 支持 `--overwrite` 重新抓取已有文件。
- 输出 JSON 汇总，包含成功数、失败数和每个 BGID 的落盘状态。

### 输出结构

```text
{output-root}/{BGID}/
├── editorData.json
├── paramModel.json
└── previewImage.png
```

默认 `output-root` 为 `temp/cases`。

### 使用方法

抓取单个组合柜：

```bash
python utils/model_info_utils/fetch_combo_case_data.py --bgid 3FO3JPCXNOPM --lookup-category-id 3FO4JSCD6RYJ
```

按目录 ID 抓取：

```bash
python utils/model_info_utils/fetch_combo_case_data.py --category-id 3FO4JSCD6RYJ
```

按目录名称/路径抓取：

```bash
python utils/model_info_utils/fetch_combo_case_data.py --category-name "柜体组合库 - AI 辅助建模-组合案例库 - 【电视柜-边界】"
```

指定输出目录：

```bash
python utils/model_info_utils/fetch_combo_case_data.py \
  --category-id 3FO4JSCD6RYJ \
  --output-root temp/category/tvcabinet/cases
```

覆盖已有文件：

```bash
python utils/model_info_utils/fetch_combo_case_data.py --category-id 3FO4JSCD6RYJ --overwrite
```

只抓取前 2 个商品做测试：

```bash
python utils/model_info_utils/fetch_combo_case_data.py --category-id 3FO4JSCD6RYJ --limit 2
```

常用参数：

- `--bgid`：抓取单个组合柜 BGID。
- `--category-id`：抓取指定目录下全部商品。
- `--category-name`：通过目录名或路径解析目录 ID 后抓取。
- `--lookup-category-id`：单 BGID 模式下用于加速商品定位。
- `--output-root`：输出根目录，默认 `temp/cases`。
- `--batch-size`：目录商品查询批大小，默认 `20`。
- `--limit`：限制抓取商品数量。
- `--overwrite`：覆盖已有输出文件。

---

## `fetch_combo_unit_pool.py`

### 职责

基于已经抓取到的组合柜数据，解析每个组合柜真实可见的子部件/单元柜，并抓取这些单元柜的数据到 `temp/unit-pool/{BGID}/`，或通过 `--unit-root` 输出到指定单元柜池目录。

### 能力

- 读取组合柜：
  - `{cases-root}/{comboBGID}/paramModel.json`
  - `{cases-root}/{comboBGID}/editorData.json`
- 使用 `paramModel.modelInstances[1..]` 作为真实可见子部件来源。
- 通过子部件 `uniqueId` 匹配 `editorData.modelInstances`，获得实际单元柜 `obsBrandGoodId`。
- 调用 `fetch_model_library.api.get_model_data` 直连后端抓取单元柜：
  - `editorData.json`
  - `paramModel.json`
- 调用 `fetch_model_library.api.get_product_preview_img_url` 按单元柜 BGID 直接获取 `previewImgUrl` 并下载：
  - `previewImage.png`
- 生成单元柜 BGID 列表和组合柜到单元柜的映射 manifest。
- 支持 `--manifest-only`，只生成 `bgid-list.json` / `bgid-list.txt`，不抓取单元柜文件。

### 输入前提

需要先运行 `fetch_combo_case_data.py` 或 `category_pipeline.py` 的组合柜抓取步骤，确保目标组合柜已经存在于 `{cases-root}/{comboBGID}/`。

### 输出结构

```text
{unit-root}/
├── bgid-list.json
├── bgid-list.txt
└── {unitBGID}/
    ├── editorData.json
    ├── paramModel.json
    └── previewImage.png
```

默认 `unit-root` 为 `temp/unit-pool`。

`bgid-list.json` 主要字段：

- `sourceCategoryId`：来源组合柜目录 ID。
- `comboBgids`：参与解析的组合柜 BGID 列表。
- `unitBgids`：去重后的单元柜 BGID 列表。
- `byCombo`：每个组合柜对应的有序单元柜 BGID 列表，保留重复项。
- `results`：每个组合柜的解析详情、计数和未解析项。

### 使用方法

解析单个组合柜：

```bash
python utils/model_info_utils/fetch_combo_unit_pool.py --bgid 3FO3JPCXNOPM
```

解析目录下全部组合柜：

```bash
python utils/model_info_utils/fetch_combo_unit_pool.py --category-id 3FO4JSCD6RYJ
```

按目录名称/路径解析：

```bash
python utils/model_info_utils/fetch_combo_unit_pool.py --category-name "柜体组合库 - AI 辅助建模-组合案例库 - 【电视柜-边界】"
```

指定输入和输出目录：

```bash
python utils/model_info_utils/fetch_combo_unit_pool.py \
  --category-id 3FO4JSCD6RYJ \
  --cases-root temp/category/tvcabinet/cases \
  --unit-root temp/category/tvcabinet/unit-pool
```

只生成 manifest，不抓取单元柜文件：

```bash
python utils/model_info_utils/fetch_combo_unit_pool.py --category-id 3FO4JSCD6RYJ --manifest-only
```

覆盖已有单元柜数据：

```bash
python utils/model_info_utils/fetch_combo_unit_pool.py --category-id 3FO4JSCD6RYJ --overwrite
```

只处理前 2 个组合柜：

```bash
python utils/model_info_utils/fetch_combo_unit_pool.py --category-id 3FO4JSCD6RYJ --limit 2
```

常用参数：

- `--bgid`：解析单个组合柜。
- `--category-id`：解析指定目录下的组合柜。
- `--category-name`：通过目录名或路径解析目录 ID。
- `--cases-root`：组合柜数据根目录，默认 `temp/cases`。
- `--unit-root`：单元柜输出根目录，默认 `temp/unit-pool`。
- `--batch-size`：目录商品查询批大小，默认 `20`。
- `--limit`：限制处理组合柜数量。
- `--overwrite`：覆盖已有输出文件。
- `--manifest-only`：只写 manifest，不抓取单元柜资产。

---

## `build_composition_report.py`

### 职责

基于 `cases`、`unit-pool` 和 `unit-pool/bgid-list.json` 生成组合柜与单元柜的关系 Markdown 报告。

### 能力

- 校验组合柜数据是否齐全：
  - `editorData.json`
  - `paramModel.json`
  - `previewImage.png`
- 校验单元柜数据是否齐全：
  - `editorData.json`
  - `paramModel.json`
  - `previewImage.png` 或 `previewImage.jpg`
- 读取 `bgid-list.json` 中的 `byCombo` 关系。
- 按组合柜生成 Markdown 表格。
- 保留重复单元柜，不对每个组合柜内的子部件去重。
- 自动从 `editorData.json` 提取组合柜和单元柜名称。
- 缺失预览图时使用 `—` 占位。
- 支持 `--strict`，在有校验警告时返回非零退出码。

### 输出文件

默认输出：

```text
temp/电视柜-composition-report.md
```

管线模式下输出：

```text
{output-root}/组合柜-单元柜关系.md
```

报告表格列：

- 组合柜名称
- 组合柜 ID
- 组合柜预览图
- 子部件数量
- 子部件名称
- 子部件 ID
- 子部件预览图

### 使用方法

使用默认路径生成报告：

```bash
python utils/model_info_utils/build_composition_report.py
```

严格校验：

```bash
python utils/model_info_utils/build_composition_report.py --strict
```

指定输入输出路径：

```bash
python utils/model_info_utils/build_composition_report.py \
  --cases-root temp/category/tvcabinet/cases \
  --unit-root temp/category/tvcabinet/unit-pool \
  --manifest temp/category/tvcabinet/unit-pool/bgid-list.json \
  --output temp/category/tvcabinet/组合柜-单元柜关系.md \
  --strict
```

常用参数：

- `--cases-root`：组合柜数据根目录，默认 `temp/cases`。
- `--unit-root`：单元柜数据根目录，默认 `temp/unit-pool`。
- `--manifest`：单元柜关系 manifest，默认 `temp/unit-pool/bgid-list.json`。
- `--output`：Markdown 报告输出路径，默认 `temp/电视柜-composition-report.md`。
- `--strict`：有校验警告时退出失败。

---

## `analyze_custom_params.py`

### 职责

统计组合柜样本中的自定义参数、参数组、出现频率、公式和值，并生成 JSON 与 Markdown 分析结果。

### 能力

- 遍历组合柜 `editorData.json`。
- 只统计顶层 `customParamGroups[*].paramNames` 引用的自定义参数。
- 从 `inputs` 中补充参数中文名、公式、公式变体和值。
- 统计参数和参数组出现在哪些 case 中。
- 输出缺失输入引用、未分组 inputs 和校验警告。
- 默认同时生成机器可读 JSON 和人类可读 Markdown 报告。

### 输出文件

默认输出：

```text
temp/custom-params-analysis.json
temp/custom-params-analysis.md
```

管线模式下输出：

```text
{output-root}/custom-params-analysis.json
{output-root}/custom-params-analysis.md
```

### 使用方法

使用默认路径分析全部样本：

```bash
python utils/model_info_utils/analyze_custom_params.py --strict
```

只分析单个样本并打印摘要：

```bash
python utils/model_info_utils/analyze_custom_params.py --case 3FO3JPCXNOPM --pretty
```

指定输出路径：

```bash
python utils/model_info_utils/analyze_custom_params.py \
  --cases-root temp/category/tvcabinet/cases \
  --output temp/category/tvcabinet/custom-params-analysis.json \
  --md-output temp/category/tvcabinet/custom-params-analysis.md \
  --strict
```

常用参数：

- `--cases-root`：组合柜数据根目录，默认 `temp/cases`。
- `--output`：JSON 分析结果输出路径，默认 `temp/custom-params-analysis.json`。
- `--md-output`：Markdown 报告输出路径，默认 `temp/custom-params-analysis.md`。
- `--case`：只分析指定 BGID，可重复传入。
- `--limit`：限制分析样本数量。
- `--pretty`：在控制台打印人类可读摘要。
- `--strict`：有警告或缺失输入引用时返回非零退出码。

---

## `generate_assembly_parameter_template.py`

### 职责

基于现有组合柜 `cases/*/editorData.json` 生成实施人员可编辑、可阅读的装配参数模板，输出 `custom_params_template.json` 和 `custom_params_template.md`。

### 能力

- 遍历组合柜 `editorData.json`，不从模型库重新抓取数据。
- 读取 `customParamGroups` 和 `inputs`，按参数组汇总参数信息。
- 将 `inputs` 中未归入任何参数组的参数放入置顶的 `【系统参数】` 参数组。
- 统计参数组和参数在样本中的出现占比。
- 参数组表保留 `职责`、`加入模版` 空列，便于人工填写。
- 参数表输出 `参数引用名`、`参数显示名`、`参数值类型`、`参数说明`、`使用条件`、`参数控件类型`、`公式样例`、`可见性`、`出现占比`、`加入模版`。
- `paramTypeId` 渲染为 `single = 0`、`interval = 1` 等枚举说明。
- 公式样例展示出现最多的公式，并在文档后部列出每个参数的全部公式变体。
- 支持 `--strict`，在有警告或缺失输入引用时返回非零退出码。

### 输出文件

```text
{output-dir}/custom_params_template.json
{output-dir}/custom_params_template.md
```

### 使用方法

单例验证：

```bash
python utils/model_info_utils/generate_assembly_parameter_template.py \
  --cases-root D:/agentStudio/studyData/category/2TV/cases \
  --output-dir temp/assembly-template-single \
  --case 3FO3JPCXNOPM \
  --strict
```

限制前 2 个样本验证：

```bash
python utils/model_info_utils/generate_assembly_parameter_template.py \
  --cases-root D:/agentStudio/studyData/category/2TV/cases \
  --output-dir temp/assembly-template-2tv \
  --limit 2 \
  --strict
```

全量生成：

```bash
python utils/model_info_utils/generate_assembly_parameter_template.py \
  --cases-root D:/agentStudio/studyData/category/topwardobe/cases \
  --output-dir temp/assembly-template-topwardobe \
  --strict
```

常用参数：

- `--cases-root`：组合柜 cases 根目录，目录下每个 case 子目录应包含 `editorData.json`。
- `--output-dir`：输出目录，脚本会在其中生成 `custom_params_template.json` 和 `custom_params_template.md`。
- `--case`：只处理指定 case BGID，可重复传入。
- `--limit`：限制处理样本数量。
- `--strict`：有警告或缺失输入引用时返回非零退出码。

---

## `analyze_param_relations.py`

### 职责

分析组合柜参数与可见单元柜实例参数之间的关系，生成机器可读 JSON 和人类可读 Markdown 报告，用于理解和复用组合柜模板中的参数传递规则。

### 能力

- 读取组合柜数据：
  - `{cases-root}/{comboBGID}/editorData.json`
  - `{cases-root}/{comboBGID}/paramModel.json`
- 读取单元柜池数据：
  - `{unit-root}/{unitBGID}/editorData.json`
  - `{unit-root}/{unitBGID}/paramModel.json`
  - `{manifest}`
- 从组合柜 `inputs` 的公式和值中提取 `#ParamName` 引用，生成组合柜参数之间的 DAG 依赖边。
- 从组合柜 `editorData.modelInstances[].parameters[]` 中提取单元柜实例参数绑定，例如 `W = #Z_A1W`。
- 将组合柜槽位参数绑定到具体单元柜实例参数，例如 `Z_A1W(①柜宽度) -> instance[1].W(宽度)`。
- 抽象出可复用的 `templateRules`，把具体单元柜 BGID 解耦为槽位规则，便于后续类似结构自动迁移。
- 在 JSON 和 Markdown 中都输出 `paramName(displayName)` 形式，便于人工理解。
- 支持 `--strict`，在有校验警告时返回非零退出码。

### “槽位”的含义

脚本中的“槽位”指组合柜结构中预留给某个单元柜的位置编号/坑位，不是具体的单元柜 BGID。

槽位通常从组合柜参数名中解析：

- `Z_A1W(①柜宽度)` -> 槽位 `A1`
- `Z_A2H(②柜高度)` -> 槽位 `A2`
- `Z_A5D(⑤柜深度)` -> 槽位 `A5`

例如报告中的：

```text
Z_A1W(①柜宽度) | A1 | W(宽度)
```

含义是：组合柜中 `A1` 槽位的宽度参数 `Z_A1W`，会传递到该槽位实际单元柜实例的 `W` 参数。

这种抽象可以让规则脱离具体 BGID：未来如果 `A1` 位置换成另一个单元柜，只要它仍然是 `A1` 槽位，就可以复用 `Z_A1W -> slot A1 -> unit.W` 这条模板规则。

### 输出文件

默认输出：

```text
temp/paramRelation.json
temp/paramRelation.md
```

管线模式下输出：

```text
{output-root}/paramRelation.json
{output-root}/paramRelation.md
```

`paramRelation.json` 主要字段：

- `bindingPatterns`：槽位参数到单元柜参数的绑定模式汇总。
- `templateRules`：可供后续程序复用的模板规则。
- `cases[].formulaEdges`：组合柜参数之间的公式依赖边。
- `cases[].bindingEdges`：组合柜参数到单元柜实例参数的绑定边。
- `cases[].paths`：从组合柜高层参数经槽位参数到单元柜实例参数的可追踪路径。

`paramRelation.md` 主要章节：

- 表达形式说明。
- 参数绑定模式汇总。
- 可复用模板规则。
- 按组合柜展开的实例表、公式依赖、槽位绑定和追踪路径。
- 数据校验与限制。

### 使用方法

使用默认路径分析全部样本：

```bash
python utils/model_info_utils/analyze_param_relations.py --strict
```

只分析单个组合柜：

```bash
python utils/model_info_utils/analyze_param_relations.py --case 3FO3JPCXNOPM
```

指定输入输出路径：

```bash
python utils/model_info_utils/analyze_param_relations.py \
  --cases-root temp/category/tvcabinet/cases \
  --unit-root temp/category/tvcabinet/unit-pool \
  --manifest temp/category/tvcabinet/unit-pool/bgid-list.json \
  --output temp/category/tvcabinet/paramRelation.json \
  --md-output temp/category/tvcabinet/paramRelation.md \
  --strict
```

常用参数：

- `--cases-root`：组合柜数据根目录，默认 `temp/cases`。
- `--unit-root`：单元柜数据根目录，默认 `temp/unit-pool`。
- `--manifest`：组合柜到单元柜关系 manifest，默认 `temp/unit-pool/bgid-list.json`。
- `--output`：JSON 关系结果输出路径，默认 `temp/paramRelation.json`。
- `--md-output`：Markdown 报告输出路径，默认 `temp/paramRelation.md`。
- `--case`：只分析指定组合柜 BGID，可重复传入。
- `--limit`：限制分析样本数量。
- `--strict`：有校验警告时返回非零退出码。

---

## `analyze_param_relations_tree.py`

### 职责

复用 `analyze_param_relations.py` 的分析逻辑，额外生成树状 Markdown 报告，用更清晰的层级结构展示组合柜参数与单元柜实例参数之间的关系。

### 能力

- 读取与 `analyze_param_relations.py` 相同的 `cases-root`、`unit-root` 和 `manifest`。
- 输出“组合柜公式参数 -> 依赖参数 -> 单元柜实例参数”的树状视角。
- 输出“槽位 -> 组合柜参数 -> 单元柜实例参数”的树状视角。
- 输出可复用模板规则树。
- 支持按 `--case`、`--limit` 缩小分析范围。
- 支持 `--strict`，在有校验警告时返回非零退出码。

### 输出文件

默认输出：

```text
temp/paramRelation_tree.md
```

管线模式下输出：

```text
{output-root}/paramRelation_tree.md
```

### 使用方法

使用默认路径生成树状报告：

```bash
python utils/model_info_utils/analyze_param_relations_tree.py --strict
```

只分析单个组合柜：

```bash
python utils/model_info_utils/analyze_param_relations_tree.py --case 3FO3JPCXNOPM
```

指定输入输出路径：

```bash
python utils/model_info_utils/analyze_param_relations_tree.py \
  --cases-root temp/category/tvcabinet/cases \
  --unit-root temp/category/tvcabinet/unit-pool \
  --manifest temp/category/tvcabinet/unit-pool/bgid-list.json \
  --md-output temp/category/tvcabinet/paramRelation_tree.md \
  --strict
```

常用参数：

- `--cases-root`：组合柜数据根目录，默认 `temp/cases`。
- `--unit-root`：单元柜数据根目录，默认 `temp/unit-pool`。
- `--manifest`：组合柜到单元柜关系 manifest，默认 `temp/unit-pool/bgid-list.json`。
- `--md-output`：Markdown 报告输出路径，默认 `temp/paramRelation_tree.md`。
- `--case`：只分析指定组合柜 BGID，可重复传入。
- `--limit`：限制分析样本数量。
- `--strict`：有校验警告时返回非零退出码。

---

## 手动分步执行顺序

如果不使用 `category_pipeline.py`，可以按以下顺序手动执行：

```bash
python utils/model_info_utils/fetch_combo_case_data.py --category-id 3FO4JSCD6RYJ --overwrite
python utils/model_info_utils/fetch_combo_unit_pool.py --category-id 3FO4JSCD6RYJ --overwrite
python utils/model_info_utils/build_composition_report.py --strict
python utils/model_info_utils/analyze_custom_params.py --strict
python utils/model_info_utils/analyze_param_relations.py --strict
python utils/model_info_utils/analyze_param_relations_tree.py --strict
```

执行完成后，重点检查：

```text
temp/cases/
temp/unit-pool/bgid-list.json
temp/unit-pool/bgid-list.txt
temp/电视柜-composition-report.md
temp/custom-params-analysis.json
temp/custom-params-analysis.md
temp/paramRelation.json
temp/paramRelation.md
temp/paramRelation_tree.md
```

更推荐直接使用完整管线：

```bash
python utils/model_info_utils/category_pipeline.py \
  --category-id 3FO4JSCD6RYJ \
  --output-root temp/yaoshitempfolder \
  --strict \
  --overwrite
```

---

## 注意事项

- `previewImage.png` 不来自 `get_model_data`，需单独下载。
- 组合柜目录批量抓取时，`fetch_combo_case_data.py` 使用 `fetch_model_library.get_products_by_categories` 返回的商品 `previewImgUrl`。
- 单 BGID 预览图下载和单元柜预览图抓取使用 `fetch_model_library.api.get_product_preview_img_url`（`GET /editor/api/site/editordata` → `model.previewImgUrl`）。
- `fetch_model_library.api.get_model_data` 负责输出 `editorData.json`（`GET /editor/api/site/editordata`）和 `paramModel.json`（`POST /editor/api/site/3d`），不需要 MCP 服务。
- `fetch_combo_unit_pool.py` 依赖 `cases-root` 中已存在组合柜数据，不能单独替代 `fetch_combo_case_data.py`。
- 当前下载逻辑只允许 `*.kujiale.com` 域名下的预览图。
- `category_pipeline.py` 会在失败时仍写入 `pipeline-summary.json`，可优先查看该文件定位失败步骤。
- 对真实类目建议使用 `--strict`，对冒烟测试建议同时使用 `--limit` 和独立的临时 `--output-root`。
