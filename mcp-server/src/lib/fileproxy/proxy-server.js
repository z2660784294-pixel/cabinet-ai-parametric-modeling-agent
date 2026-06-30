import express from 'express';
import axios from 'axios';
import cors from 'cors';
import { URL, fileURLToPath } from 'url';
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';
import { gltf2obj } from '../gltf2obj/index.js'; // 导入GLB转OBJ的方法

// 在ES模块中获取__dirname的等效方法
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;

// 启用CORS
app.use(cors());

// 设置缓存目录
const cacheDir = path.join(__dirname, 'cache');
if (!fs.existsSync(cacheDir)) {
    fs.mkdirSync(cacheDir);
}

// 设置上传目录
const uploadsDir = path.join(__dirname, 'uploads');
if (!fs.existsSync(uploadsDir)) {
    fs.mkdirSync(uploadsDir);
}

// 创建安全的缓存文件名 - 使用哈希而非Base64编码
const createSafeCacheFilename = (url) => {
    // 使用MD5哈希创建固定长度的文件名
    const hash = crypto.createHash('md5').update(url).digest('hex');
    // 添加URL的扩展名以便更容易识别文件类型
    try {
        const extension = path.extname(new URL(url).pathname).toLowerCase();
        // 如果有合法扩展名，则添加，否则使用.bin
        return extension && extension.length > 0 && extension.length < 10
            ? `${hash}${extension}`
            : `${hash}.bin`;
    } catch (e) {
        // 如果URL解析失败，直接返回哈希
        return `${hash}.bin`;
    }
};

// 根据URL获取内容类型
const getContentTypeFromURL = (sourceUrl) => {
    try {
        const extension = path.extname(new URL(sourceUrl).pathname).toLowerCase();
        const mimeTypes = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.svg': 'image/svg+xml',
            '.pdf': 'application/pdf',
            '.json': 'application/json',
            '.txt': 'text/plain',
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.mp3': 'audio/mpeg',
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.glb': 'model/gltf-binary',
            '.gltf': 'model/gltf+json',
            '.obj': 'application/octet-stream',
            '.fbx': 'application/octet-stream'
        };
        return mimeTypes[extension] || null;
    } catch (e) {
        return null;
    }
};

// 主要代理端点
app.get('/proxy', async (req, res) => {
    try {
        // 获取源文件URL参数
        let { url: sourceUrl } = req.query;
        try {
            // 尝试去掉双引号
            sourceUrl = JSON.parse(sourceUrl);
        } catch (e) { }
        if (!sourceUrl) {
            return res.status(400).json({ error: '缺少url参数' });
        }
        // 验证URL
        try {
            new URL(sourceUrl);
        } catch (e) {
            return res.status(400).json({ error: '无效的URL' });
        }
        // 为缓存创建安全的文件名
        const cacheFilename = createSafeCacheFilename(sourceUrl);
        const cachePath = path.join(cacheDir, cacheFilename);
        // 记录URL和缓存文件的映射（调试用）
        // console.log(`URL: ${sourceUrl}`);
        // console.log(`缓存文件: ${cacheFilename}`);
        // 检查缓存
        if (fs.existsSync(cachePath)) {
            const stats = fs.statSync(cachePath);
            const fileAge = Date.now() - stats.mtime.getTime();
            // 如果缓存小于1小时，直接使用缓存
            if (fileAge < 3600000) {
                // console.log(`使用缓存: ${sourceUrl}`);
                const contentType = getContentTypeFromURL(sourceUrl);
                if (contentType) {
                    res.setHeader('Content-Type', contentType);
                }
                return fs.createReadStream(cachePath).pipe(res);
            }
        }
        // 获取远程文件
        // console.log(`获取文件: ${sourceUrl}`);
        const response = await axios({
            method: 'get',
            url: sourceUrl,
            responseType: 'stream',
            timeout: 30000,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        });
        // 设置响应头
        const { headers } = response;
        const contentType = headers['content-type'];
        if (contentType) {
            res.setHeader('Content-Type', contentType);
        }
        // 设置其他响应头
        Object.entries(headers)
            .filter(([key]) => !['transfer-encoding', 'connection'].includes(key.toLowerCase()))
            .forEach(([key, value]) => {
                res.setHeader(key, value);
            });
        // 将文件流同时写入缓存和响应
        const cacheStream = fs.createWriteStream(cachePath);
        response.data.pipe(cacheStream);
        response.data.pipe(res);
        // 错误处理
        cacheStream.on('error', (err) => {
            // console.error(`缓存写入错误: ${err.message}`);
            if (!res.headersSent) {
                res.status(500).json({ error: '服务器缓存错误' });
            }
        });
    } catch (error) {
        // console.error('代理请求错误:', error.message);
        // 检查请求是否已经发送响应
        if (!res.headersSent) {
            res.status(500).json({
                error: '无法获取请求的文件',
                details: error.message,
                url: req.query.url
            });
        }
    }
});

// ====== 新增: GLB到OBJ的转换接口 ======

/**
 * GLB到OBJ转换接口 - 通过URL
 * 通过提供GLB文件的URL将其转换为OBJ
 */
