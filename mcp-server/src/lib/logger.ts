import * as fs from 'fs';
import * as path from 'path';
import * as util from 'util';
import { fileURLToPath } from 'url';

const __filenameNew = fileURLToPath(import.meta.url);
const __dirnameNew = path.dirname(__filenameNew)

const timestamp = new Date().toISOString().replace(/[:.]/g, '-');

// 日志级别枚举
export enum LogLevel {
    DEBUG = 0,
    INFO = 1,
    WARN = 2,
    ERROR = 3,
    NONE = 100 // 用于完全禁用日志
}

class Logger {
    private logFile: fs.WriteStream | null = null;
    private logLevel: LogLevel = LogLevel.INFO;
    private logDir: string;
    private baseFilename: string;
    private currentLogPath: string = '';
    private rotationSize: number; // 单位: 字节
    private maxLogFiles: number;
    private isFileReady: boolean = false;
    private pendingMessages: string[] = [];

    constructor(options: {
        logDir?: string;
        baseFilename?: string;
        logLevel?: LogLevel;
        rotationSize?: number; // 单位: MB
        maxLogFiles?: number;
    } = {}) {
        // 设置默认值和用户配置
        this.logDir = options.logDir || path.join(path.resolve(__dirnameNew, "../../"), 'logs');
        this.baseFilename = options.baseFilename || 'koomaster-mcp';
        this.logLevel = options.logLevel !== undefined ? options.logLevel : LogLevel.INFO;
        this.rotationSize = (options.rotationSize || 5) * 1024 * 1024; // 默认 5MB
        this.maxLogFiles = options.maxLogFiles || 5;

        // 确保日志目录存在
        this.ensureLogDirectory();

        // 创建日志文件
        this.createLogFile();

        // 捕获未处理的异常和拒绝，确保它们被记录
        process.on('uncaughtException', (error) => {
            this.error(`Uncaught Exception: ${error.stack || error.toString()}`);
            process.exit(1);
        });

        process.on('unhandledRejection', (reason) => {
            this.error(`Unhandled Rejection: ${reason instanceof Error ? reason.stack : util.inspect(reason)}`);
        });
    }

    // 确保日志目录存在
    private ensureLogDirectory(): void {
        try {
            if (!fs.existsSync(this.logDir)) {
                fs.mkdirSync(this.logDir, { recursive: true });
            }
        } catch (error) {
            // console.error(`Failed to create log directory: ${error instanceof Error ? error.message : String(error)}`);
            // 不抛出错误，继续使用控制台作为回退
        }
    }

    // 创建新的日志文件
    private createLogFile(): void {
        try {
            // 关闭现有的日志文件（如果有）
            if (this.logFile) {
                this.logFile.end();
                this.logFile = null;
                this.isFileReady = false;
            }

            // 创建带时间戳的日志文件名
            const filename = `${this.baseFilename}-${new Date().toISOString().replace(/[:.]/g, '-')}.log`;
            this.currentLogPath = path.join(this.logDir, filename);

            // 先创建空文件确保它存在
            fs.writeFileSync(this.currentLogPath, '');

            // 创建文件流
            this.logFile = fs.createWriteStream(this.currentLogPath, { flags: 'a' });

            // 设置打开事件处理程序
            this.logFile.on('open', () => {
                this.isFileReady = true;
                // console.log(`Log file created: ${this.currentLogPath}`);

                // 写入内部启动消息
                this._writeToFile(`[${new Date().toISOString()}] [INFO] Log file created: ${this.currentLogPath}\n`);

                // 处理待处理的消息
                if (this.pendingMessages.length > 0) {
                    this.pendingMessages.forEach(msg => this._writeToFile(msg));
                    this.pendingMessages = [];
                }

                // 执行日志轮转 - 删除超过最大数量的旧日志
                this.rotateLogFiles();
            });

            // 设置错误事件处理程序
            this.logFile.on('error', (error) => {
                // console.error(`Error with log file: ${error.message}`);
                this.isFileReady = false;
                this.logFile = null;
            });
        } catch (error) {
            // console.error(`Failed to create log file: ${error instanceof Error ? error.message : String(error)}`);
            // 出错时回退到控制台日志
            this.isFileReady = false;
            this.logFile = null;
        }
    }

    // 确保文件存在的辅助方法
    private ensureFileExists(filePath: string): boolean {
        try {
            if (!fs.existsSync(filePath)) {
                fs.writeFileSync(filePath, '');
            }
            return true;
        } catch (error) {
            // console.error(`Failed to ensure file exists: ${error instanceof Error ? error.message : String(error)}`);
            return false;
        }
    }

