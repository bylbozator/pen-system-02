import React, { useEffect, useState } from 'react';
import { admin, Role } from '../api';
import toast from 'react-hot-toast';
import ConfirmDialog from './ConfirmDialog';
import { Plus, Pencil, Copy, Trash2, ShieldCheck } from 'lucide-react';

const PERMISSIONS_LIST = [
  { key: 'full_access', label: 'Полный доступ (администратор)' },
  { key: 'can_create_datasets', label: 'Создание таблиц' },
  { key: 'can_edit_all_datasets', label: 'Редактирование всех таблиц' },
  { key: 'can_view_all_datasets', label: 'Просмотр всех таблиц' },
  { key: 'can_edit_own_sheets', label: 'Редактирование своих таблиц (устар.)' },
  { key: 'can_edit_rows', label: 'Редактирование строк' },
  { key: 'can_edit_fact_data', label: 'Редактирование фактических данных' },
  { key: 'can_export', label: 'Экспорт данных' },
  { key: 'can_import', label: 'Импорт данных' },
  { key: 'can_manage_users', label: 'Управление пользователями' },
  { key: 'can_manage_roles', label: 'Управление ролями' },
  { key: 'can_manage_schemas', label: 'Управление схемами' },
  { key: 'can_view_reports', label: 'Просмотр отчётов' },
];

