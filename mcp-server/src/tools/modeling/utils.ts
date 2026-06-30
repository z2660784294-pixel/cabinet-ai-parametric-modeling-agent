
export function parseSvgPath3D(pathString: string) {
    // 移除多余空格并标准化
    const normalizedPath = pathString.trim().replace(/\s+/g, ' ');
    // 用于存储解析后的路径段
    const pathSegments = [];
    // 当前点的位置
    let currentX = 0, currentY = 0, currentZ = 0;
    // 记录路径起始点，用于闭合路径
    let startX = 0, startY = 0, startZ = 0;
    // 辅助函数：解析坐标字符串为数字数组
    const parseCoords = (coordStr: string): number[] => {
        // Replace commas with spaces, then split by spaces and filter out empty strings
        return coordStr.replace(/,/g, ' ')
            .split(/\s+/)
            .filter(s => s.length > 0)
            .map(coord => parseFloat(coord.trim()));
    };

    // 将路径字符串分解为命令和参数 - 只关注M, L, C, A, Z命令
    const tokens = normalizedPath.match(/([MLCAZmlcaz])\s*([^MLCAZmlcaz]*)/g) || [];

    for (const token of tokens) {
        const command = token[0].toUpperCase();
        const paramsStr = token.substring(1).trim();

        switch (command) {
            case 'M': // 移动到
                {
                    const coords = parseCoords(paramsStr);
                    if (coords.length !== 3) {
                        throw new Error(`Invalid M command. Expected 3 coordinates, got ${coords.length}.`);
                    }
                    currentX = coords[0];
                    currentY = coords[1];
                    currentZ = coords[2];
                    // 记录起始点，用于Z命令
                    startX = currentX;
                    startY = currentY;
                    startZ = currentZ;
                }
                break;

            case 'L': // 线段
                {
                    const coords = parseCoords(paramsStr);
                    if (coords.length !== 3) {
                        throw new Error(`Invalid L command. Expected 3 coordinates, got ${coords.length}.`);
                    }
                    // 创建线段
                    pathSegments.push({
                        type: 'line',
                        startPoint: [currentX, currentY, currentZ],
                        endPoint: [coords[0], coords[1], coords[2]]
                    });
                    // 更新当前点
                    currentX = coords[0];
                    currentY = coords[1];
                    currentZ = coords[2];
                }
                break;

            case 'C': // 三次贝塞尔曲线
                {
                    const coords = parseCoords(paramsStr);
                    if (coords.length !== 9) {
                        throw new Error(`Invalid C command. Expected 9 coordinates (3 points), got ${coords.length}.`);
                    }

                    // 创建3D贝塞尔曲线
                    pathSegments.push({
                        type: 'bezier',
                        startPoint: [currentX, currentY, currentZ],
                        controlPoint1: [coords[0], coords[1], coords[2]],
                        controlPoint2: [coords[3], coords[4], coords[5]],
                        endPoint: [coords[6], coords[7], coords[8]]
                    });

                    // 更新当前点为终点
                    currentX = coords[6];
                    currentY = coords[7];
                    currentZ = coords[8];
                }
                break;

            case 'A': // 通过三点定义的圆弧
                {
                    // A midX,midY,midZ endX,endY,endZ
                    const coords = parseCoords(paramsStr);
                    if (coords.length !== 6) {
                        throw new Error(`Invalid A command. Expected 6 coordinates, got ${coords.length}.`);
                    }
                    const midX = coords[0];
                    const midY = coords[1];
                    const midZ = coords[2];
                    const endX = coords[3];
                    const endY = coords[4];
                    const endZ = coords[5];
                    // 起点(当前位置)
                    const startPoint = [currentX, currentY, currentZ];
                    // 弧上的中间点
                    const midPoint = [midX, midY, midZ];
                    // 终点
                    const endPoint = [endX, endY, endZ];
                    // 检查三点是否共线
                    const isCollinear = checkCollinear(startPoint, midPoint, endPoint);
                    if (isCollinear) {
                        // 如果共线，改为创建线段
                        pathSegments.push({
                            type: 'line',
                            startPoint: startPoint,
                            endPoint: endPoint
                        });
                    } else {
                        // 创建圆弧
                        pathSegments.push({
                            type: 'arc',
                            startPoint: startPoint,
                            centerPoint: midPoint, // 这是弧上的中点
                            endPoint: endPoint
                        });
                    }
                    // 更新当前点
                    currentX = endX;
                    currentY = endY;
                    currentZ = endZ;
                }
                break;

            case 'Z': // 闭合路径
                // 添加一个线段闭合路径
                if (
                    Math.abs(currentX - startX) > 0.0001 ||
                    Math.abs(currentY - startY) > 0.0001 ||
                    Math.abs(currentZ - startZ) > 0.0001
                ) {
                    pathSegments.push({
                        type: 'line',
                        startPoint: [currentX, currentY, currentZ],
                        endPoint: [startX, startY, startZ]
                    });
                }
                // 更新当前点为起始点
                currentX = startX;
                currentY = startY;
                currentZ = startZ;
                break;

            default:
                throw new Error(`Unsupported path command: ${command}. Only M, L, C, A, and Z commands are supported.`);
        }
    }

    return pathSegments;
}

// 检查三点是否共线
function checkCollinear(p1, p2, p3, tolerance = 0.0001) {
    // 计算向量p1->p2和p1->p3
    const v1 = [p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]];
    const v2 = [p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]];

    // 计算向量的叉积
    const cross = [
        v1[1] * v2[2] - v1[2] * v2[1],
        v1[2] * v2[0] - v1[0] * v2[2],
        v1[0] * v2[1] - v1[1] * v2[0]
    ];

    // 计算叉积的大小
    const crossLength = Math.sqrt(cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2]);

    // 计算向量v1和v2的长度
    const v1Length = Math.sqrt(v1[0] * v1[0] + v1[1] * v1[1] + v1[2] * v1[2]);
    const v2Length = Math.sqrt(v2[0] * v2[0] + v2[1] * v2[1] + v2[2] * v2[2]);

    // 计算sin值，如果接近0则三点共线
    const sinValue = crossLength / (v1Length * v2Length);

    return sinValue < tolerance;
}
