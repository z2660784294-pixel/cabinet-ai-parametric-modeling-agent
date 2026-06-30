
要分析某个指定模型库类目的方法：

在Claude Code中，输入

使用 wardrobe-agent\data-tools\utils\model_info_utils 下的category_pipeline.py 生成信息，
组合柜在模型库中的目录 AI辅助建模-组合案例库 \ 药师临时测试目录  ，
目标文件夹 wardrobe-agent\temp\category\test

然后进行运行，就在指定文件夹下生成内容

实际是Powershell中进行了

python utils\model_info_utils\category_pipeline.py `
  --category-name "柜体组合库/AI 辅助建模-组合案例库/药师临时测试目录" `
  --output-root "..\temp\category\test"


  如果获得category-id，等价于
  
  python utils\model_info_utils\category_pipeline.py `
  --category-id 3FO4JROEXDFL `
  --output-root "..\temp\category\test"


如何使用 generate_assembly_parameter_template.py
在Powershell中使用python运行
输入：1. 组合柜的数据的文件夹  2. 输出文件的目录
例子：

 python .\utils\model_info_utils\generate_assembly_parameter_template.py --cases-root "D:\agentStudio\studyData\category\topwardobe\cases" --output-dir ".\temp\assembly-template-topwardobe" --strict

运行后生成文件在：
  .\temp\assembly-template-topwardobe\custom_params_template.md
  .\temp\assembly-template-topwardobe\custom_params_template.json