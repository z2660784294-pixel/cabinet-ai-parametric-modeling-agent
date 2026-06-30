
/**
 * Tripo3D 任务状态响应接口
 */
export interface Tripo3DTaskStatusResponse {
    code: number;
    data: {
        /** 任务ID */
        task_id: string;
        /** 任务类型 */
        type: string;
        /** 任务状态 */
        status: 'queued' | 'running' | 'success' | 'failed' | 'cancelled' | 'unknown';
        /** 输入参数 */
        input: {
            prompt: string;
            [key: string]: any;
        };
        /** 输出数据 */
        output: {
            /** 模型下载URL */
            model?: string;
            /** 基础模型下载URL */
            base_model?: string;
            /** PBR模型下载URL */
            pbr_model?: string;
            /** 渲染图像URL */
            rendered_image?: string;
            /** 其他可能的输出 */
            [key: string]: any;
        };
        /** 进度（0-100） */
        progress: number;
        running_left_time?: number;
        /** 创建时间（时间戳） */
        create_time: number;
    }
}