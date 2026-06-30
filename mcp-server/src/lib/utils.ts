import net from 'net';

// 检查端口是否可用
export async function isPortAvailable(port: number): Promise<boolean> {
    return new Promise((resolve) => {
        const server = net.createServer()
            .once('error', (err: any) => {
                // 如果端口已被占用，会抛出 EADDRINUSE 错误
                if (err.code === 'EADDRINUSE') {
                    resolve(false);
                } else {
                    resolve(false); // 其他错误也视为不可用
                }
            })
            .once('listening', () => {
                // 端口可用，关闭测试服务器
                server.close();
                resolve(true);
            })
            .listen(port);
    });
}

// 查找可用端口
export async function findAvailablePort(startPort: number, maxTries: number = 100): Promise<number> {
    let port = startPort;
    for (let i = 0; i < maxTries; i++) {
        if (await isPortAvailable(port)) {
            return port;
        }
        port++;
    }
    throw new Error(`Could not find available port in range ${startPort} to ${startPort + maxTries - 1}`);
}
