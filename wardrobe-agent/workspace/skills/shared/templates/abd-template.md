# abd.json 模板

## 使用场景

创建或阅读 `abd.json` 时，参考本文档，了解各字段含义与填写约定。

## 字段说明

### 根级

| 字段 | 说明 |
| --- | --- |
| `name` | 组合柜名称 |
| `units` | 单元柜列表，每项对应一个单元柜实例 |

### `units[]` 单元柜

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 否 | 组合柜名称 |
| `units[*].name` | 是 | 单元柜名称 |
| `referenceImageUrl` | 否 |**仅支持本机图片的绝对路径**，如 `C:\Users\...\assets\xxx.png`|
| `description` | 否 | 单元柜描述 |
| `cabinetSize` | 否 | 没有提供时，从单元柜信息中推断 |
| `candidates` | 否 | 其他候选单元柜的id列表 |
| `obsBrandGoodId` | 是 | 单元柜在模型库中的唯一标识 |
| `position` | 是 | 摆放位置 `{ x, y, z }` ，左后下位置|
| `size` | 是 | 外框尺寸 `{ x, y, z }`，分别对应宽、深、高 |
| `rotate` | 否 | 绕各轴旋转角度 `{ x, y, z }`（度）。无旋转时可省略 |
| `scale` | 否 | 各轴缩放比例 `{ x, y, z }`。无缩放时可省略 |
| `cells` | 否 | 单元柜在表格布局中的占位。按行列划分整柜平面，一个单元柜可占 1 个或多个**连续**单元格；`row`、`column` 均从 1 开始，`row=1` 为最底行，`column=1` 为最左列。不使用表格布局时可省略 |

### 坐标系约定
- units[*].position的参考坐标系是整个组合柜的中心点
- positon代表单元柜的原点，位于BBox的左后下位置

### `cells[]` 示例

- 占 1 格：`[{ "row": 1, "column": 1 }]`
- 占同一行连续 2 格：`[{ "row": 1, "column": 2 }, { "row": 1, "column": 3 }]`

## 示例

```json
{
  "name": "组合",
  "referenceImageUrl": "C:\\\\Users\\\\...\\\\image.png",
  "description": "给用户看的需求描述",
  "cabinetSize": { "width": 3000, "height": 2600 },
  "units": [
    {
      "name": "【2门断背高柜】V1",
      "obsBrandGoodId": "3FO3PVG4P0Y6",
      "position": {
        "x": -1150.0,
        "y": 200.0,
        "z": -1200.0
      },
      "rotate": {
        "x": 0.0,
        "y": 0.0,
        "z": 0.0
      },
      "size": {
        "x": 800.0,
        "y": 400.0,
        "z": 2400.0
      },
      "scale": {
        "x": 1.0,
        "y": 1.0,
        "z": 1.0
      },
      "cells": [
        { "row": 1, "column": 1 }
      ]
    },
    {
      "name": "【4门常规高柜】V1",
      "obsBrandGoodId": "3FO3PVTM5PPJ",
      "position": {
        "x": -350.0,
        "y": 200.0,
        "z": -1200.0
      },
      "rotate": {
        "x": 0.0,
        "y": 0.0,
        "z": 0.0
      },
      "size": {
        "x": 1500.0,
        "y": 400.0,
        "z": 2400.0
      },
      "scale": {
        "x": 1.0,
        "y": 1.0,
        "z": 1.0
      },
      "cells": [
        { "row": 1, "column": 2 }
      ]
    }
  ]
}
```
