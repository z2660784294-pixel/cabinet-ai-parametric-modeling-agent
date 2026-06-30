# Model Cache Agent

参数化模型库缓存维护：目录树、商品列表、模型参数、image profile。

## 缓存路径

`workspace/data/param-model-library/`：

| 文件 | 用途 |
|------|------|
| `product_categories.json` | 目录树 |
| `parammodel.json` | 各 categoryId 商品列表 |
| `parammodel_param_list.json` | 各 categoryId 模型参数 |
| `parammodel_image_profile.json` | 各 categoryId 图像 profile |

**执行目录**：`data-tools/`

## 通用纪律

1. **确保登录状态**（功能 4 本地合并可跳过）：
```bash
python data-tools/utils/login/browser_login.py ensure
```

2. **功能选择**：用户未指定 1/2/3/4 时，先列出四项简介请用户选择

3. **覆盖检查**：
   - 功能 2：`python data-tools/utils/fetch_model_library/util.py feature2 --category-id <id>`
   - 功能 3：`python data-tools/utils/fetch_model_library/util.py feature3 --category-id <id>`
   - 功能 4：`python data-tools/utils/fetch_model_library/util.py feature4 --category-id <id>`
   - 获取包含商品的 categoryId：`python data-tools/utils/fetch_model_library/util.py list-categories-with-products --category-id <id>`

   **判定规则**：
   - 退出码 0 且 `can_proceed: true` → 继续
   - 退出码 1 且 `needs_overwrite_confirm: true` → 询问用户，确认后用 `--overwrite-confirm "<用户原话>"` 重试
   - `ok: false` → 终止

4. **脚本执行**：通过 `data-tools/utils/fetch_model_library/` 下脚本完成

5. **合并写入**：只替换/追加指定 categoryId，保留其他目录数据。功能 4 跳过已有 profile

6. **JSON 格式**：UTF-8 无 BOM，`ensure_ascii=False`，`indent=2`

7. **清理临时文件**：成功后删除中间产物

## 功能-脚本对照

| 功能 | 脚本 | API |
|------|------|-----|
| 1 | `fetch_catalogue_tree.py` | `get_catalogue_tree` |
| 2 | `fetch_products_by_categoryid.py` | `get_products_by_categories` |
| 3 | `fetch_parameters_by_categoryid.py` | `get_products_parameters` |
| 4 | `create_image_profile.py` | 无 |


---

## 功能 1：更新目录树

**输出**：`product_categories.json`

1. 登录检查
2. 文件存在检查
3. 执行：`python data-tools/utils/fetch_model_library/fetch_catalogue_tree.py`
4. 回复路径与状态

## 功能 2：更新商品列表

**输入**：`categoryId` 或目录路径
**输出**：`parammodel.json`
**递归**：处理指定 categoryId 及所有子目录

1. 登录检查
2. 解析 categoryId（路径 → 读取 `product_categories.json` 匹配）；已指定id，则跳过此步；
3. 获取所有包含商品的 categoryId：`python data-tools/utils/fetch_model_library/util.py list-categories-with-products --category-id <id>`
4. 对每个 categoryId：
   - 覆盖检查：`python data-tools/utils/fetch_model_library/util.py feature2 --category-id <id>`
   - 执行：`python data-tools/utils/fetch_model_library/fetch_products_by_categoryid.py --category-id <id>`
5. 自动接续功能 3

## 功能 3：更新模型参数

**输入**：`categoryId`（功能 2 传入或用户直接提供）
**输出**：`parammodel_param_list.json`
**递归**：处理指定 categoryId 及所有子目录

1. 登录检查（功能 2 接续可跳过）
2. 获取所有包含商品的 categoryId（功能 2 接续则复用，否则同功能 2 步骤 2-3）
3. 对每个 categoryId：
   - 覆盖检查：`python data-tools/utils/fetch_model_library/util.py feature3 --category-id <id>`
   - 检查 `workspace/data/param-model-library/parammodel.json` 中是否存在该 categoryId
   - 执行：`python data-tools/utils/fetch_model_library/fetch_parameters_by_categoryid.py --category-id <id>`
4. 回复目录数、模型数、路径

## 功能 4：创建 image Profile

**输入**：`categoryId`
**输出**：`parammodel_image_profile.json`
**递归**：串行处理指定 categoryId 及所有子目录

1. 登录检查（本地合并可跳过）
2. 获取所有包含商品的 categoryId（功能 2 接续则复用，否则同功能 2 步骤 2-3）
3. 对每个 categoryId 串行执行：
   - 覆盖检查：`python data-tools/utils/fetch_model_library/util.py feature4 --category-id <id>`
   - 导出并下载图片：`python data-tools/utils/fetch_model_library/create_image_profile.py --category-id <id> --export-with-images`
   - **逐图 subagent 分析**：
     - 每个 subagent 处理 1 个商品：`{obsBrandGoodId, name, localImgPath}`
     - 返回单条 JSON：`{obsBrandGoodId, name, profile}`
     - 分批并行，不得一次性分析全部
   - **role 判定**：
     - 先看图像和形态，再选 role
     - `unit_cabinet`：`door_count`, `drawer_count`, `has_open_shelf`, `open_shelf_dividers`, `est_width`, `est_height`, `handle_style`, `color_material`, `layout_notes`
     - `accessory_trim`：仅 `role`, `summary`, `color_material`
     - 归类提示：名称含「收口/见光/踢脚/装饰板/封板/条板」或单色薄板/长条 → `accessory_trim`
   - 写入 `profile_input_<categoryId>.json`
   - 如需覆盖已有 profile：执行 `data-tools/utils/fetch_model_library/util.py feature4 --obs-brand-good-id <id>` 并确认
   - 合并：`python data-tools/utils/fetch_model_library/create_image_profile.py --category-id <id> --profile-input <profile_input_<categoryId>.json>`
   - 删除临时文件：`<categoryId>_images/`, `profile_input_<categoryId>.json`
4. 回复目录数、各目录追加/跳过数、路径

---

## 异常处理

- **登录失效**：重新登录
- **路径解析失败**：提示核对路径或先执行功能 1
- **空商品列表**：跳过或保持原状
- **JSON 损坏**：终止，提示用户处理
- **功能 4 role 不匹配**：重跑 subagent 并修正

