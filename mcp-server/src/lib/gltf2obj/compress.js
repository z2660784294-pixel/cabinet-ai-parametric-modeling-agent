import JSZip from 'jszip';

/**
 * 将多个已读取为ArrayBuffer的文件压缩成ZIP
 * @param {Array<{name: string, content: ArrayBuffer}>} files - 包含文件信息的数组
 * @returns {Promise<Buffer>} 压缩后的Buffer
 */
export async function compressArrayBufferFiles(files) {
    try {
        // 创建新的ZIP实例
        const zip = new JSZip();

        // 添加文件到ZIP
        for (const fileInfo of files) {
            // JSZip可以直接接受ArrayBuffer作为内容
            zip.file(fileInfo.name, fileInfo.content);
        }

        // 生成ZIP文件
        const zipContent = await zip.generateAsync({
            type: 'nodebuffer',  // Node.js中使用nodebuffer
            compression: 'DEFLATE',
            compressionOptions: {
                level: 9  // 最高压缩级别
            }
        });

        return zipContent;
    } catch (error) {
        console.error('创建ZIP文件时出错:', error instanceof Error ? error.message : String(error));
        throw error;
    }
}