// src/tools/basic-tools.ts
import * as fs from 'fs';
import * as path from 'path';
import { Context } from '../types';
import { z } from 'zod';
import logger from '../lib/logger';
import { llmClient } from '../llmClient';

// getSceneInfo 工具
export const getSceneInfo = {
  name: 'get_scene_info',
  description: '获取编辑器场景里所有参数化模型的3d bbox 和 bbox 是否干涉的信息',
  parameters: z.object({}),
  execute: async (_args: {}, context: Context): Promise<string> => {
    logger.info(`Tool executed: get_scene_info`)

    try {
      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(
          'No Koomaster clients connected when attempting to get scene info'
        )
        return 'No Koomaster clients connected. Please start the Koomaster addon and connect to this server.'
      }

      logger.debug(`Sending 'get_scene_info' command to Koomaster`)
      const result = await llmClient.sendCommand('get_scene_info')
      logger.debug(
        `Received scene info response with ${Object.keys(result).length} keys`
      )

      return JSON.stringify(result, null, 2)
    } catch (e) {
      const errorMessage = `Error getting scene info from Koomaster: ${
        e instanceof Error ? e.message : String(e)
      }`
      logger.error(errorMessage)
      context.log.error(errorMessage)
      return `Error getting scene info: ${
        e instanceof Error ? e.message : String(e)
      }`
    }
  },
}

export const executeScript = {
  name: 'execute_script',
  description:
    '从本地脚本文件读取内容并执行。srcInput 为脚本文件的完整本地路径（当前仅支持本地磁盘路径）。',
  parameters: z.object({
    srcInput: z
      .string()
      .min(1)
      .describe(
        '要执行的脚本文件的完整路径（当前约定为本地路径；将来可能支持网络 URL 等）'
      ),
  }),
  execute: async (
    args: { srcInput: string },
    context: Context
  ): Promise<string> => {
    const srcInput = args.srcInput;
    logger.info(`Tool executed: execute_script (srcInput=${srcInput})`);

    const fail = (error: string) =>
      JSON.stringify({ success: false, srcInput, error }, null, 2);

    try {
      if (/^https?:\/\//i.test(srcInput)) {
        return fail(
          'srcInput 当前仅支持本地完整路径，暂不支持 http(s) 等网络地址'
        );
      }

      if (!fs.existsSync(srcInput)) {
        return fail(`文件不存在: ${srcInput}`);
      }

      const script = fs.readFileSync(srcInput, 'utf-8');

      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(
          'No Koomaster clients connected when attempting to execute script'
        );
        return fail(
          'No Koomaster clients connected. Please start the Koomaster addon and connect to this server.'
        );
      }

      logger.debug(`Sending 'execute_script' command with script from ${srcInput}`);
      const result = await llmClient.sendCommand('execute_script', {
        script,
      });
      logger.info(`Script executed successfully: ${result}`);
      return JSON.stringify({ success: true, srcInput, result }, null, 2);
    } catch (e) {
      const errorMessage = `Error executing script: ${
        e instanceof Error ? e.message : String(e)
      }`;
      logger.error(errorMessage);
      context.log.error(errorMessage);
      return fail(e instanceof Error ? e.message : String(e));
    }
  },
}

