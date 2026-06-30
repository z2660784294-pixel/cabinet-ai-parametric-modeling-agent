import { Command } from 'commander';
import { startMCPServer } from './commands/start';
import { getServerStatus } from './commands/status';

const program = new Command();

program
    .name('parameditor-mcp-server')
    .description('Parameditor MCP Server with WebSocket Bridge')

// 启动服务命令
program
    .command('start')
    .description('Start the MCP servers and WebSocket bridge')
    .option('--stdio', 'Output results via standard input/output')
    .action(async (options) => {
        await startMCPServer({
            stdio: options.stdio
        });
    });

// 查询服务状态命令
program
    .command('status')
    .description('Show the status of all running servers')
    .action(async () => {
        await getServerStatus();
    });

// 获取端口号命令
program
    .command('port')
    .description('Get the port of the running WebSocket bridge')
    .option('--url', 'Output as WebSocket URL instead of just port number')
    .action(async (options) => {
        await getServerStatus({
            portOnly: true,
            asUrl: options.url
        });
    });

// 默认命令（如果没有指定命令则启动服务器）
if (process.argv.length <= 2) {
    process.argv.push('start');
}

await program.parseAsync(process.argv);