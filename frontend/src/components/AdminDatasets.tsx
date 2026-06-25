import React, { useEffect, useState } from 'react';
import { admin, datasets, Dataset, ColumnDef } from '../api';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';
import ConfirmDialog from './ConfirmDialog';
import { ExternalLink, Archive, RefreshCw, Trash2, Columns3, Check, X } from 'lucide-react';
import LoadingSpinner from './ui/LoadingSpinner';
import Pagination from './ui/Pagination';

const AdminDatasets: React.FC = () => {
  const [allDatasets, setAllDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const [deleteDialog, setDeleteDialog] = useState<{ isOpen: boolean; datasetId: number | null; datasetName: string }>({ isOpen: false, datasetId: null, datasetName: '' });
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const pageSize = 20;
  const [ownerChange, setOwnerChange] = useState<{ datasetId: number | null; newOwnerId: string }>({ datasetId: null, newOwnerId: '' });
  const [structureEdit, setStructureEdit] = useState<{ datasetId: number | null; datasetName: string; columns: ColumnDef[] } | null>(null);
  const [savingStructure, setSavingStructure] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const res = await admin.datasets.list(page * pageSize, pageSize, true);
      setAllDatasets(res.data.items);
      setTotal(res.data.total);
    } catch { toast.error('Ошибка загрузки таблиц'); } finally { setLoading(false); }
  };

  useEffect(() => { fetchAll(); }, [page]);

  const handleArchive = async (datasetId: number) => {
    try { await datasets.delete(datasetId); toast.success('Таблица архивирована'); fetchAll(); } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка архивирования'); }
  };

  const handleRestore = async (datasetId: number) => {
    try { await datasets.restore(datasetId); toast.success('Таблица восстановлена'); fetchAll(); } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка восстановления'); }
  };

  const handlePermanentDelete = async () => {
    if (!deleteDialog.datasetId) return;
    try {
      await datasets.permanentDelete(deleteDialog.datasetId);
      toast.success(`Таблица "${deleteDialog.datasetName}" удалена навсегда`);
      setDeleteDialog({ isOpen: false, datasetId: null, datasetName: '' });
      fetchAll();
    } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка удаления'); }
  };

  const handleOwnerChange = async (datasetId: number) => {
    if (!ownerChange.newOwnerId.trim()) { toast.error('Введите ID нового владельца'); return; }
    const newOwnerId = parseInt(ownerChange.newOwnerId, 10);
    if (isNaN(newOwnerId)) { toast.error('Некорректный ID'); return; }
    try {
      await admin.datasets.changeOwner(datasetId, newOwnerId);
      toast.success('Владелец изменён');
      setOwnerChange({ datasetId: null, newOwnerId: '' });
      fetchAll();
    } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка смены владельца'); }
  };

  const handleSaveStructure = async () => {
    if (!structureEdit) return;
    setSavingStructure(true);
    try {
      const validCols = structureEdit.columns.filter(c => c.header.trim());
      await admin.datasets.updateStructure(structureEdit.datasetId!, { columns: validCols });
      toast.success('Структура сохранена');
      setStructureEdit(null);
      fetchAll();
    } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка сохранения структуры'); } finally { setSavingStructure(false); }
  };

  const updateColInEdit = (idx: number, field: keyof ColumnDef, value: any) => {
    if (!structureEdit) return;
    setStructureEdit({ ...structureEdit, columns: structureEdit.columns.map((c, i) => i === idx ? { ...c, [field]: value } : c) });
  };

  const addColToEdit = () => {
    if (!structureEdit) return;
    setStructureEdit({ ...structureEdit, columns: [...structureEdit.columns, { id: Math.random().toString(36).slice(2, 8), header: '', type: 'string' as const, editableBy: [], colorGroup: undefined }] });
  };

  const removeColFromEdit = (idx: number) => {
    if (!structureEdit || structureEdit.columns.length <= 1) return;
    setStructureEdit({ ...structureEdit, columns: structureEdit.columns.filter((_, i) => i !== idx) });
  };

  const totalPages = Math.ceil(total / pageSize);

  if (loading) return <LoadingSpinner fullHeight />;

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-slate-800">Управление таблицами</h2>
        <p className="text-sm text-slate-500 mt-1">Все таблицы системы, включая архивные</p>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {['ID', 'Название', 'Владелец', 'Создан', 'Статус', 'Столбцов', 'Действия'].map(h => (
                <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {allDatasets.map((ds) => (
              <tr key={ds.id} className={`${ds.archived ? 'bg-slate-50' : 'hover:bg-slate-50'} transition-colors`}>
                <td className="px-5 py-3.5 text-sm text-slate-500">{ds.id}</td>
                <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{ds.name}</td>
                <td className="px-5 py-3.5 text-sm">
                  {ownerChange.datasetId === ds.id ? (
                    <div className="flex items-center gap-1">
                      <input type="text" value={ownerChange.newOwnerId} onChange={(e) => setOwnerChange({ ...ownerChange, newOwnerId: e.target.value })}
                        className="w-16 border border-slate-300 rounded-lg px-2 py-1 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="ID" />
                      <button onClick={() => handleOwnerChange(ds.id)} className="p-1 text-emerald-600 hover:bg-emerald-50 rounded transition-colors"><Check className="w-4 h-4" /></button>
                      <button onClick={() => setOwnerChange({ datasetId: null, newOwnerId: '' })} className="p-1 text-slate-400 hover:bg-slate-100 rounded transition-colors"><X className="w-4 h-4" /></button>
                    </div>
                  ) : (
                    <span className="cursor-pointer text-indigo-600 hover:text-indigo-800 text-xs"
                      onClick={() => setOwnerChange({ datasetId: ds.id, newOwnerId: String(ds.owner_id) })}>
                      {ds.owner_name || `#${ds.owner_id}`}
                    </span>
                  )}
                </td>
                <td className="px-5 py-3.5 text-sm text-slate-500">{new Date(ds.created_at).toLocaleDateString('ru-RU')}</td>
                <td className="px-5 py-3.5">
                  <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${
                    ds.archived ? 'bg-slate-100 text-slate-600' : 'bg-emerald-100 text-emerald-700'
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${ds.archived ? 'bg-slate-400' : 'bg-emerald-500'}`} />
                    {ds.archived ? 'Архив' : 'Активен'}
                  </span>
                </td>
                <td className="px-5 py-3.5 text-sm text-slate-500">{ds.columns?.length || 0}</td>
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-1">
                    <button onClick={() => navigate(`/datasets/${ds.id}`)} className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="Открыть"><ExternalLink className="w-4 h-4" /></button>
                    <button onClick={() => setStructureEdit({ datasetId: ds.id, datasetName: ds.name, columns: ds.columns?.length ? [...ds.columns] : [{ id: 'col1', header: '', type: 'string', editableBy: [] }] })}
                      className="p-2 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-colors" title="Структура"><Columns3 className="w-4 h-4" /></button>
                    {!ds.archived ? (
                      <button onClick={() => handleArchive(ds.id)} className="p-2 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition-colors" title="В архив"><Archive className="w-4 h-4" /></button>
                    ) : (
                      <>
                        <button onClick={() => handleRestore(ds.id)} className="p-2 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="Восстановить"><RefreshCw className="w-4 h-4" /></button>
                        <button onClick={() => setDeleteDialog({ isOpen: true, datasetId: ds.id, datasetName: ds.name })} className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Удалить"><Trash2 className="w-4 h-4" /></button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />

      {structureEdit && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setStructureEdit(null)}>
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 p-6 border-b border-slate-200">
              <div className="w-10 h-10 rounded-xl bg-violet-100 flex items-center justify-center">
                <Columns3 className="w-5 h-5 text-violet-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold">Структура: {structureEdit.datasetName}</h3>
                <p className="text-sm text-slate-500">Редактирование колонок таблицы</p>
              </div>
            </div>
            <div className="p-6 overflow-y-auto flex-1">
              <div className="space-y-3">
                {structureEdit.columns.map((col, idx) => (
                  <div key={col.id} className="flex gap-2 items-center">
                    <span className="text-xs text-slate-400 w-6 text-right font-mono">{idx + 1}</span>
                    <input value={col.header} onChange={e => updateColInEdit(idx, 'header', e.target.value)}
                      className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="Заголовок" />
                    <select value={col.type} onChange={e => updateColInEdit(idx, 'type', e.target.value)}
                      className="border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none">
                      <option value="string">Текст</option>
                      <option value="number">Число</option>
                      <option value="date">Дата</option>
                    </select>
                    <button onClick={() => removeColFromEdit(idx)}
                      className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Удалить колонку">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
              <button onClick={addColToEdit} className="mt-3 text-sm text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1">
                + Добавить колонку
              </button>
            </div>
            <div className="p-6 border-t border-slate-200 flex justify-end gap-3">
              <button onClick={() => setStructureEdit(null)} className="px-5 py-2.5 border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors">Отмена</button>
              <button onClick={handleSaveStructure} disabled={savingStructure}
                className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                {savingStructure ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog isOpen={deleteDialog.isOpen} title="Удаление таблицы" message={`Вы действительно хотите безвозвратно удалить "${deleteDialog.datasetName}"? Все данные будут потеряны.`} confirmText="Удалить навсегда" cancelText="Отмена" onConfirm={handlePermanentDelete} onCancel={() => setDeleteDialog({ isOpen: false, datasetId: null, datasetName: '' })} type="danger" />
    </div>
  );
};

export default AdminDatasets;
