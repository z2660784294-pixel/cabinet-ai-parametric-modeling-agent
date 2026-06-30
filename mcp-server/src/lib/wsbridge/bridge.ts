// src/websocket-bridge.ts
import WebSocket, { WebSocketServer } from 'ws';
import { EventEmitter } from 'events';
import { v4 as uuidv4 } from 'uuid';
import * as http from 'http';
import { BridgeLockManager, getActiveBridges } from './lock';
import logger from '../logger';

// 客户端类型
export enum ClientType {
    MCP = 'mcp',
    KOOMASTER = 'koomaster'
}

// 定义命令接口
interface Command {
    id: string;
    type: string;
    params: Record<string, any>;
    mcpClientId?: string; // 记录发送命令的MCP客户端ID
}

// 定义响应接口
interface CommandResponse {
    id: string;
    status: 'success' | 'error';
    result?: any;
    message?: string;
}

// 客户端信息接口
interface ClientInfo {
    id: string;
    type: ClientType;
    lastActivity: number;
}

// Bridge状态
export enum BridgeStatus {
    STOPPED = 'stopped',
    RUNNING = 'running',
    USING_EXISTING = 'using_existing'
}

// WebSocketBridge类 - 充当MCP和Koomaster之间的通信桥梁
export class WebSocketBridge extends EventEmitter {
    private server: WebSocketServer | null = null;
    private httpServer: http.Server | null = null;
    private clients: Map<WebSocket, ClientInfo> = new Map();
    private pendingCommands: Map<string, {
        mcpClient: WebSocket,
        resolve: (value: any) => void,
        reject: (reason: any) => void,
        timeout: NodeJS.Timeout
    }> = new Map();
    private commandTimeout: number = 120000; // 120秒超时
    private pingInterval: number = 30000;   // 30秒心跳间隔
    private pingTimer: NodeJS.Timeout | null = null;
    private lockManager: BridgeLockManager | null = null;
    private static instance: WebSocketBridge | null = null;
    private _status: BridgeStatus = BridgeStatus.STOPPED;

    // // 单例方法
    // public static async getInstance(port: number = 8765): Promise<WebSocketBridge> {
    //     if (!WebSocketBridge.instance) {
    //         WebSocketBridge.instance = new WebSocketBridge(port);
    //         await WebSocketBridge.instance.initialize();
    //     }
    //     return WebSocketBridge.instance;
    // }

    constructor(private port: number = 8765) {
        super();
    }

    // 初始化 - 检查是否有现有桥接实例存在
    async initialize(): Promise<number> {
        try {
            // 检查是否有活跃的桥接实例
            const activeBridges = getActiveBridges();

            if (activeBridges.length > 0) {
                // 找到一个活跃的桥接实例，使用它的端口
                const existingBridge = activeBridges[0];
                this.port = existingBridge.port;

                logger.info(`Found existing WebSocketBridge at port ${this.port} (PID: ${existingBridge.pid})`);
                logger.info(`Will use existing bridge, no need to start a new server`);

                this._status = BridgeStatus.USING_EXISTING;
                // 使用现有的桥接，不需要启动服务器
                return;
            }

            // 没有找到现有实例，需要启动服务器
            logger.info(`No existing WebSocketBridge found, will start a new server`);

            // 创建锁管理器
            this.lockManager = new BridgeLockManager(this.port);

            // 使用锁管理器获取可用端口
            this.port = await this.lockManager.initialize();

            // 创建 HTTP 服务器
            this.httpServer = http.createServer((req, res) => {
                // 处理HTTP请求
                if (req.url === '/bridge-status') {
                    res.writeHead(200, { 'Content-Type': 'application/json' });
                    res.end(JSON.stringify({
                        service: 'WebSocketBridge',
                        version: '1.0.0',
                        status: this._status,
                        clients: {
                            total: this.clients.size,
                            mcp: this.getClientCount(ClientType.MCP),
                            koomaster: this.getClientCount(ClientType.KOOMASTER)
                        }
                    }));
                } else {
                    res.writeHead(426, { 'Content-Type': 'text/plain' });
                    res.end('Upgrade to WebSocket protocol required');
                }
            });

            // 创建 WebSocket 服务器
            this.server = new WebSocketServer({ server: this.httpServer });

            // 设置事件处理程序
            this.setupEventHandlers();

            // 设置锁管理器的关闭事件处理
            this.lockManager.on('shutdown', () => {
                this.stop().catch(err => {
                    logger.error('Error shutting down WebSocketBridge:', err);
                });
            });

            logger.info(`WebSocketBridge initialized with port ${this.port}`);
            this._status = BridgeStatus.STOPPED;

            await this.start();
        } catch (error) {
            logger.error('Failed to initialize WebSocketBridge:', error);
            throw error;
        }
    }

