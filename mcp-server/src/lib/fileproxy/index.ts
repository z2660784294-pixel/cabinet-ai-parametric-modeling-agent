import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import { fileURLToPath } from 'url';
import * as http from 'http';
import * as net from 'net';
import * as os from 'os';
import logger from '../logger';

// 在ES模块中获取__dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 用户主目录下的应用数据目录
const USER_HOME = os.homedir();
const APP_DATA_DIR = path.join(USER_HOME, '.koomaster-proxy');

// 配置
const config = {
    serverScript: path.join(__dirname, './proxy-server.js'),
    port: process.env.PORT || 3000,
    logDirectory: path.join(APP_DATA_DIR, 'logs'),
    lockDirectory: path.join(APP_DATA_DIR, 'locks')
};

// 确保应用数据目录存在
if (!fs.existsSync(APP_DATA_DIR)) {
    fs.mkdirSync(APP_DATA_DIR, { recursive: true });
    logger.info(`已创建应用数据目录: ${APP_DATA_DIR}`);
}

// 确保日志和锁目录存在
if (!fs.existsSync(config.logDirectory)) {
    fs.mkdirSync(config.logDirectory, { recursive: true });
    logger.info(`已创建日志目录: ${config.logDirectory}`);
}
if (!fs.existsSync(config.lockDirectory)) {
    fs.mkdirSync(config.lockDirectory, { recursive: true });
    logger.info(`已创建锁目录: ${config.lockDirectory}`);
}

// 生成锁文件路径
function getLockFilePath(pid: number, port: number): string {
    return path.join(config.lockDirectory, `proxy-${pid}-${port}.lock`);
}

// 创建锁文件
function createLockFile(pid: number, port: number): void {
    try {
        const lockFilePath = getLockFilePath(pid, port);
        const data = JSON.stringify({
            pid,
            port,
            startTime: new Date().toISOString(),
            hostname: os.hostname(),
            appVersion: process.env.npm_package_version || 'unknown'
        }, null, 2);
        fs.writeFileSync(lockFilePath, data, 'utf8');
        logger.info(`已创建锁文件: ${lockFilePath}`);
    } catch (e) {
        logger.error('创建锁文件失败:', e);
    }
}

// 删除锁文件
function removeLockFile(pid: number, port: number): void {
    try {
        const lockFilePath = getLockFilePath(pid, port);
        if (fs.existsSync(lockFilePath)) {
            fs.unlinkSync(lockFilePath);
            logger.info(`已删除锁文件: ${lockFilePath}`);
        }
    } catch (e) {
        logger.error('删除锁文件失败:', e);
    }
}

