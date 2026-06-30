#!/usr/bin/env node

// 使用 npx tsx 运行 TypeScript 源文件
/* eslint-disable @typescript-eslint/no-var-requires */
const { sync: spawnSync } = require('cross-spawn');
const path = require('path');

// 找到项目根目录的 src/cli.ts 文件
const cliPath = path.resolve(__dirname, './src/cli.ts');

const args = process.argv.slice(2);

const result = spawnSync('npx', ['tsx', cliPath, ...args], {
    stdio: 'inherit',
    env: {
        ...process.env,
    },
});

// 使用相同的退出码
process.exit(result.status || 0);