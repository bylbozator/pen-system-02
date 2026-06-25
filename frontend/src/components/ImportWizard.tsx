// frontend/src/components/ImportWizard.tsx

import React, { useState, useCallback, useRef, useEffect } from 'react';
import api from '../api';
import toast from 'react-hot-toast';

// Типы для данных предпросмотра
interface ListPreview {
  name: string;
  headers: string[];
  sample_rows: string[][];
}

const ImportWizard: React.FC<{ onClose: () => void; onSuccess: () => void }> = ({ onClose, onSuccess }) => {
  const [step, setStep] = useState<'select' | 'preview' | 'importing' | 'done'>('select');
  const [file, setFile] = useState<File | null>(null);
  const [previewData, setPreviewData] = useState<ListPreview[]>([]);
  const [selectedListy, setSelectedListy] = useState<Set<string>>(new Set());
  const [headerRowIndex, setHeaderRowIndex] = useState(-1);
  const [noHeaders, setNoHeaders] = useState(true);
  const [createMode, setCreateMode] = useState<'new' | 'replace'>('new');
  const [replaceDatasetId, setReplaceDatasetId] = useState<number | null>(null);
  const [importAll, setImportAll] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const previewTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Авто-предпросмотр при изменении headerRowIndex (с debounce)
  useEffect(() => {
    if (step !== 'preview' || noHeaders || !file) return;
    if (previewTimerRef.current) clearTimeout(previewTimerRef.current);
    previewTimerRef.current = setTimeout(() => {
      handlePreview(headerRowIndex);
    }, 500);
    return () => {
      if (previewTimerRef.current) clearTimeout(previewTimerRef.current);
    };
  }, [headerRowIndex, noHeaders]);

  // Обработчик выбора файла
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;
    setFile(selectedFile);
    setError(null);
  };

  // Загрузка предпросмотра
  const handlePreview = useCallback(async (hri?: number) => {
    if (!file) return;
    setError(null);
    setStep('preview');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const params = hri != null ? `?header_row_index=${hri}` : '';
      const res = await api.post(`/import-export/preview${params}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const listy = res.data.sheets as ListPreview[];
      if (listy.length === 0) {
        setError('Файл не содержит листов');
        setStep('select');
        return;
      }
      setPreviewData(listy);
      setSelectedListy(new Set(listy.map(s => s.name)));
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Ошибка предпросмотра файла';
      setError(msg);
      setStep('select');
    }
  }, [file]);

  // Переключение чекбокса листа
  const toggleList = (name: string) => {
    setSelectedListy(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  // Запуск импорта
  const handleImport = useCallback(async () => {
    if (!file || selectedListy.size === 0) return;
    const listNames = importAll
      ? previewData.map(s => s.name)
      : Array.from(selectedListy);
    if (createMode === 'replace' && !replaceDatasetId) {
      toast.error('Укажите ID таблицы для замены');
      return;
    }
    setStep('importing');
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const params = new URLSearchParams();
      listNames.forEach(name => params.append('sheet_names', name));
      params.append('header_row_index', String(headerRowIndex));
      params.append('create_mode', createMode);
      if (createMode === 'replace' && replaceDatasetId) {
        params.append('target_dataset_ids', String(replaceDatasetId));
      }

      const res = await api.post(`/import-export/import?${params.toString()}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      toast.success(`Импортирован датасет с ${listNames.length} листами`);
      if (res.data.errors?.length > 0) {
        toast.error(`Ошибки: ${res.data.errors.join('; ')}`);
      }
      setStep('done');
      onSuccess();
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Ошибка импорта';
      setError(msg);
      setStep('preview');
    }
  }, [file, selectedListy, createMode, replaceDatasetId, headerRowIndex, onSuccess, previewData, importAll]);

  // Сброс и закрытие
  const handleClose = () => {
    setFile(null);
    setPreviewData([]);
    setSelectedListy(new Set());
    setReplaceDatasetId(null);
    setCreateMode('new');
    setStep('select');
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Заголовок */}
        <div className="flex justify-between items-center p-4 border-b">
          <h3 className="text-xl font-bold">
            {step === 'select' && 'Импорт Excel – выбор файла'}
            {step === 'preview' && 'Предпросмотр листов'}
            {step === 'importing' && 'Импорт...'}
            {step === 'done' && 'Готово'}
          </h3>
          <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 text-2xl">×</button>
        </div>

        {/* Тело */}
        <div className="p-4 overflow-y-auto flex-1">
          {error && (
            <div className="mb-4 p-3 bg-red-50 text-red-700 rounded-lg text-sm">{error}</div>
          )}

          {/* Шаг 1: выбор файла */}
          {step === 'select' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Выберите файл (.xlsx, .xls, .csv, .tsv, .ods)
              </label>
              <input
                type="file"
                accept=".xlsx,.xls,.csv,.tsv,.ods"
                onChange={handleFileChange}
                className="w-full border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={() => handlePreview(noHeaders ? -1 : headerRowIndex)}
                disabled={!file}
                className="mt-4 bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                Далее
              </button>
            </div>
          )}

          {/* Шаг 2: предпросмотр и выбор листов */}
          {step === 'preview' && (
            <div>
              <div className="mb-4 flex items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={noHeaders}
                    onChange={e => {
                      const checked = e.target.checked;
                      setNoHeaders(checked);
                      if (checked) {
                        setHeaderRowIndex(-1);
                        handlePreview(-1);
                      } else {
                        setHeaderRowIndex(0);
                        handlePreview(0);
                      }
                    }}
                    className="rounded"
                  />
                  <span className="font-medium">Файл не содержит заголовков</span>
                </label>
                {!noHeaders && (
                  <div className="flex items-center gap-2">
                    <label className="text-sm font-medium text-gray-700">
                      Строка заголовков:
                    </label>
                    <input
                      type="number"
                      min={0}
                      value={headerRowIndex}
                      onChange={e => setHeaderRowIndex(parseInt(e.target.value) || 0)}
                      className="w-20 border rounded px-2 py-1 text-sm"
                    />
                  </div>
                )}
              </div>

              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">Режим</label>
                <select
                  value={createMode}
                  onChange={e => setCreateMode(e.target.value as any)}
                  className="border rounded px-2 py-1 text-sm"
                >
                  <option value="new">Создать новую таблицу (все листы — как вкладки)</option>
                  <option value="replace">Заменить данные в существующей</option>
                </select>
                {createMode === 'replace' && (
                  <div className="mt-2 flex items-center gap-2">
                    <label className="text-sm text-gray-600">ID таблицы:</label>
                    <input
                      type="number"
                      placeholder="ID"
                      value={replaceDatasetId ?? ''}
                      onChange={e => {
                        const val = parseInt(e.target.value);
                        setReplaceDatasetId(isNaN(val) ? null : val);
                      }}
                      className="w-24 border rounded px-2 py-1 text-sm"
                    />
                  </div>
                )}
              </div>

              <label className="flex items-center gap-2 mb-3 text-sm bg-blue-50 p-2 rounded-lg cursor-pointer hover:bg-blue-100">
                <input
                  type="checkbox"
                  checked={importAll}
                  onChange={e => setImportAll(e.target.checked)}
                  className="rounded"
                />
                <span className="font-medium">Импортировать все листы сразу</span>
              </label>

              <div className="space-y-3">
                {!importAll && previewData.map(list => {
                  const isSelected = selectedListy.has(list.name);
                  return (
                  <div key={list.name} className="border rounded-lg overflow-hidden">
                    <label className="flex items-center gap-2 p-2 bg-gray-50 cursor-pointer hover:bg-gray-100">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleList(list.name)}
                        className="rounded"
                      />
                      <span className="font-medium">{list.name}</span>
                      <span className="text-xs text-gray-500">({list.headers.length} колонок)</span>
                    </label>
                    {isSelected && (
                      <div className="p-2">
                        <div className="overflow-x-auto">
                          <table className="text-xs border-collapse">
                            <thead>
                              <tr className="bg-blue-50">
                                {list.headers.map((h, i) => (
                                  <th key={i} className="border px-2 py-1 font-medium">{h || `К${i + 1}`}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {list.sample_rows.slice(0, 5).map((row, ri) => (
                                <tr key={ri}>
                                  {row.map((cell, ci) => (
                                    <td key={ci} className="border px-2 py-1">{cell}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                  );
                })}
              </div>

              <div className="mt-4 flex gap-2">
                <button
                  onClick={() => setStep('select')}
                  className="px-4 py-2 bg-gray-200 rounded hover:bg-gray-300"
                >
                  Назад
                </button>
                <button
                  onClick={handleImport}
                  disabled={!importAll && selectedListy.size === 0}
                  className="px-6 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                >
                  Импортировать выбранные
                </button>
              </div>
            </div>
          )}

          {/* Шаг 3: импорт */}
          {step === 'importing' && (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <span className="ml-3">Импорт выполняется...</span>
            </div>
          )}

          {/* Шаг 4: завершено */}
          {step === 'done' && (
            <div className="text-center py-8">
              <div className="text-green-600 text-5xl mb-4">✓</div>
              <p>Импорт успешно завершён.</p>
              <button
                onClick={handleClose}
                className="mt-4 bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
              >
                Закрыть
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ImportWizard;