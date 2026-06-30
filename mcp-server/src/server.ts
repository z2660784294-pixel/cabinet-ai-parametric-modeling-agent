// src/server.ts
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { FastMCP } from 'fastmcp';
import { SessionAuth } from './types';
import {
   getSceneInfo,
   clearScene,
   executeScript,
   getCurrentScript,
   getCurrentEditorData,
   setCurrentEditorData,
   getPreviewImage,
} from './tools/basic-tools';

import logger from './lib/logger';
import { getParamModelEditorToolsInfo, getParamEditorDataToolsInfo } from './tools/tools-info';

// ... 其他工具导入

// 读取 prompt.txt 文件内容
export function getParamEditorToolPrompt(): string {
   // 使用 import.meta.url 获取当前模块路径
   const currentFilePath = fileURLToPath(import.meta.url);
   const currentDir = path.dirname(currentFilePath);
   const promptPath = path.join(currentDir, 'prompt.txt');
   return fs.readFileSync(promptPath, 'utf-8');
}

// 创建 parameditor 服务器
export function createParamEditorServer(): FastMCP<SessionAuth> {
   const server = new FastMCP<SessionAuth>({
      name: "parameditor",
      version: "1.0.0",
   });

   // 注册所有工具
   server.addTool(getParamModelEditorToolsInfo);
   server.addTool(getSceneInfo);
   server.addTool(clearScene);
   server.addTool(executeScript);
   server.addTool(getCurrentScript);
   server.addTool(getPreviewImage);

   server.addPrompt({
      name: '参数化组合模型生成方法',
      description: '试用单元柜拼接参数化组合模型 MCP Server',
      arguments: [],
      load: async () => {
         return getParamEditorToolPrompt();
      }
   });

   server.on('connect', (event) => {
      logger.info('[parameditor] Client connected');
   });

   server.on('disconnect', (event) => {
      logger.info('[parameditor] Client disconnected');
   });

   return server;
}

// 创建 param-editor-data 服务器（当前编辑器 EditorData 读写工具）
export function createParamEditorDataServer(): FastMCP<SessionAuth> {
   const server = new FastMCP<SessionAuth>({
      name: "param-editor-data",
      version: "1.0.0",
   });

   const toolsToRegister = [
      { name: 'get_param_editor_data_tools_info', tool: getParamEditorDataToolsInfo },
      { name: 'get_current_editor_data', tool: getCurrentEditorData },
      { name: 'set_current_editor_data', tool: setCurrentEditorData },
   ];

   for (const { tool } of toolsToRegister) {
      server.addTool(tool);
   }

   server.addPrompt({
      name: '参数化编辑器 EditorData 服务',
      description: 'param-editor-data MCP 服务器的当前编辑器 EditorData 读写服务',
      arguments: [],
      load: async () => {
         return "本服务提供当前打开的参数化编辑器中正在编辑模型的 EditorData 读写工具，通过本地 JSON 文件透传数据。";
      }
   });

   server.on('connect', (event) => {
      logger.info('[param-editor-data] Client connected');
   });

   server.on('disconnect', (event) => {
      logger.info('[param-editor-data] Client disconnected');
   });

   return server;
}

// 用于处理服务器关闭的函数
export async function shutdownServer(): Promise<void> {
   // 断开与 Parametric Editor 的连接
   //  connectionManager.shutdown();
   logger.info('Disconnected from Parametric Editor');
}