// src/bridge-lock.ts
import * as fs from 'fs';
import * as path from 'path';
import * as net from 'net';
import * as http from 'http';
import * as os from 'os';
import { EventEmitter } from 'events';
import logger from '../logger';
import { findAvailablePort, isPortAvailable } from '../utils';

// 锁文件和日志的基础目录
const USER_HOME = os.homedir();
const APP_DIR = path.join(USER_HOME, '.koomaster');
const LOCK_DIR = path.join(APP_DIR, 'bridge-locks');
const LOG_DIR = path.join(APP_DIR, 'logs');

// 确保必要的目录存在
function ensureDirectories(): void {
    [APP_DIR, LOCK_DIR, LOG_DIR].forEach(dir => {
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
    });
}

// 生成锁文件路径
function getLockFilePath(pid: number, port: number): string {
    return path.join(LOCK_DIR, `bridge-${pid}-${port}.lock`);
}

// 创建锁文件
function createLockFile(pid: number, port: number): void {
    try {
        const lockFilePath = getLockFilePath(pid, port);
        const data = JSON.stringify({
            pid,
            port,
            startTime: new Date().toISOString(),
            hostname: os.hostname()
        }, null, 2);
        fs.writeFileSync(lockFilePath, data, 'utf8');
        logger.info(`Created lock file: ${lockFilePath}`);
    } catch (e) {
        logger.error('Failed to create lock file:', e);
    }
}

// 删除锁文件
function removeLockFile(pid: number, port: number): void {
    try {
        const lockFilePath = getLockFilePath(pid, port);
        if (fs.existsSync(lockFilePath)) {
            fs.unlinkSync(lockFilePath);
            logger.info(`Removed lock file: ${lockFilePath}`);
        }
    } catch (e) {
        logger.error('Failed to delete lock file:', e);
    }
}

// 检查进程是否存在
function isProcessRunning(pid: number): boolean {
    if (!pid) return false;
    try {
        // 在Unix上，如果进程不存在，process.kill会抛出异常
        // 在Windows上，这仅会检查进程是否有权接收信号
        process.kill(pid, 0);
        return true;
    } catch (e) {
        return false;
    }
}


// 检查特定端口是否有WebSocketBridge服务响应
async function checkBridgeAtPort(port: number): Promise<boolean> {
    return new Promise((resolve) => {
        const req = http.get(`http://localhost:${port}/bridge-status`, (res) => {
            // 收到响应，检查是否是我们的服务
            let data = '';
            res.on('data', (chunk) => {
                data += chunk;
            });
            res.on('end', () => {
                try {
                    const jsonData = JSON.parse(data);
                    // 检查是否是我们的服务
                    resolve(jsonData.service === 'WebSocketBridge');
                } catch {
                    resolve(false);
                }
            });
        }).on('error', () => {
            resolve(false);
        });
        req.setTimeout(1000, () => {
            req.destroy();
            resolve(false);
        });
    });
}

// 获取所有活跃的WebSocketBridge实例
export function getActiveBridges(): { pid: number, port: number }[] {
    ensureDirectories();
    const instances: { pid: number, port: number }[] = [];

    try {
        // 读取锁目录中的所有文件
        const files = fs.readdirSync(LOCK_DIR);

        // 通过文件名解析PID和端口
        for (const file of files) {
            const match = file.match(/bridge-(\d+)-(\d+)\.lock/);
            if (match) {
                const [_, pidStr, portStr] = match;
                const pid = parseInt(pidStr, 10);
                const port = parseInt(portStr, 10);

                // 检查进程是否仍在运行
                if (isProcessRunning(pid)) {
                    instances.push({ pid, port });
                } else {
                    // 如果进程不存在，删除过期的锁文件
                    try {
                        fs.unlinkSync(path.join(LOCK_DIR, file));
                        logger.info(`Removed stale lock file: ${file}`);
                    } catch (e) {
                        // 忽略删除错误
                    }
                }
            }
        }
    } catch (e) {
        logger.error('Failed to get active bridge instances:', e);
    }

    return instances;
}

// WebSocketBridge锁管理器
export class BridgeLockManager extends EventEmitter {
    private port: number;
    private pid: number;
    private isShuttingDown: boolean = false;

    constructor(port: number = 8765) {
        super();
        this.port = port;
        this.pid = process.pid;
        ensureDirectories();
    }

    // 初始化锁并获取可用端口
    public async initialize(): Promise<number> {
        // 先检查是否有活跃实例
        const activeBridges = getActiveBridges();

        if (activeBridges.length > 0) {
            logger.info('Active WebSocketBridge instances:');
            activeBridges.forEach(({ pid, port }) => {
                logger.info(`- PID: ${pid}, Port: ${port}`);
            });

            // 检查是否有实例正在使用我们的首选端口
            const existingBridgeOnPort = activeBridges.find(bridge => bridge.port === this.port);
            if (existingBridgeOnPort) {
                logger.info(`Port ${this.port} is already used by another WebSocketBridge instance (PID: ${existingBridgeOnPort.pid})`);

                // 尝试检查这个实例是否真的在响应
                const isResponding = await checkBridgeAtPort(this.port);
                if (isResponding) {
                    // 已有可用实例，返回它的端口
                    return this.port;
                } else {
                    logger.warn(`Bridge at port ${this.port} is not responding but has a lock file, attempting to reclaim`);
                    // 删除过期锁文件
                    removeLockFile(existingBridgeOnPort.pid, this.port);
                }
            }
        }

        // 检查端口是否可用
        const portAvailable = await isPortAvailable(this.port);

        if (!portAvailable) {
            logger.info(`Port ${this.port} is not available, searching for another port...`);
            try {
                this.port = await findAvailablePort(this.port + 1);
                logger.info(`Found available port: ${this.port}`);
            } catch (e) {
                logger.error(`Cannot find available port:`, e.message);
                throw new Error(`Cannot start WebSocketBridge: no available ports`);
            }
        }

        // 创建锁文件
        createLockFile(this.pid, this.port);

        // 设置信号处理程序
        this.setupSignalHandlers();

        return this.port;
    }

    // 释放锁
    public release(): void {
        if (this.isShuttingDown) return;

        this.isShuttingDown = true;
        logger.info('Releasing WebSocketBridge lock...');

        removeLockFile(this.pid, this.port);
    }

    // 设置信号处理
    private setupSignalHandlers(): void {
        // 处理系统信号
        process.on('SIGINT', () => {
            logger.info('Received SIGINT signal');
            this.release();
            this.emit('shutdown');
        });

        process.on('SIGTERM', () => {
            logger.info('Received SIGTERM signal');
            this.release();
            this.emit('shutdown');
        });

        // 处理未捕获的异常
        process.on('uncaughtException', (err) => {
            logger.error('Uncaught exception in main process:', err);
            this.release();
            this.emit('shutdown');
        });

        // 在Node进程退出时确保清理
        process.on('exit', () => {
            logger.info('Main process exiting, cleaning up...');
            // 删除锁文件（同步操作）
            try {
                const lockFilePath = getLockFilePath(this.pid, this.port);
                if (fs.existsSync(lockFilePath)) {
                    fs.unlinkSync(lockFilePath);
                }
            } catch (e) {
                // 忽略清理锁文件的错误
            }
        });

        // 处理未处理的Promise拒绝
        process.on('unhandledRejection', (reason, promise) => {
            logger.error('Unhandled Promise rejection:', reason);
            // 不需要退出，但应记录下来
        });
    }
}