    // 启动桥接服务器
    protected async start(): Promise<void> {
        // 如果使用现有桥接，则不需要启动
        if (this._status === BridgeStatus.USING_EXISTING) {
            logger.info(`Using existing WebSocketBridge at port ${this.port}, no need to start`);
            return;
        }

        // 如果已经运行，也不需要启动
        if (this._status === BridgeStatus.RUNNING) {
            logger.info('WebSocketBridge is already running');
            return;
        }

        // 确保服务器已初始化
        if (!this.httpServer || !this.server) {
            throw new Error('Cannot start: HTTP server not initialized');
        }

        // 启动服务器
        return new Promise<void>((resolve, reject) => {
            try {
                this.httpServer!.on('listening', () => {
                    logger.info(`WebSocketBridge server listening on port ${this.port}`);
                    this.startPingTimer();
                    this._status = BridgeStatus.RUNNING;
                    resolve();
                });

                this.httpServer!.on('error', (err: any) => {
                    if (err.code === 'EADDRINUSE') {
                        logger.error(`Port ${this.port} is already in use, please restart the application`);
                        reject(new Error(`Port ${this.port} is already in use`));
                    } else {
                        logger.error(`HTTP server error: ${err.message}`);
                        reject(err);
                    }
                });

                // 启动 HTTP 服务器
                this.httpServer!.listen(this.port);
            } catch (error) {
                logger.error('Failed to start WebSocketBridge:', error);
                reject(error);
            }
        });
    }

    // 停止桥接服务器
    public async stop(): Promise<void> {
        // 如果使用现有桥接，则不需要停止
        if (this._status === BridgeStatus.USING_EXISTING) {
            logger.info('Using existing WebSocketBridge, nothing to stop');
            return;
        }

        // 如果已经停止，也不需要停止
        if (this._status === BridgeStatus.STOPPED) {
            logger.info('WebSocketBridge is already stopped');
            return;
        }

        return new Promise<void>((resolve, reject) => {
            // 清理心跳计时器
            if (this.pingTimer) {
                clearInterval(this.pingTimer);
                this.pingTimer = null;
            }

            // 清理所有挂起的命令
            for (const { resolve, reject, timeout } of this.pendingCommands.values()) {
                clearTimeout(timeout);
                reject(new Error('Bridge shutting down'));
            }
            this.pendingCommands.clear();

            // 关闭所有客户端连接
            for (const client of this.clients.keys()) {
                client.close(1000, 'Bridge shutting down');
            }

            // 释放锁
            if (this.lockManager) {
                this.lockManager.release();
            }

            // 关闭WebSocket服务器和HTTP服务器
            const closeServer = () => {
                if (this.httpServer) {
                    this.httpServer.close((err) => {
                        if (err) {
                            logger.error('Error closing HTTP server:', err);
                            reject(err);
                        } else {
                            logger.info('WebSocketBridge server closed');
                            WebSocketBridge.instance = null; // 重置单例
                            this._status = BridgeStatus.STOPPED;
                            resolve();
                        }
                    });
                } else {
                    this._status = BridgeStatus.STOPPED;
                    resolve();
                }
            };

            // 如果WebSocket服务器存在，先关闭它
            if (this.server) {
                this.server.close((err) => {
                    if (err) {
                        logger.error('Error closing WebSocket server:', err);
                    }
                    closeServer();
                });
            } else {
                closeServer();
            }
        });
    }

