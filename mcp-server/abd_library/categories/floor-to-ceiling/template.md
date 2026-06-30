---
abd_version: v2
category: 一柜到顶衣柜
category_slug: floor-to-ceiling
template_type: category_template
baseline_sample: 3FO3JCW4OAI4
updated: 2026-04-28
---

# ABD 模板：一柜到顶衣柜

> **用途**：Agent 在步骤 3 套用此模板的 frontmatter + 三段式结构，把图像分析结论填入。
> **基线**：W=2286, H=2400, D=550, GTBL=1, 高柜×3, 无边柜/下柜/见光板，SK_T=50, TH=60，SK_L/R/QYW*/MBS* 为标准公式（见 `few-shot/3FO3JCW4OAI4.md`）。
> **参数信息（工艺段）**：本模板只声明 Section 1 / Section 2 的字段契约；**参数生成策略另见 [param-strategy.md](./param-strategy.md)**，由步骤 5 调用 `get_param_strategy` 工具加载。

---

## ABD 实例 frontmatter

```yaml
---
abd_version: v2
category: 一柜到顶衣柜
instance_id: <生成 ID 或用户提供>
baseline: 3FO3JCW4OAI4
updated: <YYYY-MM-DD>
---
```

---

## Section 1：基础信息

> 决定整体尺寸 + 镜像 + 单元柜计数。

```yaml
W: <int mm>            # 必填，范围 936-3336
H: 2400                # 类目锁定；非标(2200/2334)需显式覆盖并加 note
D: 550                 # 类目锁定；非标(500/600)需显式覆盖并加 note
mirror: <bool>         # 左右镜像；推导规则：存在成对 L/R 实例名即 true
unit_count_total: <int>   # 单元柜总数 = 主要类型数 + 辅助构件数
unit_count_main: <int>    # 主要类型单元柜数量（高柜/顶柜/底柜/边柜/开放柜）
unit_count_aux: <int>     # 辅助构件数量（顶收口板/踢脚/收口板/见光板）
```

---

## Section 2：单元柜信息

> 决定"选哪些单元柜"。结构为树状：主要类型列表 + 辅助构件 + 门区布局。

### 2.1 主要类型单元柜列表

> 所有主要类型单元柜统一列在此处，从左到右、从下到上编号。
> 类型取值：`高柜/下柜` | `顶柜` | `底柜` | `边柜` | `开放柜`（整柜无门）

```yaml
units:
  - slot: 1                        # 从左到右编号，垂直分段时下柜在前、上柜在后
    type: 高柜/下柜                # 语义类型
    bgid: <BGID>
    door_count: 1                  # 下段 1 扇门
    bay_count: 1                   # 边柜语义本身独占 1 分格，无需填 merge_skip_reason
    drawer_count: 0
    has_open_shelf: true           # 上段开放层架
    open_shelf_dividers: 2         # 开放层架隔板数量
    est_width: 400                 # 窄于主柜基础分格宽
    est_height: 2400               # 通高
    position: 左侧边柜（占第1分格）
    handle_style: <string>         # 从图像推测拉手信息，如"双小拉手（中缝两侧）"
    color_material: <string>       # 从图像推测材质/颜色信息，如"白门 + 浅木纹柜体"
    layout_notes: <string>         # 从图像推测布局信息，如"上段开放层架，下段封闭单门。"
    summary: <string>              # 如"左侧通高边柜；上段2格开放层架，下段单扇白门小柜，浅木纹饰面。"

  - slot: 2
    type: 底柜                     # 与 slot:3 顶柜成对，同一门面分隔
    bgid: <BGID>
    door_count: 2
    bay_count: 2
    drawer_count: 0
    has_open_shelf: false
    est_width: 1200                # 2 个基础分格宽之和
    est_height: 2400
    position: 左数第2个（占第2-3分格）
    handle_style: <string>         # 从图像推测拉手信息，如"J-pull 竖条中缝"
    color_material: <string>       # 从图像推测材质/颜色信息，如"白门 + 浅木纹柜体"
    layout_notes: <string>         # 从图像推测布局信息，如"标准双门封闭立柜。"
    summary: <string>              # 如"双门通高柜；左右对开两扇白门，紧贴左侧边柜。"

  - slot: 3
    type: 顶柜                     # 与 slot:2 底柜成对
    bgid: <BGID>
    door_count: 2
    bay_count: 2
    drawer_count: 0
    has_open_shelf: false
    est_width: 600                 # 1 个基础分格宽
    est_height: 2400
    position: 左数第3个（占第4分格，最右端）
    handle_style: <string>         # 从图像推测拉手信息，如"单拉手"
    color_material: <string>       # 从图像推测材质/颜色信息，如"白门 + 浅木纹柜体"
    layout_notes: <string>         # 从图像推测布局信息，如"远端单门收尾立柜。"
    summary: <string>              # 如"单门通高柜；远端单门收尾，单扇白门。"
```

