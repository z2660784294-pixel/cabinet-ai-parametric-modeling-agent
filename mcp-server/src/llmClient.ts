// src/mcp-client.ts
import WebSocket from 'ws';
import { v4 as uuidv4 } from 'uuid';
import { EventEmitter } from 'events';
import logger from './lib/logger';

// LLM客户端 - 连接到WebSocketBridge并发送命令
class LLMClient extends EventEmitter {
    private ws: WebSocket | null = null;
    private clientId: string | null = null;
    private connected: boolean = false;
    private pendingCommands: Map<string, {
        resolve: (value: any) => void,
        reject: (reason: any) => void,
        timeout: NodeJS.Timeout
    }> = new Map();
    private commandTimeout: number = 60000; // 60秒命令超时
    private koomasterStatusQueries: Map<string, {
        resolve: (connected: boolean) => void,
        reject: (reason: any) => void,
        timeout: NodeJS.Timeout
    }> = new Map();
    private koomasterStatusTimeout: number = 5000; // 5秒超时

    constructor() {
        super();
    }

    // 连接到WebSocketBridge服务器
    public connect(url: string): Promise<void> {
        // 连接实现保持不变
        return new Promise((resolve, reject) => {
            if (this.connected) {
                resolve();
                return;
            }

            this.ws = new WebSocket(url);

            this.ws.on('open', () => {
                logger.info('Connected to WebSocketBridge');

                // 注册为MCP客户端
                this.ws?.send(JSON.stringify({
                    type: 'register',
                    clientType: 'mcp'
                }));
            });

            this.ws.on('message', (data) => {
                try {
                    const message = JSON.parse(data.toString());

                    // 处理欢迎消息
                    if (message.type === 'welcome') {
                        this.clientId = message.clientId;
                        this.connected = true;
                        logger.info(`Registered as MCP client with ID: ${this.clientId}`);
                        this.emit('connected', this.clientId);
                        resolve();
                    }
                    // 处理命令响应
                    else if (message.id && (message.status === 'success' || message.status === 'error')) {
                        this.handleCommandResponse(message);
                    }
                    // 处理Koomaster状态响应
                    else if (message.type === 'koomaster_status') {
                        this.handleKoomasterStatusResponse(message);
                    }
                    // 处理心跳
                    else if (message.type === 'ping') {
                        this.ws?.send(JSON.stringify({ type: 'pong', timestamp: Date.now() }));
                    }
                    // 处理其他消息
                    else {
                        this.emit('message', message);
                    }
                } catch (error) {
                    logger.error('Error processing message:', error);
                }
            });

            this.ws.on('error', (error) => {
                logger.error('WebSocket error:', error);
                this.emit('error', error);
                if (!this.connected) {
                    reject(error);
                }
            });

            this.ws.on('close', (code, reason) => {
                logger.info(`Connection closed: ${code} - ${reason}`);
                this.connected = false;
                this.ws = null;

                // 清理所有挂起的命令
                for (const { reject, timeout } of this.pendingCommands.values()) {
                    clearTimeout(timeout);
                    reject(new Error('Connection closed'));
                }
                this.pendingCommands.clear();

                // 清理所有Koomaster状态查询
                for (const { reject, timeout } of this.koomasterStatusQueries.values()) {
                    clearTimeout(timeout);
                    reject(new Error('Connection closed'));
                }
                this.koomasterStatusQueries.clear();

                this.emit('disconnected', { code, reason });
            });
        });
    }

    // 发送命令到WebSocketBridge
    public async sendCommand(commandType: string, params: Record<string, any> = {}): Promise<any> {
        if (!this.connected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            throw new Error('Not connected to WebSocketBridge');
        }

        // 在发送命令前检查是否有Koomaster客户端
        const hasKoomaster = await this.hasConnectedKoomasterClients();
        if (!hasKoomaster) {
            throw new Error('No Koomaster clients connected to WebSocketBridge');
        }

        const commandId = uuidv4();
        const command = {
            id: commandId,
            type: commandType,
            params
        };

        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                if (this.pendingCommands.has(commandId)) {
                    this.pendingCommands.delete(commandId);
                    reject(new Error(`Command ${commandType} timed out after ${this.commandTimeout}ms`));
                }
            }, this.commandTimeout);

            this.pendingCommands.set(commandId, { resolve, reject, timeout });

            this.ws?.send(JSON.stringify(command), (err) => {
                if (err) {
                    clearTimeout(timeout);
                    this.pendingCommands.delete(commandId);
                    reject(new Error(`Failed to send command: ${err.message}`));
                } else {
                    logger.info(`Sent command ${commandType} (ID: ${commandId})`);
                }
            });
        });
    }

    // 处理命令响应
    private handleCommandResponse(response: any): void {
        const pendingCommand = this.pendingCommands.get(response.id);
        if (pendingCommand) {
            clearTimeout(pendingCommand.timeout);
            this.pendingCommands.delete(response.id);

            if (response.status === 'success') {
                pendingCommand.resolve(response.result);
            } else {
                const errorMsg = (response && response.message) || (response && response.error) || 'Unknown error';
                pendingCommand.reject(new Error(errorMsg));
            }
        } else {
            logger.warn(`Received response for unknown command ID: ${response.id}`);
        }
    }

    // 处理Koomaster状态响应
    private handleKoomasterStatusResponse(response: any): void {
        const queryId = response.queryId;
        if (!queryId || !this.koomasterStatusQueries.has(queryId)) {
            // 可能是定期更新或未请求的状态更新
            this.emit('koomasterStatusChanged', response.connected);
            return;
        }

        const pendingQuery = this.koomasterStatusQueries.get(queryId)!;
        clearTimeout(pendingQuery.timeout);
        this.koomasterStatusQueries.delete(queryId);

        pendingQuery.resolve(response.connected);
    }

    // 检查是否有Koomaster客户端连接 - 实时查询
    public async hasConnectedKoomasterClients(): Promise<boolean> {
        if (!this.connected || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return false;
        }

        return new Promise<boolean>((resolve, reject) => {
            const queryId = uuidv4();

            // 设置超时
            const timeout = setTimeout(() => {
                if (this.koomasterStatusQueries.has(queryId)) {
                    this.koomasterStatusQueries.delete(queryId);
                    reject(new Error(`Koomaster status query timed out after ${this.koomasterStatusTimeout}ms`));
                }
            }, this.koomasterStatusTimeout);

            // 存储查询
            this.koomasterStatusQueries.set(queryId, { resolve, reject, timeout });

            // 发送状态查询
            this.ws.send(JSON.stringify({
                type: 'query_koomaster_status',
                queryId
            }), (err) => {
                if (err) {
                    clearTimeout(timeout);
                    this.koomasterStatusQueries.delete(queryId);
                    reject(new Error(`Failed to send status query: ${err.message}`));
                } else {
                    logger.debug(`Sent Koomaster status query (ID: ${queryId})`);
                }
            });
        });
    }

    // 检查是否连接
    public isConnected(): boolean {
        return this.connected;
    }

    // 获取客户端ID
    public getClientId(): string | null {
        return this.clientId;
    }

    // 断开连接
    public disconnect(): void {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
            this.connected = false;
        }
    }
}

export const llmClient = new LLMClient();
