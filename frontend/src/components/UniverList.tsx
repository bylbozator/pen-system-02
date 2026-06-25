import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { datasets as datasetsApi, rows as rowsApi, listy as listyApi, Dataset, Row, getAccessToken, getCurrentUser } from '../api';
import toast from 'react-hot-toast';
import { ArrowLeft, Maximize2, Minimize2 } from 'lucide-react';
import type { IWorkbookData, ICellData } from '@univerjs/core';
import { LocaleType } from '@univerjs/core';
import ruRUFunctionAliases from '../locales/ru-RU-function-aliases';
import { createFormulaRusToEngConverter } from '../utils/russianFormulas';

// ==================== МОДУЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ ТРЕКИНГА СТРОК ====================
// Скрытая колонка для хранения identity строк внутри Univer
const HIDDEN_META_COL = 9999;

const convertFormulaRusToEng = createFormulaRusToEngConverter(ruRUFunctionAliases);

function computeRowHash(data: Record<string, any>, formulas?: Record<string, string>, cell_styles?: Record<string, any>): string {
  const obj: any = {};
  const keys = Object.keys(data || {}).sort();
  for (const k of keys) obj[k] = data[k];
  if (formulas) {
    const fKeys = Object.keys(formulas).sort();
    for (const k of fKeys) obj['_f_' + k] = formulas[k];
  }
  if (cell_styles) {
    const sKeys = Object.keys(cell_styles).sort();
    for (const k of sKeys) obj['_s_' + k] = cell_styles[k];
  }
  return JSON.stringify(obj);
}

function extractError(err: any): string {
  const detail = err?.response?.data?.detail || err?.message || '';
  return typeof detail === 'string' ? detail : JSON.stringify(detail);
}

async function initUniver(containerId: string, datasetId: number, instanceRef: { current: any }, apiRef: { current: any }) {
  if (instanceRef.current) return;

  const [
    { createUniver, LocaleType, mergeLocales },
    { UniverSheetsCorePreset },
    { default: UniverPresetSheetsCoreRuRU },
    { UniverSheetsThreadCommentPreset },
    { default: UniverPresetSheetsThreadCommentRuRU },
    { default: UniverSheetsFormulaRuRU },
    { IThreadCommentDataSourceService, ThreadCommentDataSourceService },
    { createCommentDataSource },
  ] = await Promise.all([
    import('@univerjs/presets'),
    import('@univerjs/preset-sheets-core'),
    import('@univerjs/preset-sheets-core/locales/ru-RU'),
    import('@univerjs/preset-sheets-thread-comment'),
    import('@univerjs/preset-sheets-thread-comment/locales/ru-RU'),
    import('@univerjs/sheets-formula/locale/ru-RU'),
    import('@univerjs/thread-comment'),
    import('../utils/commentDataSource'),
  ]);

  await import('@univerjs/preset-sheets-core/lib/index.css');

  // mergeLocales использует Object.assign (поверхностное слияние),
  // поэтому вручную deep-merge-им sheets-formula из двух источников
  const mergedFormulaRu = (() => {
    const base: any = { 'sheets-formula': { functionList: {} } };
    for (const src of [UniverSheetsFormulaRuRU, ruRUFunctionAliases]) {
      const fl = src?.['sheets-formula']?.functionList;
      if (!fl) continue;
      for (const [key, val] of Object.entries(fl)) {
        base['sheets-formula'].functionList[key] = {
          ...(base['sheets-formula'].functionList[key] || {}),
          ...(val as any),
        };
      }
    }
    return base;
  })();

  const { univer, univerAPI } = createUniver({
    locale: LocaleType.RU_RU,
    locales: {
      [LocaleType.RU_RU]: mergeLocales(UniverPresetSheetsCoreRuRU, UniverPresetSheetsThreadCommentRuRU, mergedFormulaRu),
    },
    presets: [
      UniverSheetsCorePreset({
        container: containerId,
        customFontFamily: {
          override: true,
          list: [
            { value: 'Arial', label: 'ui.fontFamily.arial', category: 'sans-serif' },
            { value: 'Times New Roman', label: 'ui.fontFamily.times-new-roman', category: 'serif' },
            { value: 'Tahoma', label: 'ui.fontFamily.tahoma', category: 'sans-serif' },
            { value: 'Verdana', label: 'ui.fontFamily.verdana', category: 'sans-serif' },
            { value: 'Microsoft YaHei', label: 'ui.fontFamily.microsoft-yahei', category: 'sans-serif' },
            { value: 'SimSun', label: 'ui.fontFamily.simsun', category: 'serif' },
            { value: 'NSimSun', label: 'ui.fontFamily.nsimsun', category: 'serif' },
          ],
        },
      }),
      UniverSheetsThreadCommentPreset(),
    ],
    override: [
      [IThreadCommentDataSourceService, {
        useFactory: () => {
          const service = new ThreadCommentDataSourceService();
          service.dataSource = createCommentDataSource(datasetId);
          service.syncUpdateMutationToColla = false;
          return service;
        },
      }],
    ] as any,
  });

  instanceRef.current = univer;
  (instanceRef as any).__ruAliases = ruRUFunctionAliases;
  apiRef.current = univerAPI;
}

function getCellValue(val: any): ICellData {
  if (val === undefined || val === null || val === '') return {};
  const num = Number(val);
  if (!isNaN(num) && val !== '') {
    return { v: num, t: 2 };
  }
  return { v: String(val), t: 1 };
}

const INITIAL_LOAD_ROWS = 200;
const PROGRESSIVE_CHUNK = 2000;