export const getCurrentScript = {
  name: 'get_current_script',
  description:
    '从参数化编辑器获取当前模型转换而来的参数化模型构建脚本，并写入本地文件。destOutput 为保存文件的完整本地路径（当前仅支持本地磁盘路径）。成功时返回 JSON：success、destOutput、bytesWritten；失败时返回 success:false 与 error。',
  parameters: z.object({
    destOutput: z
      .string()
      .min(1)
      .describe(
        '脚本输出文件的完整路径（当前约定为本地路径；将来可能支持网络 URL 等）'
      ),
  }),
  execute: async (
    args: { destOutput: string },
    context: Context
  ): Promise<string> => {
    const destOutput = args.destOutput;
    logger.info(
      `Tool executed: get_current_script (destOutput=${destOutput})`
    );

    const fail = (error: string) =>
      JSON.stringify({ success: false, destOutput, error }, null, 2);

    try {
      if (/^https?:\/\//i.test(destOutput)) {
        return fail(
          'destOutput 当前仅支持本地完整路径，暂不支持 http(s) 等网络地址'
        );
      }

      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(
          'No Koomaster clients connected when attempting to get current script'
        );
        return fail(
          'No Koomaster clients connected. Please start the Koomaster addon and connect to this server.'
        );
      }

      logger.debug(`Sending 'get_current_script' command to Koomaster`);
      const result = await llmClient.sendCommand('get_current_script');

      const script =
        typeof result === 'string' ? result : JSON.stringify(result, null, 2);

      const dir = path.dirname(destOutput);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(destOutput, script, 'utf-8');

      const bytesWritten = Buffer.byteLength(script, 'utf-8');
      logger.info(
        `Script written to ${destOutput} (${bytesWritten} bytes)`
      );

      return JSON.stringify(
        { success: true, destOutput, bytesWritten },
        null,
        2
      );
    } catch (e) {
      const errorMessage = `Error getting current script from Koomaster: ${
        e instanceof Error ? e.message : String(e)
      }`;
      logger.error(errorMessage);
      context.log.error(errorMessage);
      return fail(e instanceof Error ? e.message : String(e));
    }
  },
}

export const clearScene = {
  name: 'clear_scene',
  description: '清除场景中的所有元素',
  parameters: z.object({}),
  execute: async (_args: {}, context: Context): Promise<string> => {
    logger.info(`Tool executed: clear_scene`)

    try {
      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(
          'No Koomaster clients connected when attempting to clear scene'
        )
        return 'No Koomaster clients connected. Please start the Koomaster addon and connect to this server.'
      }

      logger.debug(`Sending 'clear_scene' command to Koomaster`)
      const result = await llmClient.sendCommand('clear_scene')
      logger.debug(
        `Received scene info response with ${Object.keys(result).length} keys`
      )

      // 记录一些有用的场景统计信息
      if (result) {
        const objectCount = result.modelInstances?.length || 0
        logger.info(`Scene statistics: ${objectCount} objects`)
      }

      return JSON.stringify(result, null, 2)
    } catch (e) {
      const errorMessage = `Error clearing scene from Koomaster: ${
        e instanceof Error ? e.message : String(e)
      }`
      logger.error(errorMessage)
      context.log.error(errorMessage)
      return `Error clearing scene: ${
        e instanceof Error ? e.message : String(e)
      }`
    }
  },
}

/** Parse Koomaster preview payload (data URL) into raw image bytes. */
function decodePreviewDataUrl(raw: unknown): Buffer | null {
  if (typeof raw !== 'string') return null
  const text = raw.trim().replace(/^\ufeff/, '')
  if (!text.startsWith('data:')) return null
  const comma = text.indexOf(',')
  if (comma === -1) return null
  const meta = text.slice(5, comma).toLowerCase()
  if (!meta.includes('base64')) return null
  const b64 = text.slice(comma + 1).replace(/\s/g, '')
  if (!b64) return null
  const buf = Buffer.from(b64, 'base64')
  return buf.length > 0 ? buf : null
}

