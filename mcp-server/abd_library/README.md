# ABD Library

ABD（Assembly Brief Description）= 组合柜的结构化"设计意图合同"。
本目录按**类目**组织 ABD 的分析资源；ABD Toolset（6 个工具）按需读取对应类目的资源喂给 LLM。

## 目录结构

```
abd_library/
├── README.md                       # 本文件
└── categories/                     # 按类目组织
    └── floor-to-ceiling/           # 一柜到顶衣柜
        ├── workflow.md             # 分析 Plan 补充（大步骤展开，可选）
        ├── domain.md               # 图像分析参考：单元柜语义类型 + 识别规则
        ├── template.md             # ABD 模板：基础信息 + 单元柜 + 自检三段式
        ├── param-strategy.md       # 工艺参数生成策略（差量模式 + 31 项白名单）
        ├── search-strategy.md      # 单元柜搜索策略（内部规范，不喂 LLM）
        └── few-shot/               # baseline + 差量样例
            └── *.md
```

## 类目资源 ↔ ABD Toolset 工具

| 资源 | 用途 | 由哪个工具读取 | 何时被读 |
|------|------|----------------|---------|
| **domain.md** | 图像分析领域知识：语义类型 + 识别规则 + 反例 | `get_image_analysis_guide` | 步骤 2 |
| **template.md** | ABD 三段式模板字段契约 | `get_abd_template` | 步骤 3 |
| **few-shot/*.md** | baseline + 差量样例 | `get_abd_examples`（MVP 占位） | 步骤 3/5（可选） |
| **param-strategy.md** | 差量模式规则 + 固定值 + 公式化 + 白名单 | `get_param_strategy` | 步骤 5 |
| **search-strategy.md** | BGID 检索策略 | （无工具读取，作为内部规范） | 开发参考 |
| **workflow.md** | 大步骤补充扩展 | （无工具读取，作为开发参考） | 类目复杂时按需写 |

主流程编排见 `external/mcp-server/src/prompt.txt`。

## 类目 vs 行业线

- **行业线**（`toolType`）= 编辑器视角的产品大类：`wardrobe` / `cabinet` / `doorwindow`
- **类目** = ABD 视角的更细粒度场景。同一行业线下可能有多个类目（如 `wardrobe` 下的"一柜到顶 / 步入式衣帽间 / 顶柜下柜分体"等）

类目目录命名以**英文短语**为主（`floor-to-ceiling`、`walk-in`），便于代码引用；显示名称在各文件 frontmatter 的 `category` 字段中维护中文。

## 添加新类目

1. 在 `categories/` 下新建 `<category-slug>/`
2. 按上面资源表逐个填写（最少需要 `domain.md` + `template.md` + `param-strategy.md` + 至少 1 个 baseline few-shot）
3. 更新本 README 的目录结构示例
4. 调用 6 个 ABD 工具时传 `category=<slug>` 参数即可加载新类目
