import { Context } from '../types';
import { z } from 'zod';
import logger from '../lib/logger';
import { llmClient } from '../llmClient';
import { imageContent, ContentResult, UserError, ImageContent } from 'fastmcp';

export const searchKjlAssetsTool = {
    name: 'search_kjl_assets',
    description: 'Searches for 3D models and assets in the KJL(酷家乐) database based on a text description. Returns a list of models that match the search criteria, including their names, IDs, categories, and dimensions.',
    parameters: z.object({
        description: z.string().describe('用于搜索的中文文本描述。必须使用中文关键词进行搜索以获得最佳结果。可以是物体类型（如"椅子"、"桌子"、"灯"）、风格（如"现代"、"传统"）或其他描述性术语。越具体的中文查询词（如"现代皮革办公椅"而非简单的"椅子"）会产生更精确的结果。')
    }),
    execute: async (args, context: Context): Promise<ContentResult> => {
        try {
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn(`No clients connected when attempting to search for assets`);
                throw new UserError("No modeling software clients connected. Please start the software and connect to this server.");
            }
            // context.reportProgress({
            //     progress: 10,
            //     total: 100,
            // });
            const result = await llmClient.sendCommand("search_kjl_assets", args);

            // context.reportProgress({
            //     progress: 100,
            //     total: 100,
            // });
            return result;
        } catch (e) {
            const errorMessage = `Error searching for KJL assets: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return {
                content: [
                    {
                        text: errorMessage,
                        type: "text"
                    }
                ],
                isError: true
            };
        }
    }
};

export const batchSearchKjlAssetsTool = {
    name: 'batch_search_kjl_assets',
    description: 'Performs a concurrent batch search for multiple 3D models and assets in the KJL(酷家乐) database. Returns a combined list of models that match each search term, including their names, IDs, categories, and dimensions. Use this when you need to search for multiple different types of models at once.',
    parameters: z.object({
        descriptions: z.array(z.string()).describe('An array of Chinese text descriptions to search for. Each description must use Chinese keywords for best results. Can include object types (like "椅子", "桌子", "灯"), styles (like "现代", "传统"), or other descriptive terms. More specific Chinese queries (like "现代皮革办公椅" instead of just "椅子") will yield more precise results.')
    }),
    execute: async (args, context: Context): Promise<any> => {
        try {
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn(`No clients connected when attempting to batch search for assets`);
                throw new UserError("No modeling software clients connected. Please start the software and connect to this server.");
            }
            // Create an array of promises for concurrent execution
            const searchPromises = args.descriptions.map(description =>
                llmClient.sendCommand("search_kjl_assets", { description })
                    .then(result => ({
                        searchTerm: description,
                        results: result
                    }))
            );

            // Execute all searches concurrently
            const results = await Promise.all(searchPromises);

            // Combine the results into a single response
            const combinedResults = results.map(item =>
                `=== Search Results for "${item.searchTerm}" ===\n${item.results}\n`
            ).join('\n');

            const note = `Note about dimensions: The dimensions (x, y, z) show the model's default orientation. For example, a cabinet with larger x than y typically has its front facing the y direction and is wider along x. Consider these proportions when rotating models for proper placement. Use place_kjl_asset with the model ID to add items to your scene.`;

            // context.reportProgress({
            //     progress: 100,
            //     total: 100,
            // });

            return `${combinedResults}\n\n${note}`;
        } catch (e) {
            const errorMessage = `Error performing batch search for KJL assets: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return {
                content: [
                    {
                        text: errorMessage,
                        type: "text"
                    }
                ],
                isError: true
            };
        }
    }
};

export const getKjlAssetSnapshotTool = {
    name: 'get_kjl_asset_snapshot',
    description: 'Retrieves a preview image for a specific KJL(酷家乐) asset model based on its model ID. This helps visualize the asset before placing it in the scene. Use this tool to examine the appearance and style of a model to ensure it matches your design requirements.',
    parameters: z.object({
        modelId: z.number().describe('The unique ID of the KJL asset model for which to retrieve the preview image. This ID can be obtained from the batch_search_kjl_assets function results.')
    }),
    execute: async (args, context: Context): Promise<ImageContent | ContentResult> => {
        try {
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn(`No clients connected when attempting to get KJL asset snapshot`);
                throw new UserError("No modeling software clients connected. Please start the software and connect to this server.");
            }
            const result = await llmClient.sendCommand("get_kjl_asset_snapshot", args);

            // If the result is a URL, return a formatted message with the URL
            // if (typeof result === 'string' && (result.startsWith('http://') || result.startsWith('https://'))) {
            //     return `Preview image for model ID ${args.modelId} is available at: ${result}`;
            // }

            return await imageContent({
                url: result
            });
        } catch (e) {
            const errorMessage = `Error retrieving KJL asset snapshot: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return {
                content: [
                    {
                        text: errorMessage,
                        type: "text"
                    }
                ],
                isError: true
            };
        }
    }
};

