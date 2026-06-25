import React, { useEffect, useState } from 'react';
import { admin, DatasetSchema, ColumnDef } from '../api';
import toast from 'react-hot-toast';
import ConfirmDialog from './ConfirmDialog';
import { Plus, Pencil, Copy, Trash2, Columns3, ClipboardList, X, Search } from 'lucide-react';
import LoadingSpinner from './ui/LoadingSpinner';
import Modal from './ui/Modal';

const EMPTY_COL = (): ColumnDef => ({ id: Math.random().toString(36).slice(2, 8), header: '', type: 'string', editableBy: [], colorGroup: undefined });

interface SchemasViewProps {
  readonly?: boolean;
}

const SchemasView: React.FC<SchemasViewProps> = ({ readonly = false }) => {
  const [schemas, setSchemas] = useState<DatasetSchema[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingSchema, setEditingSchema] = useState<DatasetSchema | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState('');
  const [formColumns, setFormColumns] = useState<ColumnDef[]>([EMPTY_COL()]);
  const [saving, setSaving] = useState(false);
  const [deleteDialog, setDeleteDialog] = useState<{ isOpen: boolean; schemaId: number | null; schemaName: string }>({ isOpen: false, schemaId: null, schemaName: '' });
  const [search, setSearch] = useState('');

  const fetchSchemas = async () => {
    setLoading(true);
    try {
      const res = await admin.schemas.list();
      setSchemas(res.data);
    } catch { toast.error('Ошибка загрузки схем'); } finally { setLoading(false); }
  };

  useEffect(() => { fetchSchemas(); }, []);

  const openCreate = () => { setEditingSchema(null); setFormName(''); setFormColumns([EMPTY_COL()]); setShowForm(true); };

  const openEdit = (schema: DatasetSchema) => {
    setEditingSchema(schema);
    setFormName(schema.name);
    setFormColumns(schema.columns.length > 0 ? [...schema.columns] : [EMPTY_COL()]);
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!formName.trim()) { toast.error('Введите название схемы'); return; }
    const validCols = formColumns.filter(c => c.header.trim());
    if (validCols.length === 0) { toast.error('Добавьте хотя бы одну колонку с заголовком'); return; }
    setSaving(true);
    try {
      const payload = { name: formName.trim(), columns: validCols };
      if (editingSchema) { await admin.schemas.update(editingSchema.id, payload); toast.success('Схема обновлена'); }
      else { await admin.schemas.create(payload); toast.success('Схема создана'); }
      setShowForm(false);
      fetchSchemas();
    } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка сохранения'); } finally { setSaving(false); }
  };

  const handleDuplicate = async (schema: DatasetSchema) => {
    try { await admin.schemas.duplicate(schema.id, `${schema.name} (копия)`); toast.success('Схема скопирована'); fetchSchemas(); } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка копирования'); }
  };

  const handleDelete = async () => {
    if (!deleteDialog.schemaId) return;
    try { await admin.schemas.delete(deleteDialog.schemaId); toast.success(`Схема "${deleteDialog.schemaName}" удалена`); setDeleteDialog({ isOpen: false, schemaId: null, schemaName: '' }); fetchSchemas(); } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка удаления'); }
  };

  const updateCol = (idx: number, field: keyof ColumnDef, value: any) => setFormColumns(prev => prev.map((c, i) => i === idx ? { ...c, [field]: value } : c));
  const addCol = () => setFormColumns(prev => [...prev, EMPTY_COL()]);
  const removeCol = (idx: number) => { if (formColumns.length <= 1) { toast.error('Нельзя удалить последнюю колонку'); return; } setFormColumns(prev => prev.filter((_, i) => i !== idx)); };

  const filtered = search
    ? schemas.filter((s) => s.name.toLowerCase().includes(search.toLowerCase()))
    : schemas;

  if (loading) return <LoadingSpinner fullHeight />;

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Схемы таблиц</h2>
          <p className="text-sm text-slate-500 mt-1">Шаблоны для создания новых таблиц</p>
        </div>
        <div className="flex gap-3 items-center">
          {readonly && (
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input type="text" placeholder="Поиск схем..." value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full border border-slate-300 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
            </div>
          )}
          {!readonly && (
            <button onClick={openCreate} className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">
              <Plus className="w-4 h-4" />
              Создать схему
            </button>
          )}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="text-center py-20 bg-white rounded-2xl border border-slate-200">
          <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-4">
            <ClipboardList className="w-8 h-8 text-slate-400" />
          </div>
          <p className="text-slate-500 text-lg mb-1">
            {search ? 'Ничего не найдено' : 'Схем пока нет'}
          </p>
          <p className="text-slate-400 text-sm">
            {search ? 'Попробуйте изменить поисковый запрос' : (readonly ? 'Схемы создаются администратором системы' : 'Создайте первую схему')}
          </p>
        </div>
      ) : (
        <div className="grid gap-4">
          {filtered.map(schema => (
            <div key={schema.id} className="bg-white rounded-2xl border border-slate-200 p-5 hover:shadow-sm transition-shadow">
              <div className="flex justify-between items-start">
                <div className="flex items-start gap-4 flex-1 min-w-0">
                  {readonly && (
                    <div className="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center flex-shrink-0">
                      <Columns3 className="w-6 h-6 text-indigo-600" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <h3 className="text-lg font-semibold text-slate-800">{schema.name}</h3>
                    <p className="text-sm text-slate-500 mt-1">
                      {schema.columns.length} колонок · создана {new Date(schema.created_at).toLocaleDateString('ru-RU')}
                    </p>
                    <div className="flex flex-wrap gap-1.5 mt-3">
                      {schema.columns.slice(0, readonly ? 12 : 10).map(col => (
                        <span key={col.id} className="inline-flex items-center gap-1.5 text-xs bg-slate-100 text-slate-700 px-2.5 py-1 rounded-lg">
                          {col.header}
                          <span className="text-slate-400">
                            {col.type === 'number' ? '#' : col.type === 'date' ? '📅' : 'Aa'}
                          </span>
                        </span>
                      ))}
                      {schema.columns.length > (readonly ? 12 : 10) && (
                        <span className="text-xs text-slate-400 px-2">+{schema.columns.length - (readonly ? 12 : 10)} ещё</span>
                      )}
                    </div>
                  </div>
                </div>
                {!readonly && (
                  <div className="flex gap-1 ml-4 flex-shrink-0">
                    <button onClick={() => openEdit(schema)} className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="Изменить"><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => handleDuplicate(schema)} className="p-2 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="Копировать"><Copy className="w-4 h-4" /></button>
                    <button onClick={() => setDeleteDialog({ isOpen: true, schemaId: schema.id, schemaName: schema.name })} className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Удалить"><Trash2 className="w-4 h-4" /></button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {!readonly && showForm && (
        <Modal isOpen={showForm} onClose={() => setShowForm(false)}
          title={editingSchema ? `Редактировать: ${editingSchema.name}` : 'Новая схема'}
          subtitle="Определите структуру колонок"
          icon={<Columns3 className="w-5 h-5 text-indigo-600" />}
          footer={
            <>
              <button onClick={() => setShowForm(false)} className="px-5 py-2.5 border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors">Отмена</button>
              <button onClick={handleSave} disabled={saving} className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors">
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </>
          }>
          <div className="mb-4">
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Название схемы</label>
            <input value={formName} onChange={e => setFormName(e.target.value)}
              className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
              placeholder="Например: Заявка на материалы" />
          </div>
          <div className="mb-2 flex justify-between items-center">
            <label className="text-sm font-medium text-slate-700">Колонки</label>
            <button onClick={addCol} className="text-sm text-indigo-600 hover:text-indigo-800 font-medium">+ Добавить колонку</button>
          </div>
          <div className="space-y-3">
            {formColumns.map((col, idx) => (
              <div key={col.id} className="flex gap-2 items-center">
                <span className="text-xs text-slate-400 w-6 text-right font-mono">{idx + 1}</span>
                <input value={col.header} onChange={e => updateCol(idx, 'header', e.target.value)}
                  className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="Заголовок" />
                <select value={col.type} onChange={e => updateCol(idx, 'type', e.target.value)}
                  className="border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 outline-none">
                  <option value="string">Текст</option>
                  <option value="number">Число</option>
                  <option value="date">Дата</option>
                </select>
                <button onClick={() => removeCol(idx)} className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Удалить колонку">
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </Modal>
      )}

      <ConfirmDialog isOpen={deleteDialog.isOpen} title="Удалить схему?" message={`Схема "${deleteDialog.schemaName}" будет удалена. Это действие необратимо.`} onConfirm={handleDelete} onCancel={() => setDeleteDialog({ isOpen: false, schemaId: null, schemaName: '' })} />
    </div>
  );
};

export default SchemasView;
