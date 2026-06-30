import { getActiveBridges } from '../lib/wsbridge/lock';
import * as http from 'http';

interface StatusOptions {
    portOnly?: boolean;
    asUrl?: boolean;
}

export async function getServerStatus(options: StatusOptions = {}): Promise<void> {
    const activeBridges = getActiveBridges();

    if (activeBridges.length === 0) {
        if (!options.portOnly) {
            console.log('No KooMaster MCP servers are currently running.');
        }
        process.exit(0);
        return;
    }

    // 如果只需要输出端口信息
    if (options.portOnly) {
        const port = activeBridges[0].port;
        if (options.asUrl) {
            console.log(`ws://localhost:${port}`);
        } else {
            console.log(port);
        }
        return;
    }

    // 输出详细状态信息
    console.log('Active KooMaster MCP servers:');

    for (const bridge of activeBridges) {
        console.log(`\nPID: ${bridge.pid}, Port: ${bridge.port}`);
        console.log(`WebSocket URL: ws://localhost:${bridge.port}`);

        // 尝试获取更多状态信息
        try {
            const status = await fetchBridgeStatus(bridge.port);
            if (status) {
                console.log('Status:', status.status);
                console.log('Connected clients:');
                console.log(`  Total: ${status.clients.total}`);
                console.log(`  MCP: ${status.clients.mcp}`);
                console.log(`  Koomaster: ${status.clients.koomaster}`);
            }
        } catch (error) {
            console.log('Status: Unable to fetch detailed status');
        }
    }
}

// 从桥接服务器获取状态信息
async function fetchBridgeStatus(port: number): Promise<any> {
    return new Promise((resolve, reject) => {
        const req = http.get(`http://localhost:${port}/bridge-status`, (res) => {
            let data = '';

            res.on('data', (chunk) => {
                data += chunk;
            });

            res.on('end', () => {
                try {
                    const status = JSON.parse(data);
                    resolve(status);
                } catch (error) {
                    reject(new Error('Invalid status response'));
                }
            });
        });

        req.on('error', reject);

        req.setTimeout(2000, () => {
            req.destroy();
            reject(new Error('Status request timeout'));
        });
    });
}