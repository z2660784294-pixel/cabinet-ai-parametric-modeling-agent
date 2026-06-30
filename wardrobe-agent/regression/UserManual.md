Regression User Manual 
回归测试使用手册

# 说明
整个组合柜生成的流程目前是  
abd.json -> (LLM) -> design.json -> (Python) -> cabinet.js -> (PmBuilder) ->  editor_data.json

回归分析有两类:
1. design2edit: 输入design.json 输出 editor_data.json, 整个过程中是不需要LLM，存代码执行，用于检验Python代码和PmBuilder代码
2. abd2edit: 全流程回归，可以指定LLM采用哪种模型

# 前提说明
1. 从参数化工具中抓取editor_data.json 需要使用 param-editor-data 这个mcp工具，使用之前需要先配置mcp
{
  "mcpServers": {
    "parameditor": {
      "timeout": 60,
      "type": "http",
      "url": "http://localhost:7764/sse"
    },
        "param-editor-data": {
      "timeout": 60,
      "type": "http",
      "url": "http://localhost:7765/sse"
    }
  }
}
2. 在编辑器的 url 上加上 &__debug_tool=true 就可以用了

如果不进行回归案例的建立就不需要连接mcp

# 回归使用步骤
1. 运行Agent基于abd.json进行分析，生成design.json
2. 当组合柜在参数化编辑器生成后，检查没有问题后，在Agent中运行 '当前参数化编辑器中的柜子生成 editData, 放在output目录下'
会调用mcp工具生成editor_data.json
3. 将当前方案加入回归测试集，使用 'python regression/run_regression.py add-current-case', 指定测试集目录和方案名称
4. 运行 'python regression/run_regression.py run-design2edit', 回归运行得到报告


# 添加当前方案到方案集的方法
运行分析方案，生成参数化组合柜
生成必要的原始数据 abd.json, design.json, editor_data.json
进入wardrobe-agent目录, 运行
python regression/run_regression.py add-current-case --cases regressionCases --case-id case03

参数说明：
--cases regressionCases，regressionCases是指定的测试集的目录
--case-id case03，case03是指定的方案名称，如果不传 --case-id，自动生成：case_YYMMDDHHMM - 例如：case_2606152230

# abd2edit 回归分析方法步骤
进入wardrobe-agent目录

## 批量运行 design2edit：
python regression/run_regression.py run-design2edit --cases regressionCases

## 如果只跑 case04：
python regression/run_regression.py run-design2edit --cases regressionCases --case case04

## 如果出现 needs_review，总报告会生成在：
regressionCases/.runs/<时间戳>/summary.json
regressionCases/.runs/<时间戳>/Summary.md