import chalk from 'chalk';
import figures from 'figures';

export function printServerInfo(
    title: string,
    items: { label: string; value: string | number }[],
    instruction?: { icon?: string; text: string; value?: string | number }
) {
    // 清空一行
    const emptyLine = () => console.log('');

    emptyLine();
    console.log(chalk.bold.greenBright(`${figures.star} ${title}`));
    emptyLine();

    // 打印每个项目
    items.forEach(item => {
        console.log(`  ${chalk.cyan(item.label)} ${chalk.bold.white(item.value)}`);
    });

    emptyLine();

    // 打印说明（如果有）
    if (instruction) {
        const icon = instruction.icon || figures.pointer;
        const value = instruction.value !== undefined ? String(instruction.value) : '';
        const text = instruction.text.replace('VALUE', value);

        console.log(chalk.yellow(`  ${figures.info} ${chalk.bold('Connection Instructions:')}`));
        console.log(`  ${icon} ${chalk.greenBright(text)}`);
        emptyLine();
    }

    // 添加分隔线
    console.log(chalk.gray('─'.repeat(process.stdout.columns || 80)));
    emptyLine();
}