export const getPreviewImage = {
  name: 'get_preview_image',
  description:
    '获取编辑器场景的预览图并写入本地文件。可通过 cameraViewMode 指定相机观察模式（支持 top/bottom/left/right/front/back/leftfront/leftback/rightfront/rightback/3DWithOrthographic）；destOutput 为保存文件的完整本地路径（当前仅支持本地磁盘路径）。成功时返回 JSON：success、destOutput；失败时返回 success:false 与 error。',
  parameters: z.object({
    cameraViewMode: z
      .enum([
        'top', 'bottom',
        'left', 'right',
        'front', 'back',
        'leftfront', 'leftback',
        'rightfront', 'rightback',
        '3DWithOrthographic',
      ])
      .default('front')
      .describe('预览相机的观察模式, 没有特殊说明，使用`front`'),
    destOutput: z
      .string()
      .min(1)
      .describe(
        '预览图输出文件的完整路径（当前约定为本地路径；将来可能支持网络 URL 等）'
      ),
  }),
  execute: async (
    args: {
      cameraViewMode: 'top' | 'bottom' | 'left' | 'right' | 'front' | 'back' | 'leftfront' | 'leftback' | 'rightfront' | 'rightback' | '3DWithOrthographic'
      destOutput: string
    },
    context: Context
  ): Promise<string> => {
    const cameraViewMode = args.cameraViewMode ?? 'front'
    const destOutput = args.destOutput
    logger.info(
      `Tool executed: get_preview_image (cameraViewMode=${cameraViewMode}, destOutput=${destOutput})`
    )

    const fail = (error: string) =>
      JSON.stringify({ success: false, destOutput, error }, null, 2)

    try {
      if (/^https?:\/\//i.test(destOutput)) {
        return fail(
          'destOutput 当前仅支持本地完整路径，暂不支持 http(s) 等网络地址'
        )
      }

      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(
          'No Koomaster clients connected when attempting to get preview'
        )
        return fail(
          'No Koomaster clients connected. Please start the Koomaster addon and connect to this server.'
        )
      }
      logger.debug(
        `Sending 'get_preview_image' command to Koomaster (cameraViewMode=${cameraViewMode})`
      )
      const result = await llmClient.sendCommand('get_preview_image', {
        cameraViewMode,
      })
      logger.debug(`Received preview response`)

      const buffer = decodePreviewDataUrl(result)
      if (!buffer) {
        const msg =
          '预览数据无效或不是预期的 data:image/*;base64,... 格式，无法写入文件'
        logger.error(msg)
        context.log.error(msg)
        return fail(msg)
      }

      const dir = path.dirname(destOutput)
      fs.mkdirSync(dir, { recursive: true })
      fs.writeFileSync(destOutput, buffer)

      logger.info(
        `Preview written to ${destOutput} (${buffer.length} bytes)`
      )
      return JSON.stringify(
        { success: true, destOutput, bytesWritten: buffer.length },
        null,
        2
      )
    } catch (e) {
      const errorMessage = `Error getting preview from Koomaster: ${
        e instanceof Error ? e.message : String(e)
      }`
      logger.error(errorMessage)
      context.log.error(errorMessage)
      return fail(
        e instanceof Error ? e.message : String(e)
      )
    }
  },

}

export const getRating = {
  name: 'get_rating',
  description: '获取模型性能诊断数据',
  parameters: z.object({}),
  execute: async (_args: {}, context: Context): Promise<string> => {
    logger.info(`Tool executed: get_rating`)

    try {
      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(
          'No Koomaster clients connected when attempting to get rating'
        )
        return 'No Koomaster clients connected. Please start the Koomaster addon and connect to this server.'
      }
      logger.debug(`Sending 'get_rating' command to Koomaster`)
      const result = await llmClient.sendCommand('get_rating')
      logger.debug(
        `Received rating response`
      )
      return JSON.stringify(result, null, 2)

    } catch (e) {
      const errorMessage = `Error getting rating from Koomaster: ${
        e instanceof Error ? e.message : String(e)
      }`
      logger.error(errorMessage)
      context.log.error(errorMessage)
      return `Error getting rating: ${
        e instanceof Error ? e.message : String(e)
      }`
    }
  },

}