    // 日志轮转 - 删除旧的日志文件
    private rotateLogFiles(): void {
        try {
            // 读取日志目录中的所有文件
            const files = fs.readdirSync(this.logDir);

            // 过滤出匹配基本文件名的日志文件
            const logFiles = files
                .filter(file => file.startsWith(this.baseFilename) && file.endsWith('.log'))
                .map(file => ({
                    name: file,
                    path: path.join(this.logDir, file),
                    time: fs.statSync(path.join(this.logDir, file)).mtime.getTime()
                }))
                .sort((a, b) => b.time - a.time); // 按修改时间降序排序

            // 仅保留最近的 N 个文件
            if (logFiles.length > this.maxLogFiles) {
                for (let i = this.maxLogFiles; i < logFiles.length; i++) {
                    try {
                        fs.unlinkSync(logFiles[i].path);
                        this._writeToFile(`[${new Date().toISOString()}] [DEBUG] Deleted old log file: ${logFiles[i].name}\n`);
                    } catch (e) {
                        // console.warn(`Failed to delete old log file: ${logFiles[i].name}`);
                    }
                }
            }
        } catch (error) {
            // console.warn(`Error during log rotation: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    // 检查日志文件大小，必要时创建新文件
    private checkLogFileSize(): void {
        if (!this.logFile || !this.isFileReady || !this.currentLogPath) return;

        try {
            if (fs.existsSync(this.currentLogPath)) {
                const stats = fs.statSync(this.currentLogPath);
                if (stats.size >= this.rotationSize) {
                    this._writeToFile(`[${new Date().toISOString()}] [INFO] Log file size (${stats.size} bytes) exceeded rotation threshold, creating new log file\n`);
                    this.createLogFile();
                }
            } else {
                // 文件不存在，重新创建
                // console.warn(`Log file ${this.currentLogPath} does not exist, recreating`);
                this.createLogFile();
            }
        } catch (error) {
            // console.warn(`Error checking log file size: ${error instanceof Error ? error.message : String(error)}`);
        }
    }

    // 直接写入文件的内部方法
    private _writeToFile(message: string): void {
        if (!this.logFile || !this.isFileReady) return;

        try {
            this.logFile.write(message);
        } catch (error) {
            // console.error(`Failed to write to log file: ${error instanceof Error ? error.message : String(error)}`);
            this.isFileReady = false;

            // 尝试重新创建日志文件
            setTimeout(() => this.createLogFile(), 1000);
        }
    }

    // 写入日志入口
    private log(level: string, message: string): void {
        const timestamp = new Date().toISOString();
        const logEntry = `[${timestamp}] [${level}] ${message}\n`;

        // 如果日志文件就绪，写入日志文件
        if (this.isFileReady && this.logFile) {
            this._writeToFile(logEntry);
            this.checkLogFileSize();
        } else if (this.logFile) {
            // 文件流存在但未就绪，将消息加入队列
            this.pendingMessages.push(logEntry);
        } else {
            // 回退到控制台日志
            // console.log(logEntry.trim());
        }
    }

    // 设置日志级别
    public setLogLevel(level: LogLevel): void {
        this.logLevel = level;
        this.info(`Log level set to: ${LogLevel[level]}`);
    }

    // 获取当前日志级别
    public getLogLevel(): LogLevel {
        return this.logLevel;
    }

    // 获取当前日志文件路径
    public getCurrentLogPath(): string {
        return this.currentLogPath;
    }

    // 调试日志
    public debug(message: string): void {
        if (this.logLevel <= LogLevel.DEBUG) {
            this.log('DEBUG', message);
        }
    }

    // 信息日志
    public info(message: string, ...args: any[]): void {
        if (this.logLevel <= LogLevel.INFO) {
            this.log('INFO', message + args.join(" "));
        }
    }

    // 警告日志
    public warn(message: string, ...args: any[]): void {
        if (this.logLevel <= LogLevel.WARN) {
            this.log('WARN', message + args.join(" "));
        }
    }

    // 错误日志
    public error(message: string, error?: any): void {
        if (this.logLevel <= LogLevel.ERROR) {
            this.log('ERROR', message + (error ? (": " + error.message + "\n" + error.stack) : ""));
        }
    }

    // 关闭日志
    public close(): void {
        if (this.logFile) {
            this.info('Closing log file');
            this.logFile.end();
            this.logFile = null;
            this.isFileReady = false;
        }
    }

    // 强制将所有待写入的日志刷新到磁盘
    public flush(): Promise<void> {
        return new Promise<void>((resolve) => {
            if (!this.logFile || !this.isFileReady) {
                resolve();
                return;
            }

            this.logFile.once('drain', () => {
                resolve();
            });

            // 也设置一个超时，以防 'drain' 事件未触发
            setTimeout(() => {
                resolve();
            }, 1000);
        });
    }
}

// 创建单例记录器实例
const logger = new Logger();

// 导出单例和类型
export { logger };
export default logger;