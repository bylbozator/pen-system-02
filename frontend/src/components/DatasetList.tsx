import React, { useEffect, useState } from 'react';
import { datasets, excel, admin, Dataset, DatasetSchema } from '../api';
import { useAuth } from '../contexts/AuthContext';
import toast from 'react-hot-toast';
import { Link, useNavigate } from 'react-router-dom';
import ConfirmDialog from './ConfirmDialog';
import ImportWizard from './ImportWizard';
import PdfParser from './PdfParser';
import LoadingSpinner from './ui/LoadingSpinner';
import Pagination from './ui/Pagination';
import {
  Table2,
  Plus,
  Upload,
  ExternalLink,
  Copy,
  Archive,
  Download,
  Trash2,
  RefreshCw,
  Calendar,
  Clock,
  MoreHorizontal,
  FileSpreadsheet,
  FolderOpen,
  FileText,
} from 'lucide-react';

const PAGE_SIZE = 12;

const DatasetList: React.FC = () => {
  const [datasetList, setDatasetList] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(0);
  const [totalDatasets, setTotalDatasets] = useState(0);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showPdfModal, setShowPdfModal] = useState(false);
  const [newDatasetName, setNewDatasetName] = useState('');
  const [schemas, setSchemas] = useState<DatasetSchema[]>([]);
  const [selectedSchemaId, setSelectedSchemaId] = useState<number | ''>('');
  const [openMenuId, setOpenMenuId] = useState<number | null>(null);

  const [exportCounters, setExportCounters] = useState<Record<string, number>>({});

  const [deleteDialog, setDeleteDialog] = useState<{ isOpen: boolean; datasetId: number | null; datasetName: string }>(
    { isOpen: false, datasetId: null, datasetName: '' }
  );
  const [restoreDialog, setRestoreDialog] = useState<{ isOpen: boolean; datasetId: number | null; datasetName: string }>(
    { isOpen: false, datasetId: null, datasetName: '' }
  );

  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role_name === 'администратор';

  const fetchDatasets = async () => {
    setLoading(true);
    try {
      const res = await datasets.list(currentPage * PAGE_SIZE, PAGE_SIZE, includeArchived);
      setDatasetList(res.data.items);
      setTotalDatasets(res.data.total);
    } catch {
      toast.error('Ошибка загрузки таблиц');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchDatasets(); }, [currentPage, includeArchived]);

  useEffect(() => {
    admin.schemas.list().then(res => setSchemas(res.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (openMenuId === null) return;
    const handleClickOutside = (e: MouseEvent) => {
      const el = document.querySelector(`[data-menu-id="${openMenuId}"]`);
      if (el && !el.contains(e.target as Node)) {
        setOpenMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [openMenuId]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDatasetName.trim()) { toast.error('Введите название таблицы'); return; }
    try {
      const payload: any = { name: newDatasetName.trim() };
      if (selectedSchemaId !== '') payload.schema_id = selectedSchemaId;
      const res = await datasets.create(payload);
      toast.success(`Таблица "${newDatasetName}" создана`);
      setNewDatasetName('');
      setSelectedSchemaId('');
      setShowCreateModal(false);
      navigate(`/datasets/${res.data.id}`);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Ошибка создания таблицы');
    }
  };

  const handleArchive = async (datasetId: number, datasetName: string) => {
    try {
      await datasets.delete(datasetId);
      toast.success(`Таблица "${datasetName}" перемещена в архив`);
      setOpenMenuId(null);
      fetchDatasets();
    } catch { toast.error('Ошибка архивирования'); }
  };

  const handlePermanentDelete = async () => {
    if (!deleteDialog.datasetId) return;
    try {
      await datasets.permanentDelete(deleteDialog.datasetId);
      toast.success(`Таблица "${deleteDialog.datasetName}" удалена навсегда`);
      setDeleteDialog({ isOpen: false, datasetId: null, datasetName: '' });
      fetchDatasets();
    } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка удаления'); }
  };

  const handleRestore = async () => {
    if (!restoreDialog.datasetId) return;
    try {
      await datasets.restore(restoreDialog.datasetId);
      toast.success(`Таблица "${restoreDialog.datasetName}" восстановлена`);
      setRestoreDialog({ isOpen: false, datasetId: null, datasetName: '' });
      fetchDatasets();
    } catch { toast.error('Ошибка восстановления'); }
  };

  const handleDuplicate = async (datasetId: number, datasetName: string) => {
    try {
      const res = await datasets.duplicate(datasetId, `${datasetName} (копия)`);
      toast.success('Копия создана');
      setOpenMenuId(null);
      navigate(`/datasets/${res.data.id}`);
    } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка копирования'); }
  };

  const handleExport = async (datasetId: number, datasetName: string) => {
    try {
      const res = await excel.export(datasetId);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      const count = exportCounters[datasetName] || 0;
      const suffix = count === 0 ? '' : ` (${count + 1})`;
      link.setAttribute('download', `${datasetName}${suffix}.xlsx`);
      setExportCounters(prev => ({ ...prev, [datasetName]: count + 1 }));
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Экспорт выполнен');
      setOpenMenuId(null);
    } catch { toast.error('Ошибка экспорта'); }
  };

  const formatDate = (dateStr: string): string =>
    new Date(dateStr).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });

  const totalPages = Math.ceil(totalDatasets / PAGE_SIZE);

  if (loading && datasetList.length === 0) {
    return <LoadingSpinner fullHeight />;
  }

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Таблицы</h1>
          <p className="text-sm text-slate-500 mt-1">
            {includeArchived ? 'Все таблицы, включая архивные' : 'Активные таблицы'}
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowPdfModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
          >
            <FileText className="w-4 h-4" />
            Парсер PDF
          </button>
          <button
            onClick={() => setShowImportModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors"
          >
            <Upload className="w-4 h-4" />
            Импорт Excel
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            Новая таблица
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-6">
        <label className="inline-flex items-center gap-2.5 cursor-pointer group">
          <div className="relative">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(e) => { setIncludeArchived(e.target.checked); setCurrentPage(0); }}
              className="sr-only peer"
            />
            <div className="w-10 h-6 bg-slate-200 rounded-full peer-checked:bg-indigo-500 transition-colors" />
            <div className="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow peer-checked:translate-x-4 transition-transform" />
          </div>
          <span className="text-sm font-medium text-slate-700 group-hover:text-slate-900 transition-colors">
            Показывать архивные таблицы
          </span>
        </label>
      </div>

      {/* Grid */}
      {datasetList.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-2xl border border-slate-200">
          <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-4">
            <FolderOpen className="w-8 h-8 text-slate-400" />
          </div>
          <p className="text-slate-500 text-lg mb-1">
            {includeArchived ? 'Нет таблиц' : 'Нет активных таблиц'}
          </p>
          <p className="text-slate-400 text-sm mb-6">
            {includeArchived ? '' : 'Создайте первую таблицу или импортируйте из Excel'}
          </p>
          {!includeArchived && (
            <div className="flex gap-3 justify-center">
              <button onClick={() => setShowImportModal(true)}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-white border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors">
                <Upload className="w-4 h-4" /> Импортировать из Excel
              </button>
              <button onClick={() => setShowCreateModal(true)}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">
                <Plus className="w-4 h-4" /> Создать новую таблицу
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
          {datasetList.map((dataset) => (
            <div
              key={dataset.id}
              className={`group bg-white rounded-2xl border transition-all hover:shadow-md ${
                dataset.archived
                  ? 'border-slate-200 bg-slate-50 hover:border-slate-300'
                  : 'border-slate-200 hover:border-indigo-200'
              }`}
            >
              <div className="p-5">
                {/* Card header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                      dataset.archived ? 'bg-slate-200' : 'bg-indigo-100'
                    }`}>
                      <Table2 className={`w-5 h-5 ${dataset.archived ? 'text-slate-500' : 'text-indigo-600'}`} />
                    </div>
                    <h3 className={`font-semibold truncate min-w-0 ${dataset.archived ? 'text-slate-600' : 'text-slate-800'}`} title={dataset.name}>
                      {dataset.name}
                    </h3>
                  </div>
                  {dataset.archived && (
                    <span className="px-2.5 py-1 text-xs font-medium bg-slate-200 text-slate-600 rounded-lg flex-shrink-0 ml-2">
                      Архив
                    </span>
                  )}
                </div>

                {/* Info */}
                <div className="space-y-1.5 mb-5">
                  <p className="text-sm text-slate-500 flex items-center gap-1.5">
                    <Calendar className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                    Создан: {formatDate(dataset.created_at)}
                  </p>
                  {dataset.updated_at && dataset.updated_at !== dataset.created_at && (
                    <p className="text-sm text-slate-500 flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                      Обновлён: {formatDate(dataset.updated_at)}
                    </p>
                  )}
                  {dataset.schema_id && (
                    <p className="text-xs text-slate-400 ml-5">Схема #{dataset.schema_id}</p>
                  )}
                </div>

                {/* Actions */}
                <div className="flex justify-between items-center pt-4 border-t border-slate-100">
                  {dataset.archived ? (
                    <>
                      <button onClick={() => setRestoreDialog({ isOpen: true, datasetId: dataset.id, datasetName: dataset.name })}
                        className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-600 hover:text-emerald-800 transition-colors">
                        <RefreshCw className="w-4 h-4" />
                        Восстановить
                      </button>
                      {isAdmin && (
                        <button onClick={() => setDeleteDialog({ isOpen: true, datasetId: dataset.id, datasetName: dataset.name })}
                          className="inline-flex items-center gap-1.5 text-sm font-medium text-red-500 hover:text-red-700 transition-colors">
                          <Trash2 className="w-4 h-4" />
                          Удалить
                        </button>
                      )}
                    </>
                  ) : (
                    <>
                      <Link to={`/datasets/${dataset.id}`}
                        className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-800 transition-colors">
                        Открыть
                        <ExternalLink className="w-4 h-4" />
                      </Link>
                      <div className="relative" data-menu-id={dataset.id}>
                        <button onClick={() => setOpenMenuId(openMenuId === dataset.id ? null : dataset.id)}
                          className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
                          <MoreHorizontal className="w-5 h-5" />
                        </button>
                        {openMenuId === dataset.id && (
                          <div className="absolute right-0 top-full mt-1 bg-white rounded-xl shadow-lg border border-slate-200 py-1.5 w-48 z-20 animate-in fade-in">
                            <button onClick={() => handleDuplicate(dataset.id, dataset.name)}
                              className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2.5 transition-colors">
                              <Copy className="w-4 h-4 text-slate-400" />
                              Копировать
                            </button>
                            <button onClick={() => handleArchive(dataset.id, dataset.name)}
                              className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2.5 transition-colors">
                              <Archive className="w-4 h-4 text-slate-400" />
                              В архив
                            </button>
                            <button onClick={() => handleExport(dataset.id, dataset.name)}
                              className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2.5 transition-colors">
                              <Download className="w-4 h-4 text-slate-400" />
                              Экспорт Excel
                            </button>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Pagination page={currentPage} totalPages={totalPages} onPageChange={setCurrentPage} />

      {/* Create modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => { setShowCreateModal(false); setNewDatasetName(''); setSelectedSchemaId(''); }}>
          <div className="bg-white rounded-2xl shadow-xl w-[460px] p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center">
                <FileSpreadsheet className="w-5 h-5 text-indigo-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-slate-800">Создание новой таблицы</h3>
                <p className="text-sm text-slate-500">Задайте название и выберите схему</p>
              </div>
            </div>
            <form onSubmit={handleCreate}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-slate-700 mb-1.5">Название таблицы</label>
                <input type="text" placeholder="Например: План-2026" value={newDatasetName}
                  onChange={(e) => setNewDatasetName(e.target.value)}
                  className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
                  autoFocus required />
              </div>
              <div className="mb-6">
                <label className="block text-sm font-medium text-slate-700 mb-1.5">Схема таблицы (необязательно)</label>
                <select value={selectedSchemaId} onChange={(e) => setSelectedSchemaId(e.target.value === '' ? '' : Number(e.target.value))}
                  className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none">
                  <option value="">— Без схемы —</option>
                  {schemas.map(s => <option key={s.id} value={s.id}>{s.name} ({s.columns.length} кол.)</option>)}
                </select>
              </div>
              <div className="flex justify-end gap-3">
                <button type="button" onClick={() => { setShowCreateModal(false); setNewDatasetName(''); setSelectedSchemaId(''); }}
                  className="px-5 py-2.5 border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors">
                  Отмена
                </button>
                <button type="submit"
                  className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">
                  Создать
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showPdfModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowPdfModal(false)}>
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-5xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 bg-white z-10 flex items-center justify-between p-6 border-b border-slate-200">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center">
                  <FileText className="w-5 h-5 text-indigo-600" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold">Парсер PDF</h3>
                  <p className="text-sm text-slate-500">Загрузите PDF для извлечения данных</p>
                </div>
              </div>
              <button onClick={() => setShowPdfModal(false)}
                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="p-6">
              <PdfParser />
            </div>
          </div>
        </div>
      )}

      {showImportModal && (
        <ImportWizard onClose={() => setShowImportModal(false)} onSuccess={() => { setShowImportModal(false); fetchDatasets(); }} />
      )}

      <ConfirmDialog
        isOpen={deleteDialog.isOpen}
        title="Удаление таблицы"
        message={`Вы уверены, что хотите навсегда удалить таблицу "${deleteDialog.datasetName}"? Все данные будут безвозвратно потеряны.`}
        confirmText="Удалить навсегда"
        cancelText="Отмена"
        onConfirm={handlePermanentDelete}
        onCancel={() => setDeleteDialog({ isOpen: false, datasetId: null, datasetName: '' })}
        type="danger"
      />

      <ConfirmDialog
        isOpen={restoreDialog.isOpen}
        title="Восстановление таблицы"
        message={`Восстановить таблицу "${restoreDialog.datasetName}" из архива?`}
        confirmText="Восстановить"
        cancelText="Отмена"
        onConfirm={handleRestore}
        onCancel={() => setRestoreDialog({ isOpen: false, datasetId: null, datasetName: '' })}
        type="info"
      />
    </div>
  );
};

export default DatasetList;