export const getPositionEvaluation = {
  name: 'get_position_evaluation',
  description: '获取模型位置评估',
  parameters: z.object({}),
  execute: async (_args: {}, context: Context): Promise<string> => {
    logger.info(`Tool executed: get_position_evaluation`)

    try {
      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(
          'No Koomaster clients connected when attempting to get position evaluation'
        )
        return 'No Koomaster clients connected. Please start the Koomaster addon and connect to this server.'
      }
      logger.debug(`Sending 'get_position_evaluation' command to Koomaster`)
      const result = await llmClient.sendCommand('get_position_evaluation')
      logger.debug(
        `Received model position evaluation response`
      )
      return JSON.stringify(result, null, 2)

    } catch (e) {
      const errorMessage = `Error getting model position evaluation from Koomaster: ${
        e instanceof Error ? e.message : String(e)
      }`
      logger.error(errorMessage)
      context.log.error(errorMessage)
      return `Error getting model position evaluation: ${
        e instanceof Error ? e.message : String(e)
      }`
    }
  },

}

export const switchIndustryLine = {
  name: 'switch_industry_line',
  description:
    '切换参数化编辑器的行业线（toolType）。根据用户输入判断要设计的产品类别后调用：衣柜/鞋柜/书柜/储物柜等选 wardrobe，厨柜/橱柜/吊柜/台盆柜等选 cabinet，门窗/推拉门等选 doorwindow。\n\n**行为说明：**\n- 若已在目标行业线，返回 "already on xxx"，不刷新（幂等）\n- 否则编辑器整页刷新到目标行业线；刷新会短暂断开 WS，koomaster 自动重连\n- 调用此工具后的下一个工具若遇 "No Koomaster clients connected"，等待 2-3 秒后重试即可',
  parameters: z.object({
    toolType: z
      .enum(['cabinet', 'wardrobe', 'doorwindow'])
      .describe('目标行业线：cabinet=厨卫，wardrobe=全屋家具，doorwindow=定制门窗'),
    reason: z
      .string()
      .optional()
      .describe('可选，切换理由（人类可读），仅用于日志追踪。例：用户需要衣柜组合'),
  }),
  execute: async (
    args: { toolType: 'cabinet' | 'wardrobe' | 'doorwindow'; reason?: string },
    context: Context
  ): Promise<string> => {
    logger.info(
      `Tool executed: switch_industry_line (toolType=${args.toolType}, reason=${args.reason || '(none)'})`
    )

    try {
      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn('No Koomaster clients connected when attempting to switch industry line')
        return 'No Koomaster clients connected. Please start the Koomaster addon and connect to this server.'
      }

      logger.debug(
        `Sending 'switch_industry_line' command to Koomaster with toolType=${args.toolType}`
      )
      const result = await llmClient.sendCommand('switch_industry_line', {
        toolType: args.toolType,
        reason: args.reason,
      })
      logger.info(`switch_industry_line result: ${JSON.stringify(result)}`)

      return JSON.stringify(result, null, 2)
    } catch (e) {
      const errorMessage = `Error switching industry line: ${
        e instanceof Error ? e.message : String(e)
      }`
      logger.error(errorMessage)
      context.log.error(errorMessage)
      return errorMessage
    }
  },
}

