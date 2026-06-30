# utils Python 脚本说明

`utils/` 目录存放当前 buildAgent 项目中用于模型数据抓取、预览图下载、单元柜池构建和组合关系报告生成的辅助脚本。

这些脚本主要依赖：

- `utils/fetch_model_library/api.py`：通过 HTTP 直接调用 `get_catalogue_tree`、`get_products_by_categories`、`get_products_parameters`、`get_model_data`、`get_product_preview_img_url` 等接口，需配置 `fetch_model_library/config.json` 并保持登录态。

运行前需确保 `fetch_model_library/config.json` 配置正确，且登录态有效（`python utils/login/browser_login.py check`）。

---

## `fetch_model_library/`（参数化模型库缓存）

维护仓库根目录 `workspace/data/param-model-library/` 下的目录树、商品列表、模型参数与 image profile。脚本位于 `utils/fetch_model_library/`，完整流程与 agent 纪律见 [`model_cache_agent.md`](model_cache_agent.md) 与 [`fetch_model_library/README.md`](fetch_model_library/README.md)。

```bash
python utils/fetch_model_library/fetch_catalogue_tree.py
python utils/fetch_model_library/fetch_products_by_categoryid.py --category-id <categoryId>
python utils/fetch_model_library/fetch_parameters_by_categoryid.py --category-id <categoryId>
python utils/fetch_model_library/create_image_profile.py --category-id <categoryId> --export-with-images
```

---

## `download_preview_image_bybgid.py`

### 职责

按单个 BGID 查询商品库中的 `previewImgUrl`，并下载商品预览图到指定目录。

### 能力

- 调用 `fetch_model_library.api.get_product_preview_img_url` 按 BGID 获取 `previewImgUrl`。
- 下载预览图到本地。
- 仅允许下载 `*.kujiale.com` 白名单域名下的图片，避免任意 URL 下载。

### 使用方法

```bash
python utils/download_preview_image_bybgid.py 3FO3JCVO58AE temp
```

指定输出文件名：

```bash
python utils/download_preview_image_bybgid.py 3FO3JCVO58AE temp --output-name previewImage.png
```

限制搜索目录：

```bash
python utils/download_preview_image_bybgid.py 3FO3JCVO58AE temp --category-id <categoryId>
```

常用参数：

- `bgid`：商品 BGID。
- `output_dir`：图片输出目录。
- `--output-name`：输出图片文件名，默认 `previewImage.png`。
- `--overwrite`：覆盖已有输出文件。

---

## `fetch_combo_case_data.py`

### 职责

按单个组合柜 BGID 或商品目录批量抓取组合柜原始数据，输出到 `temp/cases/{BGID}/`。

### 能力

- 查询商品目录并获取组合柜商品列表。
- 调用 `fetch_model_library.api.get_model_data` 直连后端获取：
  - `editorData.json`（`GET /editor/api/site/editordata`）
  - `paramModel.json`（`POST /editor/api/site/3d`）
- 通过 `fetch_model_library.get_products_by_categories` 返回的 `previewImgUrl` 下载：
  - `previewImage.png`
- 支持按 BGID、目录 ID、目录名称/路径三种方式运行。
- 支持 `--limit` 做小批量冒烟测试。
- 支持 `--overwrite` 重新抓取已有文件。
- 输出 JSON 汇总，包含成功数、失败数和每个 BGID 的落盘状态。

### 输出结构

```text
temp/cases/{BGID}/
├── editorData.json
├── paramModel.json
└── previewImage.png
```

### 使用方法

抓取单个组合柜：

```bash
python utils/fetch_combo_case_data.py --bgid 3FO3JPCXNOPM --lookup-category-id 3FO4JSCD6RYJ
```

按目录 ID 抓取：

```bash
python utils/fetch_combo_case_data.py --category-id 3FO4JSCD6RYJ
```

按目录名称/路径抓取：

```bash
python utils/fetch_combo_case_data.py --category-name "柜体组合库 - AI 辅助建模-组合案例库 - 【电视柜-边界】"
```

覆盖已有文件：

```bash
python utils/fetch_combo_case_data.py --category-id 3FO4JSCD6RYJ --overwrite
```

