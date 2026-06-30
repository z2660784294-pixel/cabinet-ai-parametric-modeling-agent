import { Context } from "../../types";
import { z } from "zod";
import logger from "../../lib/logger";
import { llmClient } from "../../llmClient";

// Tool: Sweep Face Along Auxiliary Curves
export const sweepTool = {
    name: 'sweep',
    description: 'Creates a 3D solid by sweeping a FACE along auxiliary curves. NOTE: This tool operates ONLY on faces, not on entire objects or groups. The face can be either selected by the user or created programmatically. IMPORTANT: The face being swept (profile) must NOT be parallel to the auxiliary curves (path) - the sweep direction must have some component perpendicular to the face normal for the operation to succeed. After the sweep operation completes, the original face (profile) will be automatically deleted from the model. If you need to perform multiple sweep operations with the same profile, you will need to recreate the face after each sweep operation using add_faces or other face creation methods.',
    parameters: z.object({
        face_id: z.string()
            .describe('ID of the face to sweep. You can obtain this ID by: 1) Using get_selection with type="face" to get a user-selected face, 2) Creating a new face with add_faces and using the returned face ID, or 3) Using find_face_by_points tool to locate a face when model geometry has been modified or split. IMPORTANT: The face being swept (profile) must NOT be parallel to the auxiliary curves (path) - there must be some angle between the face normal and the path direction, otherwise the sweep operation will fail.'),
        auxiliary_curve_ids: z.array(z.string())
            .describe('IDs of auxiliary curves to use as the sweep path. Obtain these either from user-selected curves (get_selection) or by creating new curves (create_auxiliary_curve). IMPORTANT: The curves must connect end-to-end in a continuous path (each curve must start where the previous one ends), though they do not need to form a closed loop. Disconnected curves will cause the sweep operation to fail.'),
    }),
    execute: async (args, context: Context): Promise<string> => {
        logger.info(`Tool executed: sweep with face_id "${args.face_id}" and auxiliary curve IDs ${JSON.stringify(args.auxiliary_curve_ids)}`);
        try {
            // Check if any modeling software clients are connected
            if (!llmClient.hasConnectedKoomasterClients()) {
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }

            // Validate parameters
            if (!args.face_id) {
                return `Error: You must provide a face_id to sweep. You can:

1. Ask the user to select a face in the scene, then use get_selection tool with type="face" to obtain the ID of the selected face, OR
2. Create a new face using the add_faces tool and use the returned face ID.`;
            }

            if (!args.auxiliary_curve_ids || args.auxiliary_curve_ids.length === 0) {
                return `Error: You must provide at least one auxiliary curve ID for the sweep path. Follow these steps:

1. First use get_selection to check if the user has already selected any auxiliary curves.
2. If no auxiliary curves are selected, create them using the create_auxiliary_curve tool with a 3D path.
3. Once you have the auxiliary curve IDs (either from get_selection or create_auxiliary_curve), use them in this tool.

Example workflow:
- Get face ID: either get_selection with type="face" or create with add_faces
- Get curve IDs: either get_selection or create_auxiliary_curve
- Sweep: use this tool with the obtained face_id and auxiliary_curve_ids`;
            }

            // Send the sweep command
            const result = await llmClient.sendCommand('sweep', args);

            // Return success message with information from the result
            return `${result}
The sweep operation used face ${args.face_id} and swept it along the path defined by auxiliary curve(s): ${args.auxiliary_curve_ids.join(', ')}.
`;
            // Note: To see the result, use the get_scene_screenshot tool to capture an image of the scene.
        } catch (e) {
            const errorMessage = `Error creating swept object: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    }
};