export const getCurrentEditorData = {
  name: 'get_current_editor_data',
  description:
    '获取当前打开的参数化编辑器中正在编辑模型的 EditorData，并写入本地 JSON 文件。destOutput 为保存文件的完整本地路径（当前仅支持本地磁盘路径）。MCP Server 与编辑器之间透传 EditorData JSON 字符串，不解析其结构。成功时返回 JSON：success、destOutput、bytesWritten；失败时返回 success:false 与 error。',
  parameters: z.object({
    destOutput: z
      .string()
      .min(1)
      .describe(
        'EditorData JSON 输出文件的完整路径（当前约定为本地路径；将来可能支持网络 URL 等）'
      ),
  }),
  execute: async (
    args: { destOutput: string },
    context: Context
  ): Promise<string> => {
    const destOutput = args.destOutput;
    logger.info(
      `Tool executed: get_current_editor_data (destOutput=${destOutput})`
    );

    const fail = (error: string) =>
      JSON.stringify({ success: false, destOutput, error }, null, 2);

    try {
      if (/^https?:\/\//i.test(destOutput)) {
        return fail(
          'destOutput 当前仅支持本地完整路径，暂不支持 http(s) 等网络地址'
        );
      }

      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(
          'No Koomaster clients connected when attempting to get current editor data'
        );
        return fail(
          'No Koomaster clients connected. Please start the Koomaster addon and connect to this server.'
        );
      }

      logger.debug(`Sending 'get_current_editor_data' command to Koomaster`);
      const result = await llmClient.sendCommand('get_current_editor_data');

      const json =
        typeof result === 'string' ? result : JSON.stringify(result, null, 2);

      const dir = path.dirname(destOutput);
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(destOutput, json, 'utf-8');

      const bytesWritten = Buffer.byteLength(json, 'utf-8');
      logger.info(
        `EditorData written to ${destOutput} (${bytesWritten} bytes)`
      );

      return JSON.stringify(
        { success: true, destOutput, bytesWritten },
        null,
        2
      );
    } catch (e) {
      const errorMessage = `Error getting current editor data: ${
        e instanceof Error ? e.message : String(e)
      }`;
      logger.error(errorMessage);
      context.log.error(errorMessage);
      return fail(e instanceof Error ? e.message : String(e));
    }
  },
};

export const setCurrentEditorData = {
  name: 'set_current_editor_data',
  description:
    '从本地 JSON 文件读取 EditorData，并设置给当前打开的参数化编辑器中正在编辑的模型。srcInput 为 EditorData JSON 文件的完整本地路径（当前仅支持本地磁盘路径）。MCP Server 与编辑器之间透传 EditorData JSON 字符串，不解析其结构。成功时返回 JSON：success、srcInput；失败时返回 success:false 与 error。',
  parameters: z.object({
    srcInput: z
      .string()
      .min(1)
      .describe(
        'EditorData JSON 输入文件的完整路径（当前约定为本地路径；将来可能支持网络 URL 等）'
      ),
  }),
  execute: async (
    args: { srcInput: string },
    context: Context
  ): Promise<string> => {
    const srcInput = args.srcInput;
    logger.info(
      `Tool executed: set_current_editor_data (srcInput=${srcInput})`
    );

    const fail = (error: string) =>
      JSON.stringify({ success: false, srcInput, error }, null, 2);

    try {
      if (/^https?:\/\//i.test(srcInput)) {
        return fail(
          'srcInput 当前仅支持本地完整路径，暂不支持 http(s) 等网络地址'
        );
      }

      if (!fs.existsSync(srcInput)) {
        return fail(`文件不存在: ${srcInput}`);
      }

      const editorData = fs.readFileSync(srcInput, 'utf-8');

      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(
          'No Koomaster clients connected when attempting to set current editor data'
        );
        return fail(
          'No Koomaster clients connected. Please start the Koomaster addon and connect to this server.'
        );
      }

      logger.debug(`Sending 'set_current_editor_data' command to Koomaster`);
      const result = await llmClient.sendCommand('set_current_editor_data', {
        editorData,
      });

      if (typeof result === 'string') {
        return JSON.stringify({ success: true, srcInput, message: result }, null, 2);
      }

      return JSON.stringify({ success: true, srcInput, ...result }, null, 2);
    } catch (e) {
      const errorMessage = `Error setting current editor data: ${
        e instanceof Error ? e.message : String(e)
      }`;
      logger.error(errorMessage);
      context.log.error(errorMessage);
      return fail(e instanceof Error ? e.message : String(e));
    }
  },
};

// 导出所有工具
export const basicTools = {
    getSceneInfo,
    executeScript,
    getCurrentScript,
    clearScene,
    getPreviewImage,
    getRating,
    getPositionEvaluation,
    switchIndustryLine,
    getCurrentEditorData,
    setCurrentEditorData,
};