只抓取前 2 个商品做测试：

```bash
python utils/fetch_combo_case_data.py --category-id 3FO4JSCD6RYJ --limit 2
```

常用参数：

- `--bgid`：抓取单个组合柜 BGID。
- `--category-id`：抓取指定目录下全部商品。
- `--category-name`：通过目录名或路径解析目录 ID 后抓取。
- `--lookup-category-id`：单 BGID 模式下用于加速商品定位。
- `--output-root`：输出根目录，默认 `temp/cases`。
- `--limit`：限制抓取商品数量。
- `--overwrite`：覆盖已有输出文件。

---

## `fetch_combo_unit_pool.py`

### 职责

基于已经抓取到 `temp/cases/{BGID}/` 的组合柜数据，解析每个组合柜真实可见的子部件/单元柜，并抓取这些单元柜的数据到 `temp/unit-pool/{BGID}/`。

### 能力

- 读取组合柜：
  - `temp/cases/{BGID}/paramModel.json`
  - `temp/cases/{BGID}/editorData.json`
- 使用 `paramModel.modelInstances[1..]` 作为真实可见子部件来源。
- 解析子部件 numeric `brandGoodId`，并映射到字符串 BGID。
- 优先使用已有 `temp/unit-pool` 中的 `paramModel.json` 建立 numeric -> BGID 映射。
- 对未解析项使用 `editorData.modelInstances` 的顺序进行 provisional pairing，并抓取后校验单元柜根 `brandGoodId` 是否匹配。
- 优先搜索 `柜体模式库` 分支下商品作为单元柜候选。
- 抓取单元柜：
  - `editorData.json`
  - `paramModel.json`
  - `previewImage.png`
- 生成单元柜 BGID 列表和组合柜到单元柜的映射 manifest。

### 输入前提

需要先运行 `fetch_combo_case_data.py`，确保目标组合柜已经存在于 `temp/cases/{BGID}/`。

### 输出结构

```text
temp/unit-pool/
├── bgid-list.json
├── bgid-list.txt
└── {unitBGID}/
    ├── editorData.json
    ├── paramModel.json
    └── previewImage.png
```

`bgid-list.json` 主要字段：

- `sourceCategoryId`：来源组合柜目录 ID。
- `comboBgids`：参与解析的组合柜 BGID 列表。
- `unitBgids`：去重后的单元柜 BGID 列表。
- `byCombo`：每个组合柜对应的有序单元柜 BGID 列表，保留重复项。
- `results`：每个组合柜的解析详情、计数和未解析项。

### 使用方法

解析单个组合柜：

```bash
python utils/fetch_combo_unit_pool.py --bgid 3FO3JPCXNOPM
```

解析目录下全部组合柜：

```bash
python utils/fetch_combo_unit_pool.py --category-id 3FO4JSCD6RYJ
```

按目录名称/路径解析：

```bash
python utils/fetch_combo_unit_pool.py --category-name "柜体组合库 - AI 辅助建模-组合案例库 - 【电视柜-边界】"
```

覆盖已有单元柜数据：

```bash
python utils/fetch_combo_unit_pool.py --category-id 3FO4JSCD6RYJ --overwrite
```

只处理前 2 个组合柜：

```bash
python utils/fetch_combo_unit_pool.py --category-id 3FO4JSCD6RYJ --limit 2
```

常用参数：

- `--bgid`：解析单个组合柜。
- `--category-id`：解析指定目录下的组合柜。
- `--category-name`：通过目录名或路径解析目录 ID。
- `--cases-root`：组合柜数据根目录，默认 `temp/cases`。
- `--unit-root`：单元柜输出根目录，默认 `temp/unit-pool`。
- `--limit`：限制处理组合柜数量。
- `--overwrite`：覆盖已有输出文件。

---

## `build_composition_report.py`

### 职责

基于 `temp/cases`、`temp/unit-pool` 和 `temp/unit-pool/bgid-list.json` 生成电视柜组合柜与单元柜的关系报告。

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