> **字段说明（逐行）**
>
> | 字段 | 必填条件 | 说明 |
> |---|---|---|
> | `type` | 必填 | 取值见上方类型枚举；**`顶柜` / `底柜` 仅在显式垂直拆分证据满足时才允许使用** |
> | `bay_count` | 必填 | 1=独占 1 分格；2=合并 2 相邻分格双门柜 |
> | `merge_skip_reason` | `bay_count=1` 且 `type ∈ {高柜/下柜, 顶柜, 底柜}` 时必填 | 见 §4 R-bay-3 枚举；`边柜`/`开放柜` 不需要填 |
> | `door_count` | 必填 | 0=开放柜；1=单门；2=双门 |
> | `has_open_shelf` | 必填 | 含开放区域则 true；`open_shelf_dividers` 随之填写 |
> | `est_width` | 必填 | `bay_count=2` 时 ≈ 2× 基础分格宽 |
> | `handle_style` | 必填 | 从图像推测拉手/把手样式描述 为搜索匹配增加的内容|
> | `color_material` | 必填 | 从图像推测材质/颜色组合描述 为搜索匹配增加的内容|
> | `layout_notes` | 必填 | 从图像推测单元柜布局特征简述 为搜索匹配增加的内容|

### 2.2 辅助构件

> 工艺性构件，不承担储物功能。`style` 区分收口板（贴墙隐藏）和见光板（外露装饰）。

```yaml
aux_components:
  top_seal:                        # 顶收口板，100% 样本出现
    present: true
    bgid: <BGID>                   # 高频 Top1: 3FO3JCM5DNWR
    segments: <1 | 3>              # 3 段: 左/中/右；1 段: 整段
    color_material: <string>       # 从图像推测材质/颜色信息，如"浅木纹封口"
    summary: <string>              # 从图像推测总体描述，如"浅木纹封口"
  toe_kick:                        # 踢脚装饰板
    present: true
    bgid: <BGID>                   # 高频: 3FO3JCVJTR0E
    color_material: <string>       # 从图像推测材质/颜色信息，如"浅木纹封口"
    summary: <string>              # 从图像推测总体描述，如"浅木纹封口"
  left_panel:                      # 左侧构件
    present: <bool>
    style: 收口板 | 见光板          # 收口板=贴墙隐藏；见光板=外露需美观
    bgid: <BGID | null>
    segments: <1 | 2>
    color_material: <string>       # 从图像推测材质/颜色信息，如"浅木纹封口"
    summary: <string>              # 从图像推测总体描述，如"浅木纹封口"
  right_panel:                     # 右侧构件；可被边柜替代则 present: false
    present: <bool>
    style: 收口板 | 见光板
    bgid: <BGID | null>
    segments: <0 | 1 | 2>
    color_material: <string>       # 从图像推测材质/颜色信息，如"浅木纹封口"
    summary: <string>              # 从图像推测总体描述，如"浅木纹封口"
```

### 2.3 门区布局

```yaml
door_layout:
  GTBL: <1 | 2 | 3 | 4>            # 枚举：1="2:2:1" (59%), 2="2:1:2" (12%), 3="1:2:2" (12%), 4=其他 (14%)
  QYW_mode: formula                # 100% 公式驱动，无需手填
```

---

## Section 3：参数信息（工艺段）

**移到独立文件**：[param-strategy.md](./param-strategy.md)。
步骤 5 调用 `get_param_strategy` 工具加载。

---

## Section 4：保险栓校验清单（Agent 产出 ABD 后自检）

> 仅含 Section 1 / Section 2 的结构性自检；参数段自检见 `param-strategy.md` §6。

- [ ] 骨架完整：顶收口板 / 左收口 or 见光板 / 右收口 or 见光板 / 踢脚 四件套齐备
- [ ] `unit_count_total == unit_count_main + unit_count_aux`
- [ ] `unit_count_main == len(units)`，`unit_count_aux == aux_components 中 present:true 的数量`
- [ ] 门区一致：`Σ door_count` 与 `GTBL` 对应的比例一致

---

## 使用说明（给 Agent）

1. 复制本模板的 frontmatter 作为 ABD 实例的起点（替换 `instance_id` / `updated`）
2. **Section 1 + 2**：逐字段填具体值，参照图像分析结论
3. **Section 3 参数段**：调 `get_param_strategy` 加载 `param-strategy.md` 的差量模式规则后再填
4. 产出后按 Section 4 + `param-strategy.md` §6 清单各自自检
5. 保留 frontmatter 的 `abd_version` + `baseline`
