import { Context } from '../types';
import { z } from 'zod';
import logger from '../lib/logger';
import { llmClient } from '../llmClient';

export const getMaterialNames = {
    name: 'get_material_names',
    description: 'Retrieves a list of all available material names from the connected connected koomaster client. This function queries the active connection to obtain the names of all materials that can be applied to 3D models. Returns the complete list of material names as a string, with materials typically separated by a delimiter. Useful for discovering what materials are available before applying them to specific models.',
    parameters: z.object({}),
    execute: async (args, context: Context): Promise<string> => {

        try {
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn(`No clients connected when attempting to set material for model "${args.modelName}"`);
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }

            const result = await llmClient.sendCommand("get_material_names");

            return result;

        } catch (e) {
            const errorMessage = `Error setting material for model "${args.modelName}": ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return `Error setting material: ${e instanceof Error ? e.message : String(e)}`;
        }
    }
};

export const setFaceMaterialTool = {
    name: 'set_face_material',
    description: 'Applies a specific material to an existing face in the 3D model. This tool allows you to change the appearance of a face by assigning a different material to it.',
    parameters: z.object({
        faceName: z.string().describe('The name of the face to apply material to. This should be the full face name (e.g., "face_wall1"). You can get face names from previously created faces or by using tools that provide model information.'),
        materialName: z.string().describe('The name of the material to apply to the face. Use the get_material_names function first to retrieve a list of all available materials in the current scene. Only materials returned by get_material_names can be successfully applied.')
    }),
    execute: async (args, context: Context): Promise<string> => {
        try {
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn(`No clients connected when attempting to set material for face "${args.faceName}"`);
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }

            const result = await llmClient.sendCommand("set_face_material", args);

            return result;
        } catch (e) {
            const errorMessage = `Error setting material for face "${args.faceName}": ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);

            if (String(e).includes("Face not found")) {
                return `Error: Face "${args.faceName}" not found in the model. Please verify the face name is correct and that the face exists.`;
            } else if (String(e).includes("Material not found")) {
                return `Error: Material "${args.materialName}" not found. Use the get_material_names function to see available materials.`;
            }

            return errorMessage;
        }
    }
};

export const setGroupMaterialTool = {
    name: 'set_group_material',
    description: 'Applies a specific material to an entire group of objects in the 3D model. This tool changes the appearance of all elements within the named group by assigning a different material to them.',
    parameters: z.object({
        modelName: z.string().describe('The name of the group or model to apply material to. This should be the name you assigned when creating the group or importing the model. You can get model names using tools that provide scene information.'),
        materialName: z.string().describe('The name of the material to apply to the entire group. Use the get_material_names function first to retrieve a list of all available materials in the current scene. Only materials returned by get_material_names can be successfully applied.')
    }),
    execute: async (args, context: Context): Promise<string> => {
        try {
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn(`No clients connected when attempting to set material for group "${args.modelName}"`);
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }

            const result = await llmClient.sendCommand("set_group_material", args);

            return result;
        } catch (e) {
            const errorMessage = `Error setting material for group "${args.modelName}": ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    }
};