    // 获取当前连接的客户端数量
    public getClientCount(type?: ClientType): number {
        if (this._status !== BridgeStatus.RUNNING) {
            return 0;
        }

        if (!type) {
            return this.clients.size;
        }

        let count = 0;
        for (const clientInfo of this.clients.values()) {
            if (clientInfo.type === type) {
                count++;
            }
        }
        return count;
    }

    // 检查是否有特定类型的客户端连接
    public hasConnectedClients(type?: ClientType): boolean {
        if (this._status !== BridgeStatus.RUNNING) {
            return false;
        }

        if (!type) {
            return this.clients.size > 0;
        }

        for (const clientInfo of this.clients.values()) {
            if (clientInfo.type === type) {
                return true;
            }
        }
        return false;
    }

    // 获取桥接状态
    public getStatus(): BridgeStatus {
        return this._status;
    }

    // 获取桥接端口
    public getPort(): number {
        return this.port;
    }

    // 私有方法：设置事件处理程序
    private setupEventHandlers(): void {
        if (!this.server) return;

        // 处理新连接
        this.server.on('connection', (socket, request) => {
            const clientId = uuidv4();
            logger.info(`New client connected (ID: ${clientId}), IP: ${request.socket.remoteAddress}`);

            // 等待客户端标识自己的类型
            socket.once('message', (data) => {
                try {
                    const message = JSON.parse(data.toString());

                    // 识别客户端类型
                    if (message.type === 'register') {
                        const clientType = message.clientType === ClientType.MCP
                            ? ClientType.MCP
                            : ClientType.KOOMASTER;

                        // 存储客户端信息
                        this.clients.set(socket, {
                            id: clientId,
                            type: clientType,
                            lastActivity: Date.now()
                        });

                        // 发送欢迎消息
                        socket.send(JSON.stringify({
                            type: 'welcome',
                            message: `Connected to WebSocketBridge as ${clientType}`,
                            clientId
                        }));

                        // 通知客户端连接事件
                        this.emit('clientConnected', { id: clientId, type: clientType });

                        logger.info(`Client ${clientId} registered as ${clientType}`);

                        // 设置消息处理
                        this.setupMessageHandler(socket, clientId, clientType);
                    } else {
                        // 未注册的客户端
                        socket.send(JSON.stringify({
                            type: 'error',
                            message: 'Please register with clientType first'
                        }));
                        socket.close(4000, 'Registration required');
                    }
                } catch (error) {
                    logger.error('Error processing registration:', error);
                    socket.close(4000, 'Invalid registration');
                }
            });

            // 处理关闭
            socket.on('close', (code, reason) => {
                const clientInfo = this.clients.get(socket);
                if (clientInfo) {
                    logger.info(`Client ${clientInfo.id} (${clientInfo.type}) disconnected (Code: ${code}, Reason: ${reason})`);
                    this.clients.delete(socket);
                    this.emit('clientDisconnected', { id: clientInfo.id, type: clientInfo.type });
                }
            });

            // 处理错误
            socket.on('error', (error) => {
                const clientInfo = this.clients.get(socket);
                logger.error(`WebSocket error for client ${clientInfo?.id || 'unknown'}:`, error);
            });
        });

        // 处理服务器错误
        this.server.on('error', (error) => {
            logger.error('WebSocketBridge server error:', error);
            this.emit('error', error);
        });
    }