const AdminRoles: React.FC = () => {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingRole, setEditingRole] = useState<Role | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({ name: '', permissions: {} as Record<string, boolean>, description: '' });
  const [deleteDialog, setDeleteDialog] = useState<{ isOpen: boolean; roleId: number | null }>({ isOpen: false, roleId: null });
  const [duplicateDialog, setDuplicateDialog] = useState<{ isOpen: boolean; role: Role | null; newName: string }>({ isOpen: false, role: null, newName: '' });

  const fetchRoles = async () => {
    try {
      const res = await admin.roles.list();
      setRoles(res.data);
    } catch {
      toast.error('Ошибка загрузки ролей');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRoles(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await admin.roles.create(formData);
      toast.success('Роль создана');
      setShowForm(false);
      setFormData({ name: '', permissions: {}, description: '' });
      fetchRoles();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Ошибка создания');
    }
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingRole) return;
    try {
      await admin.roles.update(editingRole.id, { name: formData.name, permissions: formData.permissions, description: formData.description });
      toast.success('Роль обновлена');
      setEditingRole(null);
      setShowForm(false);
      fetchRoles();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Ошибка обновления');
    }
  };

  const startEdit = (role: Role) => {
    setEditingRole(role);
    setFormData({ name: role.name, permissions: role.permissions || {}, description: role.description || '' });
    setShowForm(true);
  };

  const handleDelete = async () => {
    if (!deleteDialog.roleId) return;
    try {
      await admin.roles.delete(deleteDialog.roleId);
      toast.success('Роль удалена');
      setDeleteDialog({ isOpen: false, roleId: null });
      fetchRoles();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Ошибка удаления');
    }
  };

  const togglePermission = (key: string) => {
    setFormData((prev) => ({
      ...prev,
      permissions: { ...prev.permissions, [key]: !prev.permissions[key] },
    }));
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-slate-500"><div className="w-5 h-5 border-2 border-slate-300 border-t-indigo-500 rounded-full animate-spin mr-2" />Загрузка...</div>;

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Роли</h2>
          <p className="text-sm text-slate-500 mt-1">Управление ролями и правами доступа</p>
        </div>
        <button
          onClick={() => { setEditingRole(null); setFormData({ name: '', permissions: {}, description: '' }); setShowForm(true); }}
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Новая роль
        </button>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => { setShowForm(false); setEditingRole(null); }}>
          <div className="bg-white rounded-2xl shadow-xl w-[520px] max-h-[85vh] overflow-y-auto p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center">
                <ShieldCheck className="w-5 h-5 text-indigo-600" />
              </div>
              <h3 className="text-lg font-semibold">{editingRole ? 'Редактирование роли' : 'Новая роль'}</h3>
            </div>
            <form onSubmit={editingRole ? handleUpdate : handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">Название *</label>
                <input type="text" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1.5">Описание</label>
                <textarea value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" rows={2} />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Права</label>
                <div className="space-y-2 border border-slate-200 rounded-xl p-4 max-h-48 overflow-y-auto">
                  {PERMISSIONS_LIST.map((perm) => (
                    <label key={perm.key} className="flex items-center gap-3 cursor-pointer p-1.5 rounded-lg hover:bg-slate-50 transition-colors">
                      <input type="checkbox" checked={!!formData.permissions[perm.key]}
                        onChange={() => togglePermission(perm.key)}
                        className="w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500" />
                      <span className="text-sm text-slate-700">{perm.label}</span>
                    </label>
                  ))}
                </div>
                <p className="text-xs text-slate-400 mt-1">full_access автоматически даёт все остальные права.</p>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button type="button" onClick={() => { setShowForm(false); setEditingRole(null); }}
                  className="px-5 py-2.5 border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors">Отмена</button>
                <button type="submit" className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">
                  {editingRole ? 'Сохранить' : 'Создать'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {['Название', 'Описание', 'Права', 'Действия'].map(h => (
                <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {roles.map((role) => (
              <tr key={role.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-5 py-4 text-sm font-medium text-slate-800">{role.name}</td>
                <td className="px-5 py-4 text-sm text-slate-500">{role.description || '—'}</td>
                <td className="px-5 py-4">
                  <div className="flex flex-wrap gap-1.5">
                    {Object.entries(role.permissions).filter(([, v]) => v).map(([key]) => {
                      const perm = PERMISSIONS_LIST.find((p) => p.key === key);
                      return (
                        <span key={key} className="px-2.5 py-1 bg-indigo-50 text-indigo-700 text-xs font-medium rounded-lg">
                          {perm?.label || key}
                        </span>
                      );
                    })}
                    {!Object.values(role.permissions).some(Boolean) && <span className="text-xs text-slate-400">Нет прав</span>}
                  </div>
                </td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-1">
                    <button onClick={() => startEdit(role)} className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="Изменить"><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => setDuplicateDialog({ isOpen: true, role, newName: `${role.name} (копия)` })}
                      className="p-2 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="Дублировать"><Copy className="w-4 h-4" /></button>
                    <button onClick={() => setDeleteDialog({ isOpen: true, roleId: role.id })}
                      className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Удалить"><Trash2 className="w-4 h-4" /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog isOpen={deleteDialog.isOpen} title="Удаление роли" message="Вы уверены? Если роль назначена пользователям, удаление невозможно." confirmText="Удалить" cancelText="Отмена" onConfirm={handleDelete} onCancel={() => setDeleteDialog({ isOpen: false, roleId: null })} type="danger" />

      {duplicateDialog.isOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setDuplicateDialog({ isOpen: false, role: null, newName: '' })}>
          <div className="bg-white rounded-2xl shadow-xl w-96 p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-2">Дублирование роли</h3>
            <p className="text-sm text-slate-500 mb-4">Исходная роль: <strong>{duplicateDialog.role?.name}</strong></p>
            <input type="text" placeholder="Название новой роли" value={duplicateDialog.newName}
              onChange={(e) => setDuplicateDialog({ ...duplicateDialog, newName: e.target.value })}
              className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none mb-4" />
            <div className="flex justify-end gap-3">
              <button onClick={() => setDuplicateDialog({ isOpen: false, role: null, newName: '' })}
                className="px-4 py-2 border border-slate-300 rounded-xl text-sm text-slate-700 hover:bg-slate-50 transition-colors">Отмена</button>
              <button onClick={async () => {
                if (!duplicateDialog.role) return;
                try {
                  await admin.roles.duplicate(duplicateDialog.role.id, duplicateDialog.newName);
                  toast.success('Роль дублирована');
                  setDuplicateDialog({ isOpen: false, role: null, newName: '' });
                  fetchRoles();
                } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка дублирования'); }
              }} className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm hover:bg-indigo-700 transition-colors">Создать копию</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminRoles;
