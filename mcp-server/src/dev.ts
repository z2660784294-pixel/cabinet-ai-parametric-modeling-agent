import { Command } from 'commander';
import { startMCPServer } from './commands/start';

const program = new Command();

program
    .name('parametric-mcp-server')
    .description('Parametric MCP Server with WebSocket Bridge')

// 启动服务命令
program
    .command('start')
    .description('Start the MCP server and WebSocket bridge')
    .action(async () => {
        await startMCPServer({ dev: true });
    });

// 默认命令（如果没有指定命令则启动服务器）
if (process.argv.length <= 2) {
    process.argv.push('start');
}

program.parse();