export const batchGetKjlAssetSnapshotTool = {
    name: 'batch_get_kjl_asset_snapshot',
    description: 'Retrieves preview images for multiple KJL(酷家乐) asset models concurrently based on their model IDs. This helps visualize multiple assets before placing them in the scene. Use this tool to efficiently examine the appearance and style of several models at once to ensure they match your design requirements.',
    parameters: z.object({
        modelIds: z.array(z.number()).describe('An array of unique IDs of the KJL asset models for which to retrieve preview images. These IDs can be obtained from the batch_search_kjl_assets function results.')
    }),
    execute: async (args, context: Context): Promise<ContentResult> => {
        try {
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn(`No clients connected when attempting to batch get KJL asset snapshots`);
                throw new UserError("No modeling software clients connected. Please start the software and connect to this server.");
            }

            // Create an array of promises for concurrent execution
            const snapshotPromises = args.modelIds.map(modelId =>
                llmClient.sendCommand("get_kjl_asset_snapshot", { modelId })
                    .then(async (result) => {
                        try {
                            // Create image content for each snapshot
                            const content = await imageContent({
                                url: result
                            });

                            return {
                                modelId,
                                imageContent: content,
                                success: true
                            };
                        } catch (error) {
                            return {
                                modelId,
                                error: `Failed to get image for model ID ${modelId}: ${error.message}`,
                                success: false
                            };
                        }
                    })
            );

            // Execute all snapshot retrievals concurrently
            const results = await Promise.all(snapshotPromises);

            // Convert results into content array
            const contents = [];

            // First add a header text
            contents.push({
                text: `Preview images for ${args.modelIds.length} model(s):`,
                type: "text"
            });

            // Add all successful images and error messages
            for (const result of results) {
                if (result.success) {
                    // Add a label for the image
                    contents.push({
                        text: `Model ID: ${result.modelId}`,
                        type: "text"
                    });

                    // Add the image content
                    contents.push(result.imageContent);
                } else {
                    // Add error message
                    contents.push({
                        text: result.error,
                        type: "text"
                    });
                }
            }

            return {
                content: contents
            };
        } catch (e) {
            const errorMessage = `Error batch retrieving KJL asset snapshots: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return {
                content: [
                    {
                        text: errorMessage,
                        type: "text"
                    }
                ],
                isError: true
            };
        }
    }
};

export const placeKjlAssetTool = {
    name: 'place_kjl_asset',
    description: 'Places a 3D model from the KJL(酷家乐) asset library into the current scene with specified position, rotation, and scale. Before placing, analyze the model\'s bounding box dimensions to determine proper orientation - elongated objects like wall panels may require 90° rotation based on intended function. Ensure bottoms align with the ground plane (z=0) by setting z-value to half the model\'s height. After placement, verify no clipping with existing objects and confirm dimensions match real-world proportions.',
    parameters: z.object({
        modelId: z.number().describe('The unique ID of the model to place. This ID can be obtained from the batch_search_kjl_assets function results. Use the exact ID value returned by the search.'),
        name: z.string().describe('Specify a name for the placed model. This name will be used for subsequent identification and reference to the model, such as when applying materials or performing transformation operations. Use descriptive names for easy identification, such as "dining_table", "office_chair", etc.'),
        originalDimensions: z.array(z.number()).describe('The original [width, height, depth] dimensions of the model as provided in the batch_search_kjl_assets results. These values must be obtained from the asset search results.'),

        // 添加变换参数
        location: z.array(z.number()).describe('[x, y, z] center position coordinates for the imported model'),
        targetDimensions: z.array(z.number()).describe('The target [width, height, depth] dimensions for the model after importing. These values specify the absolute size the model should be scaled to in the scene.'),
        rotation: z.array(z.number()).optional().describe('Optional [x, y, z] rotation in degrees. Following the Z-up coordinate system: rotation around X-axis tilts the object left/right (like nodding sideways), rotation around Y-axis tilts the object forward/backward (like nodding), and rotation around Z-axis rotates the object in the horizontal plane (like spinning on the ground). Positive values follow the right-hand rule: point thumb in positive axis direction, fingers show positive rotation direction.'),
    }),
    execute: async (args, context: Context): Promise<ContentResult> => {
        try {
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn(`No clients connected when attempting to place KJL asset`);
                throw new UserError("No modeling software clients connected. Please start the software and connect to this server.");
            }

            // context.reportProgress({
            //     progress: 30,
            //     total: 100,
            // });

            const result = await llmClient.sendCommand("place_kjl_asset", args);

            // context.reportProgress({
            //     progress: 100,
            //     total: 100,
            // });
            return result;
        } catch (e) {
            const errorMessage = `Error placing KJL asset: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return {
                content: [
                    {
                        text: errorMessage,
                        type: "text"
                    }
                ],
                isError: true
            };
        }
    }
};

export const replaceKjlAssetTool = {
    name: 'replace_kjl_asset',
    description: 'Replaces an existing object in the scene with a new 3D model from the KJL(酷家乐) asset library. The replacement maintains the position, rotation, aligning the centers of both models. After replacement, review the scene to ensure no intersections or clipping with other objects.',
    parameters: z.object({
        targetName: z.string().describe('The name of the existing object in the scene that will be replaced. This must exactly match the name of a placed object.'),
        newModelId: z.number().describe('The unique ID of the new model that will replace the existing object. This ID should be obtained from the batch_search_kjl_assets function results.'),
        newName: z.string().describe('Specify a name for the replacement model. This name will be used for subsequent identification and reference, such as when applying materials or performing transformation operations. Use descriptive names for easy identification.'),
        originalDimensions: z.array(z.number()).describe('The original [width, height, depth] dimensions of the new model as provided in the batch_search_kjl_assets results. These values must be obtained from the asset search results.'),
        targetDimensions: z.array(z.number()).optional().describe('The target [width, height, depth] dimensions for the model after importing. These values specify the absolute size the model should be scaled to in the scene.'),
    }),
    execute: async (args, context: Context): Promise<ContentResult> => {
        try {
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn(`No clients connected when attempting to replace KJL asset`);
                throw new UserError("No modeling software clients connected. Please start the software and connect to this server.");
            }

            const result = await llmClient.sendCommand("replace_kjl_asset", args);

            return result;
        } catch (e) {
            const errorMessage = `Error replacing KJL asset: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return {
                content: [
                    {
                        text: errorMessage,
                        type: "text"
                    }
                ],
                isError: true
            };
        }
    }
};