报告表格列与 `optimize/composition-report.md` 保持一致：

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
python utils/build_composition_report.py
```

严格校验：

```bash
python utils/build_composition_report.py --strict
```

指定输入输出路径：

```bash
python utils/build_composition_report.py \
  --cases-root temp/cases \
  --unit-root temp/unit-pool \
  --manifest temp/unit-pool/bgid-list.json \
  --output temp/电视柜-composition-report.md
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

统计 `temp/cases` 下组合柜样本中的自定义参数、参数组、出现频率、公式和值，并生成 JSON 与 Markdown 分析结果。

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

### 使用方法

使用默认路径分析全部样本：

```bash
python utils/analyze_custom_params.py --strict
```

只分析单个样本并打印摘要：

```bash
python utils/analyze_custom_params.py --case 3FO3JPCXNOPM --pretty
```

指定输出路径：

```bash
python utils/analyze_custom_params.py \
  --cases-root temp/cases \
  --output temp/custom-params-analysis.json \
  --md-output temp/custom-params-analysis.md
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

## `analyze_param_relations.py`

### 职责

分析组合柜参数与可见单元柜实例参数之间的关系，生成机器可读 JSON 和人类可读 Markdown 报告，用于理解和复用组合柜模板中的参数传递规则。

### 能力

- 读取组合柜数据：
  - `temp/cases/{BGID}/editorData.json`
  - `temp/cases/{BGID}/paramModel.json`
- 读取单元柜池数据：
  - `temp/unit-pool/{unitBGID}/editorData.json`
  - `temp/unit-pool/{unitBGID}/paramModel.json`
  - `temp/unit-pool/bgid-list.json`
- 从组合柜 `inputs` 的公式和值中提取 `#ParamName` 引用，生成组合柜参数之间的 DAG 依赖边。
- 从组合柜 `editorData.modelInstances[].parameters[]` 中提取单元柜实例参数绑定，例如 `W = #Z_A1W`。
- 将组合柜槽位参数绑定到具体单元柜实例参数，例如 `Z_A1W(①柜宽度) -> instance[1].W(宽度)`。
- 抽象出可复用的 `templateRules`，把具体单元柜 BGID 解耦为槽位规则，便于后续类似结构自动迁移。
- 在 JSON 和 Markdown 中都输出 `paramName(displayName)` 形式，便于人工理解。
- 支持 `--strict`，在有校验警告时返回非零退出码。

### “槽位”的含义

脚本中的“槽位”指的是组合柜结构中预留给某个单元柜的位置编号/坑位，不是具体的单元柜 BGID。

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
python utils/analyze_param_relations.py --strict
```

只分析单个组合柜：

```bash
python utils/analyze_param_relations.py --case 3FO3JPCXNOPM
```

指定输入输出路径：

```bash
python utils/analyze_param_relations.py \
  --cases-root temp/cases \
  --unit-root temp/unit-pool \
  --manifest temp/unit-pool/bgid-list.json \
  --output temp/paramRelation.json \
  --md-output temp/paramRelation.md
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

## 推荐执行顺序

针对“给定组合柜目录，生成样本数据、单元柜池、组合关系报告、参数分析和参数关系报告”的完整流程：

```bash
python utils/fetch_combo_case_data.py --category-id 3FO4JSCD6RYJ --overwrite
python utils/fetch_combo_unit_pool.py --category-id 3FO4JSCD6RYJ --overwrite
python utils/build_composition_report.py --strict
python utils/analyze_custom_params.py --strict
python utils/analyze_param_relations.py --strict
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
```

---

## 注意事项

- `previewImage.png` 不来自 `get_model_data`，组合柜目录抓取时通过 `fetch_model_library.get_products_by_categories` 返回的 `previewImgUrl` 下载；单 BGID 预览图使用 `fetch_model_library.api.get_product_preview_img_url`。
- `fetch_model_library.api.get_model_data` 负责输出 `editorData.json` 和 `paramModel.json`，不需要 MCP 服务。
- `fetch_combo_unit_pool.py` 依赖 `temp/cases` 中已存在组合柜数据，不能单独替代 `fetch_combo_case_data.py`。
- 当前下载逻辑只允许 `*.kujiale.com` 域名下的预览图。
- 目录名称包含中文时，如果 shell 编码导致参数异常，优先使用 `--category-id`。
