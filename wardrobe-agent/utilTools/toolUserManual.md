# run_cabinet_script 使用说明

`run_cabinet_script.py` 用于把已有的 `cabinet_script.js` 加载到参数化编辑器中生成组合柜。

## 前置条件

1. 参数化编辑器已启动。
2. ParamEditor MCP 服务可访问，默认地址为 `http://localhost:7764/sse`。
3. 已准备好可执行的 `cabinet_script.js` 文件。

## 基本用法

```bash
python utilTools/run_cabinet_script.py workspace/tmp/output/cabinet_script.js
```

执行后脚本会依次：

1. 清空当前参数化编辑器场景。
2. 执行传入的 `cabinet_script.js`。

## 指定 ParamEditor 地址

如果 MCP 地址不是默认值，可以使用 `--parameditor-url`：

```bash
python utilTools/run_cabinet_script.py workspace/tmp/output/cabinet_script.js --parameditor-url http://localhost:7764/sse
```

## 查看帮助

```bash
python utilTools/run_cabinet_script.py --help
```

## 注意事项

- 该工具只执行已有的 `cabinet_script.js`，不会生成 JS。
- 每次执行前都会先清空编辑器场景。
- 如果传入路径不存在或不是文件，工具会返回错误。
