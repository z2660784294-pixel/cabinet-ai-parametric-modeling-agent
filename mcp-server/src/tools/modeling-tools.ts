import { Context } from "../types";
import { z } from "zod";
import logger from "../lib/logger";
import { llmClient } from "../llmClient";
import { parseSvgPath3D } from "./modeling/utils";
import { UserError } from "fastmcp";

export const addFacesTool = {
  name: "add_faces",
  description:
    "Creates new faces in the 3D model using SVG-style path notation. Each face must form a closed planar boundary - all points defining a single face MUST be coplanar (lie exactly on the same plane). IMPORTANT: When a new face intersects or overlaps with existing faces, Koomaster will automatically split those faces, which may cause the original face IDs to change or become invalid. After adding faces that might cause splits, use the 'find_face_by_points' tool to locate the resulting faces by specifying points that lie on them. ",
  parameters: z.object({
    faces: z
      .array(
        z.object({
          path: z
            .string()
            .describe('3D curve path defined using SVG path commands:\n- M x,y,z: Move to initial point\n- L x,y,z: Line to point\n- C cp1x,cp1y,cp1z cp2x,cp2y,cp2z endX,endY,endZ: Cubic Bezier curve with two control points\n- A midX,midY,midZ endX,endY,endZ: Arc defined by three points\n  - Current position is the start point\n  - midX,midY,midZ: A point ON THE ARC between start and end (NOT the center)\n  - endX,endY,endZ: End point of the arc\n- Z: Close path\n\nIMPORTANT NOTES:\n1. The path MUST form a closed shape (use Z command at the end)\n2. All points MUST be coplanar (on the same plane)\n3. The arc command uses a custom 3-point format (not standard SVG arc)\n4. For arcs, the three points must not be collinear\n5. For a circle, use 3-4 arcs connecting points along the circumference\n\nEXAMPLES:\n- Square: "M 0,0,0 L 100,0,0 L 100,100,0 L 0,100,0 Z"\n- Rectangle with rounded corner: "M 0,0,0 L 100,0,0 L 100,80,0 A 90,90,0 80,100,0 L 0,100,0 Z"\n- Circle approximation: "M 100,0,0 A 70.7,70.7,0 0,100,0 A -70.7,70.7,0 -100,0,0 A -70.7,-70.7,0 0,-100,0 A 70.7,-70.7,0 100,0,0 Z"\n- Curved path: "M 0,0,0 C 30,10,0 60,30,0 100,0,0 L 100,100,0 L 0,100,0 Z"'),
        })
      )
      .min(1)
      .describe(
        "An array of face definitions, each with an SVG-style path string that defines a closed, planar boundary. Multiple faces can be created in a single operation. Each created face will receive a unique ID that can be used in other operations."
      ),
  }),
  execute: async (args, context: Context): Promise<string> => {
    if (!llmClient.hasConnectedKoomasterClients()) {
      logger.warn("No clients connected when attempting to add faces");
      return "No modeling software clients connected. Please start the software and connect to this server.";
    }

    try {
      const processedArgs = {
        faces: args.faces.map(face => {
          try {
            // 解析SVG路径字符串
            const pathCurves = parseSvgPath3D(face.path);
            return {
              // faceName: face.faceName,
              path: pathCurves
            };
          } catch (parseError) {
            throw new Error(`Error parsing SVG path for face "${face.path}": ${parseError instanceof Error ? parseError.message : String(parseError)}`);
          }
        })
      };

      const result = await llmClient.sendCommand("add_faces", processedArgs);

      return result;
    } catch (e) {
      const errorMessage = `Error adding faces: ${e instanceof Error ? e.message : String(e)}`;
      logger.error(errorMessage);
      context.log.error(errorMessage);
      return `Failed to create faces: ${e instanceof Error ? e.message : String(e)}. Common issues include:
- Non-coplanar points: All points defining a face MUST lie exactly on the same plane
- Path does not form a closed loop (ensure it ends with Z command)
- Invalid arc definition (check A command parameters)
- Self-intersecting boundaries
- Invalid SVG path syntax
- Missing or incorrect coordinates`;
    }
  },
};
export const getFacePathTool = {
  name: "get_face_path",
  description:
    "Retrieves the SVG-style path representation of a face's boundary. This tool extracts the geometric outline of a face and returns it as a path string that can be used for visualization or further operations. The path includes all curves that form the outer boundary of the face.",
  parameters: z.object({
    name: z
      .string()
      .describe(
        'ID of the face to extract the path from. You can obtain this ID by: 1) Using get_selection with type="face" to get a user-selected face, 2) Creating a new face with add_faces and using the returned face ID, or 3) Using find_face_by_points tool to locate a face when model geometry has been modified or split.'
      ),
  }),
  execute: async (args, context: Context): Promise<string> => {
    try {
      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(`No clients connected when attempting to get face path`);
        throw new UserError("No modeling software clients connected. Please start the software and connect to this server.");
      }

      const result = await llmClient.sendCommand("get_face_path", args);
      return result;
    } catch (e) {
      const errorMessage = `Error retrieving face path: ${e instanceof Error ? e.message : String(e)
        }`;
      logger.error(errorMessage);
      context.log.error(errorMessage);
      return errorMessage;
    }
  },
};

export const pullFacesTool = {
  name: "pull_faces",
  description:
    "Performs a push/pull operation on one or more faces to create or modify 3D shapes. This tool allows you to extrude faces along their normal direction to add or remove volume from a model.",
  parameters: z.object({
    faceNames: z
      .array(z.string())
      .min(1)
      .describe(
        'Array of face names to push/pull. These should be the face identifiers that you want to extrude. You can get face names from previously created faces, by using tools that provide model information, or specifically by using the "find_face_by_points" tool to locate faces when model geometry has been modified or split.'
      ),
    distance: z
      .number()
      .describe(
        "The distance to push/pull the face(s), measured in model units. Use positive values to extrude outward (adding volume) or negative values to extrude inward (removing volume if possible)."
      ),
    separator: z
      .boolean()
      .describe(
        "Whether to keep the original face(s) unchanged. If true, a new face will be created at the end of the extrusion while preserving the original face. If false, the original face will be moved to the new position."
      ),
  }),
  execute: async (args, context: Context): Promise<string> => {
    try {
      if (!llmClient.hasConnectedKoomasterClients()) {
        logger.warn(`No clients connected when attempting to pull faces`);
        return "No modeling software clients connected. Please start the software and connect to this server.";
      }

      const result = await llmClient.sendCommand("pull_faces", args);

      return result;
    } catch (e) {
      const errorMessage = `Error during push/pull operation: ${e instanceof Error ? e.message : String(e)
        }`;
      logger.error(errorMessage);
      context.log.error(errorMessage);
      return errorMessage;
    }
  },
};