// 获取所有活跃服务实例
export function getActiveInstances(): { pid: number, port: number }[] {
    const instances: { pid: number, port: number }[] = [];
    try {
        logger.info(`正在检查锁目录: ${config.lockDirectory}`);
        // 读取锁目录中的所有文件
        if (!fs.existsSync(config.lockDirectory)) {
            logger.info('锁目录不存在，创建中...');
            fs.mkdirSync(config.lockDirectory, { recursive: true });
            return instances;
        }

        const files = fs.readdirSync(config.lockDirectory);
        logger.info(`发现 ${files.length} 个锁文件`);

        // 通过文件名解析PID和端口
        for (const file of files) {
            const match = file.match(/proxy-(\d+)-(\d+)\.lock/);
            if (match) {
                const [_, pidStr, portStr] = match;
                const pid = parseInt(pidStr, 10);
                const port = parseInt(portStr, 10);

                logger.info(`检查进程 PID ${pid} 是否在运行...`);

                // 检查进程是否仍在运行
                if (isProcessRunning(pid)) {
                    logger.info(`进程 PID ${pid} 在运行中，添加到活跃实例列表`);
                    instances.push({ pid, port });
                } else {
                    // 如果进程不存在，删除过期的锁文件
                    try {
                        const staleLockPath = path.join(config.lockDirectory, file);
                        logger.info(`进程 PID ${pid} 不在运行，删除过期锁文件: ${staleLockPath}`);
                        fs.unlinkSync(staleLockPath);
                    } catch (e) {
                        logger.error(`删除过期锁文件失败: ${e.message}`);
                    }
                }
            }
        }
    } catch (e) {
        logger.error('获取活跃实例失败:', e);
    }

    logger.info(`找到 ${instances.length} 个活跃实例`);
    return instances;
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

// 检查端口是否可用
async function isPortAvailable(port: number): Promise<boolean> {
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
async function findAvailablePort(startPort: number, maxTries: number = 100): Promise<number> {
    let port = startPort;
    for (let i = 0; i < maxTries; i++) {
        if (await isPortAvailable(port)) {
            return port;
        }
        port++;
    }
    throw new Error(`无法在 ${startPort} 到 ${startPort + maxTries - 1} 范围内找到可用端口`);
}

// 检查特定端口是否有服务响应
async function checkServiceAtPort(port: number): Promise<boolean> {
    return new Promise((resolve) => {
        logger.info(`检查端口 ${port} 上的服务...`);
        const req = http.get(`http://localhost:${port}`, (res) => {
            // 收到响应，检查是否是我们的服务
            let data = '';
            res.on('data', (chunk) => {
                data += chunk;
            });
            res.on('end', () => {
                // 简单检查响应内容是否包含我们的服务特征
                const isOurService = data.includes('文件转发服务') ||
                    data.includes('proxy') ||
                    res.headers['server']?.includes('proxy');

                logger.info(`端口 ${port} 服务检查结果: ${isOurService ? '是我们的服务' : '不是我们的服务'}`);
                resolve(isOurService);
            });
        }).on('error', (err) => {
            logger.info(`连接到端口 ${port} 失败: ${err.message}`);
            resolve(false);
        });

        req.setTimeout(1000, () => {
            logger.info(`连接到端口 ${port} 超时`);
            req.destroy();
            resolve(false);
        });
    });
}

export class ProxyServiceManager {
    private serverProcess: ChildProcess | null = null;
    private isShuttingDown: boolean = false;
    private exitTimeout: NodeJS.Timeout | null = null;
    private actualPort: number | null = null;
    private pid: number | null = null;

    constructor() {
        this.setupSignalHandlers();
        this.setupExitHooks();
    }

    // 获取实际端口
    public getPort(): number | null {
        return this.actualPort;
    }

    // 获取进程ID
    public getPid(): number | null {
        return this.pid;
    }

    // 列出所有活跃实例
    public static listActiveInstances(): { pid: number, port: number }[] {
        return getActiveInstances();
    }

    // 启动服务
    public async start(): Promise<number> {
        // 先列出现有实例
        const activeInstances = getActiveInstances();
        if (activeInstances.length > 0) {
            logger.info('当前活跃的文件转发服务实例:');
            activeInstances.forEach(({ pid, port }) => {
                logger.info(`- PID: ${pid}, 端口: ${port}`);
            });
            this.actualPort = activeInstances[0].port;
            return this.actualPort;
        }

        // 检查指定的端口是否可用
        const portAvailable = await isPortAvailable(Number(config.port));

        // 如果端口不可用，寻找可用端口
        let finalPort = Number(config.port);
        if (!portAvailable) {
            logger.info(`端口 ${config.port} 不可用，寻找其他可用端口...`);
            try {
                finalPort = await findAvailablePort(Number(config.port) + 1);
                logger.info(`找到可用端口: ${finalPort}`);
                config.port = finalPort;
            } catch (e) {
                logger.error(`无法找到可用端口:`, e.message);
                throw new Error(`无法启动服务: 找不到可用端口`);
            }
        }

        logger.info(`启动文件转发服务在端口 ${finalPort}...`);
        await this.startServer(finalPort);
        this.actualPort = finalPort;
        return finalPort;
    }

    // 启动服务器进程
    private async startServer(port: number): Promise<void> {
        // 创建日志文件 - 使用端口号作为区分
        const logFile = path.join(config.logDirectory, `proxy-${port}.log`);
        const logStream = fs.createWriteStream(logFile, { flags: 'a' });

        // 添加时间戳到日志
        const timestamp = new Date().toISOString();
        logStream.write(`\n[${timestamp}] === 服务启动于端口 ${port} ===\n`);

        // 设置环境变量
        const env = {
            ...process.env,
            PORT: port.toString()
        };

        // 启动节点进程
        this.serverProcess = spawn('node', [config.serverScript], {
            env,
            stdio: ['ignore', 'pipe', 'pipe'],
            detached: false
        });

        // 保存进程ID
        const { pid } = this.serverProcess;
        this.pid = pid;
        logger.info(`文件转发服务进程 (PID: ${pid}) 已启动，监听端口 ${port}`);

        // 创建锁文件
        if (pid) {
            createLockFile(pid, port);
        }

        // 连接输出到日志文件和控制台
        this.serverProcess.stdout?.pipe(logStream);
        this.serverProcess.stderr?.pipe(logStream);

        // 同时显示在控制台
        this.serverProcess.stdout?.on('data', (data) => {
            process.stdout.write(data);
        });
        this.serverProcess.stderr?.on('data', (data) => {
            process.stderr.write(data);
        });

        // 处理服务器退出
        this.serverProcess.on('exit', (code, signal) => {
            logger.info(`服务进程 (PID: ${pid}) 退出，代码: ${code}, 信号: ${signal || 'none'}`);

            // 删除锁文件
            if (pid && port) {
                removeLockFile(pid, port);
            }

            // 关闭日志流
            logStream.end();

            // 清除进程引用
            this.serverProcess = null;

            // 如果不是正在关闭且进程异常退出，则重启服务
            if (!this.isShuttingDown && code !== 0) {
                logger.info('服务异常退出，2秒后重启...');
                setTimeout(() => this.startServer(port), 2000);
            }
        });

        // 处理错误
        this.serverProcess.on('error', (err) => {
            logger.error('服务进程启动错误:', err);

            // 写入错误到日志
            logStream.write(`[ERROR] 进程启动错误: ${err.message}\n`);

            // 删除锁文件
            if (pid && port) {
                removeLockFile(pid, port);
            }
        });

        // 等待服务器启动并检查是否可访问
        let retries = 10;
        logger.info(`等待服务在端口 ${port} 上响应...`);

        while (retries > 0) {
            await new Promise(resolve => setTimeout(resolve, 500));
            const isResponding = await checkServiceAtPort(port);
            if (isResponding) {
                logger.info(`服务已在端口 ${port} 上成功启动并响应请求`);
                return;
            }
            retries--;
            logger.info(`等待服务响应，剩余尝试次数: ${retries}`);
        }

        logger.info(`警告: 服务进程已启动但未在预期时间内响应请求`);
    }

    // 关闭服务
    public shutdown(): void {
        if (this.isShuttingDown) {
            return;
        }

        this.isShuttingDown = true;
        logger.info('正在关闭文件转发服务...');

        // 清除之前的退出超时
        if (this.exitTimeout) {
            clearTimeout(this.exitTimeout);
        }

        // 删除锁文件
        if (this.pid && this.actualPort) {
            removeLockFile(this.pid, this.actualPort);
        }

        if (!this.serverProcess) {
            logger.info('没有运行中的服务进程');
            return;
        }

        // 尝试优雅关闭
        try {
            logger.info(`发送终止信号到进程 PID: ${this.serverProcess.pid}`);
            // 首先尝试SIGTERM
            this.serverProcess.kill('SIGTERM');

            // 设置强制终止超时
            this.exitTimeout = setTimeout(() => {
                if (this.serverProcess) {
                    logger.info('服务未能在时间内优雅关闭，强制终止');
                    try {
                        // 尝试SIGKILL
                        this.serverProcess.kill('SIGKILL');
                    } catch (err) {
                        logger.error('强制终止进程失败:', err);
                    }
                    // 额外保障：通过系统命令强制终止进程
                    this.forceKillProcess(this.serverProcess.pid);
                }
                // 清除引用
                this.serverProcess = null;
            }, 5000);
        } catch (error) {
            logger.error('关闭服务时出错:', error);
            // 如果常规方法失败，尝试系统级终止
            if (this.serverProcess && this.serverProcess.pid) {
                this.forceKillProcess(this.serverProcess.pid);
            }
            this.serverProcess = null;
        }
    }

    // 使用系统命令强制终止进程
    private forceKillProcess(pid: number): void {
        try {
            const isWin = process.platform === 'win32';
            if (isWin) {
                // Windows
                spawn('taskkill', ['/F', '/PID', pid.toString()]);
            } else {
                // Unix/Linux/macOS
                spawn('kill', ['-9', pid.toString()]);
            }
            logger.info(`已通过系统命令强制终止进程 PID: ${pid}`);
        } catch (err) {
            logger.error(`使用系统命令终止进程 ${pid} 失败:`, err);
        }
    }

    // 设置信号处理
    private setupSignalHandlers(): void {
        // 处理系统信号
        process.on('SIGINT', () => {
            logger.info('收到 SIGINT 信号');
            this.shutdown();
            // 给进程一些时间来清理后强制退出
            setTimeout(() => {
                process.exit(0);
            }, 2000);
        });

        process.on('SIGTERM', () => {
            logger.info('收到 SIGTERM 信号');
            this.shutdown();
            setTimeout(() => {
                process.exit(0);
            }, 2000);
        });

        // 处理未捕获的异常
        process.on('uncaughtException', (err) => {
            logger.error('主进程未捕获的异常:', err);
            this.shutdown();
            setTimeout(() => {
                process.exit(1);
            }, 2000);
        });
    }

    // 设置Node进程退出钩子
    private setupExitHooks(): void {
        // 在Node进程退出时确保子进程被终止
        process.on('exit', () => {
            logger.info('主进程退出，正在清理...');
            // 删除锁文件
            if (this.pid && this.actualPort) {
                try {
                    const lockFilePath = getLockFilePath(this.pid, this.actualPort);
                    if (fs.existsSync(lockFilePath)) {
                        fs.unlinkSync(lockFilePath);
                    }
                } catch (e) {
                    // 忽略清理锁文件的错误
                }
            }

            // 直接使用process.exit()时，Node不会等待异步操作
            // 所以我们需要在同步代码中尽可能清理
            if (this.serverProcess && this.serverProcess.pid) {
                try {
                    // 同步操作：尝试发送SIGKILL
                    this.serverProcess.kill('SIGKILL');
                    logger.info(`在主进程退出前终止了子进程 PID: ${this.serverProcess.pid}`);
                } catch (e) {
                    // 无法处理，但至少我们尝试了
                }
            }
        });

        // 处理未处理的Promise拒绝
        process.on('unhandledRejection', (reason, promise) => {
            logger.error('未处理的Promise拒绝:', reason);
            // 不需要退出，但应记录下来
        });
    }
}