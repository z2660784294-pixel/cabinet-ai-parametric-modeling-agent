import { randomUUID } from 'crypto';
import { ExporterWorker } from "./handler.js";
import { compressArrayBufferFiles } from './compress.js';


/**
 * 将 GLB 文件转换为 OBJ 格式并压缩
 * @param {string} glbUrl - GLB 文件的 URL
 * @returns {Promise<{zipBuffer:any,boundingBox:any}>} - 压缩后的文件内容
 */
export async function gltf2obj(glbUrl, onProgress) {
    const data = {};
    data.file_name = "test.glb";
    data.convert_type = "obj";
    data.url = glbUrl;
    data.gid = randomUUID();
    data.urlType = 1;

    const {
        files,
        boundingBox
    } = await new Promise((res, rej) => {
        const exporterWorker = new ExporterWorker();
        exporterWorker.export(data, {
            onProgress,
            onError(error) {
                rej(error);
            },
            onSuccess(files, boundingBox) {
                res({
                    files,
                    boundingBox
                });
            }
        });
    });

    // 将导出的文件映射为压缩需要的格式
    const buffer = await compressArrayBufferFiles(
        files.map(f => ({ name: f.name, content: f.content }))
    );

    return {
        zipBuffer: buffer,
        boundingBox
    };
}