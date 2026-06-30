# AGENTS.md

本仓库用于通过编码代理生成参数化组合柜模型。用户以图片与文字描述需求。

## 子Agent介绍

| 序号  | 文档                                                                                                | 用途                               |
| --- | ---------------------------------------------------------------------------------------------------- | ---------------------------------- |
| 1   | `[agents/model-designer.md](agents/model-designer.md)`                       | 根据 `abd.json` 设计参数化模型布局，生成 `design.json`           |
| 2   | `[agents/model-builder.md](agents/model-builder.md)`                         | 根据 `design.json` 生成参数化模型脚本并执行          |
| 3   | `[agents/model-analyzer.md](agents/model-analyzer.md)`                       | 根据用户输入的图片和文字描述生成 abd.json      |
