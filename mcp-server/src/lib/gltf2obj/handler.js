import * as OV from './engine/main.js';
export class ExporterWorker {
    constructor() {
        this.settings = new OV.ImportSettings()
        this.loader = new OV.ThreeModelLoader()
        this.exporterSettings = new OV.ExporterSettings()
        this.exporter = new OV.Exporter();
    }
    export(req, listeners) {
        let file_name = req.file_name
        // this.storage.startExport(req.gid, req.request_id, req.convert_type)
        let inputFiles = []
        if (req.urlType == 2) {
            inputFiles = [new OV.InputFile(file_name, OV.FileSource.File, req.url)]
        } else {
            inputFiles = [new OV.InputFile(file_name, OV.FileSource.Url, req.url)]
        }
        this.loader.LoadModel(inputFiles, this.settings, {
            onLoadStart: () => { },
            onFileListProgress: (current, total) => {
                // let msg = current + "," + total
                // this.storage.exportStage(req.gid, "FileListProgress", msg)
            },
            onFileLoadProgress: (current, total) => {
                // let msg = current + "," + total
                // this.storage.exportStage(req.gid, "FileLoadProgress", msg)
                if (listeners.onProgress) listeners.onProgress(Math.ceil(current * 100 / total))
            },
            onImportStart: () => {
                // let msg = "Importing model..."
                // this.storage.exportStage(req.gid, "ImportStart", msg)
            },
            onSelectMainFile: (fileNames, selectFile) => {

            },
            onImportSuccess: (importResult) => {
            },
            onModelFinished: (importResult, threeObject) => {
                // let msg = "Exporting model..."
                // this.storage.exportStage(req.gid, "ExportStart", msg)
                let model = importResult.model;
                this.exporter.Export(model, this.exporterSettings, OV.FileFormat.Text, req.convert_type, {
                    onError: () => {
                        // this.storage.executionErr(req.gid, "ExportStart", "")
                        if (listeners.onError) listeners.onError(new Error("ExportStart"));
                    },
                    onSuccess: (files, boundingBox) => {
                        if (files.length < 1) {
                            return
                        }
                        if (listeners.onSuccess) listeners.onSuccess(files, boundingBox);
                        // this.storage.executionSuccess(req.gid, req.save_path, Buffer.from(file.GetBufferContent()))
                    }
                })
            },
            onLoadError: (importError) => {
                // this.storage.executionErr(req.gid, "importError", importError)
                if (listeners.onError) listeners.onError(importError);
            },
            onVisualizationStart: () => { }
        })
    }
}