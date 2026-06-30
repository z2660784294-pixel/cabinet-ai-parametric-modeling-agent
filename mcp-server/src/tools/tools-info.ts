import logger from "../lib/logger";
import { z } from "zod";
import { Context } from "../types";
import { llmClient } from "../llmClient";
import { getParamEditorToolPrompt } from "../server";

// Parametric Editor 工具信息 - 获取编辑器相关工具列表和使用信息
// 包含: get_scene_info, clear_scene, execute_script, get_current_script, get_preview_image
export const getParamModelEditorToolsInfo = {
    name: "get_param_model_editor_tools_info",
    description:
        "CRITICAL FIRST STEP: Returns comprehensive documentation about all available Parametric Editor tools, coordinate system specifications, measurement units, and best practices. Must be called before using any other functions to ensure proper model placement and prevent clipping issues. Provides essential information about the Z-up right-handed coordinate system and proper object positioning.",
    parameters: z.object({}),
    execute: async (_args: {}, _context: Context): Promise<string> => {
        logger.info(`Tool executed: get_param_model_editor_tools_info (parameditor)`);

        try {
            // 组织工具信息
            const toolsInfo = {
                basic: [
                    "get_scene_info - 获取编辑器场景里所有参数化模型的3d bbox 和 bbox 是否干涉的信息",
                    "clear_scene - 清空编辑器场景里所有的模型",
                    "execute_script - 执行一个脚本生成参数化模型",
                    "get_current_script - 获取当前参数化编辑器场景里的模型所对应的脚本",
                    "get_preview_image - 将预览图写入本地文件",
                ],
            };

            // 连接状态信息
            const connectionStatus = llmClient.hasConnectedKoomasterClients()
                ? `✅ Connected to Parametric Editor client`
                : "❌ Not connected to Parametric Editor";

            // 格式化工具信息
            let result = `# Parametric Editor MCP Tools Overview\n\n`;
            result += `${connectionStatus}\n\n`;
            result += `## Basic Tools\n\n`;
            toolsInfo.basic.forEach((tool) => {
                result += `- ${tool}\n`;
            });

            result += getParamEditorToolPrompt();

            logger.debug(
                `Generated tools info summary (${result.length} characters)`
            );
            return result;
        } catch (e) {
            const errorMessage = `Error getting tools info: ${e instanceof Error ? e.message : String(e)
                }`;
            logger.error(errorMessage);
            return `Error getting tools info: ${e instanceof Error ? e.message : String(e)
                }`;
        }
    },
};

// Param Editor Data 工具信息 - 当前编辑器 EditorData 读写工具
// 包含: get_current_editor_data, set_current_editor_data
export const getParamEditorDataToolsInfo = {
    name: "get_param_editor_data_tools_info",
    description:
        "CRITICAL FIRST STEP: Returns documentation for the param-editor-data MCP tools. Call before get_current_editor_data or set_current_editor_data to understand file path parameters and KooMaster connection prerequisites.",
    parameters: z.object({}),
    execute: async (_args: {}, _context: Context): Promise<string> => {
        logger.info(`Tool executed: get_param_editor_data_tools_info`);

        try {
            const toolsInfo = {
                basic: [
                    "get_current_editor_data - 获取当前编辑器正在编辑模型的 EditorData，写入本地 JSON 文件",
                    "set_current_editor_data - 从本地 JSON 文件读取 EditorData，写回当前编辑器正在编辑的模型",
                ],
            };

            const connectionStatus = llmClient.hasConnectedKoomasterClients()
                ? `✅ Connected to Parametric Editor client`
                : "❌ Not connected to Parametric Editor";

            let result = `# Parametric Editor Data MCP Tools Overview\n\n`;
            result += `${connectionStatus}\n\n`;
            result += `## Basic Tools\n\n`;
            toolsInfo.basic.forEach((tool) => {
                result += `- ${tool}\n`;
            });
            result += `\n## get_current_editor_data Usage\n\n`;
            result += `- destOutput: required absolute local path for the output JSON file.\n`;
            result += `- Prerequisites: KooMaster client must be connected, and a model must be open in the parametric editor.\n`;
            result += `- Output: writes EditorData JSON to destOutput and returns success, destOutput, and bytesWritten. The MCP server does not parse EditorData structure.\n`;
            result += `\n## set_current_editor_data Usage\n\n`;
            result += `- srcInput: required absolute local path to an EditorData JSON file (typically produced by get_current_editor_data).\n`;
            result += `- Prerequisites: same as get_current_editor_data.\n`;
            result += `- Output: reads JSON from srcInput, passes it to the editor as a string, and returns success or error. The MCP server does not parse EditorData structure.\n`;

            logger.debug(
                `Generated tools info summary (${result.length} characters)`
            );
            return result;
        } catch (e) {
            const errorMessage = `Error getting tools info: ${e instanceof Error ? e.message : String(e)
                }`;
            logger.error(errorMessage);
            return `Error getting tools info: ${e instanceof Error ? e.message : String(e)
                }`;
        }
    },
};