    // 为已注册的客户端设置消息处理
    private setupMessageHandler(socket: WebSocket, clientId: string, clientType: ClientType): void {
        socket.on('message', (data) => {
            try {
                // 更新最后活动时间
                const clientInfo = this.clients.get(socket);
                if (clientInfo) {
                    clientInfo.lastActivity = Date.now();
                }

                // 解析消息
                const message = JSON.parse(data.toString());

                // 根据客户端类型处理不同的消息
                if (clientType === ClientType.KOOMASTER) {
                    this.handleKoomasterMessage(socket, message);
                } else if (clientType === ClientType.MCP) {
                    this.handleMcpMessage(socket, message);
                }
            } catch (error) {
                logger.error(`Error processing message from ${clientType} ${clientId}:`, error);
            }
        });
    }

    // 处理来自Koomaster客户端的消息
    private handleKoomasterMessage(socket: WebSocket, message: any): void {
        const clientInfo = this.clients.get(socket);

        // 处理响应
        if (message.id && (message.status === 'success' || message.status === 'error')) {
            this.handleResponse(message);
        }
        // 处理心跳
        else if (message.type === 'pong') {
            logger.info(`Received pong from Koomaster client ${clientInfo?.id}`);
        }
        // 处理其他消息类型
        else {
            logger.info(`Received message from Koomaster client ${clientInfo?.id}:`, message);
        }
    }

    // 处理来自MCP客户端的消息
    private handleMcpMessage(socket: WebSocket, message: any): void {
        const clientInfo = this.clients.get(socket);

        // 处理心跳
        if (message.type === 'pong') {
            logger.info(`Received pong from MCP client ${clientInfo?.id}`);
            return;
        }

        // 处理Koomaster状态查询
        if (message.type === 'query_koomaster_status') {
            logger.debug(`Received Koomaster status query from MCP client ${clientInfo?.id} with queryId: ${message.queryId}`);

            const hasKoomasterClients = this.hasConnectedClients(ClientType.KOOMASTER);

            // 构建响应
            const response = {
                type: 'koomaster_status',
                queryId: message.queryId,
                connected: hasKoomasterClients
            };

            logger.debug(`Sending Koomaster status response: ${JSON.stringify(response)}`);

            // 发送响应，包含查询ID以便客户端关联请求和响应
            socket.send(JSON.stringify(response), (err) => {
                if (err) {
                    logger.error(`Failed to send Koomaster status response: ${err.message}`);
                }
            });

            logger.debug(`Responded to Koomaster status query from MCP client ${clientInfo?.id}: ${hasKoomasterClients}`);
            return;
        }
        // 处理命令请求
        if (message.type && message.params) {
            logger.info(`Received command from MCP client ${clientInfo?.id}: ${message.type}`);

            // 转发命令到Koomaster
            this.forwardCommand(socket, message.type, message.params, message.id);
        } else {
            logger.warn(`Received invalid message from MCP client ${clientInfo?.id}:`, message);
        }
    }