async function buildWorkbookData(
  datasetId: number,
  dataset: Dataset,
  onProgress: ((loaded: number, total: number) => void) | undefined,
  rowMetaByIndex: Map<string, { id: number; version: number; hash: string }>,
  initialRowCount: number,
): Promise<{
  wbData: IWorkbookData;
  remainingBySheet: Record<string, Row[]>;
  colIds: string[];
  styles: Record<string, any>;
}> {
  const colIds = dataset.columns.map((c) => c.id);
  const numCols = Math.max(colIds.length, 26);
  const styles = dataset.styles || {};

  rowMetaByIndex.clear();

  const mainList = dataset.sub_sheets?.[0] || { id: 'main', name: 'Лист1', order: 0 };
  const listy: Record<string, any> = {};
  const remainingBySheet: Record<string, Row[]> = {};

  for (const list of (dataset.sub_sheets || [mainList])) {
    const cellData: Record<number, Record<number, ICellData>> = {};

    const addRowToCellData = (row: Row, dataRowIdx: number) => {
      const dataRow: Record<number, ICellData> = {};

      dataRow[HIDDEN_META_COL] = {
        v: JSON.stringify({ id: row.id, version: row.version, order: dataRowIdx, orig: row.row_order }),
        t: 1,
      };

      colIds.forEach((colId, colIdx) => {
        const val = row.data?.[colId];
        let formula = row.formulas?.[colId];
        const styleVal = row.cell_styles?.[colId];
        const cell = getCellValue(val);
        if (formula) {
          formula = convertFormulaRusToEng(formula);
          cell.f = formula;
        }
        if (styleVal) {
          if (typeof styleVal === 'string' && styles[styleVal]) {
            cell.s = styleVal;
            cell.si = styleVal;
          } else if (typeof styleVal === 'object') {
            cell.s = styleVal as any;
          }
        }

        if (cell.v !== undefined || cell.f || cell.s) {
          dataRow[colIdx] = cell;
        }
      });

      if (row.data) {
        for (const key of Object.keys(row.data)) {
          const match = key.match(/^_col_(\d+)$/);
          if (match) {
            const colIdx = parseInt(match[1], 10);
            if (colIdx >= colIds.length && !dataRow[colIdx]) {
              const val = row.data[key];
              const cell = getCellValue(val);
              const styleVal = row.cell_styles?.[key];
              if (styleVal && typeof styleVal === 'string' && styles[styleVal]) {
                cell.s = styleVal;
                cell.si = styleVal;
              }
              if (cell.v !== undefined || cell.f || cell.s) {
                dataRow[colIdx] = cell;
              }
            }
          }
        }
      }

      cellData[dataRowIdx] = dataRow;

      rowMetaByIndex.set(`${list.id}:::${dataRowIdx}`, {
        id: row.id,
        version: row.version,
        hash: computeRowHash(row.data || {}, row.formulas || undefined, row.cell_styles || undefined),
      });
    };

    const allResp = await rowsApi.list(datasetId, 1, 100000, undefined, undefined, undefined, undefined, list.id);
    const allData = allResp.data as any;
    const allItems = (allData.items as Row[]) || [];
    const totalRows = allData.total || 0;

    const processCount = Math.min(allItems.length, initialRowCount);
    const usedPositions = new Set<number>();
    for (let i = 0; i < processCount; i += PROGRESSIVE_CHUNK) {
      const chunk = allItems.slice(i, i + PROGRESSIVE_CHUNK);
      await new Promise<void>(resolve => {
        requestAnimationFrame(() => {
          chunk.forEach((row) => {
            let dataRowIdx = row.row_order;
            while (usedPositions.has(dataRowIdx)) dataRowIdx++;
            usedPositions.add(dataRowIdx);
            addRowToCellData(row, dataRowIdx);
          });
          resolve();
        });
      });
      onProgress?.(Math.min(i + PROGRESSIVE_CHUNK, totalRows), totalRows);
    }

    remainingBySheet[list.id] = allItems.slice(initialRowCount);

    const numRows = Math.max(totalRows, 500);

    const mergeData = (list.merged_cells || []).map((mc: any) => ({
      startRow: mc.startRow ?? mc.start_row,
      endRow: mc.endRow ?? mc.end_row,
      startColumn: mc.startColumn ?? mc.start_column,
      endColumn: mc.endColumn ?? mc.end_column,
    }));

    const rowData: Record<number, { h: number }> = {};
    if (list.row_heights) {
      for (const [rowKey, ht] of Object.entries(list.row_heights)) {
        rowData[Number(rowKey)] = { h: Math.round(Number(ht) * 96 / 72) };
      }
    }

    const columnData: Record<number, { w: number }> = {};
    if (list.column_widths) {
      for (const [colKey, w] of Object.entries(list.column_widths)) {
        columnData[Number(colKey)] = { w: Math.round(Number(w) * 7 + 5) };
      }
    }

    listy[list.id] = {
      id: list.id,
      name: list.name,
      cellData,
      columnCount: numCols,
      rowCount: numRows,
      freeze: { xSplit: 0, ySplit: 0, startRow: 0, startColumn: 0 },
      mergeData,
      rowData,
      columnData,
    };
  }

  return {
    wbData: {
      id: String(dataset.id),
      name: dataset.name,
      appVersion: '0.25.0',
      locale: LocaleType.RU_RU,
      styles,
      sheetOrder: (dataset.sub_sheets || [mainList]).map((s) => s.id),
      sheets: listy,
    },
    remainingBySheet,
    colIds,
    styles,
  };
}