app.get('/convert/glb-to-obj', async (req, res) => {
    try {
        // 获取GLB文件URL
        let { url: glbUrl } = req.query;
        try {
            // 尝试去掉双引号
            glbUrl = JSON.parse(glbUrl);
        } catch (e) { }

        if (!glbUrl) {
            return res.status(400).json({ error: '缺少GLB文件URL' });
        }

        // 验证URL
        try {
            new URL(glbUrl);
        } catch (e) {
            return res.status(400).json({ error: '无效的URL' });
        }

        // 验证是否为GLB文件
        const urlExt = path.extname(new URL(glbUrl).pathname).toLowerCase();
        if (urlExt !== '.glb') {
            return res.status(400).json({ error: '提供的URL必须是GLB文件' });
        }

        // console.log("download file:", urlExt);

        // 使用gltf2obj转换文件
        const { zipBuffer, boundingBox } = await gltf2obj(glbUrl);
        // console.log("boundingBox", JSON.stringify(boundingBox));

        // 从URL获取文件名用于下载 
        const urlFileName = path.basename(new URL(glbUrl).pathname);
        const downloadName = path.basename(urlFileName, '.glb') + '.zip';

        res.setHeader('Content-Type', 'application/zip');
        // 设置响应头，以便浏览器下载文件
        res.setHeader('Content-Disposition', `attachment; filename="${downloadName}"`);
        res.setHeader("Access-Control-Expose-Headers", "X-Bounding-Box")
        res.setHeader('X-Bounding-Box', JSON.stringify(boundingBox));
        res.set('Cache-Control', 'no-store');
        // console.log("send", zipBuffer.length);
        // 发送转换后的ZIP文件
        res.send(zipBuffer);
    } catch (error) {
        // console.error('GLB转OBJ处理出错:', error);
        res.status(500).json({
            error: '转换GLB到OBJ时出错',
            details: error.message
        });
    }
});

// 清理缓存的路由
app.get('/clear-cache', (req, res) => {
    const { key: apiKey } = req.query;
    // 简单的API密钥验证
    if (apiKey !== process.env.ADMIN_API_KEY) {
        return res.status(403).json({ error: '未授权' });
    }
    try {
        const files = fs.readdirSync(cacheDir);
        let deletedCount = 0;
        files.forEach(file => {
            fs.unlinkSync(path.join(cacheDir, file));
            deletedCount++;
        });
        res.json({ success: `已清除 ${deletedCount} 个缓存文件` });
    } catch (error) {
        res.status(500).json({ error: `清除缓存时出错: ${error.message}` });
    }
});

// 缓存信息路由
app.get('/cache-info', (req, res) => {
    try {
        const files = fs.readdirSync(cacheDir);
        let totalSize = 0;
        const fileDetails = [];
        files.forEach(file => {
            const filePath = path.join(cacheDir, file);
            const stats = fs.statSync(filePath);
            totalSize += stats.size;
            fileDetails.push({
                name: file,
                size: (stats.size / 1024).toFixed(2) + ' KB',
                created: stats.birthtime.toISOString()
            });
        });
        res.json({
            totalFiles: files.length,
            totalSize: (totalSize / (1024 * 1024)).toFixed(2) + ' MB',
            details: fileDetails.slice(0, 50) // 只返回前50个文件信息以避免响应过大
        });
    } catch (error) {
        res.status(500).json({ error: `获取缓存信息时出错: ${error.message}` });
    }
});
// 服务器状态检查，修改添加新功能描述(续)
app.get('/', (req, res) => {
    res.send(`
    <html>
      <head><title>文件转发与转换服务</title>
      <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { color: #333; }
        h2 { color: #555; margin-top: 20px; }
        pre { background: #f4f4f4; padding: 10px; border-radius: 5px; }
        code { font-family: monospace; }
        .endpoint { margin-bottom: 20px; }
      </style>
      </head>
      <body>
        <h1>文件转发与转换服务</h1>
        <p>这是一个文件代理和转换服务，用于解决跨域资源访问问题并提供文件格式转换功能。</p>
        
        <h2>文件代理：</h2>
        <div class="endpoint">
          <pre><code>GET /proxy?url="https://example.com/path/to/file.ext"</code></pre>
          <p>上面的请求将获取指定URL的文件内容并返回，无需担心跨域限制。</p>
        </div>
        
        <h2>GLB转OBJ转换：</h2>
        <div class="endpoint">
          <h3>通过URL转换：</h3>
          <pre><code>GET /convert/glb-to-obj?url="https://example.com/path/to/model.glb"</code></pre>
          <p>使用指定URL的GLB文件，转换为OBJ格式并以ZIP压缩包返回。</p>
          
          <h3>通过文件上传转换：</h3>
          <pre><code>POST /convert/glb-to-obj</code></pre>
          <p>上传一个GLB文件，表单字段名为'file'，服务器将转换为OBJ格式并以ZIP压缩包返回。</p>
          <p>示例HTML表单：</p>
          <pre><code>&lt;form action="/convert/glb-to-obj" method="post" enctype="multipart/form-data"&gt;
  &lt;input type="file" name="file" accept=".glb"&gt;
  &lt;button type="submit"&gt;转换为OBJ&lt;/button&gt;
&lt;/form&gt;</code></pre>
        </div>
        
        <p>服务状态: 正常运行</p>
      </body>
    </html>
  `);
});

// 启动服务器
const server = app.listen(PORT, () => {
    // console.log(`文件转发与转换服务运行在 http://localhost:${PORT}`);
});

// 处理终止信号
process.on('SIGTERM', () => {
    // console.log('收到终止信号，服务器正在优雅关闭...');
    server.close(() => {
        // console.log('HTTP服务器已关闭，正在完成剩余请求');

        // 清理上传文件夹中的临时文件
        try {
            const files = fs.readdirSync(uploadsDir);
            files.forEach(file => {
                fs.unlinkSync(path.join(uploadsDir, file));
            });
            // console.log('已清理临时文件');
        } catch (err) {
            // console.error('清理临时文件时出错:', err);
        }

        // console.log('资源清理完成，进程将退出');
        process.exit(0);
    });

    // 设置强制退出超时
    setTimeout(() => {
        // console.log('关闭超时，强制退出');
        process.exit(1);
    }, 3000);
});