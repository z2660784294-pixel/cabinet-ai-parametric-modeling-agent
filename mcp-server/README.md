# Parameditor MCP Server

## 核心功能
- 🔌 WebSocket桥接服务（详见`src/llmClient.ts`）
- 🧰 丰富工具集（`src/tools/`包含基础建模工具）
  - 基础建模工具（立方体/扫掠体/布尔切割）
  - 参数化模型生成
  - 场景管理工具

## 快速开始

### 运行环境准备
1. 安装Node.js（**v18+**）：
   - 官方下载：[Node.js 18+](https://nodejs.org/zh-cn/download)
2. 打开系统终端：
   - Mac系统：[终端使用指南](https://support.apple.com/zh-cn/guide/terminal/apd5265185d-f365-44cb-8b09-71a064a42125/mac)
   - Windows系统：[CMD打开方式](https://blog.csdn.net/B11050729/article/details/131494056)

### 启动服务
```bash
npx -y parameditor-mcp-server start --stdio
```
当终端显示`MCP Server Endpoint: `即表示启动成功


### 故障排除
若启动失败，可尝试安装指定版本：
```bash
npm i -g parameditor-mcp-server@1.0.27 --registry=https://registry.npmjs.org
```

## 核心模块
### 1. 工具系统 (`src/tools/`)
- **基础工具**：
  - initialize - 初始化编辑器建模数据
  - get_scene_info - 获取编辑器场景里所有参数化模型的3d bbox 和 bbox 是否干涉的信息
  - list_models - 获取编辑器场景里的模型(id, name)对照表
  - list_params - 获取编辑器里的所有参数的信息
  - clear_scene - 清除场景中的所有元素
  - execute_script - 执行一段参数化模型生成的代码
  - get_current_script - 获取最近一次通过 execute_script 成功执行的脚本内容，便于在原脚本基础上继续修改参数化模型
  - get_position_evaluation - 获取模型位置情况评估
  - move_model_to - 移动模型到指定位置
  - modify_param - 修改或新增参数

### 2. 客户端连接 (`src/llmClient.ts`)
- WebSocket长连接管理
- 命令队列与超时控制
- 客户端状态监测

### 3. 提示策略 (`src/prompt.ts`)
```
包含300+条建模规范：
- 坐标系标准 (Z-up右手系)
- 单位系统 (毫米级精度)
- 参数化表达式语法
```


## 开发指南
1. 工具扩展：在`src/tools/`创建新工具类
2. API集成：参考`basic-tools.ts`实现基础工具
3. 客户端协议：遵循`llmClient.ts`定义的消息格式

## 贡献者协议
请遵循`src/prompt.ts`中定义的建模规范提交代码