(() => {
  const PROFILE_URL = './api/model_profiles';
  const PRODUCT_URL = './api/model_products';
  const INPUT_URL = './api/input';
  const SUBMIT_URL = './submit';
  const EDGE_HIT_PX = 8;
  const EPSILON = 1e-6;
  const LINE_EPSILON = 1e-5;
  const ACTION_OFFSET_PX = 76;

  const state = {
    canvas: { width: 0, height: 0 },
    cabinetSize: { width: 1200, height: 800 },
    referenceImageUrl: '',
    description: '',
    minCellRatio: 0.04,
    columns: [],
    rows: [],
    selection: null,
    hover: null,
    dragging: null,
    modelMetaById: new Map(),
    previewById: new Map(),
    allModels: [],
    recommendedIds: [],
    imageCache: new Map(),
    layoutBoxes: [],
    layoutOrigin: { x: 0, z: 0 },
    defaultDepth: 400,
    inputName: ''
  };

  const dom = {
    confirmButton: document.getElementById('confirmButton'),
    errorOutput: document.getElementById('errorOutput'),
    descriptionText: document.getElementById('descriptionText'),
    cabinetWidthInput: document.getElementById('cabinetWidthInput'),
    cabinetHeightInput: document.getElementById('cabinetHeightInput'),
    referenceImage: document.getElementById('referenceImage'),
    referenceFallback: document.getElementById('referenceFallback'),
    stage: document.getElementById('stage'),
    canvas: document.getElementById('layoutCanvas'),
    toolbar: document.getElementById('cellToolbar'),
    replaceModal: document.getElementById('replaceModal'),
    replaceList: document.getElementById('replaceList'),
    replaceSearch: document.getElementById('replaceSearch'),
    closeReplaceButton: document.getElementById('closeReplaceButton')
  };

  const ctx = dom.canvas.getContext('2d');

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function round6(value) {
    return Number(value.toFixed(6));
  }

  function setMessage(text, ok = false) {
    if (!dom.errorOutput) {
      return;
    }
    dom.errorOutput.textContent = text || '';
    dom.errorOutput.classList.toggle('ok', ok);
  }

  function flattenUnits(units) {
    return units;
  }

  function parseOccupiedCell(cell, unitIndex, cellIndex) {
    const row = Number(cell?.row ?? cell?.r ?? cell?.[0]);
    const column = Number(cell?.column ?? cell?.col ?? cell?.c ?? cell?.[1]);
    if (!Number.isInteger(row) || !Number.isInteger(column) || row < 1 || column < 1) {
      throw new Error(`units[${unitIndex}].cells[${cellIndex}] 必须包含从 1 开始的 row 与 column。`);
    }
    return { row, column };
  }

  function getUnitCells(unit) {
    return unit.cells;
  }

  function readVector(unit, fieldName, unitIndex) {
    const vector = unit[fieldName];
    if (!vector || typeof vector !== 'object') {
      throw new Error(`units 扁平序号 ${unitIndex} 的 ${fieldName} 必填。`);
    }
    ['x', 'y', 'z'].forEach((axis) => {
      if (!Number.isFinite(Number(vector[axis]))) {
        throw new Error(`units 扁平序号 ${unitIndex} 的 ${fieldName}.${axis} 必须是数值。`);
      }
    });
    return {
      x: Number(vector.x),
      y: Number(vector.y),
      z: Number(vector.z)
    };
  }

  function unitToRealBbox(unit, unitIndex) {
    const position = readVector(unit, 'position', unitIndex);
    const size = readVector(unit, 'size', unitIndex);
    if (size.x <= 0) {
      throw new Error(`units 扁平序号 ${unitIndex} 的 size.x 必须 > 0。`);
    }
    if (size.y <= 0) {
      throw new Error(`units 扁平序号 ${unitIndex} 的 size.y 必须 > 0。`);
    }
    if (size.z <= 0) {
      throw new Error(`units 扁平序号 ${unitIndex} 的 size.z 必须 > 0。`);
    }
    return {
      x: position.x,
      y: position.z,
      w: size.x,
      h: size.z,
      depth: size.y,
      depthOffset: position.y
    };
  }

  function normalizeOccupiedCells(unit, unitIndex) {
    const sourceCells = getUnitCells(unit);
    if (!Array.isArray(sourceCells) || sourceCells.length < 1) {
      throw new Error(`units[${unitIndex}].cells 必填，且必须是非空数组。`);
    }
    const cells = sourceCells.map((cell, cellIndex) => parseOccupiedCell(cell, unitIndex, cellIndex));
    const unique = new Set(cells.map((cell) => `${cell.row}:${cell.column}`));
    if (unique.size !== cells.length) {
      throw new Error(`units[${unitIndex}].cells 不能包含重复格子。`);
    }
    const rows = cells.map((cell) => cell.row);
    const columns = cells.map((cell) => cell.column);
    const rowStart = Math.min(...rows);
    const rowEnd = Math.max(...rows);
    const columnStart = Math.min(...columns);
    const columnEnd = Math.max(...columns);
    const expectedCount = (rowEnd - rowStart + 1) * (columnEnd - columnStart + 1);
    if (expectedCount !== cells.length) {
      throw new Error(`units[${unitIndex}].cells 必须组成连续矩形。`);
    }
    for (let row = rowStart; row <= rowEnd; row += 1) {
      for (let column = columnStart; column <= columnEnd; column += 1) {
        if (!unique.has(`${row}:${column}`)) {
          throw new Error(`units[${unitIndex}].cells 必须组成连续矩形。`);
        }
      }
    }
    return { cells, rowStart, rowEnd, columnStart, columnEnd };
  }

  function normalize(values, minValue = 0) {
    const safe = values.map((value) => Math.max(value, minValue));
    const total = safe.reduce((sum, value) => sum + value, 0);
    if (total <= 0) {
      return safe.map(() => 1 / safe.length);
    }
    return safe.map((value) => value / total);
  }

  function normalizeGrid() {
    const heights = normalize(state.rows.map((row) => row.heightRatio), state.minCellRatio);
    state.rows.forEach((row, index) => {
      row.heightRatio = heights[index];
    });
    const widths = normalize(state.columns.map((column) => column.widthRatio), state.minCellRatio);
    state.columns.forEach((column, index) => {
      column.widthRatio = widths[index];
    });
  }

  function cloneCell(cell) {
    return {
      ...cell,
      candidates: Array.isArray(cell.candidates) ? [...cell.candidates] : []
    };
  }

  function cloneGrid() {
    return {
      columns: state.columns.map((column) => ({ ...column })),
      rows: state.rows.map((row) => ({
        heightRatio: row.heightRatio,
        cells: row.cells.map(cloneCell)
      }))
    };
  }

  function cellCount() {
    return getAnchorRecords().length;
  }

  function normalizeLines(values) {
    const sorted = values
      .map((value) => clamp(Number(value), 0, 1))
      .sort((a, b) => a - b);
    const lines = [];
    sorted.forEach((value) => {
      if (!lines.length || Math.abs(value - lines[lines.length - 1]) > LINE_EPSILON) {
        lines.push(value);
      } else {
        lines[lines.length - 1] = (lines[lines.length - 1] + value) / 2;
      }
    });
    if (Math.abs(lines[0]) > LINE_EPSILON) {
      lines.unshift(0);
    } else {
      lines[0] = 0;
    }
    if (Math.abs(lines[lines.length - 1] - 1) > LINE_EPSILON) {
      lines.push(1);
    } else {
      lines[lines.length - 1] = 1;
    }
    return lines;
  }

  function findLineIndex(lines, value) {
    const index = lines.findIndex((line) => Math.abs(line - value) <= LINE_EPSILON);
    if (index === -1) {
      throw new Error('输入布局边界无法对齐为表格网格。');
    }
    return index;
  }

  function emptyCell() {
    return {
      obsBrandGoodId: '',
      previewImageUrl: '',
      candidates: [],
      rowSpan: 1,
      colSpan: 1
    };
  }

  function createCellFromUnit(unit) {
    return {
      name: unit.name || '',
      obsBrandGoodId: unit.obsBrandGoodId || '',
      previewImageUrl: unit.previewImageUrl || '',
      candidates: (Array.isArray(unit.candidates) ? unit.candidates : unit.recommendedObsBrandGoodIds || []).filter(Boolean).map(String),
      depth: unit.depth,
      depthOffset: unit.depthOffset,
      rotate: unit.rotate,
      scale: unit.scale,
      cabinetSize: unit.cabinetSize,
      rowSpan: 1,
      colSpan: 1
    };
  }

  function createCellFromSource(source) {
    return {
      name: source?.name || '',
      obsBrandGoodId: source?.obsBrandGoodId || '',
      previewImageUrl: source?.previewImageUrl || '',
      candidates: Array.isArray(source?.candidates) ? [...source.candidates] : [],
      depth: source?.depth,
      depthOffset: source?.depthOffset,
      rotate: source?.rotate,
      scale: source?.scale,
      cabinetSize: source?.cabinetSize,
      rowSpan: 1,
      colSpan: 1
    };
  }

  function validateInput(input) {
    if (!input || typeof input !== 'object') {
      throw new Error('输入必须是 JSON object。');
    }
    const cabinetSize = extractCabinetSize(input);
    if (!Array.isArray(input.units) || input.units.length < 1 || !input.units.every((unit) => unit && !Array.isArray(unit) && typeof unit === 'object')) {
      throw new Error('units 必填，且必须是非空一维对象数组。');
    }
    const units = flattenUnits(input.units);
    const occupied = new Map();
    if (units.length < 1) {
      throw new Error('units 至少需要 1 个单元柜。');
    }
    units.forEach((unit, index) => {
      if (!unit || typeof unit.obsBrandGoodId !== 'string' || !unit.obsBrandGoodId.trim()) {
        throw new Error(`units 扁平序号 ${index} 的 obsBrandGoodId 必须是非空字符串。`);
      }
      const bbox = unitToRealBbox(unit, index);
      if (bbox.x < state.layoutOrigin.x || bbox.y < state.layoutOrigin.z || bbox.x + bbox.w > state.layoutOrigin.x + cabinetSize.width || bbox.y + bbox.h > state.layoutOrigin.z + cabinetSize.height) {
        throw new Error(`units 扁平序号 ${index} 的 position/size 必须在 cabinetSize 范围内。`);
      }
      normalizeOccupiedCells(unit, index).cells.forEach((cell) => {
        const key = `${cell.row}:${cell.column}`;
        if (occupied.has(key)) {
          throw new Error(`units[${index}].cells 与 units[${occupied.get(key)}] 重叠。`);
        }
        occupied.set(key, index);
      });
    });
  }

  function normalizeUnit(unit, index) {
    const bbox = unitToRealBbox(unit, index);
    const cabinetWidth = Math.max(1, Number(state.cabinetSize.width) || 1200);
    const cabinetHeight = Math.max(1, Number(state.cabinetSize.height) || 800);
    const x = clamp((bbox.x - state.layoutOrigin.x) / cabinetWidth, 0, 1);
    const y = clamp((bbox.y - state.layoutOrigin.z) / cabinetHeight, 0, 1);
    const w = clamp(bbox.w / cabinetWidth, 0, 1);
    const h = clamp(bbox.h / cabinetHeight, 0, 1);
    return {
      name: unit.name || '',
      obsBrandGoodId: unit.obsBrandGoodId.trim(),
      previewImageUrl: unit.previewImageUrl || '',
      candidates: (Array.isArray(unit.candidates) ? unit.candidates : unit.recommendedObsBrandGoodIds || []).filter(Boolean).map(String),
      occupied: normalizeOccupiedCells(unit, index),
      depth: bbox.depth,
      depthOffset: bbox.depthOffset,
      rotate: unit.rotate,
      scale: unit.scale,
      cabinetSize: unit.cabinetSize,
      bbox: {
        x,
        y,
        w: Math.min(w, 1 - x),
        h: Math.min(h, 1 - y)
      }
    };
  }

  function bboxToGrid(units) {
    const normalized = units.map((unit, index) => normalizeUnit(unit, index));
    const maxRow = Math.max(...normalized.map((unit) => unit.occupied.rowEnd));
    const maxColumn = Math.max(...normalized.map((unit) => unit.occupied.columnEnd));
    const columnEdges = Array.from({ length: maxColumn + 1 }, () => null);
    const rowEdges = Array.from({ length: maxRow + 1 }, () => null);
    columnEdges[0] = 0;
    columnEdges[maxColumn] = 1;
    rowEdges[0] = 0;
    rowEdges[maxRow] = 1;

    normalized.forEach((unit) => {
      const { rowStart, rowEnd, columnStart, columnEnd } = unit.occupied;
      const xStart = unit.bbox.x;
      const xEnd = unit.bbox.x + unit.bbox.w;
      const yStart = unit.bbox.y;
      const yEnd = unit.bbox.y + unit.bbox.h;
      const existingXStart = columnEdges[columnStart - 1];
      const existingXEnd = columnEdges[columnEnd];
      const existingYStart = rowEdges[rowStart - 1];
      const existingYEnd = rowEdges[rowEnd];
      if (existingXStart !== null && Math.abs(existingXStart - xStart) > LINE_EPSILON) {
        throw new Error('输入布局的 cells 与 position/size 列边界不一致。');
      }
      if (existingXEnd !== null && Math.abs(existingXEnd - xEnd) > LINE_EPSILON) {
        throw new Error('输入布局的 cells 与 position/size 列边界不一致。');
      }
      if (existingYStart !== null && Math.abs(existingYStart - yStart) > LINE_EPSILON) {
        throw new Error('输入布局的 cells 与 position/size 行边界不一致。');
      }
      if (existingYEnd !== null && Math.abs(existingYEnd - yEnd) > LINE_EPSILON) {
        throw new Error('输入布局的 cells 与 position/size 行边界不一致。');
      }
      columnEdges[columnStart - 1] = xStart;
      columnEdges[columnEnd] = xEnd;
      rowEdges[rowStart - 1] = yStart;
      rowEdges[rowEnd] = yEnd;
    });

    const xLines = normalizeLines(columnEdges.map((edge, index) => edge ?? index / maxColumn));
    const yLines = normalizeLines(rowEdges.map((edge, index) => edge ?? index / maxRow));
    const columns = xLines.slice(0, -1).map((line, index) => ({ widthRatio: xLines[index + 1] - line }));
    const rows = yLines.slice(0, -1).map((line, index) => ({
      heightRatio: yLines[index + 1] - line,
      cells: Array.from({ length: columns.length }, () => null)
    }));

    normalized.forEach((unit) => {
      const rowStart = unit.occupied.rowStart - 1;
      const rowEnd = unit.occupied.rowEnd;
      const columnStart = unit.occupied.columnStart - 1;
      const columnEnd = unit.occupied.columnEnd;
      const anchor = createCellFromUnit(unit);
      anchor.rowSpan = rowEnd - rowStart;
      anchor.colSpan = columnEnd - columnStart;
      for (let rowIndex = rowStart; rowIndex < rowEnd; rowIndex += 1) {
        for (let columnIndex = columnStart; columnIndex < columnEnd; columnIndex += 1) {
          if (rows[rowIndex].cells[columnIndex]) {
            throw new Error('输入布局存在重叠单元格，无法转换为表格。');
          }
          rows[rowIndex].cells[columnIndex] = rowIndex === rowStart && columnIndex === columnStart
            ? anchor
            : { hidden: true, anchorRow: rowStart, anchorColumn: columnStart };
        }
      }
    });

    rows.forEach((row) => {
      row.cells = row.cells.map((cell) => cell || emptyCell());
    });

    return { rows, columns };
  }

  function getColumnOffsets(columns = state.columns) {
    const offsets = [0];
    columns.forEach((column) => {
      offsets.push(offsets[offsets.length - 1] + column.widthRatio);
    });
    offsets[offsets.length - 1] = 1;
    return offsets;
  }

  function getRowOffsets(rows = state.rows) {
    const offsets = [0];
    rows.forEach((row) => {
      offsets.push(offsets[offsets.length - 1] + row.heightRatio);
    });
    offsets[offsets.length - 1] = 1;
    return offsets;
  }

  function isAnchorCell(cell) {
    return cell && cell.hidden !== true;
  }

  function getAnchorAt(rowIndex, columnIndex) {
    const cell = state.rows[rowIndex]?.cells[columnIndex];
    if (!cell) {
      return null;
    }
    if (cell.hidden) {
      const anchor = state.rows[cell.anchorRow]?.cells[cell.anchorColumn];
      return anchor ? { rowIndex: cell.anchorRow, columnIndex: cell.anchorColumn, cell: anchor } : null;
    }
    return { rowIndex, columnIndex, cell };
  }

  function getCellSpanRect(rowIndex, columnIndex) {
    const anchor = getAnchorAt(rowIndex, columnIndex);
    if (!anchor) {
      return null;
    }
    return {
      rowStart: anchor.rowIndex,
      rowEnd: anchor.rowIndex + anchor.cell.rowSpan,
      columnStart: anchor.columnIndex,
      columnEnd: anchor.columnIndex + anchor.cell.colSpan
    };
  }

  function rectIntersects(a, b) {
    return a.rowStart < b.rowEnd && a.rowEnd > b.rowStart && a.columnStart < b.columnEnd && a.columnEnd > b.columnStart;
  }

  function rectContains(outer, inner) {
    return outer.rowStart <= inner.rowStart && outer.rowEnd >= inner.rowEnd && outer.columnStart <= inner.columnStart && outer.columnEnd >= inner.columnEnd;
  }

  function rectEquals(a, b) {
    return a.rowStart === b.rowStart && a.rowEnd === b.rowEnd && a.columnStart === b.columnStart && a.columnEnd === b.columnEnd;
  }

  function normalizeSelection(selection) {
    if (!selection || state.rows.length === 0 || state.columns.length === 0) {
      return null;
    }
    let expanded = {
      rowStart: clamp(Math.min(selection.rowStart, selection.rowEnd), 0, state.rows.length - 1),
      rowEnd: clamp(Math.max(selection.rowStart, selection.rowEnd), 1, state.rows.length),
      columnStart: clamp(Math.min(selection.columnStart, selection.columnEnd), 0, state.columns.length - 1),
      columnEnd: clamp(Math.max(selection.columnStart, selection.columnEnd), 1, state.columns.length)
    };
    let changed = true;
    while (changed) {
      changed = false;
      getAnchorRecords().forEach((record) => {
        const rect = {
          rowStart: record.rowStart,
          rowEnd: record.rowStart + record.cell.rowSpan,
          columnStart: record.columnStart,
          columnEnd: record.columnStart + record.cell.colSpan
        };
        if (rectIntersects(expanded, rect) && !rectContains(expanded, rect)) {
          expanded = {
            rowStart: Math.min(expanded.rowStart, rect.rowStart),
            rowEnd: Math.max(expanded.rowEnd, rect.rowEnd),
            columnStart: Math.min(expanded.columnStart, rect.columnStart),
            columnEnd: Math.max(expanded.columnEnd, rect.columnEnd)
          };
          changed = true;
        }
      });
    }
    return expanded;
  }

  function getAnchorRecords() {
    const records = [];
    state.rows.forEach((row, rowIndex) => {
      row.cells.forEach((cell, columnIndex) => {
        if (isAnchorCell(cell)) {
          records.push({ rowStart: rowIndex, columnStart: columnIndex, cell });
        }
      });
    });
    return records;
  }

  function getAnchorsInSelection(selection = state.selection) {
    if (!selection) {
      return [];
    }
    return getAnchorRecords().filter((record) => rectContains(selection, {
      rowStart: record.rowStart,
      rowEnd: record.rowStart + record.cell.rowSpan,
      columnStart: record.columnStart,
      columnEnd: record.columnStart + record.cell.colSpan
    }));
  }

  function getSingleSelectedAnchor() {
    const anchors = getAnchorsInSelection();
    if (anchors.length !== 1) {
      return null;
    }
    const anchor = anchors[0];
    const rect = {
      rowStart: anchor.rowStart,
      rowEnd: anchor.rowStart + anchor.cell.rowSpan,
      columnStart: anchor.columnStart,
      columnEnd: anchor.columnStart + anchor.cell.colSpan
    };
    return state.selection && rectEquals(state.selection, rect) ? anchor : null;
  }

  function selectionToBbox(selection = state.selection) {
    if (!selection) {
      return null;
    }
    const columnOffsets = getColumnOffsets();
    const rowOffsets = getRowOffsets();
    return {
      x: columnOffsets[selection.columnStart],
      y: rowOffsets[selection.rowStart],
      w: columnOffsets[selection.columnEnd] - columnOffsets[selection.columnStart],
      h: rowOffsets[selection.rowEnd] - rowOffsets[selection.rowStart]
    };
  }

  function gridToUnits() {
    const columnOffsets = getColumnOffsets();
    const rowOffsets = getRowOffsets();
    return getAnchorRecords()
      .sort((a, b) => a.rowStart - b.rowStart || a.columnStart - b.columnStart)
      .map((record) => ({
        obsBrandGoodId: record.cell.obsBrandGoodId,
        rowIndex: record.rowStart,
        columnIndex: record.columnStart,
        cell: record.cell,
        bbox: {
          x: round6(columnOffsets[record.columnStart]),
          y: round6(rowOffsets[record.rowStart]),
          w: round6(columnOffsets[record.columnStart + record.cell.colSpan] - columnOffsets[record.columnStart]),
          h: round6(rowOffsets[record.rowStart + record.cell.rowSpan] - rowOffsets[record.rowStart])
        }
      }));
  }

  function ratioBboxToUnitGeometry(unit) {
    const cabinetWidth = Math.max(1, Number(state.cabinetSize.width) || 1200);
    const cabinetHeight = Math.max(1, Number(state.cabinetSize.height) || 800);
    const depth = Number(unit.cell.depth);
    const depthOffset = Number(unit.cell.depthOffset);
    return {
      position: {
        x: round6(state.layoutOrigin.x + unit.bbox.x * cabinetWidth),
        y: round6(Number.isFinite(depthOffset) ? depthOffset : 0),
        z: round6(state.layoutOrigin.z + unit.bbox.y * cabinetHeight)
      },
      size: {
        x: round6(unit.bbox.w * cabinetWidth),
        y: round6(Number.isFinite(depth) && depth > 0 ? depth : state.defaultDepth),
        z: round6(unit.bbox.h * cabinetHeight)
      }
    };
  }

  function getOccupiedCells(unit) {
    const cells = [];
    for (let row = unit.rowIndex + 1; row <= unit.rowIndex + unit.cell.rowSpan; row += 1) {
      for (let column = unit.columnIndex + 1; column <= unit.columnIndex + unit.cell.colSpan; column += 1) {
        cells.push({ row, column });
      }
    }
    return cells;
  }

  function gridToOutputUnits() {
    return gridToUnits()
      .filter((unit) => unit.obsBrandGoodId)
      .map((unit) => {
        const geometry = ratioBboxToUnitGeometry(unit);
        const output = {
          obsBrandGoodId: unit.obsBrandGoodId,
          position: geometry.position,
          size: geometry.size,
          cells: getOccupiedCells(unit)
        };
        if (unit.cell.name) {
          output.name = unit.cell.name;
        }
        if (unit.cell.cabinetSize) {
          output.cabinetSize = unit.cell.cabinetSize;
        }
        if (unit.cell.rotate) {
          output.rotate = unit.cell.rotate;
        }
        if (unit.cell.scale) {
          output.scale = unit.cell.scale;
        }
        return output;
      });
  }

  function validateGrid({ requireFilled = false } = {}) {
    if (state.rows.length < 1 || state.columns.length < 1) {
      throw new Error('至少需要 1 个单元格。');
    }
    const occupied = state.rows.map(() => Array.from({ length: state.columns.length }, () => false));
    getAnchorRecords().forEach((record) => {
      const { cell, rowStart, columnStart } = record;
      const rowSpan = Number(cell.rowSpan) || 0;
      const colSpan = Number(cell.colSpan) || 0;
      if (rowSpan < 1 || colSpan < 1 || rowStart + rowSpan > state.rows.length || columnStart + colSpan > state.columns.length) {
        throw new Error('表格中存在非法合并范围。');
      }
      if (requireFilled && !cell.obsBrandGoodId) {
        throw new Error('拆分后存在空单元格，请先替换/补齐。');
      }
      for (let rowIndex = rowStart; rowIndex < rowStart + rowSpan; rowIndex += 1) {
        for (let columnIndex = columnStart; columnIndex < columnStart + colSpan; columnIndex += 1) {
          if (occupied[rowIndex][columnIndex]) {
            throw new Error('表格中存在重叠单元格。');
          }
          occupied[rowIndex][columnIndex] = true;
          const slot = state.rows[rowIndex].cells[columnIndex];
          if (rowIndex === rowStart && columnIndex === columnStart) {
            if (slot !== cell) {
              throw new Error('表格锚点状态不一致。');
            }
          } else if (!slot?.hidden || slot.anchorRow !== rowStart || slot.anchorColumn !== columnStart) {
            throw new Error('合并单元格覆盖状态不一致。');
          }
        }
      }
    });
    occupied.forEach((row, rowIndex) => {
      row.forEach((filled, columnIndex) => {
        if (!filled) {
          throw new Error(`表格存在空洞：第 ${rowIndex + 1} 行第 ${columnIndex + 1} 列。`);
        }
      });
    });
    const widthTotal = state.columns.reduce((sum, column) => sum + column.widthRatio, 0);
    const heightTotal = state.rows.reduce((sum, row) => sum + row.heightRatio, 0);
    if (Math.abs(widthTotal - 1) > EPSILON || Math.abs(heightTotal - 1) > EPSILON) {
      throw new Error('行高或列宽比例合计异常。');
    }
  }

  function rebuildCellsFromRecords(records, rowCount, columnCount, filler = emptyCell) {
    const rows = state.rows.slice(0, rowCount).map((row) => ({
      heightRatio: row.heightRatio,
      cells: Array.from({ length: columnCount }, () => null)
    }));
    records.forEach((record) => {
      const cell = cloneCell(record.cell);
      cell.rowSpan = record.cell.rowSpan;
      cell.colSpan = record.cell.colSpan;
      for (let rowIndex = record.rowStart; rowIndex < record.rowStart + cell.rowSpan; rowIndex += 1) {
        for (let columnIndex = record.columnStart; columnIndex < record.columnStart + cell.colSpan; columnIndex += 1) {
          if (!rows[rowIndex] || columnIndex >= columnCount || rows[rowIndex].cells[columnIndex]) {
            return;
          }
          rows[rowIndex].cells[columnIndex] = rowIndex === record.rowStart && columnIndex === record.columnStart
            ? cell
            : { hidden: true, anchorRow: record.rowStart, anchorColumn: record.columnStart };
        }
      }
    });
    rows.forEach((row, rowIndex) => {
      row.cells = row.cells.map((cell, columnIndex) => cell || filler(rowIndex, columnIndex));
    });
    state.rows = rows;
  }

  function getModelName(obsBrandGoodId) {
    return state.modelMetaById.get(obsBrandGoodId)?.name || obsBrandGoodId || '空单元格';
  }

  function getPreviewUrl(cell) {
    return cell.previewImageUrl || state.previewById.get(cell.obsBrandGoodId) || '';
  }

  function getImage(url) {
    if (!url) {
      return null;
    }
    const cached = state.imageCache.get(url);
    if (cached) {
      return cached;
    }
    const image = new Image();
    image.onload = render;
    image.onerror = render;
    image.src = url;
    state.imageCache.set(url, image);
    return image;
  }

  function createLayoutBoxes() {
    const units = gridToUnits();
    return units.map((unit) => {
      const cell = state.rows[unit.rowIndex].cells[unit.columnIndex];
      return {
        ...unit,
        rowStart: unit.rowIndex,
        rowEnd: unit.rowIndex + cell.rowSpan,
        columnStart: unit.columnIndex,
        columnEnd: unit.columnIndex + cell.colSpan,
        cell
      };
    });
  }

  function getCabinetFrame() {
    const canvasWidth = dom.canvas.clientWidth;
    const canvasHeight = dom.canvas.clientHeight;
    const cabinetWidth = Math.max(1, Number(state.cabinetSize.width) || 1200);
    const cabinetHeight = Math.max(1, Number(state.cabinetSize.height) || 800);
    const scale = Math.min(canvasWidth / cabinetWidth, canvasHeight / cabinetHeight) * 0.94;
    const width = cabinetWidth * scale;
    const height = cabinetHeight * scale;
    return {
      left: (canvasWidth - width) / 2,
      top: (canvasHeight - height) / 2,
      width,
      height
    };
  }

  function logicToScreen(bbox) {
    const frame = getCabinetFrame();
    return {
      left: frame.left + bbox.x * frame.width,
      top: frame.top + (1 - bbox.y - bbox.h) * frame.height,
      width: bbox.w * frame.width,
      height: bbox.h * frame.height
    };
  }

  function eventPosition(event) {
    const rect = dom.canvas.getBoundingClientRect();
    const frame = getCabinetFrame();
    const x = clamp(event.clientX - rect.left, 0, rect.width);
    const y = clamp(event.clientY - rect.top, 0, rect.height);
    return {
      x,
      y,
      logicX: frame.width > 0 ? clamp((x - frame.left) / frame.width, 0, 1) : 0,
      logicY: frame.height > 0 ? clamp(1 - (y - frame.top) / frame.height, 0, 1) : 0
    };
  }

  function ensureCanvasSize() {
    const rect = dom.stage.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const availableWidth = Math.max(1, rect.width);
    const availableHeight = Math.max(1, rect.height);
    const width = Math.max(1, Math.round(Math.min(availableWidth, availableHeight * 1.5)));
    const height = Math.max(1, Math.round(width / 1.5));
    const backingWidth = Math.round(width * dpr);
    const backingHeight = Math.round(height * dpr);
    if (dom.canvas.width !== backingWidth || dom.canvas.height !== backingHeight) {
      dom.canvas.width = backingWidth;
      dom.canvas.height = backingHeight;
      dom.canvas.style.width = `${width}px`;
      dom.canvas.style.height = `${height}px`;
    }
    state.canvas = { width, height };
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { width, height };
  }

  function drawContainedImage(image, box) {
    if (!image || !image.complete || image.naturalWidth === 0) {
      return false;
    }
    const padding = Math.min(14, box.width * 0.08, box.height * 0.08);
    const maxWidth = Math.max(1, box.width - padding * 2);
    const maxHeight = Math.max(1, box.height - padding * 2);
    const scale = Math.min(maxWidth / image.naturalWidth, maxHeight / image.naturalHeight);
    const drawWidth = image.naturalWidth * scale;
    const drawHeight = image.naturalHeight * scale;
    ctx.drawImage(image, box.left + (box.width - drawWidth) / 2, box.top + (box.height - drawHeight) / 2, drawWidth, drawHeight);
    return true;
  }

  function drawPlaceholder(box, cell) {
    const hasUnit = Boolean(cell.obsBrandGoodId);
    ctx.fillStyle = hasUnit ? '#f8fafc' : '#fff7ed';
    ctx.fillRect(box.left + 1, box.top + 1, Math.max(0, box.width - 2), Math.max(0, box.height - 2));
    ctx.fillStyle = hasUnit ? '#475569' : '#c2410c';
    ctx.font = '700 13px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText((hasUnit ? getModelName(cell.obsBrandGoodId) : '未放置图片').slice(0, 18), box.left + box.width / 2, box.top + box.height / 2 - 10, Math.max(20, box.width - 18));
    ctx.font = '12px sans-serif';
    ctx.fillStyle = hasUnit ? '#64748b' : '#ea580c';
    ctx.fillText(hasUnit ? cell.obsBrandGoodId : '不会生成 unit', box.left + box.width / 2, box.top + box.height / 2 + 12, Math.max(20, box.width - 18));
  }

  function isSelected(item) {
    return state.selection && rectIntersects(state.selection, item);
  }

  function isHovered(item) {
    return state.hover && !state.hover.boundary && rectEquals(state.hover, {
      rowStart: item.rowStart,
      rowEnd: item.rowEnd,
      columnStart: item.columnStart,
      columnEnd: item.columnEnd
    });
  }

  function drawBoundaryHighlight(boundary) {
    const frame = getCabinetFrame();
    ctx.strokeStyle = '#f97316';
    ctx.lineWidth = 4;
    ctx.beginPath();
    if (boundary.type === 'column') {
      const x = frame.left + getColumnOffsets()[boundary.boundaryIndex] * frame.width;
      ctx.moveTo(x, frame.top);
      ctx.lineTo(x, frame.top + frame.height);
    } else {
      const y = frame.top + (1 - getRowOffsets()[boundary.boundaryIndex]) * frame.height;
      ctx.moveTo(frame.left, y);
      ctx.lineTo(frame.left + frame.width, y);
    }
    ctx.stroke();
  }

  function render() {
    const { width, height } = ensureCanvasSize();
    ctx.clearRect(0, 0, width, height);
    const frame = getCabinetFrame();
    ctx.fillStyle = 'rgba(255, 255, 255, 0.82)';
    ctx.fillRect(frame.left, frame.top, frame.width, frame.height);
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 2;
    ctx.strokeRect(frame.left, frame.top, frame.width, frame.height);
    state.layoutBoxes = createLayoutBoxes();

    state.layoutBoxes.forEach((item) => {
      const box = logicToScreen(item.bbox);
      ctx.save();
      ctx.beginPath();
      ctx.rect(box.left, box.top, box.width, box.height);
      ctx.clip();
      const image = item.cell.obsBrandGoodId ? getImage(getPreviewUrl(item.cell)) : null;
      if (!drawContainedImage(image, box)) {
        drawPlaceholder(box, item.cell);
      }
      ctx.restore();

      ctx.strokeStyle = '#cbd5e1';
      ctx.lineWidth = 1;
      if (isHovered(item)) {
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
      }
      if (isSelected(item)) {
        ctx.strokeStyle = '#4f46e5';
        ctx.lineWidth = 3;
      }
      ctx.strokeRect(box.left + 0.5, box.top + 0.5, Math.max(0, box.width - 1), Math.max(0, box.height - 1));
    });

    if (state.hover?.boundary) {
      drawBoundaryHighlight(state.hover.boundary);
    }

    updateToolbar();
  }

  function findBoxAt(x, y) {
    for (let index = state.layoutBoxes.length - 1; index >= 0; index -= 1) {
      const item = state.layoutBoxes[index];
      const box = logicToScreen(item.bbox);
      if (x >= box.left && x <= box.left + box.width && y >= box.top && y <= box.top + box.height) {
        return { item, box };
      }
    }
    return null;
  }

  function nearestResizableBoundary(item, box, x, y) {
    const distances = [];
    if (item.columnStart > 0) {
      distances.push({ type: 'column', edge: 'left', boundaryIndex: item.columnStart, distance: Math.abs(x - box.left) });
    }
    if (item.columnEnd < state.columns.length) {
      distances.push({ type: 'column', edge: 'right', boundaryIndex: item.columnEnd, distance: Math.abs(x - (box.left + box.width)) });
    }
    if (item.rowEnd < state.rows.length) {
      distances.push({ type: 'row', edge: 'top', boundaryIndex: item.rowEnd, distance: Math.abs(y - box.top) });
    }
    if (item.rowStart > 0) {
      distances.push({ type: 'row', edge: 'bottom', boundaryIndex: item.rowStart, distance: Math.abs(y - (box.top + box.height)) });
    }
    const nearest = distances.sort((a, b) => a.distance - b.distance)[0];
    return nearest && nearest.distance <= EDGE_HIT_PX ? nearest : null;
  }

  function updateHover(event) {
    if (state.dragging) {
      return;
    }
    const position = eventPosition(event);
    const hit = findBoxAt(position.x, position.y);
    if (!hit) {
      state.hover = null;
      dom.canvas.style.cursor = 'default';
      render();
      return;
    }
    const boundary = nearestResizableBoundary(hit.item, hit.box, position.x, position.y);
    state.hover = boundary
      ? { ...hit.item, boundary }
      : {
        rowStart: hit.item.rowStart,
        rowEnd: hit.item.rowEnd,
        columnStart: hit.item.columnStart,
        columnEnd: hit.item.columnEnd
      };
    dom.canvas.style.cursor = boundary?.type === 'column' ? 'col-resize' : boundary?.type === 'row' ? 'row-resize' : 'pointer';
    render();
  }

  function canDeleteSelection(selection = state.selection) {
    if (!selection || cellCount() <= 1) {
      return false;
    }
    const deletingRows = selection.columnStart === 0 && selection.columnEnd === state.columns.length;
    const deletingColumns = selection.rowStart === 0 && selection.rowEnd === state.rows.length;
    if (!deletingRows && !deletingColumns) {
      return false;
    }
    if (deletingRows && state.rows.length <= selection.rowEnd - selection.rowStart) {
      return false;
    }
    if (deletingColumns && state.columns.length <= selection.columnEnd - selection.columnStart) {
      return false;
    }
    const deletedStart = deletingRows ? selection.rowStart : selection.columnStart;
    const deletedEnd = deletingRows ? selection.rowEnd : selection.columnEnd;
    return getAnchorRecords().every((record) => {
      const start = deletingRows ? record.rowStart : record.columnStart;
      const end = start + (deletingRows ? record.cell.rowSpan : record.cell.colSpan);
      return end <= deletedStart || start >= deletedEnd || (start >= deletedStart && end <= deletedEnd);
    });
  }

  function updateToolbar() {
    if (!state.selection) {
      dom.toolbar.classList.add('hidden');
      return;
    }
    const bbox = selectionToBbox();
    if (!bbox) {
      dom.toolbar.classList.add('hidden');
      return;
    }
    const box = logicToScreen(bbox);
    const centerX = box.left + box.width / 2;
    const centerY = box.top + box.height / 2;
    const positions = {
      'add-up': [centerX, centerY - ACTION_OFFSET_PX],
      'add-down': [centerX, centerY + ACTION_OFFSET_PX],
      'add-left': [centerX - ACTION_OFFSET_PX, centerY],
      'add-right': [centerX + ACTION_OFFSET_PX, centerY]
    };
    dom.toolbar.querySelectorAll('button[data-action^="add-"]').forEach((button) => {
      const [left, top] = positions[button.dataset.action];
      button.style.left = `${left}px`;
      button.style.top = `${top}px`;
    });
    const centerActions = document.getElementById('cellCenterActions');
    centerActions.style.left = `${centerX}px`;
    centerActions.style.top = `${centerY}px`;
    const singleAnchor = getSingleSelectedAnchor();
    const mergeButton = centerActions.querySelector('button[data-action="merge"]');
    const splitButton = centerActions.querySelector('button[data-action="split"]');
    const replaceButton = centerActions.querySelector('button[data-action="replace"]');
    const clearButton = centerActions.querySelector('button[data-action="clear"]');
    const deleteButton = centerActions.querySelector('button[data-action="delete"]');
    const selectedAnchors = getAnchorsInSelection();
    const canMerge = selectedAnchors.length > 1;
    const canSplit = selectedAnchors.some((record) => record.cell.rowSpan > 1 || record.cell.colSpan > 1);
    replaceButton.classList.toggle('hidden', !singleAnchor);
    clearButton.classList.toggle('hidden', !singleAnchor || !singleAnchor.cell.obsBrandGoodId);
    mergeButton.classList.toggle('hidden', !canMerge);
    splitButton.classList.toggle('hidden', !canSplit);
    deleteButton.classList.toggle('hidden', !canDeleteSelection());
    dom.toolbar.classList.remove('hidden');
  }

  function selectRange(selection) {
    state.selection = normalizeSelection(selection);
    render();
  }

  function selectItem(item, extend = false) {
    const rect = {
      rowStart: item.rowStart,
      rowEnd: item.rowEnd,
      columnStart: item.columnStart,
      columnEnd: item.columnEnd
    };
    if (extend && state.selection) {
      selectRange({
        rowStart: Math.min(state.selection.rowStart, rect.rowStart),
        rowEnd: Math.max(state.selection.rowEnd, rect.rowEnd),
        columnStart: Math.min(state.selection.columnStart, rect.columnStart),
        columnEnd: Math.max(state.selection.columnEnd, rect.columnEnd)
      });
    } else {
      selectRange(rect);
    }
  }

  function mergeSelection() {
    const selection = normalizeSelection(state.selection);
    if (!selection) {
      return;
    }
    const area = (selection.rowEnd - selection.rowStart) * (selection.columnEnd - selection.columnStart);
    if (area <= 1) {
      setMessage('请选择至少两个单元格后再合并。');
      return;
    }
    const source = getAnchorsInSelection(selection).find((record) => record.cell.obsBrandGoodId)?.cell || emptyCell();
    const mergedCell = createCellFromSource(source);
    mergedCell.rowSpan = selection.rowEnd - selection.rowStart;
    mergedCell.colSpan = selection.columnEnd - selection.columnStart;
    for (let rowIndex = selection.rowStart; rowIndex < selection.rowEnd; rowIndex += 1) {
      for (let columnIndex = selection.columnStart; columnIndex < selection.columnEnd; columnIndex += 1) {
        state.rows[rowIndex].cells[columnIndex] = rowIndex === selection.rowStart && columnIndex === selection.columnStart
          ? mergedCell
          : { hidden: true, anchorRow: selection.rowStart, anchorColumn: selection.columnStart };
      }
    }
    state.selection = selection;
    setMessage(mergedCell.obsBrandGoodId ? '已合并单元格，保留选区中的第一张图片。' : '已合并为空格子。', true);
    render();
  }

  function clearSelected() {
    const anchor = getSingleSelectedAnchor();
    if (!anchor) {
      setMessage('请选择单个格子后再清除图片展位。');
      return;
    }
    anchor.cell.obsBrandGoodId = '';
    anchor.cell.previewImageUrl = '';
    anchor.cell.candidates = [];
    setMessage('已清除图片展位，该格子不会生成 unit。', true);
    render();
  }

  function splitSelection() {
    const anchors = getAnchorsInSelection().filter((record) => record.cell.rowSpan > 1 || record.cell.colSpan > 1);
    if (!anchors.length) {
      setMessage('当前选区没有可拆分的合并单元格。');
      return;
    }
    anchors.forEach((record) => {
      const source = cloneCell(record.cell);
      for (let rowIndex = record.rowStart; rowIndex < record.rowStart + record.cell.rowSpan; rowIndex += 1) {
        for (let columnIndex = record.columnStart; columnIndex < record.columnStart + record.cell.colSpan; columnIndex += 1) {
          state.rows[rowIndex].cells[columnIndex] = rowIndex === record.rowStart && columnIndex === record.columnStart
            ? createCellFromSource(source)
            : emptyCell();
        }
      }
    });
    setMessage('已拆分单元格，第一个格子保留图片，其余为空格子。', true);
    render();
  }

  function addColumn(direction) {
    if (!state.selection) {
      return;
    }
    const singleAnchor = getSingleSelectedAnchor() || getAnchorsInSelection()[0];
    const source = singleAnchor?.cell || emptyCell();
    const insertIndex = direction === 'left' ? state.selection.columnStart : state.selection.columnEnd;
    const splitIndex = direction === 'left' ? state.selection.columnStart : state.selection.columnEnd - 1;
    const halfWidth = state.columns[splitIndex].widthRatio / 2;
    state.columns[splitIndex].widthRatio = halfWidth;
    state.columns.splice(insertIndex, 0, { widthRatio: halfWidth });

    const records = getAnchorRecords().map((record) => {
      const updated = { rowStart: record.rowStart, columnStart: record.columnStart, cell: cloneCell(record.cell) };
      if (updated.columnStart >= insertIndex) {
        updated.columnStart += 1;
      } else if (updated.columnStart < insertIndex && updated.columnStart + updated.cell.colSpan > insertIndex) {
        updated.cell.colSpan += 1;
      }
      return updated;
    });
    rebuildCellsFromRecords(records, state.rows.length, state.columns.length, () => createCellFromSource(source));
    normalizeGrid();
    selectRange({ rowStart: 0, rowEnd: state.rows.length, columnStart: insertIndex, columnEnd: insertIndex + 1 });
    setMessage(`已向${direction === 'left' ? '左' : '右'}添加整列。`, true);
  }

  function addRow(direction) {
    if (!state.selection) {
      return;
    }
    const singleAnchor = getSingleSelectedAnchor() || getAnchorsInSelection()[0];
    const source = singleAnchor?.cell || emptyCell();
    const insertIndex = direction === 'down' ? state.selection.rowStart : state.selection.rowEnd;
    const splitIndex = direction === 'down' ? state.selection.rowStart : state.selection.rowEnd - 1;
    const halfHeight = state.rows[splitIndex].heightRatio / 2;
    state.rows[splitIndex].heightRatio = halfHeight;
    const records = getAnchorRecords().map((record) => {
      const updated = { rowStart: record.rowStart, columnStart: record.columnStart, cell: cloneCell(record.cell) };
      if (updated.rowStart >= insertIndex) {
        updated.rowStart += 1;
      } else if (updated.rowStart < insertIndex && updated.rowStart + updated.cell.rowSpan > insertIndex) {
        updated.cell.rowSpan += 1;
      }
      return updated;
    });
    state.rows.splice(insertIndex, 0, {
      heightRatio: halfHeight,
      cells: Array.from({ length: state.columns.length }, () => null)
    });
    rebuildCellsFromRecords(records, state.rows.length, state.columns.length, () => createCellFromSource(source));
    normalizeGrid();
    selectRange({ rowStart: insertIndex, rowEnd: insertIndex + 1, columnStart: 0, columnEnd: state.columns.length });
    setMessage(`已向${direction === 'up' ? '上' : '下'}添加整行。`, true);
  }

  function deleteSelected() {
    if (!state.selection) {
      return;
    }
    if (cellCount() <= 1) {
      setMessage('至少保留 1 个单元格，不能删除最后一个。');
      return;
    }
    const deletingRows = state.selection.columnStart === 0 && state.selection.columnEnd === state.columns.length;
    const deletingColumns = state.selection.rowStart === 0 && state.selection.rowEnd === state.rows.length;
    if (!deletingRows && !deletingColumns) {
      setMessage('当前为表格结构，删除仅支持整行或整列；可先选择整行/整列或通过拆分/合并调整布局。');
      return;
    }
    if (deletingRows && state.rows.length <= state.selection.rowEnd - state.selection.rowStart) {
      setMessage('至少保留 1 行。');
      return;
    }
    if (deletingColumns && state.columns.length <= state.selection.columnEnd - state.selection.columnStart) {
      setMessage('至少保留 1 列。');
      return;
    }
    const records = [];
    const deletedStart = deletingRows ? state.selection.rowStart : state.selection.columnStart;
    const deletedEnd = deletingRows ? state.selection.rowEnd : state.selection.columnEnd;
    const deleteCount = deletedEnd - deletedStart;
    for (const record of getAnchorRecords()) {
      const start = deletingRows ? record.rowStart : record.columnStart;
      const end = start + (deletingRows ? record.cell.rowSpan : record.cell.colSpan);
      if (end <= deletedStart) {
        records.push({ rowStart: record.rowStart, columnStart: record.columnStart, cell: cloneCell(record.cell) });
      } else if (start >= deletedEnd) {
        records.push({
          rowStart: deletingRows ? record.rowStart - deleteCount : record.rowStart,
          columnStart: deletingRows ? record.columnStart : record.columnStart - deleteCount,
          cell: cloneCell(record.cell)
        });
      } else if (!(start >= deletedStart && end <= deletedEnd)) {
        setMessage('选区穿过了合并单元格，需先拆分后再删除整行或整列。');
        return;
      }
    }
    if (deletingRows) {
      state.rows.splice(state.selection.rowStart, deleteCount);
    } else {
      state.columns.splice(state.selection.columnStart, deleteCount);
    }
    rebuildCellsFromRecords(records, state.rows.length, state.columns.length, emptyCell);
    normalizeGrid();
    state.selection = null;
    setMessage(`已删除整${deletingRows ? '行' : '列'}。`, true);
    render();
  }

  function handleToolbarAction(action) {
    if (action === 'delete') {
      deleteSelected();
    } else if (action === 'add-left') {
      addColumn('left');
    } else if (action === 'add-right') {
      addColumn('right');
    } else if (action === 'add-up') {
      addRow('up');
    } else if (action === 'add-down') {
      addRow('down');
    } else if (action === 'replace') {
      openReplaceModal();
    } else if (action === 'clear') {
      clearSelected();
    } else if (action === 'merge') {
      mergeSelection();
    } else if (action === 'split') {
      splitSelection();
    }
  }

  function startDragging(event, hit, boundary) {
    const position = eventPosition(event);
    state.dragging = {
      ...boundary,
      startLogicX: position.logicX,
      startLogicY: position.logicY,
      snapshot: cloneGrid()
    };
    dom.canvas.setPointerCapture(event.pointerId);
  }

  function applyColumnDrag(position) {
    const drag = state.dragging;
    const leftIndex = drag.boundaryIndex - 1;
    const rightIndex = drag.boundaryIndex;
    if (leftIndex < 0 || rightIndex >= state.columns.length) {
      return;
    }
    const delta = position.logicX - drag.startLogicX;
    const leftStart = drag.snapshot.columns[leftIndex].widthRatio;
    const rightStart = drag.snapshot.columns[rightIndex].widthRatio;
    const min = state.minCellRatio;
    const clampedDelta = clamp(delta, min - leftStart, rightStart - min);
    state.columns[leftIndex].widthRatio = leftStart + clampedDelta;
    state.columns[rightIndex].widthRatio = rightStart - clampedDelta;
  }

  function applyRowDrag(position) {
    const drag = state.dragging;
    const lowerIndex = drag.boundaryIndex - 1;
    const upperIndex = drag.boundaryIndex;
    if (lowerIndex < 0 || upperIndex >= state.rows.length) {
      return;
    }
    const delta = position.logicY - drag.startLogicY;
    const lowerStart = drag.snapshot.rows[lowerIndex].heightRatio;
    const upperStart = drag.snapshot.rows[upperIndex].heightRatio;
    const min = state.minCellRatio;
    const clampedDelta = clamp(delta, min - lowerStart, upperStart - min);
    state.rows[lowerIndex].heightRatio = lowerStart + clampedDelta;
    state.rows[upperIndex].heightRatio = upperStart - clampedDelta;
  }

  function handlePointerMove(event) {
    if (!state.dragging) {
      updateHover(event);
      return;
    }
    const position = eventPosition(event);
    if (state.dragging.type === 'column') {
      applyColumnDrag(position);
    } else {
      applyRowDrag(position);
    }
    render();
  }

  function handlePointerDown(event) {
    const position = eventPosition(event);
    const hit = findBoxAt(position.x, position.y);
    if (!hit) {
      state.selection = null;
      state.hover = null;
      render();
      return;
    }
    const boundary = nearestResizableBoundary(hit.item, hit.box, position.x, position.y);
    selectItem(hit.item, event.shiftKey);
    if (boundary) {
      startDragging(event, hit, boundary);
    }
  }

  function handlePointerUp(event) {
    if (!state.dragging) {
      return;
    }
    dom.canvas.releasePointerCapture(event.pointerId);
    state.dragging = null;
    normalizeGrid();
    render();
  }

  function readCabinetSizeInputs() {
    const width = Number(dom.cabinetWidthInput.value);
    const height = Number(dom.cabinetHeightInput.value);
    if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(height) || height <= 0) {
      throw new Error('组合柜宽和高必须是大于 0 的数值。');
    }
    return { width, height };
  }

  async function confirmLayout() {
    try {
      validateGrid();
      state.cabinetSize = readCabinetSizeInputs();
    } catch (error) {
      setMessage(error.message);
      return;
    }
    const payload = {
      name: state.inputName,
      cabinetSize: state.cabinetSize,
      units: gridToOutputUnits()
    };
    dom.confirmButton.disabled = true;
    setMessage('正在保存确认结果...', true);
    try {
      const response = await fetch(SUBMIT_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        throw new Error(`保存失败：HTTP ${response.status}`);
      }
      window.parent?.postMessage({ type: 'cabinet-layout-confirmed', payload }, '*');
      setMessage('已保存确认结果，可以关闭页面。', true);
    } catch (error) {
      dom.confirmButton.disabled = false;
      setMessage(error.message);
    }
  }

  function canUseImageUrl(url) {
    if (typeof url !== 'string') {
      return false;
    }
    const trimmed = url.trim();
    if (!trimmed) {
      return false;
    }
    return (
      trimmed.startsWith('/workspace-file/')
      || trimmed.startsWith('/reference-image')
    );
  }

  function updateReferenceImageDisplay() {
    const hasSrc = canUseImageUrl(state.referenceImageUrl);
    if (!hasSrc) {
      dom.referenceImage.removeAttribute('src');
      dom.referenceFallback.classList.remove('hidden');
      return;
    }
    dom.referenceImage.onload = () => {
      dom.referenceFallback.classList.add('hidden');
    };
    dom.referenceImage.onerror = () => {
      dom.referenceImage.removeAttribute('src');
      dom.referenceFallback.classList.remove('hidden');
    };
    dom.referenceImage.src = state.referenceImageUrl;
  }

  function collectRecommendedIds(units) {
    const ids = [];
    flattenUnits(units).forEach((unit) => {
      const candidates = Array.isArray(unit?.candidates) ? unit.candidates : unit?.recommendedObsBrandGoodIds || [];
      candidates.filter(Boolean).map(String).forEach((id) => {
        if (!ids.includes(id)) {
          ids.push(id);
        }
      });
    });
    return ids;
  }

  function extractCabinetSize(input) {
    const candidates = [
      input.cabinetSize,
      input.cabinetDimensions,
      input.wardrobeSize,
      input.outerSize,
      input.cabinet
    ];
    for (const candidate of candidates) {
      if (!candidate || typeof candidate !== 'object') {
        continue;
      }
      const width = Number(candidate.width ?? candidate.w ?? candidate.W ?? candidate.x);
      const height = Number(candidate.height ?? candidate.h ?? candidate.H ?? candidate.z);
      if (Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0) {
        return { width, height };
      }
    }
    const units = Array.isArray(input.units) ? flattenUnits(input.units) : [];
    if (units.length) {
      const boxes = units.map((unit, index) => unitToRealBbox(unit, index));
      const minX = Math.min(...boxes.map((box) => box.x));
      const maxX = Math.max(...boxes.map((box) => box.x + box.w));
      const minZ = Math.min(...boxes.map((box) => box.y));
      const maxZ = Math.max(...boxes.map((box) => box.y + box.h));
      if (Number.isFinite(minX) && Number.isFinite(maxX) && Number.isFinite(minZ) && Number.isFinite(maxZ)) {
        return { width: maxX - minX, height: maxZ - minZ };
      }
    }
    return { width: 1200, height: 800 };
  }

  function extractLayoutOrigin(input) {
    const units = Array.isArray(input.units) ? flattenUnits(input.units) : [];
    if (!units.length) {
      return { x: 0, z: 0 };
    }
    const boxes = units.map((unit, index) => unitToRealBbox(unit, index));
    const minX = Math.min(...boxes.map((box) => box.x));
    const minZ = Math.min(...boxes.map((box) => box.y));
    return {
      x: Number.isFinite(minX) ? minX : 0,
      z: Number.isFinite(minZ) ? minZ : 0
    };
  }

  function extractDefaultDepth(input) {
    const units = Array.isArray(input.units) ? flattenUnits(input.units) : [];
    const depths = units.map((unit, index) => unitToRealBbox(unit, index).depth).filter((depth) => Number.isFinite(depth) && depth > 0);
    return depths[0] || 400;
  }

  function applyInput(input) {
    state.layoutOrigin = extractLayoutOrigin(input);
    state.defaultDepth = extractDefaultDepth(input);
    state.cabinetSize = extractCabinetSize(input);
    state.inputName = input.name || '';
    validateInput(input);
    dom.cabinetWidthInput.value = state.cabinetSize.width;
    dom.cabinetHeightInput.value = state.cabinetSize.height;
    state.recommendedIds = collectRecommendedIds(input.units);
    state.referenceImageUrl = input.referenceImageUrl || input.imageUrl || input.inputImageUrl || '';
    state.description = input.description || input.text || input.prompt || '';
    dom.descriptionText.textContent = state.description || '暂无描述';
    const grid = bboxToGrid(flattenUnits(input.units));
    state.rows = grid.rows;
    state.columns = grid.columns;
    normalizeGrid();
    state.selection = null;
    state.hover = null;
    state.dragging = null;
    dom.stage.style.aspectRatio = '3 / 2';
    updateReferenceImageDisplay();
    setMessage('布局已加载。', true);
    render();
  }

  async function loadInitialInput() {
    const response = await fetch(INPUT_URL);
    if (!response.ok) {
      throw new Error(`输入数据加载失败：HTTP ${response.status}`);
    }
    return response.json();
  }

  async function loadModelData() {
    const [profileResponse, productResponse] = await Promise.all([fetch(PROFILE_URL), fetch(PRODUCT_URL)]);
    if (!profileResponse.ok || !productResponse.ok) {
      throw new Error('模型数据加载失败。');
    }
    const [profileData, productData] = await Promise.all([profileResponse.json(), productResponse.json()]);
    const previewById = new Map();
    productData.categories?.forEach((category) => {
      category.products?.forEach((product) => {
        if (product.obsBrandGoodId && product.previewImgUrl) {
          previewById.set(product.obsBrandGoodId, product.previewImgUrl);
        }
      });
    });

    const modelMetaById = new Map();
    profileData.category_list?.forEach((category) => {
      category.profile_list?.forEach((model) => {
        if (model.obsBrandGoodId) {
          modelMetaById.set(model.obsBrandGoodId, {
            ...model,
            previewImgUrl: previewById.get(model.obsBrandGoodId) || ''
          });
        }
      });
    });

    state.previewById = previewById;
    state.modelMetaById = modelMetaById;
    state.allModels = Array.from(modelMetaById.values()).sort((a, b) => String(a.name).localeCompare(String(b.name), 'zh-CN'));
  }

  function openReplaceModal() {
    if (!getSingleSelectedAnchor()) {
      setMessage('请选择单个单元格后再替换。');
      return;
    }
    dom.replaceSearch.value = '';
    renderReplaceList('');
    dom.replaceModal.classList.remove('hidden');
    dom.replaceSearch.focus();
  }

  function closeReplaceModal() {
    dom.replaceModal.classList.add('hidden');
  }

  function getSelectedCell() {
    return getSingleSelectedAnchor()?.cell || null;
  }

  function getRecommendedIds() {
    return state.recommendedIds;
  }

  function modelMatches(model, query) {
    if (!query) {
      return true;
    }
    const fields = [
      model.obsBrandGoodId,
      model.name,
      model.profile?.layout_notes,
      model.profile?.color_material,
      model.profile?.handle_style
    ];
    return fields.some((field) => String(field || '').toLowerCase().includes(query));
  }

  function renderReplaceList(queryText) {
    const query = queryText.trim().toLowerCase();
    const recommendedIds = getRecommendedIds();
    const recommendedSet = new Set(recommendedIds);
    const orderedModels = [
      ...recommendedIds.map((id) => state.modelMetaById.get(id)).filter(Boolean),
      ...state.allModels.filter((model) => !recommendedSet.has(model.obsBrandGoodId))
    ];
    const models = orderedModels.filter((model) => modelMatches(model, query));
    dom.replaceList.textContent = '';
    if (models.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'message';
      empty.textContent = '没有匹配的模型。';
      dom.replaceList.appendChild(empty);
      return;
    }
    models.forEach((model) => {
      const button = document.createElement('button');
      button.type = 'button';
      const isRecommended = recommendedSet.has(model.obsBrandGoodId);
      button.className = `replace-item${isRecommended ? ' recommended' : ''}`;
      button.dataset.bgid = model.obsBrandGoodId;

      if (model.previewImgUrl) {
        const img = document.createElement('img');
        img.src = model.previewImgUrl;
        img.alt = model.name || model.obsBrandGoodId;
        button.appendChild(img);
      } else {
        const thumb = document.createElement('div');
        thumb.className = 'replace-thumb';
        thumb.textContent = '无图';
        button.appendChild(thumb);
      }

      const content = document.createElement('div');
      const name = document.createElement('div');
      name.className = 'replace-name';
      name.textContent = model.name || model.obsBrandGoodId;
      if (isRecommended) {
        const badge = document.createElement('span');
        badge.className = 'recommended-badge';
        badge.textContent = '推荐';
        name.appendChild(badge);
      }
      const bgid = document.createElement('div');
      bgid.className = 'replace-bgid';
      bgid.textContent = model.obsBrandGoodId;
      const note = document.createElement('div');
      note.className = 'replace-note';
      note.textContent = model.profile?.layout_notes || '';
      content.append(name, bgid, note);
      button.appendChild(content);
      dom.replaceList.appendChild(button);
    });
  }

  function replaceSelected(obsBrandGoodId) {
    const anchor = getSingleSelectedAnchor();
    if (!anchor) {
      return;
    }
    anchor.cell.obsBrandGoodId = obsBrandGoodId;
    anchor.cell.name = state.modelMetaById.get(obsBrandGoodId)?.name || anchor.cell.name || '';
    anchor.cell.previewImageUrl = state.previewById.get(obsBrandGoodId) || '';
    closeReplaceModal();
    setMessage('已替换选中单元格。', true);
    render();
  }

  function bindEvents() {
    dom.confirmButton.addEventListener('click', confirmLayout);
    [dom.cabinetWidthInput, dom.cabinetHeightInput].forEach((input) => {
      input.addEventListener('input', () => {
        try {
          state.cabinetSize = readCabinetSizeInputs();
          render();
        } catch {
        }
      });
    });
    dom.canvas.addEventListener('pointerdown', handlePointerDown);
    dom.canvas.addEventListener('pointermove', handlePointerMove);
    dom.canvas.addEventListener('pointerup', handlePointerUp);
    dom.canvas.addEventListener('pointercancel', handlePointerUp);
    dom.canvas.addEventListener('mouseleave', () => {
      if (!state.dragging) {
        state.hover = null;
        dom.canvas.style.cursor = 'default';
        render();
      }
    });
    dom.toolbar.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-action]');
      if (button && !button.disabled) {
        handleToolbarAction(button.dataset.action);
      }
    });
    dom.closeReplaceButton.addEventListener('click', closeReplaceModal);
    dom.replaceModal.addEventListener('click', (event) => {
      if (event.target === dom.replaceModal) {
        closeReplaceModal();
      }
    });
    dom.replaceSearch.addEventListener('input', () => renderReplaceList(dom.replaceSearch.value));
    dom.replaceList.addEventListener('click', (event) => {
      const button = event.target.closest('button[data-bgid]');
      if (button) {
        replaceSelected(button.dataset.bgid);
      }
    });
    window.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        if (!dom.replaceModal.classList.contains('hidden')) {
          closeReplaceModal();
        } else {
          state.selection = null;
          render();
        }
      }
      if (event.key === 'Delete' && dom.replaceModal.classList.contains('hidden')) {
        deleteSelected();
      }
    });
    window.addEventListener('resize', render);
  }

  async function init() {
    bindEvents();
    try {
      await loadModelData();
      const input = await loadInitialInput();
      applyInput(input);
    } catch (error) {
      setMessage(error.message || '初始化失败。');
      dom.confirmButton.disabled = true;
    }
  }

  window.CabinetLayoutConfirm = {
    validateInput,
    bboxToGrid,
    gridToUnits,
    validateGrid,
    bboxToRows: (units) => bboxToGrid(units).rows,
    rowsToUnits: gridToUnits,
    state
  };

  init();
})();
