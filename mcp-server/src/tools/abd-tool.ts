// src/tools/abd-tool.ts
// ABD（Assembly Brief Description）工具集 —— 由 image-abd MCP 暴露。
//
// 三个工具按 LLM 在 requirement-analysis 流程里的调用顺序排列：
//   1. get_image_analysis_guide  → 返回 domain.md（图像分析领域知识）
//   2. get_abd_template          → 返回 template.md（ABD 三段式字段契约）
//   3. get_abd_examples          → 返回 few-shot 样例（MVP 占位）
//
// 所有工具按 `category` 参数从 abd_library/categories/<slug>/ 读取资源。
import { z } from 'zod';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { Context } from '../types';
import logger from '../lib/logger';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 运行时 __dirname = dist/tools，因此 abd_library 在 ../..
const ABD_CATEGORIES_DIR = path.resolve(__dirname, '..', '..', 'abd_library', 'categories');
const DEFAULT_CATEGORY = 'floor-to-ceiling';

/**
 * 在指定类目目录下读取一份资源文件。
 * 失败返回结构化错误字符串（资源缺失 / 类目不存在），LLM 端按需识别。
 */
function loadCategoryResource(slug: string, filename: string): string {
    const root = path.join(ABD_CATEGORIES_DIR, slug);
    if (!fs.existsSync(root)) {
        const available = fs.existsSync(ABD_CATEGORIES_DIR)
            ? fs.readdirSync(ABD_CATEGORIES_DIR)
                .filter(n => fs.statSync(path.join(ABD_CATEGORIES_DIR, n)).isDirectory())
                .join(', ')
            : '(categories dir missing)';
        const msg = `Category not found: ${slug}. Available categories: ${available || '(none)'}`;
        logger.error(msg);
        return msg;
    }

    const file = path.join(root, filename);
    if (!fs.existsSync(file)) {
        const msg = `Resource missing in category "${slug}": ${filename}`;
        logger.error(msg);
        return msg;
    }

    return fs.readFileSync(file, 'utf-8').trim();
}

// ─────────────────────────────────────────────────────────────────────────────
// Tool 1: get_image_analysis_guide
// 返回 domain.md，LLM 在分析图像前调用，理解单元柜语义类型 + 识别规则 + 反例。
// ─────────────────────────────────────────────────────────────────────────────
export const getImageAnalysisGuide = {
    name: 'get_image_analysis_guide',
    description:
        '获取指定类目的图像分析领域知识（domain.md）：单元柜语义类型、识别规则、反例。LLM 在分析图像前调用。',
    parameters: z.object({
        category: z
            .string()
            .optional()
            .describe(`类目 slug，对应 abd_library/categories/<slug>/。缺省 ${DEFAULT_CATEGORY}（一柜到顶衣柜）`)
    }),
    execute: async (args: { category?: string }, _context: Context): Promise<string> => {
        const slug = args.category || DEFAULT_CATEGORY;
        logger.info(`Tool executed: get_image_analysis_guide (category=${slug})`);
        return loadCategoryResource(slug, 'domain.md');
    }
};

// ─────────────────────────────────────────────────────────────────────────────
// Tool 2: get_abd_template
// 返回 template.md，LLM 在产出 ABD 草稿（步骤 3）时调用，作为字段契约骨架。
// ─────────────────────────────────────────────────────────────────────────────
export const getAbdTemplate = {
    name: 'get_abd_template',
    description:
        '获取指定类目的 ABD 模板（template.md）：frontmatter + 三段式 YAML 字段契约 + 自检清单。LLM 在产出 ABD 草稿时调用。',
    parameters: z.object({
        category: z
            .string()
            .optional()
            .describe(`类目 slug，对应 abd_library/categories/<slug>/。缺省 ${DEFAULT_CATEGORY}（一柜到顶衣柜）`)
    }),
    execute: async (args: { category?: string }, _context: Context): Promise<string> => {
        const slug = args.category || DEFAULT_CATEGORY;
        logger.info(`Tool executed: get_abd_template (category=${slug})`);
        return loadCategoryResource(slug, 'template.md');
    }
};

// ─────────────────────────────────────────────────────────────────────────────
// Tool 3: get_abd_examples
// MVP 占位实现：返回固定提示文案。
// 后续实现方向：
//   - 全量返回 few-shot/*.md
//   - 按 mode 过滤（baseline / diff / all）
//   - 进阶：根据当前 ABD 草稿做相似度筛选返回 Top-K
// ─────────────────────────────────────────────────────────────────────────────
export const getAbdExamples = {
    name: 'get_abd_examples',
    description:
        '获取指定类目的 ABD 参考样例。MVP 阶段返回空提示，具体策略后续实现。LLM 调用此工具应能优雅跳过。',
    parameters: z.object({
        category: z
            .string()
            .optional()
            .describe(`类目 slug，对应 abd_library/categories/<slug>/。缺省 ${DEFAULT_CATEGORY}（一柜到顶衣柜）`),
        mode: z
            .enum(['baseline', 'diff', 'all'])
            .optional()
            .describe('返回模式：baseline=仅基线 / diff=仅差量样例 / all=全部。MVP 阶段未生效。')
    }),
    execute: async (
        args: { category?: string; mode?: 'baseline' | 'diff' | 'all' },
        _context: Context
    ): Promise<string> => {
        const slug = args.category || DEFAULT_CATEGORY;
        const mode = args.mode || 'all';
        logger.info(`Tool executed: get_abd_examples (category=${slug}, mode=${mode}) — MVP placeholder`);

        return `[get_abd_examples MVP 占位] ABD 样例服务尚未实现，请暂时跳过此步骤。\n类目=${slug}，请求模式=${mode}。\n后续会从 abd_library/categories/${slug}/few-shot/ 加载样例。`;
    }
};
