import { Context } from "../../types";
import { z } from "zod";
import logger from "../../lib/logger";
import { llmClient } from "../../llmClient";

export const findFaceByMultiplePointsTool = {
    name: "find_face_by_points",
    description:
        "Finds a face by specifying multiple points that lie on the face. By providing 1-5 points that lie on the target face, you can identify faces reliably even when topology changes occur.  Returns the face's information including its ID, normal vector, area, and other properties.",
    parameters: z.object({
        points: z.array(
            z.object({
                x: z.number().describe("X coordinate of a point on the face"),
                y: z.number().describe("Y coordinate of a point on the face"),
                z: z.number().describe("Z coordinate of a point on the face"),
            })
        ).min(1).max(5)
            .describe("Array of points that lie on the face you want to find. More points increase finding accuracy."),
        tolerance: z.number().positive().optional().default(0.001)
            .describe("Maximum distance between points and face for matching to occur (default: 0.001 model units)")
    }),
    execute: async (args, context: Context): Promise<string> => {
        try {
            if (!llmClient.hasConnectedKoomasterClients()) {
                logger.warn(`No clients connected when attempting to find face by points`);
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }
            const result = await llmClient.sendCommand("find_face_by_points", args);
            return result;
        } catch (e) {
            const errorMessage = `Error during face finding by points: ${e instanceof Error ? e.message : String(e)
                }`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    },
};