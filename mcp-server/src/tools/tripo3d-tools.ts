import { Context } from '../types';
import { z } from 'zod';
import logger from '../lib/logger';
import { Tripo3DTaskStatusResponse } from '../types/tripo3d';
import { llmClient } from '../llmClient';
import { gltf2obj } from '../lib/gltf2obj/index.js'; // 导入GLB转OBJ的方法
import { imageContent, UserError } from 'fastmcp';

export const apiKey = process.env.TRIPO3D_API_KEY;

// Tool: Get Tripo3D Status
export const getTripo3DStatusTool = {
    name: 'get_tripo3d_status',
    description: 'Check if Tripo3D is configured and available for use by verifying the presence of required API keys and configuration',
    parameters: z.object({}),  // No parameters needed
    execute: async (args, context: Context): Promise<string> => {
        logger.info(`Tool executed: get_tripo3d_status`);
        try {
            // Check if Tripo3D API key is provided in environment variables
            const tripo3dApiKey = apiKey;

            if (!tripo3dApiKey) {
                throw new UserError("Tripo3D is not fully configured. The API key is missing from the environment variables. Please set TRIPO3D_API_KEY in your environment to use Tripo3D features.");
            }

            return "Tripo3D is properly configured and ready to use. API key is present in the environment.";
        } catch (e) {
            const errorMessage = `Error checking Tripo3D status: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    }
};

export const createTripo3DJobTool = {
    name: 'create_tripo3d_job',
    description: 'Generate a 3D model using tripo3d service from text or images',
    parameters: z.object({
        // 任务类型标识符 (隐式参数，根据输入自动确定)

        // 文本到模型的基本参数
        prompt: z.string().optional().describe('Text input that directs the model generation. Required for Text-to-3D mode. Max 1024 characters.'),
        negative_prompt: z.string().optional().describe('Text input that provides a reverse direction to assist in generating content contrasting with the original prompt. Max 255 characters.'),

        // 图像到模型的基本参数
        // condition_mode: z.enum(['fuse', 'concat']).optional().default('concat').describe('For fuse mode, features from multiple images are fused. For concat mode, multi-view images of the same object are used.'),

        // 随机种子控制
        model_seed: z.number().int().min(0).max(65535).optional().describe('Random seed for model geometry generation. Using the same seed produces identical models.'),
        image_seed: z.number().int().min(0).max(65535).optional().describe('Random seed used for the process based on the prompt.'),
        texture_seed: z.number().int().min(0).max(65535).optional().describe('Random seed for texture generation. Using the same seed produces identical textures.'),

        // 输出格式控制
        // output_format: z.enum(['glb', 'usdz', 'fbx', 'obj', 'stl']).optional().default('glb').describe('Format of the output 3D model file.'),

        // 模型版本
        // model_version: z.enum(['v2.5-20250123', 'v2.0-20240919', 'v1.4-20240625']).optional().default('v2.5-20250123').describe('Tripo3D model version to use for generation.'),

        // 模型质量控制参数 (v2.0-20240919及以上版本可用)
        face_limit: z.number().int().positive().optional().describe('Limits the number of faces on the output model. If not set, it will be determined adaptively.'),
        // texture: z.boolean().optional().default(true).describe('Enable texturing. Set false to get a base model without textures.'),
        // pbr: z.boolean().optional().default(true).describe('Enable PBR materials. If true, texture will be forced to true.'),
        texture_quality: z.enum(['standard', 'detailed']).optional().default('standard').describe('Controls texture quality. "detailed" provides high-resolution textures.'),
        auto_size: z.boolean().optional().default(false).describe('Automatically scale the model to real-world dimensions (in meters).'),
        style: z.enum([
            'person:person2cartoon',
            'object:clay',
            'object:steampunk',
            'animal:venom',
            'object:barbie',
            'object:christmas',
            'gold',
            'ancient_bronze'
        ]).optional().describe(
            'Defines the artistic style to be applied to the 3D model. Available styles:\n' +
            '- person:person2cartoon: Transforms the model into a cartoon-style version of input character\n' +
            '- object:clay: Applies a clay-like appearance to the object\n' +
            '- object:steampunk: Applies a steampunk aesthetic with metallic gears and vintage details\n' +
            '- animal:venom: Applies a venom-like, dark, and glossy appearance to the animal model (warning: may be horrific)\n' +
            '- object:barbie: Applies a barbie style to the object\n' +
            '- object:christmas: Applies a christmas style to the object\n' +
            '- gold: Applies a gold style to the object\n' +
            '- ancient_bronze: Applies a ancient bronze style to the object'
        ),
        quad: z.boolean().optional().default(false).describe('Enable quad mesh output. Forces the output to be an FBX model.'),

        // 姿态控制
        pose: z.enum(['T-pose', 'A-pose']).optional().describe('Set the model in a specific pose.'),
        pose_params: z.string().optional().describe('Custom pose parameters in format "A:B:C:D:E" where A=head-to-body height ratio, B=head-to-body width ratio, C=legs-to-body height ratio, D=arms-to-body length ratio, E=span of two legs(0-15).')
    }),
    execute: async (args, context: Context): Promise<string> => {
        // 记录工具执行
        const logMethod = args.prompt ?
            `text prompt: "${args.prompt.substring(0, 50)}${args.prompt.length > 50 ? '...' : ''}"` :
            `${args.input_image_urls?.length || 0} image(s)`;
        logger.info(`Tool executed: create_tripo3d_job with ${logMethod}`);

        try {
            // 参数验证
            if (!args.prompt) {
                return "Error: Either 'prompt' (for Text-to-3D) or 'input_image_urls' (for Image-to-3D) must be provided.";
            }

            // 检查是否有客户端连接
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn('No modeling software clients connected');
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }

            // 准备请求参数 - 直接传递所有参数
            const params = {
                ...args,
                pbr: false,
                texture: true,
                model_version: "v2.5-20250123"
            };

            // 处理特殊姿态参数
            if (args.pose) {
                let poseString = args.pose;
                if (args.pose_params) {
                    poseString += `:${args.pose_params}`;
                }

                // 如果提示词已存在，将姿态信息附加到提示词末尾
                if (args.prompt) {
                    params.prompt = `${args.prompt}, ${poseString}`;
                }

                // 从参数中移除这些特殊处理的字段，防止 API 混淆
                delete params.pose;
                delete params.pose_params;
            }

            logger.debug(`Sending create_tripo3d_job command to client with params: ${JSON.stringify(params)}`);

            // 从 params 提取参数，映射到 Tripo3D API 需要的格式
            const requestData: Record<string, any> = {
                type: 'text_to_model',
                model_version: params.model_version || 'v2.5-20250123', // 默认使用最新版本
                prompt: params.prompt
            };

            // 添加可选参数
            if (params.negative_prompt) {
                requestData.negative_prompt = params.negative_prompt;
            }

            if (params.image_seed !== undefined) {
                requestData.image_seed = params.image_seed;
            }

            if (params.model_seed !== undefined) {
                requestData.model_seed = params.model_seed;
            }

            // v2.0及以上版本可用的特殊参数
            if (requestData.model_version && requestData.model_version.startsWith('v2')) {
                if (params.face_limit !== undefined) {
                    requestData.face_limit = params.face_limit;
                }

                if (params.texture !== undefined) {
                    requestData.texture = params.texture;
                }

                if (params.pbr !== undefined) {
                    requestData.pbr = params.pbr;
                }

                if (params.texture_seed !== undefined) {
                    requestData.texture_seed = params.texture_seed;
                }

                if (params.texture_quality) {
                    requestData.texture_quality = params.texture_quality;
                }

                if (params.auto_size !== undefined) {
                    requestData.auto_size = params.auto_size;
                }

                if (params.style) {
                    requestData.style = params.style;
                }

                if (params.quad !== undefined) {
                    requestData.quad = params.quad;
                }
            }

            // 处理姿势设置
            // 如果有 TAPose 参数，根据值添加 T-pose 或 A-pose
            if (params.TAPose !== undefined) {
                if (typeof params.TAPose === 'string') {
                    // 如果是字符串，直接使用（假设用户已经提供了正确格式如 "T-pose:1:1:1:1:9"）
                    const poseSuffix = params.TAPose;
                    if (!requestData.prompt.includes(poseSuffix)) {
                        requestData.prompt = `${requestData.prompt}, ${poseSuffix}`;
                    }
                } else if (params.TAPose === true) {
                    // 如果是布尔值 true，使用默认 T-pose
                    if (!requestData.prompt.includes('T-pose') && !requestData.prompt.includes('A-pose')) {
                        requestData.prompt = `${requestData.prompt}, T-pose`;
                    }
                }
            }

            logger.info('Sending request to Tripo3D API:', requestData);

            // 调用 Tripo3D API
            const response = await fetch('https://api.tripo3d.ai/v2/openapi/task', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${apiKey}`
                },
                body: JSON.stringify(requestData)
            });
            // 通过 llmClient 发送命令到客户端
            // const result = await llmClient.sendCommand("create_tripo3d_job", params);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message);
                // return {
                //     status: "error",
                //     message: `Tripo3D API error: ${response.status} - ${errorData.code || 'Unknown error code'} - ${errorData.message || 'Unknown error message'}`
                // };
            }

            const result = await response.json();

            if (result.code !== 0) {
                return `Error creating Tripo3D job, HTTP Status Code${result.code}`;
            }

            return `✅ 3D model generation job submitted successfully!

                Request ID: ${result.data.task_id}
                
                Your 3D model is being generated. This process typically takes 1-5 minutes.
                Use the 'poll_tripo3d_job_status' tool with this task_id to check the status.
                
                Generation parameters:
                ${params.prompt ? `- Prompt: "${params.prompt}"` : ''}
                ${params.input_image_urls ? `- Images: ${params.input_image_urls.length} image(s)` : ''}
                - Mode: Text-to-3D
                - Format: obj
                - Quality: ${params.quality || 'medium'}
                - Material: ${params.material || 'PBR'}
                
                When the model is ready, use the 'import_generated_asset' tool to import it into your scene.`

        } catch (e) {
            // 处理执行期间的任何错误
            const errorMessage = `Error creating Tripo3D job: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    }
};

// 工具: 检查 Tripo3D 任务状态 - 仅传递参数
export const pollTripo3DJobStatusTool = {
    name: 'poll_tripo3d_job_status',
    description: 'Check the status of a Tripo3D 3D model generation job',
    parameters: z.object({
        task_id: z.string().optional().describe('The request ID for FAL_AI mode'),
    }),
    execute: async (args, context: Context): Promise<string> => {
        logger.info(`Tool executed: poll_tripo3d_job_status with params: ${JSON.stringify(args)}`);

        try {
            // 检查是否有客户端连接
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn('No modeling software clients connected');
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }

            // 检查是否提供了必要参数
            if (!args.task_id) {
                return "Error: 'task_id' must be provided.";
            }

            logger.debug(`Sending poll_tripo3d_job_status command to client`);


            const url = `https://api.tripo3d.ai/v2/openapi/task/${args.task_id}`;

            const options = {
                headers: {
                    'Authorization': 'Bearer ' + apiKey
                }
            };

            const result: Tripo3DTaskStatusResponse = await fetch(url, options)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status},info : ${response.statusText}`);
                    }
                    return response.json();
                })

            // 通过 llmClient 发送命令到客户端
            // const result: QueueStatus = await llmClient.sendCommand("poll_tripo3d_job_status", args);

            logger.info(`Received status response from client`, JSON.stringify(result));

            if (result.data.status === 'success') {
                return `✅ 3D model generation completed successfully!\nYou can now import this model using the 'import_generated_asset' tool with the task_id.`
            } else {
                return `⏳ 3D model generation is still ${result.data.status === 'running' ? `in progress (progress:${result.data.progress}%), (running left time:${result.data.running_left_time}s)` : 'queued'}.\nPlease wait and check again in a minute. Most models take 1-5 minutes to generate`
            }
        } catch (e) {
            const errorMessage = `Error checking Tripo3D job status: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    }
};