    // 转发命令从MCP到Koomaster
    private forwardCommand(
        mcpClient: WebSocket,
        commandType: string,
        params: Record<string, any> = {},
        clientCommandId?: string
    ): void {
        // 检查MCPClient是否有效
        const mcpClientInfo = this.clients.get(mcpClient);
        if (!mcpClientInfo || mcpClientInfo.type !== ClientType.MCP) {
            mcpClient.send(JSON.stringify({
                id: clientCommandId || uuidv4(),
                status: 'error',
                message: 'Invalid MCP client'
            }));
            return;
        }

        // 检查是否有可用的Koomaster客户端
        const koomasterClient = this.getMostRecentClientByType(ClientType.KOOMASTER);
        if (!koomasterClient) {
            mcpClient.send(JSON.stringify({
                id: clientCommandId || uuidv4(),
                status: 'error',
                message: 'No Koomaster clients connected'
            }));
            return;
        }

        // 创建命令ID
        const commandId = clientCommandId || uuidv4();

        // 创建命令对象
        const command: Command = {
            id: commandId,
            type: commandType,
            params,
            mcpClientId: mcpClientInfo.id
        };

        // 设置超时
        const timeout = setTimeout(() => {
            // 如果命令超时，从挂起命令中移除
            if (this.pendingCommands.has(commandId)) {
                this.pendingCommands.delete(commandId);

                // 通知MCP客户端超时
                mcpClient.send(JSON.stringify({
                    id: commandId,
                    status: 'error',
                    message: `Command ${commandType} timed out after ${this.commandTimeout}ms`
                }));
            }
        }, this.commandTimeout);

        // 存储挂起的命令
        this.pendingCommands.set(commandId, {
            mcpClient,
            resolve: () => { }, // 这些函数在这个简化版本中不再使用
            reject: () => { },
            timeout
        });

        // 发送命令到Koomaster客户端
        koomasterClient.send(JSON.stringify(command), (err) => {
            if (err) {
                clearTimeout(timeout);
                this.pendingCommands.delete(commandId);

                // 通知MCP客户端发送失败
                mcpClient.send(JSON.stringify({
                    id: commandId,
                    status: 'error',
                    message: `Failed to forward command: ${err.message}`
                }));
            } else {
                logger.info(`Forwarded command ${commandType} (ID: ${commandId}) from MCP client ${mcpClientInfo.id} to Koomaster client`);
            }
        });
    }

    // 私有方法：处理来自 Koomaster 的响应
    private handleResponse(response: CommandResponse): void {
        // 查找挂起的命令
        const pendingCommand = this.pendingCommands.get(response.id);
        if (pendingCommand) {
            // 清除超时
            clearTimeout(pendingCommand.timeout);
            // 从挂起命令中移除
            this.pendingCommands.delete(response.id);

            // 获取MCP客户端
            const mcpClient = pendingCommand.mcpClient;
            const mcpClientInfo = this.clients.get(mcpClient);

            if (mcpClientInfo && mcpClientInfo.type === ClientType.MCP) {
                // 将响应发送回MCP客户端
                mcpClient.send(JSON.stringify(response), (err) => {
                    if (err) {
                        logger.error(`Failed to send response to MCP client ${mcpClientInfo.id}:`, err);
                    }
                });

                logger.info(`Forwarded response for command ${response.id} to MCP client ${mcpClientInfo.id}`);
            }
        } else {
            logger.warn(`Received response for unknown command ID: ${response.id}`);
        }
    }

    // 私有方法：获取特定类型的最近活动客户端
    private getMostRecentClientByType(type: ClientType): WebSocket | null {
        let mostRecent: WebSocket | null = null;
        let lastActivity = 0;

        for (const [client, info] of this.clients.entries()) {
            if (info.type === type && info.lastActivity > lastActivity) {
                mostRecent = client;
                lastActivity = info.lastActivity;
            }
        }

        return mostRecent;
    }

    // 私有方法：启动心跳计时器
    private startPingTimer(): void {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
        }
        this.pingTimer = setInterval(() => {
            this.pingClients();
        }, this.pingInterval);
    }

    // 私有方法：发送心跳到所有客户端
    private pingClients(): void {
        const now = Date.now();
        const timeoutThreshold = now - (this.pingInterval * 2);
        // 检查和移除超时的客户端
        for (const [client, info] of this.clients.entries()) {
            if (info.lastActivity < timeoutThreshold) {
                logger.warn(`Client ${info.id} (${info.type}) timed out, closing connection`);
                client.close(1000, 'Connection timed out');
                this.clients.delete(client);
                this.emit('clientDisconnected', { id: info.id, type: info.type });
                continue;
            }
            // 发送 ping
            try {
                client.send(JSON.stringify({ type: 'ping', timestamp: now }));
            } catch (error) {
                logger.error(`Error sending ping to client ${info.id}:`, error);
            }
        }
    }
}