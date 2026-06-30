---
name: confirm-abd
description: >-
  弹出组合柜单元柜布局确认 UI，接收标准 JSON 输入，让用户调整/确认单元柜 obsBrandGoodId 与 position/size 后输出确认 JSON。 agent需要用户确认单元柜选型或布局时使用。
disable-model-invocation: false
---

### 输入 JSON

`tmp/input/abd.json`，格式见：`skills/shared/templates/abd-template.md`

### 启动 UI

```bash
python skills/confirm-abd/ui/confirm_abd.py --input tmp/input/abd.json --output tmp/input/abd.json
```

脚本会自动选择空闲端口，启动本地 Flask UI 并打开浏览器。用户点击「确认」后，脚本退出，并在 stdout 输出结果文件路径。

### 输出 JSON

输出文件为确认后的abd.json: tmp/input/abd.json；
