import { createParamEditorServer, createParamEditorDataServer, shutdownServer } from '../server';
// import { ProxyServiceManager } from '../lib/fileproxy';
import { WebSocketBridge } from '../lib/wsbridge/bridge';
import { llmClient } from '../llmClient';
import logger from '../lib/logger';
import { findAvailablePort } from '../lib/utils';
import { printServerInfo } from '../lib/print';

// 启动服务器
export async function startMCPServer(options: { dev?: boolean, stdio?: boolean } = {}) {
    try {
        const isDevMode = options.dev || false;
        const stdioMode = options.stdio || false;

        // 初始化 WebSocket 服务器
        logger.info('Initializing WebSocket server...');

        const wsBridge = new WebSocketBridge();
        await wsBridge.initialize();
        const wsPort = wsBridge.getPort();
        const wsUrl = `ws://localhost:${wsPort}`;

        await llmClient.connect(wsUrl);

        // // 启动文件下载代理服务
        // const manager = new ProxyServiceManager();
        // await manager.start();

        // 创建 MCP 服务器
        logger.info('Creating MCP servers...');

        // parameditor 服务器
        const paramEditorServer = createParamEditorServer();

        // param-editor-data 服务器（当前编辑器 EditorData 读写工具）
        const paramEditorDataServer = createParamEditorDataServer();

        // 处理进程终止信号
        process.on('SIGINT', async () => {
            logger.info('Caught SIGINT, shutting down...');
            await shutdownServer();
            process.exit(0);
        });

        process.on('SIGTERM', async () => {
            logger.info('Caught SIGTERM, shutting down...');
            await shutdownServer();
            process.exit(0);
        });

        if (!isDevMode && !stdioMode) {
            // parameditor 端口
            const paramEditorPort = await findAvailablePort(7764);

            // param-editor-data 端口
            const paramEditorDataPort = await findAvailablePort(paramEditorPort + 1);

            // 启动 parameditor 服务器
            await paramEditorServer.start({
                transportType: "httpStream",
                httpStream: {
                    endpoint: `/sse`,
                    port: paramEditorPort,
                }
            });

            // 启动 param-editor-data 服务器
            await paramEditorDataServer.start({
                transportType: "httpStream",
                httpStream: {
                    endpoint: `/sse`,
                    port: paramEditorDataPort,
                }
            });

            const paramEditorUrl = `http://localhost:${paramEditorPort}/sse`;
            const paramEditorDataUrl = `http://localhost:${paramEditorDataPort}/sse`;

            printServerInfo(
                'SERVER STARTED SUCCESSFULLY',
                [
                    { label: 'parameditor MCP Endpoint:', value: paramEditorUrl },
                    { label: 'param-editor-data MCP Endpoint:', value: paramEditorDataUrl },
                    { label: 'KooMaster Bridge Server Address:', value: wsUrl }
                ],
                {
                    icon: '📱',
                    text: 'Enter Bridge Server Address "VALUE" in the KooMaster app to connect',
                    value: wsUrl
                }
            );

            logger.info(`parameditor MCP server started: ${paramEditorUrl}`);
            logger.info(`param-editor-data MCP server started: ${paramEditorDataUrl}`);
            logger.info(`WebSocket Bridge running on port: ${wsPort}`);
        } else {
            // stdio 模式下只启动 parameditor 服务器
            await paramEditorServer.start({
                transportType: "stdio",
            });
            logger.info('parameditor MCP server running on stdio');
        }

    } catch (error) {
        logger.error('Failed to start servers:', error);
        await shutdownServer().catch(err => logger.error('Error during shutdown:', err));
        process.exit(1);
    }
}
