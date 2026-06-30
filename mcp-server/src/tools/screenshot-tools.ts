import { Context } from "../types";
import { z } from "zod";
import logger from "../lib/logger";
import { llmClient } from "../llmClient";

export const getObjectsScreenshotTool = {
    name: 'get_objects_screenshot',
    description: 'Captures a screenshot of the specific objects from different view angles. Note: Only supports KJL models, Tripo3D models, and basic geometric shapes - face screenshots are not supported.',
    parameters: z.object({
        view_angle: z.enum(['front', 'back', 'left', 'right', 'top', 'bottom']).default('top')
            .describe('Camera angle for the screenshot. Options: standard orthographic views (front, back, left, right, top, bottom) .'),
        groupNames: z.array(z.string())
            .describe('array of group names to capture.')
    }),
    execute: async (args, context: Context): Promise<any> => {
        logger.info(`Tool executed: get_scene_screenshot with view_angle "${args.view_angle}"`);
        try {
            // Check if any modeling software clients are connected
            if (!llmClient.hasConnectedKoomasterClients()) {
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }

            // Capture the screenshot using getModelSnapshot
            const result = await llmClient.sendCommand('get_objects_screenshot', args);

            if (!result) {
                return "Failed to capture screenshot.";
            }

            if (!result.startsWith("data:")) {
                return result;
            }

            let base64Data = result;
            // Extract base64 data if it includes data URL format (data:image/png;base64,)
            if (base64Data.includes(',')) {
                base64Data = base64Data.split(',')[1];
            }

            return {
                content: [
                    {
                        type: "image",
                        data: base64Data,
                        mimeType: "image/png",
                    },
                ],
            };
        } catch (e) {
            const errorMessage = `Error capturing screenshot: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    }
};

export const getSceneScreenshotTool = {
    name: 'get_scene_screenshot',
    description: 'Captures a screenshot of the entire 3D scene from the specified view angle. Note: the screenshot result may appear upside-down compared to the actual scene orientation.',
    parameters: z.object({
        view_angle: z.enum(['front', 'back', 'left', 'right', 'top', 'bottom', 'auto']).default('auto')
            .describe('Camera angle for the screenshot. Standard orthographic views available, or select "auto" to automatically calculate an optimal angle that includes all objects in the scene. The "auto" view positions the camera at a diagonal angle (from the top-right-front quadrant) to provide a comprehensive overview of the scene.'),
    }),
    execute: async (args, context: Context): Promise<any> => {
        logger.info(`Tool executed: get_scene_screenshot with view_angle "${args.view_angle}"`);
        try {
            // Check if any modeling software clients are connected
            if (!llmClient.hasConnectedKoomasterClients()) {
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }

            // Capture the screenshot using getModelSnapshot
            const result = await llmClient.sendCommand('get_scene_screenshot', args);

            if (!result) {
                return "Failed to capture screenshot.";
            }

            if (!result.startsWith("data:")) {
                return result;
            }

            let base64Data = result;
            // Extract base64 data if it includes data URL format (data:image/png;base64,)
            if (base64Data.includes(',')) {
                base64Data = base64Data.split(',')[1];
            }

            return {
                content: [
                    {
                        type: "image",
                        data: base64Data,
                        mimeType: "image/png",
                    },
                ],
            };
        } catch (e) {
            const errorMessage = `Error capturing screenshot: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    }
};

