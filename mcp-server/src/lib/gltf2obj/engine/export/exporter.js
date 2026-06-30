import { ExporterModel } from './exportermodel.js';
import { ExporterObj } from './exporterobj.js';

export class Exporter {
    constructor() {
        this.exporters = [
            new ExporterObj(),
        ];
    }

    AddExporter(exporter) {
        this.exporters.push(exporter);
    }

    Export(model, settings, format, extension, callbacks) {
        let exporter = null;
        for (let i = 0; i < this.exporters.length; i++) {
            let currentExporter = this.exporters[i];
            if (currentExporter.CanExport(format, extension)) {
                exporter = currentExporter;
                break;
            }
        }
        if (exporter === null) {
            callbacks.onError();
            return;
        }

        let exporterModel = new ExporterModel(model, settings);
        exporter.Export(exporterModel, format, (files) => {
            if (files.length === 0) {
                callbacks.onError();
            } else {
                callbacks.onSuccess(files, exporterModel.boundingBox);
            }
        });
    }
}
