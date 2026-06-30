import { Context } from "../../types";
import { z } from "zod";
import logger from "../../lib/logger";
import { llmClient } from "../../llmClient";
import { parseSvgPath3D } from "./utils";

export const createAuxiliaryCurve = {
    name: 'create_auxiliary_curve',
    description: 'Creates an auxiliary 3D curve using SVG-like path commands with explicit 3D coordinates. Auxiliary curves can be used for sweep operations, as guides, or for visualization purposes.',
    parameters: z.object({
        path: z.string().describe('3D curve path defined using SVG path commands:\n- M x,y,z: Move to initial point\n- L x,y,z: Line to point\n- C cp1x,cp1y,cp1z cp2x,cp2y,cp2z endX,endY,endZ: Cubic Bezier curve with two control points\n- A midX,midY,midZ endX,endY,endZ: Arc defined by three points\n  - Current position is the start point\n  - midX,midY,midZ: A point ON THE ARC between start and end (NOT the center)\n  - endX,endY,endZ: End point of the arc\n- Z: Close path (optional for auxiliary curves)\n\nIMPORTANT NOTES:\n1. CRITICAL: For Bezier curves (C command), ALL POINTS (start, control points, and end) MUST be coplanar (lie on the same plane). Non-planar Bezier curves will fail to create\n2. Unlike faces, auxiliary curves as a whole do NOT need to be closed or planar\n3. For connected curve segments used in sweep operations, ensure endpoints match exactly\n4. The arc command uses a custom 3-point format (not standard SVG arc)\n5. For arcs, the three points must not be collinear\n6. For a circle, use 3-4 arcs connecting points along the circumference\n\nEXAMPLES:\n- Straight line: "M 0,0,0 L 100,0,0"\n- Polyline: "M 0,0,0 L 50,50,50 L 100,0,100"\n- Arc: "M 0,0,0 A 50,50,50 100,0,0"\n- Planar Bezier curve: "M 0,0,0 C 25,25,0 75,75,0 100,100,0" (note all z-values are 0, ensuring coplanarity)\n- Closed shape: "M 0,0,0 L 100,0,0 L 100,100,0 L 0,100,0 Z"\n- Complex path (arcs and lines): "M 0,0,0 L 100,0,0 A 150,50,0 200,0,0 L 200,100,0 L 0,100,0 Z"'),
    }),
    execute: async (args, context: Context): Promise<string> => {
        logger.info(`Tool executed: create_auxiliary_curve with path "${args.path}" and name "${args.name}"`);
        try {
            // Check if any modeling software clients are connected
            if (!llmClient.hasConnectedKoomasterClients()) {
                return "No modeling software clients connected. Please start the software and connect to this server.";
            }

            // Parse the SVG path into 3D curve segments
            try {
                // Parse the path
                const pathCurves = parseSvgPath3D(args.path);

                // Send the command to create the auxiliary curve
                const result = await llmClient.sendCommand('create_auxiliary_curve', {
                    ...args,
                    path: pathCurves,
                });

                return result;
            } catch (parseError) {
                return `Error parsing SVG path: ${parseError instanceof Error ? parseError.message : String(parseError)}`;
            }

        } catch (e) {
            const errorMessage = `Error creating auxiliary curve: ${e instanceof Error ? e.message : String(e)}`;
            logger.error(errorMessage);
            context.log.error(errorMessage);
            return errorMessage;
        }
    }
};