async function progressiveLoad(
  remainingBySheet: Record<string, Row[]>,
  colIds: string[],
  styles: Record<string, any>,
  rowMetaByIndex: Map<string, { id: number; version: number; hash: string }>,
  univerAPI: any,
  fWorkbook: any,
  wbData: IWorkbookData,
  onProgress?: (loaded: number, total: number) => void,
) {
  const sheetIds = Object.keys(remainingBySheet);
  if (sheetIds.length === 0) return;

  for (const sheetId of sheetIds) {
    const items = remainingBySheet[sheetId];
    if (!items || items.length === 0) continue;

    const sheet = fWorkbook.getActiveSheet();
    if (!sheet) continue;

    let processedCount = 0;

    const progUsedPositions = new Set<number>();
    let hasMore = true;

    while (hasMore) {
      await new Promise<void>(resolve => requestAnimationFrame(resolve));

      const chunk = items.splice(0, PROGRESSIVE_CHUNK);
      if (chunk.length === 0) { hasMore = false; break; }

      const startRow = chunk[0].row_order;
      const numCols = Math.max(colIds.length, 26);

      const dataValues: any[][] = [];
      const metaValues: any[][] = [];

      chunk.forEach((row) => {
        const dataRow: any[] = [];
        for (let c = 0; c < numCols; c++) {
          dataRow.push(null);
        }

        colIds.forEach((colId, colIdx) => {
          const val = row.data?.[colId];
          const formula = row.formulas?.[colId];
          const styleVal = row.cell_styles?.[colId];
          const cell = getCellValue(val);
          if (formula) {
            cell.f = convertFormulaRusToEng(formula);
          }
          if (styleVal) {
            if (typeof styleVal === 'string' && styles[styleVal]) {
              cell.s = styleVal;
              cell.si = styleVal;
            } else if (typeof styleVal === 'object') {
              cell.s = styleVal as any;
            }
          }
          if (cell.v !== undefined || cell.f || cell.s) {
            dataRow[colIdx] = cell;
          }
        });

        if (row.data) {
          for (const key of Object.keys(row.data)) {
            const match = key.match(/^_col_(\d+)$/);
            if (match) {
              const colIdx = parseInt(match[1], 10);
              if (colIdx >= colIds.length && !dataRow[colIdx]) {
                const val = row.data[key];
                const cell = getCellValue(val);
                const styleVal = row.cell_styles?.[key];
                if (styleVal && typeof styleVal === 'string' && styles[styleVal]) {
                  cell.s = styleVal;
                  cell.si = styleVal;
                }
                if (cell.v !== undefined || cell.f || cell.s) {
                  dataRow[colIdx] = cell;
                }
              }
            }
          }
        }

        let dataRowIdx = row.row_order;
        while (progUsedPositions.has(dataRowIdx)) dataRowIdx++;
        progUsedPositions.add(dataRowIdx);

        dataValues.push(dataRow);
        metaValues.push([{
          v: JSON.stringify({ id: row.id, version: row.version, order: dataRowIdx, orig: row.row_order }),
          t: 1,
        }]);

        rowMetaByIndex.set(`${sheetId}:::${dataRowIdx}`, {
          id: row.id,
          version: row.version,
          hash: computeRowHash(row.data || {}, row.formulas || undefined, row.cell_styles || undefined),
        });
      });

      try {
        sheet.getRange(startRow, 0, chunk.length, numCols).setValues(dataValues);
      } catch (e) {
        console.warn('[PROGRESSIVE] set data values failed:', e);
      }

      try {
        sheet.getRange(startRow, HIDDEN_META_COL, chunk.length, 1).setValues(metaValues);
      } catch (e) {
        console.warn('[PROGRESSIVE] set meta values failed:', e);
      }

      processedCount += chunk.length;
      onProgress?.(processedCount, processedCount + items.length);
      hasMore = items.length > 0;
    }
  }
}
const UniverList: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState('');
  const [title, setTitle] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const apiRef = useRef<any>(null);
  const wbRef = useRef<any>(null);
  const autoSaveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const saveNowRef = useRef<() => Promise<void>>(async () => {});

  // Component-level refs instead of module-level mutable state
  const rowMetaByIndexRef = useRef<Map<string, { id: number; version: number; hash: string }>>(new Map());
  const saveInProgressRef = useRef(false);
  const univerInstanceRef = useRef<any>(null);
  const univerAPIRef = useRef<any>(null);
  const workbookIdRef = useRef<string | null>(null);
  const colIdsRef = useRef<string[]>([]);
  const dirtyRef = useRef(false);

  const loadData = useCallback(async (datasetId: number) => {
    const dsRes = await datasetsApi.get(datasetId);
    return dsRes.data as Dataset;
  }, []);

  // WebSocket для real-time уведомлений от других пользователей
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!id) return;
    const datasetId = parseInt(id, 10);
    let disposed = false;

    // Сбрасываем state для нового dataset
    rowMetaByIndexRef.current = new Map();
    saveInProgressRef.current = false;
    univerInstanceRef.current = null;
    univerAPIRef.current = null;
    workbookIdRef.current = null;

    // Подключаемся к WebSocket с токеном
    const connectWs = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const token = getAccessToken() || '';
      const currentUser = getCurrentUser();
      const currentUserId = currentUser?.id;
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/${datasetId}?token=${encodeURIComponent(token)}`);
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          // Не показываем уведомление о своих же изменениях
          if (currentUserId && msg.user_id === currentUserId) return;
          if (msg.type === 'cell_updated' || msg.type === 'row_updated' || msg.type === 'rows_updated') {
            if (!disposed) {
              toast('Данные изменены другим пользователем', {
                icon: '🔄',
                duration: 3000,
              });
            }
          }
          if (msg.type === 'rows_created' || msg.type === 'rows_deleted') {
            if (!disposed) {
              toast('Структура таблицы изменена другим пользователем. Рекомендуется перезагрузить.', {
                icon: '⚠️',
                duration: 5000,
              });
            }
          }
        } catch { /* ignore */ }
      };
      ws.onclose = () => {
        if (!disposed) {
          // Переподключаемся через 5 секунд
          setTimeout(() => { if (!disposed) connectWs(); }, 5000);
        }
      };
      wsRef.current = ws;
    };
    connectWs();

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);

    (async () => {
      try {
        setLoading(true);
        setProgress('Загрузка таблицы...');

        const ds = await loadData(datasetId);
        if (disposed) return;
        setDataset(ds);
        setTitle(ds.name);

        setProgress('Загрузка данных...');
        const colIds = ds.columns.map((c: any) => c.id);
        colIdsRef.current = colIds;
        const { wbData, remainingBySheet } = await buildWorkbookData(datasetId, ds, (loaded, total) => {
          if (!disposed) setProgress(`Загрузка данных (${loaded}/${total})...`);
        }, rowMetaByIndexRef.current, INITIAL_LOAD_ROWS);
        if (disposed) return;

        setProgress('Инициализация редактора...');
        await initUniver('univer-container', datasetId, univerInstanceRef, univerAPIRef);

        const univerAPI = univerAPIRef.current;
        apiRef.current = univerAPI;

        const fWorkbook = univerAPI.createWorkbook(wbData);
        if (fWorkbook) {
          workbookIdRef.current = fWorkbook.getId();
          wbRef.current = fWorkbook;
        } else {
          throw new Error('Не удалось создать рабочую книгу');
        }

        const hasRemaining = Object.values(remainingBySheet).some(r => r.length > 0);
        if (hasRemaining) {
          const dsStyles = ds.styles || {};
          progressiveLoad(remainingBySheet, colIds, dsStyles, rowMetaByIndexRef.current, univerAPIRef.current, fWorkbook, wbData, (loaded, total) => {
            if (!disposed) setProgress(`Загрузка данных (${loaded + INITIAL_LOAD_ROWS}/${total + INITIAL_LOAD_ROWS})...`);
          });
        }

        // Регистрируем русские executor-алиасы и описания ПОСЛЕ createWorkbook
        // (т.к. executors заполняются в onReady, который триггерится createWorkbook)
        try {
          const { IFunctionService } = await import('@univerjs/engine-formula');
          const injector = univerInstanceRef.current.__getInjector();
          const ruAliases = (univerInstanceRef as any).__ruAliases;
          const { registerRussianExecutorAliases, createFormulaRusToEngConverter, registerRussianDescriptions } = await import('../utils/russianFormulas');
          const functionService = injector.get(IFunctionService);
          registerRussianExecutorAliases(functionService, ruAliases);

          // Убираем формулы с функциями, которые Univer не поддерживает (SUBTOTAL и т.п.)
          try {
            const executors = functionService.getExecutors();
            if (executors && fWorkbook) {
              const sheets = fWorkbook.getSheets?.() || [];
              for (const sheet of sheets) {
                const cellData = (sheet as any).getCellData?.() || {};
                const toFix: Array<{ row: number; col: number; v: any; t?: number }> = [];
                for (const rowKey of Object.keys(cellData)) {
                  const row = cellData[rowKey];
                  if (!row || typeof row !== 'object') continue;
                  for (const colKey of Object.keys(row)) {
                    const cell = row[colKey];
                    if (!cell || typeof cell.f !== 'string') continue;
                    const fnMatch = cell.f.match(/^=([A-Za-z_]\w*)/);
                    if (!fnMatch) continue;
                    if (!executors.has(fnMatch[1]) && cell.v !== undefined && cell.v !== null) {
                      toFix.push({ row: Number(rowKey), col: Number(colKey), v: cell.v, t: cell.t });
                      delete cell.f;
                    }
                  }
                }
                if (toFix.length > 0) {
                  for (const { row, col, v, t } of toFix) {
                    try {
                      (sheet as any).getRange?.(row, col, 1, 1)?.setValues?.([[{ v, t: t ?? (typeof v === 'number' ? 2 : 1) }]]);
                    } catch (e2) { /* skip */ }
                  }
                  console.log(`[STRIP] Fixed ${toFix.length} cells with unsupported formulas`);
                }
              }
            }
          } catch (e) {
            console.warn('[STRIP] Failed to strip unsupported formulas:', e);
          }

          // Регистрируем русские описания для поиска/подсказок
          try {
            const { IDescriptionService } = await import('@univerjs/sheets-formula');
            if (injector.has(IDescriptionService)) {
              registerRussianDescriptions(injector.get(IDescriptionService), ruAliases);
            } else {
              console.warn('[RUSSIAN] IDescriptionService not available in injector');
            }
          } catch (e) {
            console.warn('[RUSSIAN] Failed to register descriptions:', e);
          }

          // Quick-fix: перехватываем команды/мутации установки значений и конвертируем
          // русские имена функций в английские. Нужно и для SetRangeValuesCommand (прямой ввод в ячейку),
          // и для SetRangeValuesMutation (ввод через строку формул).
          const convertFormula = createFormulaRusToEngConverter((univerInstanceRef as any).__ruAliases);
          const { ICommandService } = await import('@univerjs/core');
          const commandService = injector.get(ICommandService);
          const targetIds = new Set([
            'sheet.command.set-range-values',
            'sheet.mutation.set-range-values',
          ]);
          const dispose = commandService.beforeCommandExecuted((command: any) => {
            if (!targetIds.has(command.id)) return;
            const params = command.params;
            if (!params) return;
            const cellValue = params.cellValue || params.value;
            if (!cellValue || typeof cellValue !== 'object') return;
            // Рекурсивно обходим cellValue и заменяем f (формулы)
            const walk = (obj: any): boolean => {
              if (!obj || typeof obj !== 'object') return false;
              let changed = false;
              for (const key of Object.keys(obj)) {
                const val = obj[key];
                if (key === 'f' && typeof val === 'string' && val.startsWith('=')) {
                  const converted = convertFormula(val);
                  if (converted !== val) {
                    obj[key] = converted;
                    changed = true;
                  }
                } else if (typeof val === 'object') {
                  if (walk(val)) changed = true;
                }
              }
              return changed;
            };
            walk(cellValue);
          });
          // Отпишемся при размонтировании
          (univerInstanceRef as any).__rusDisposables = (univerInstanceRef as any).__rusDisposables || [];
          (univerInstanceRef as any).__rusDisposables.push(dispose);

          // 2. Слушаем команды форматирования и сохраняем
          const MODIFYING_COMMANDS = new Set([
            'sheet.command.set-range-values',
            'sheet.mutation.set-range-values',
            'sheet.command.set-style',
            'sheet.command.set-bold',
            'sheet.command.set-italic',
            'sheet.command.set-underline',
            'sheet.command.set-stroke',
            'sheet.command.set-overline',
            'sheet.command.set-font-family',
            'sheet.command.set-font-size',
            'sheet.command.set-text-color',
            'sheet.command.reset-text-color',
            'sheet.command.set-background-color',
            'sheet.command.reset-background-color',
            'sheet.command.set-vertical-text-align',
            'sheet.command.set-horizontal-text-align',
            'sheet.command.set-text-wrap',
            'sheet.command.set-text-rotation',
            'sheet.command.set-border',
            'sheet.command.set-border-position',
            'sheet.command.set-border-style',
            'sheet.command.set-border-color',
            'sheet.command.set-border-basic',
            'sheet.command.clear-selection-all',
            'sheet.command.clear-selection-format',
            'sheet.command.clear-selection-content',
            'sheet.command.set-range-bold',
            'sheet.command.set-range-italic',
            'sheet.command.set-range-underline',
            'sheet.command.set-range-stroke',
            'sheet.command.set-range-subscript',
            'sheet.command.set-range-superscript',
            'sheet.command.set-range-fontsize',
            'sheet.command.set-range-font-increase',
            'sheet.command.set-range-font-decrease',
            'sheet.command.set-range-font-family',
            'sheet.command.set-range-text-color',
            'sheet.command.reset-range-text-color',
          ]);
          const fmtDispose = commandService.beforeCommandExecuted((command: any) => {
            if (isStyleFixup) return;
            if (MODIFYING_COMMANDS.has(command.id)) {
              dirtyRef.current = true;
              setTimeout(() => saveNowRef.current(), 0);
            }
          });
          (univerInstanceRef as any).__rusDisposables.push(fmtDispose);

          // 3. Дублируем стили через FRange API, чтобы пустые ячейки тоже получали заливку/границы
          const STYLE_FIXUP_COMMANDS = new Set([
            'sheet.command.set-background-color',
            'sheet.command.set-border-basic',
            'sheet.command.clear-selection-all',
            'sheet.command.clear-selection-format',
          ]);
          let isStyleFixup = false;
          const fixupDispose = commandService.onCommandExecuted((command: any) => {
            if (isStyleFixup) return;
            if (!STYLE_FIXUP_COMMANDS.has(command.id)) return;

            isStyleFixup = true;
            try {
              const wb = univerAPIRef.current?.getActiveWorkbook();
              if (!wb) return;
              const sheet = wb.getActiveSheet();
              if (!sheet) return;
              const selection = sheet.getSelection();
              if (!selection) return;
              const ranges = selection.getActiveRangeList();
              if (!ranges || ranges.length === 0) return;

              for (const range of ranges) {
                if (command.id === 'sheet.command.set-background-color') {
                  const color = command.params?.value;
                  if (color) {
                    range.setBackground(color);
                    // Univer's save() excludes cells that have only `s` (style) without
                    // `si` (style ID) or `v` (value) — see isNullCell().
                    // Set `si` on all affected cells so they survive serialization.
                    const r = range.getRange();
                    const rowCount = r.endRow - r.startRow + 1;
                    const colCount = r.endColumn - r.startColumn + 1;
                    if (rowCount * colCount <= 5000) {
                      const updates: any[][] = [];
                      for (let row = r.startRow; row <= r.endRow; row++) {
                        const rowArr: any[] = [];
                        for (let col = r.startColumn; col <= r.endColumn; col++) {
                          const cell = sheet.getRange(row, col).getCellData();
                          if (cell && typeof cell.s === 'string') {
                            rowArr.push({ ...cell, si: cell.s });
                          } else if (cell) {
                            rowArr.push(cell);
                          } else {
                            rowArr.push(null);
                          }
                        }
                        updates.push(rowArr);
                      }
                      range.setValues(updates);
                    }
                  }
                } else if (command.id === 'sheet.command.set-border-basic') {
                  const info = command.params?.value;
                  if (info) {
                    range.setBorder(info.type, info.style ?? 0, info.color);
                  }
                } else if (command.id === 'sheet.command.clear-selection-format') {
                  const r = range.getRange();
                  const rowCount = r.endRow - r.startRow + 1;
                  const colCount = r.endColumn - r.startColumn + 1;
                  if (rowCount * colCount <= 5000) {
                    const updates: any[][] = [];
                    let hasUpdates = false;
                    for (let row = r.startRow; row <= r.endRow; row++) {
                      const rowArr: any[] = [];
                      for (let col = r.startColumn; col <= r.endColumn; col++) {
                        const cell = sheet.getRange(row, col).getCellData();
                        if (cell) {
                          const hasStyle = cell.si != null || cell.s != null;
                          if (hasStyle) {
                            const hasValue = cell.v !== undefined && cell.v !== null;
                            const hasFormula = cell.f != null;
                            if (hasValue || hasFormula) {
                              rowArr.push({ v: cell.v, t: cell.t, f: cell.f, si: null, s: null });
                            } else {
                              rowArr.push(null);
                            }
                            hasUpdates = true;
                          } else if (cell.v !== undefined || cell.f != null) {
                            rowArr.push(cell);
                          } else {
                            rowArr.push(null);
                          }
                        } else {
                          rowArr.push(null);
                        }
                      }
                      updates.push(rowArr);
                    }
                    if (hasUpdates) {
                      range.setValues(updates);
                    }
                  }
                } else if (command.id === 'sheet.command.clear-selection-all') {
                    const r = range.getRange();

                    // Визуальный fixup: принудительно очищаем s/si/v
                    const MAX_FIXUP = 5000;
                    if ((r.endRow - r.startRow + 1) * (r.endColumn - r.startColumn + 1) <= MAX_FIXUP) {
                      const updates: any[][] = [];
                      let hasUpdates = false;
                      for (let row = r.startRow; row <= r.endRow; row++) {
                        const rowArr: any[] = [];
                        for (let col = r.startColumn; col <= r.endColumn; col++) {
                          const cell = sheet.getRange(row, col).getCellData();
                          if (cell && (cell.si != null || cell.s != null || cell.v !== undefined || cell.f != null)) {
                            rowArr.push({ v: null, s: null, si: null });
                            hasUpdates = true;
                          } else {
                            rowArr.push(null);
                          }
                        }
                        updates.push(rowArr);
                      }
                      if (hasUpdates) range.setValues(updates);
                    }

                    // fmtDispose (beforeCommandExecuted) уже поставил dirtyRef + saveNow,
                    // но на всякий случай дублируем — если сетка уже очищена, setValues
                    // ничего не сделает и fmtDispose не сработает.
                    dirtyRef.current = true;
                    setTimeout(() => saveNowRef.current(), 0);
                  }
              }
            } catch (e) {
              console.warn('[STYLE FIXUP]', e);
            } finally {
              isStyleFixup = false;
            }
          });
          (univerInstanceRef as any).__rusDisposables.push(fixupDispose);
        } catch (e) {
          console.warn('Failed to register Russian formula interceptor:', e);
        }

        setLoading(false);
        setProgress('');
      } catch (err: any) {
        if (!disposed) {
          toast.error('Ошибка загрузки: ' + extractError(err));
          setLoading(false);
          setProgress('');
        }
      }
    })();

    return () => {
      disposed = true;
      window.removeEventListener('beforeunload', handleBeforeUnload);

      // Закрываем WebSocket
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      const doSaveThenCleanup = async () => {
        if (wbRef.current && apiRef.current && datasetId) {
          try {
            const wb = univerAPIRef.current?.getActiveWorkbook();
            if (wb) { try { await wb.endEditingAsync(true); } catch {} }
            await saveToBackend(datasetId, wbRef.current, colIdsRef.current, rowMetaByIndexRef.current, saveInProgressRef);
          } catch (err: any) {
            console.error('[UNMOUNT] save error', err);
          }
        }
      };
      doSaveThenCleanup();

      if (workbookIdRef.current && univerAPIRef.current) {
        try {
          univerAPIRef.current.disposeUnit(workbookIdRef.current);
        } catch {}
        workbookIdRef.current = null;
      }
      // Отписываем русский interceptor
      const disposables = (univerInstanceRef as any).__rusDisposables;
      if (disposables) {
        for (const d of disposables) { try { d.dispose(); } catch {} }
        (univerInstanceRef as any).__rusDisposables = null;
      }
      univerInstanceRef.current = null;
      univerAPIRef.current = null;
    };
  }, [id, loadData]);

  const saveNow = useCallback(async () => {
    if (!dataset || !apiRef.current || !wbRef.current) return;
    try {
      const wb = univerAPIRef.current?.getActiveWorkbook();
      if (wb) {
        try { await wb.endEditingAsync(true); } catch {}
      }
      await saveToBackend(dataset.id, wbRef.current, colIdsRef.current, rowMetaByIndexRef.current, saveInProgressRef, dataset);
      dirtyRef.current = false;
    } catch (err: any) {
      console.error('[SAVE] error', err);
      toast.error('Ошибка сохранения: ' + extractError(err));
    }
  }, [dataset]);

  // Всегда храним актуальный saveNow в ref, чтобы замыкания в
  // beforeCommandExecuted / onCommandExecuted не захватывали stale dataset.
  saveNowRef.current = saveNow;

  // Автосохранение каждые 30 секунд
  useEffect(() => {
    if (!dataset) return;
    autoSaveTimerRef.current = setInterval(async () => {
      if (!apiRef.current || !wbRef.current) return;
      try {
        await saveNow();
      } catch (err: any) {
        console.error('[AUTOSAVE] error', err);
      }
    }, 30000);
    return () => {
      if (autoSaveTimerRef.current) {
        clearInterval(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
    };
  }, [dataset, saveNow]);

  // Сохранение по Enter и при потере фокуса
  useEffect(() => {
    if (!dataset) return;
    const container = document.getElementById('univer-container');
    if (!container) return;

    // Save on Enter — deferred so Univer commits the edit first
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        setTimeout(() => saveNow(), 0);
      }
    };
    const handleBlur = () => {
      saveNow();
    };

    container.addEventListener('keydown', handleKeyDown);
    window.addEventListener('blur', handleBlur);
    return () => {
      container.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('blur', handleBlur);
    };
  }, [dataset, saveNow]);

  const handleBack = useCallback(async () => {
    if (autoSaveTimerRef.current) {
      clearInterval(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }
    if (dataset && apiRef.current && wbRef.current) {
      try {
        const wb = univerAPIRef.current?.getActiveWorkbook();
        if (wb) { try { await wb.endEditingAsync(true); } catch {} }
        await saveToBackend(dataset.id, wbRef.current, colIdsRef.current, rowMetaByIndexRef.current, saveInProgressRef, dataset);
      } catch (err: any) {
        console.error('[BACK] save error', err);
        toast.error('Ошибка сохранения: ' + extractError(err));
      }
    }
    navigate('/datasets');
  }, [dataset, navigate]);

  return (
    <div className={`pen-list-container${isFullscreen ? ' fixed inset-0 z-50 bg-white' : ''}`}>
      <div className="pen-list-header">
        <button className="pen-list-back-btn" onClick={handleBack} title="Назад">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <input
          className="pen-list-title-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <div className="pen-list-header-spacer" />
        <button
          onClick={() => setIsFullscreen(!isFullscreen)}
          className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
          title={isFullscreen ? 'Свернуть' : 'На весь экран'}
        >
          {isFullscreen ? <Minimize2 className="w-5 h-5" /> : <Maximize2 className="w-5 h-5" />}
        </button>
      </div>
      <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', background: '#f8fafc', zIndex: 10, gap: '8px',
          }}>
            <span className="text-slate-500">{progress || 'Загрузка таблицы...'}</span>
          </div>
        )}
        <div
          id="univer-container"
          ref={containerRef}
          style={{ width: '100%', height: '100%' }}
        />
      </div>
    </div>
  );
};

async function saveToBackend(datasetId: number, fWorkbook: any,
  colIds: string[],
  rowMetaByIndex: Map<string, { id: number; version: number; hash: string }>,
  saveInProgressRef: { current: boolean },
  datasetArg?: Dataset) {
  if (saveInProgressRef.current) return;
  saveInProgressRef.current = true;
  try {
    if (!fWorkbook || typeof fWorkbook.save !== 'function') return;
    const snapshot = fWorkbook.save() as IWorkbookData;
    if (!snapshot) return;
    const allSheetIds = snapshot.sheetOrder || [];
    if (allSheetIds.length === 0) return;

    const originalSubSheets = datasetArg?.sub_sheets || [];
    const originalSheetIds = new Set(originalSubSheets.map(s => s.id));
    const originalSheetMap = new Map(originalSubSheets.map(s => [s.id, s]));

    // ===== 0. Создаём новые листы на бэкенде =====
    for (const sheetId of allSheetIds) {
      if (originalSheetIds.has(sheetId)) continue;
      const list = snapshot.sheets[sheetId];
      if (!list) continue;
      const name = list.name || `Лист${allSheetIds.indexOf(sheetId) + 1}`;
      try {
        await listyApi.create(datasetId, name);
      } catch (e) {
        console.error('[SAVE] create sheet', sheetId, e);
      }
    }

    // ===== 1. Удаляем листы, которых больше нет =====
    for (const origSheet of originalSubSheets) {
      if (!allSheetIds.includes(origSheet.id)) {
        try {
          await listyApi.delete(datasetId, origSheet.id);
        } catch (e) {
          console.error('[SAVE] delete sheet', origSheet.id, e);
        }
      }
    }

    // ===== 2. Сохраняем стили =====
    try {
      if (snapshot.styles && Object.keys(snapshot.styles).length > 0) {
        await datasetsApi.updateStyles(datasetId, snapshot.styles);
      } else if (datasetArg?.styles && Object.keys(datasetArg.styles).length > 0) {
        await datasetsApi.updateStyles(datasetId, datasetArg.styles);
      }
    } catch (e) {
      console.error('[SAVE] failed to save styles:', e);
    }

    // ===== 3. Обрабатываем каждый лист =====
    let totalToDelete: number[] = [];
    let totalToUpdate: Array<{ id: number; version: number; data: Record<string, any>; formulas?: any; cell_styles?: any; row_order?: number; sheet_id?: string }> = [];
    let totalToCreate: Array<{ data: Record<string, any>; formulas?: any; cell_styles?: any; row_order?: number; sheet_id?: string }> = [];

    const newSubSheets: any[] = [];

    for (const sheetId of allSheetIds) {
      const list = snapshot.sheets[sheetId];
      if (!list) continue;

      const prefix = sheetId + ':::';
      const cellData = list.cellData || {};
      const currentKeys = new Set(Object.keys(cellData).map(Number));

      // ===== 3a. Преобразуем строки листа =====
      const currentRows = new Map<number, { data: Record<string, any>; formulas?: Record<string, string>; cell_styles?: Record<string, any>; meta?: { id: number; version: number } }>();

      for (const rowKey of currentKeys) {
        const row = cellData[rowKey];
        if (!row) continue;

        let meta: { id: number; version: number; orig?: number } | undefined;
        const hiddenCell = row[HIDDEN_META_COL];
        if (hiddenCell?.v) {
          try { meta = JSON.parse(hiddenCell.v as string); } catch {}
        }
        if (!meta) {
          const stored = rowMetaByIndex.get(prefix + rowKey);
          if (stored) meta = { id: stored.id, version: stored.version };
        }

        // detect shift: if orig row_order differs from current position
        const origOrder = (meta as any)?.orig;
        const wasShifted = origOrder !== undefined && origOrder !== rowKey;

        const data: Record<string, any> = {};
        const formulas: Record<string, string> = {};
        const cell_styles: Record<string, any> = {};

        for (const colKeyStr of Object.keys(row)) {
          const colKey = Number(colKeyStr);
          if (colKey === HIDDEN_META_COL || colKey < 0) continue;
          const cell = row[colKey];
          const colId = colKey < colIds.length ? colIds[colKey] : `_col_${colKey}`;

          if (cell.f) formulas[colId] = cell.f;
          const styleRef = cell.s || cell.si;
          if (styleRef) cell_styles[colId] = styleRef;
          if (cell.v !== undefined && cell.v !== null) data[colId] = cell.v;
        }

        currentRows.set(rowKey, {
          data,
          formulas: Object.keys(formulas).length > 0 ? formulas : undefined,
          cell_styles: Object.keys(cell_styles).length > 0 ? cell_styles : undefined,
          meta,
          wasShifted,
        });
      }

      // ===== 3b. Определяем изменения строк для этого листа =====
      const toDelete: number[] = [];
      const toUpdate: Array<{ id: number; version: number; data: Record<string, any>; formulas?: any; cell_styles?: any; row_order?: number; sheet_id?: string }> = [];
      const toCreate: Array<{ data: Record<string, any>; formulas?: any; cell_styles?: any; row_order?: number; sheet_id?: string }> = [];

      const versionsById = new Map<number, number>();
      const idToOldKey = new Map<number, string>();
      for (const [k, stored] of rowMetaByIndex) {
        if (!k.startsWith(prefix)) continue;
        versionsById.set(stored.id, stored.version);
        idToOldKey.set(stored.id, k);
      }

      for (const [storedKey, stored] of rowMetaByIndex) {
        if (!storedKey.startsWith(prefix)) continue;
        const localKey = parseInt(storedKey.slice(prefix.length), 10);
        if (!currentKeys.has(localKey) && stored.hash !== '{}' && stored.hash !== '') {
          toDelete.push(stored.id);
        }
      }

      for (const [rowKey, converted] of currentRows) {
        const { data, formulas, cell_styles, meta, wasShifted } = converted;
        const hasData = Object.keys(data).length > 0;
        const hasFormulas = formulas && Object.keys(formulas).length > 0;
        const hasStyles = cell_styles && Object.keys(cell_styles).length > 0;
        const isEmpty = !hasData && !hasFormulas;

        if (meta && meta.id) {
          let storedVersion = meta.version;
          const storedFromMeta = versionsById.get(meta.id);
          if (storedFromMeta !== undefined) storedVersion = storedFromMeta;

          const hash = computeRowHash(data, formulas, cell_styles);
          let oldHash = '';
          for (const [, s] of rowMetaByIndex) {
            if (s.id === meta.id) { oldHash = s.hash; break; }
          }

          const oldKey = idToOldKey.get(meta.id);
          const posChanged = oldKey !== undefined && parseInt(oldKey.slice(prefix.length), 10) !== rowKey;

          const shouldUpdate = posChanged || wasShifted;
          if (hash !== oldHash || shouldUpdate) {
            const wasEmptyBefore = oldHash === '{}' || oldHash === '';
            if (!isEmpty || !wasEmptyBefore || hasStyles || shouldUpdate) {
              const oldHadStyles = oldHash.includes('_s_');
              const finalStyles = hasStyles ? cell_styles : (oldHadStyles ? {} : undefined);
              const upd: any = { id: meta.id, version: storedVersion, data, formulas, cell_styles: finalStyles, sheet_id: sheetId };
              if (shouldUpdate) {
                upd.row_order = rowKey;
              }
              if (hash !== oldHash) {
                console.log('[SAVE_UPD]', JSON.stringify({ id: upd.id, data: upd.data, styles: upd.cell_styles }));
              }
              toUpdate.push(upd);
            }
          }
        } else {
          if (isEmpty && !hasStyles) continue;
          const hash = computeRowHash(data, formulas, cell_styles);
          let foundExisting = false;
          for (const [, stored] of rowMetaByIndex) {
            if (stored.hash === hash) { foundExisting = true; break; }
          }
          if (!foundExisting) {
            console.log('[[[CREATE]]]', JSON.stringify({ rowKey, row_order: rowKey, data }));
            toCreate.push({ data, formulas, cell_styles, row_order: rowKey, sheet_id: sheetId });
          }
        }
      }

      totalToDelete.push(...toDelete);
      totalToUpdate.push(...toUpdate);
      totalToCreate.push(...toCreate);

      // ===== 3c. Собираем метаданные листа для обновления sub_sheets =====
      const origSheet = originalSheetMap.get(sheetId);
      const mergeData = (list.mergeData || []).map((m: any) => ({
        startRow: m.startRow, endRow: m.endRow,
        startColumn: m.startColumn, endColumn: m.endColumn,
      }));
      const rowHeights: Record<string, number> = {};
      if (list.rowData) {
        for (const [rk, rd] of Object.entries(list.rowData) as [string, any][]) {
          if (rd?.h) rowHeights[rk] = Math.round(Number(rd.h) * 72 / 96 * 10) / 10;
        }
      }
      const colWidths: Record<string, number> = {};
      if (list.columnData) {
        for (const [ck, cd] of Object.entries(list.columnData) as [string, any][]) {
          if (cd?.w) colWidths[ck] = Math.round((Number(cd.w) - 5) / 7 * 100) / 100;
        }
      }

      newSubSheets.push({
        ...(origSheet || { id: sheetId, order: newSubSheets.length, frozen_rows: 0, frozen_columns: 0, hidden_columns: [], hidden_rows: [] }),
        name: list.name || origSheet?.name || `Лист${newSubSheets.length + 1}`,
        merged_cells: mergeData,
        ...(Object.keys(rowHeights).length > 0 ? { row_heights: rowHeights } : {}),
        ...(Object.keys(colWidths).length > 0 ? { column_widths: colWidths } : {}),
      });
    } // end for each sheet

    // ===== 4. Обновляем sub_sheets =====
    if (datasetArg) {
      try {
        await datasetsApi.update(datasetId, { sub_sheets: newSubSheets as any });
      } catch (e) {
        console.error('[SAVE] update sub_sheets', e);
      }
    }

    // ===== 5. Если нет изменений данных — выходим =====
    if (totalToDelete.length === 0 && totalToUpdate.length === 0 && totalToCreate.length === 0) {
      saveInProgressRef.current = false;
      return;
    }

    // ===== 6. Выполняем операции со строками =====
    if (totalToCreate.length > 0 && totalToDelete.length > 0) {
      await rowsApi.batchDelete(datasetId, totalToDelete);
    }

    console.log('[SAVE] changes:', totalToDelete.length + ' delete, ' + totalToUpdate.length + ' update, ' + totalToCreate.length + ' create');
    const updatedVersions: Array<{ id: number; version: number }> = [];
    if (totalToUpdate.length > 0) {
      const chunkSize = 500;
      for (let i = 0; i < totalToUpdate.length; i += chunkSize) {
        const chunk = totalToUpdate.slice(i, i + chunkSize);
        const res = await rowsApi.batchUpdate(datasetId, chunk);
        const respData = res.data as any;
        if (Array.isArray(respData?.rows)) {
          updatedVersions.push(...respData.rows);
        } else {
          for (const upd of chunk) updatedVersions.push({ id: upd.id, version: upd.version + 1 });
        }
      }
    }

    const createdRows: Array<{ id: number; version: number }> = [];
    if (totalToCreate.length > 0) {
      const chunkSize = 1000;
      for (let i = 0; i < totalToCreate.length; i += chunkSize) {
        const chunk = totalToCreate.slice(i, i + chunkSize);
        const res = await rowsApi.batchCreate(datasetId, chunk);
        const respData = res.data as any;
        if (Array.isArray(respData?.rows)) {
          for (const r of respData.rows) createdRows.push({ id: r.id, version: r.version });
        }
      }
    }

    // ===== 7. Обновляем rowMetaByIndex =====
    const prevRowMetaByIndex = new Map(rowMetaByIndex);
    rowMetaByIndex.clear();

    const versionMap = new Map<number, number>();
    for (const r of updatedVersions) versionMap.set(r.id, r.version);

    for (const sheetId of allSheetIds) {
      const list = snapshot.sheets[sheetId];
      if (!list) continue;
      const prefix = sheetId + ':::';
      const cellData = list.cellData || {};

      for (const rowKeyStr of Object.keys(cellData)) {
        const rowKey = Number(rowKeyStr);
        const row = cellData[rowKey];
        if (!row) continue;

        let meta: { id: number; version: number } | undefined;
        const hiddenCell = row[HIDDEN_META_COL];
        if (hiddenCell?.v) {
          try { meta = JSON.parse(hiddenCell.v as string); } catch {}
        }
        if (!meta) continue;

        const data: Record<string, any> = {};
        const formulas: Record<string, string> = {};
        const cell_styles: Record<string, any> = {};
        for (const colKeyStr of Object.keys(row)) {
          const colKey = Number(colKeyStr);
          if (colKey === HIDDEN_META_COL || colKey < 0) continue;
          const cell = row[colKey];
          const colId = colKey < colIds.length ? colIds[colKey] : `_col_${colKey}`;
          if (cell.f) formulas[colId] = cell.f;
          const styleRef = cell.s || cell.si;
          if (styleRef) cell_styles[colId] = styleRef;
          if (cell.v !== undefined && cell.v !== null) data[colId] = cell.v;
        }

        const newVer = versionMap.get(meta.id) ?? meta.version;
        const hash = computeRowHash(data, formulas, cell_styles);
        rowMetaByIndex.set(prefix + rowKey, { id: meta.id, version: newVer, hash });
      }
    }

    let createdIdx = 0;
    for (const sheetId of allSheetIds) {
      const list = snapshot.sheets[sheetId];
      if (!list) continue;
      const prefix = sheetId + ':::';
      const cellData = list.cellData || {};

      for (const rowKeyStr of Object.keys(cellData)) {
        const rowKey = Number(rowKeyStr);
        const key = prefix + rowKey;
        if (rowMetaByIndex.has(key)) continue;

        // Восстанавливаем мету из предыдущего сохранения (если строка была создана ранее)
        const prevStored = prevRowMetaByIndex.get(key);
        if (prevStored) {
          const row = cellData[rowKey];
          if (!row) continue;
          const data: Record<string, any> = {};
          for (const colKeyStr of Object.keys(row)) {
            const colKey = Number(colKeyStr);
            if (colKey === HIDDEN_META_COL || colKey < 0) continue;
            const cell = row[colKey];
            const colId = colKey < colIds.length ? colIds[colKey] : `_col_${colKey}`;
            if (cell.v !== undefined && cell.v !== null) data[colId] = cell.v;
          }
          const newVer = versionMap.get(prevStored.id) ?? prevStored.version;
          const hash = computeRowHash(data);
          rowMetaByIndex.set(key, { id: prevStored.id, version: newVer, hash });
          continue;
        }

        const created = createdRows[createdIdx];
        if (created) {
          const row = cellData[rowKey];
          if (!row) continue;
          const data: Record<string, any> = {};
          for (const colKeyStr of Object.keys(row)) {
            const colKey = Number(colKeyStr);
            if (colKey === HIDDEN_META_COL || colKey < 0) continue;
            const cell = row[colKey];
            const colId = colKey < colIds.length ? colIds[colKey] : `_col_${colKey}`;
            if (cell.v !== undefined && cell.v !== null) data[colId] = cell.v;
          }
          const hash = computeRowHash(data);
          rowMetaByIndex.set(key, { id: created.id, version: created.version, hash });
          createdIdx++;
        }
      }
    }

    // Fallback: перезагружаем трекинг с сервера при ошибках ответа
    try {
      if ((totalToCreate.length > 0 && createdRows.length === 0) || (totalToUpdate.length > 0 && updatedVersions.length === 0)) {
        rowMetaByIndex.clear();
        for (const sheetId of allSheetIds) {
          const prefix = sheetId + ':::';
          const freshRows = (await rowsApi.list(datasetId, 1, 100000, undefined, undefined, undefined, undefined, sheetId)).data.items as any[];
          (freshRows || []).forEach((r: any, idx: number) => {
            let key = r.row_order != null ? r.row_order : idx;
            const compKey = prefix + key;
            while (rowMetaByIndex.has(compKey)) key++;
            rowMetaByIndex.set(prefix + key, { id: r.id, version: r.version, hash: computeRowHash(r.data || {}) });
          });
        }
      }
    } catch {}

    // ===== 8. Записываем мету обратно в скрытую колонку для всех листов =====
    try {
      for (const sheetId of allSheetIds) {
        const snapCellData = snapshot.sheets?.[sheetId]?.cellData;
        if (!snapCellData) continue;
        const prefix = sheetId + ':::';
        for (const [key, stored] of rowMetaByIndex) {
          if (!key.startsWith(prefix)) continue;
          const rowKey = parseInt(key.slice(prefix.length), 10);
          if (!snapCellData[rowKey]) snapCellData[rowKey] = {};
          const idStr = JSON.stringify({ id: stored.id, version: stored.version, order: rowKey });
          snapCellData[rowKey][HIDDEN_META_COL] = { v: idStr, t: 1 };
        }
      }
    } catch {}

  } catch (err: any) {
    if (err?.response?.status === 409) {
      toast.error('Конфликт версий. Данные были изменены другим пользователем. Перезагрузите страницу.', { duration: 6000 });
    } else {
      throw err;
    }
  } finally {
    saveInProgressRef.current = false;
  }
}

export default UniverList;