interface IImportProgress {
    task_id: string;
    modelData: Tripo3DTaskStatusResponse;
    progress: number;
    data?: string;
    error?: Error;
}

const importProgressMap = new Map<string, IImportProgress>();

// 工具: 导入生成的 3D 模型 - 仅传递参数
export const importGeneratedAssetTool = {
    name: 'import_generated_asset',
    description: 'Import a 3D model generated by Tripo3D into the scene',
    parameters: z.object({
        name: z.string().describe('The name to give to the imported object in the scene'),
        task_id: z.string().describe('For FAL_AI mode: The request ID of the completed Tripo3D job'),

        // 添加变换参数
        location: z.array(z.number()).describe('[x, y, z] center position coordinates for the imported model'),
        dimensions: z.array(z.number()).describe('Optional [width, height, depth] absolute dimensions for the imported model'),
        rotation: z.array(z.number()).optional().describe('Optional [x, y, z] rotation in degrees. Following the Z-up coordinate system: rotation around X-axis tilts the object left/right (like nodding sideways), rotation around Y-axis tilts the object forward/backward (like nodding), and rotation around Z-axis rotates the object in the horizontal plane (like spinning on the ground). Positive values follow the right-hand rule: point thumb in positive axis direction, fingers show positive rotation direction.'),
    }),
    execute: async (args, context: Context): Promise<any> => {
        logger.info(`Tool executed: import_generated_asset with name "${args.name}"`);

        try {
            // 检查是否有客户端连接
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn('No modeling software clients connected');
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }

            // 检查是否提供了必要参数
            if (!args.task_id) {
                return "Error: 'task_id' must be provided.";
            }

            const url = `https://api.tripo3d.ai/v2/openapi/task/${args.task_id}`;

            const options = {
                headers: {
                    'Authorization': 'Bearer ' + apiKey
                }
            };

            const result: Tripo3DTaskStatusResponse = await fetch(url, options)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status},info : ${response.statusText}`);
                    }
                    return response.json();
                })


            if (result.data.status !== 'success') {
                return `Task is not completed yet. Current status: ${result.data.status}, progress: ${result.data.progress}%`;
            }

            const modelData = result.data.output;

            if (!modelData.model) {
                return 'Model not found or not yet completed';
            }
            logger.info('Model data:', JSON.stringify(result.data));

            const importUUID = `${Date.now()}`;
            const baseProgressObj: IImportProgress = {
                task_id: args.task_id,
                modelData: result,
                progress: 0,
            }
            importProgressMap.set(importUUID, baseProgressObj);

            setImmediate(async () => {
                try {
                    const { zipBuffer, boundingBox } = await gltf2obj(modelData.model, (progress) => {
                        baseProgressObj.progress = progress;
                    });
                    // 文件转换完成，此时需要执行置入
                    const objectInfo = await llmClient.sendCommand("import_generated_asset", {
                        ...args,
                        zipBuffer: zipBuffer.toString("base64"),
                        boundingBox,
                    });
                    baseProgressObj.data = objectInfo;

                    logger.info("import success:" + objectInfo);
                } catch (e) {
                    baseProgressObj.error = e;
                }
            });

            // args.model = modelData.model;
            // args.model = 'https://qhstaticssl.kujiale.com/application/octetstream/1743496618932/3884A1CACC11ACB5264705935D5F121C.glb'
            // args.model = `http://localhost:${fileProxyInstance.port}/proxy?url="${encodeURIComponent(modelData.model)}"`;
            // 直接使用模型文件转换
            // args.model = `http://localhost:${fileProxyInstance.port}/convert/glb-to-obj?url="${encodeURIComponent(modelData.model)}"`;
            // rendered_image
            logger.info("model url:", args.model);
            const content: any[] = [{
                type: 'text', text: `Import process started with importUUID: ${importUUID}. 
Please use the \`poll_tripo3d_import_progress\` tool with this UUID to monitor the conversion progress and get the final model data when ready. 
Call \`poll_tripo3d_import_progress\` with parameter: { "import_uuid": "${importUUID}" }`
            }];

            if (modelData.rendered_image) {
                content.push(await imageContent({ url: modelData.rendered_image }))
            }

            return {
                content
            }
        } catch (e) {
            const errorMessage = `Error importing generated asset: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    }
};
// 工具: 轮询Tripo3D导入状态
export const pollTripo3DImportStatusTool = {
    name: 'poll_tripo3d_import_status',
    description: 'Query the progress status of importing a Tripo3D-generated 3D model into the Koomaster scene, allowing you to monitor the model conversion and scene placement process',
    parameters: z.object({
        import_uuid: z.string().describe('The unique identifier for the import process to poll'),
    }),
    execute: async (args, context: Context): Promise<string> => {
        logger.info(`Tool executed: poll_tripo3d_import_status with import_uuid "${args.import_uuid}"`);
        try {
            const importUUID = args.import_uuid;

            // 检查UUID是否存在于进度映射中
            if (!importProgressMap.has(importUUID)) {
                return `Error: No import process found with UUID: ${importUUID}`;
            }

            // 获取当前进度信息
            const progressObj = importProgressMap.get(importUUID);

            // 检查是否发生错误
            if (progressObj.error) {
                // 从映射中删除此项目，因为它已完成（出错）
                // importProgressMap.delete(importUUID);
                return `Error during model conversion: ${progressObj.error.message || String(progressObj.error)}`;
            }

            // 检查是否已完成
            if (progressObj.data) {
                // 模型转换已完成，可以获取数据
                return progressObj.data;
            }

            // 如果仍在进行中，返回当前进度
            return `Import process in progress: ${Math.max(0, progressObj.progress - 5)}% complete. Please check again in a few moments.`;

        } catch (e) {
            const errorMessage = `Error polling import status: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    }
};

// 导出所有 Tripo3D 相关工具
export const tripo3dTools = {
    pollTripo3DJobStatusTool,
    importGeneratedAssetTool
};