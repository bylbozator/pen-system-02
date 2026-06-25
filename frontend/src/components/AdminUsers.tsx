import React, { useEffect, useState } from 'react';
import { admin } from '../api';
import toast from 'react-hot-toast';
import ConfirmDialog from './ConfirmDialog';
import {
  Plus,
  Search,
  Upload,
  Pencil,
  ToggleLeft,
  ToggleRight,
  KeyRound,
  Trash2,
  X,
} from 'lucide-react';

interface User { id: number; username: string; email: string; role_id: number; is_active: boolean; last_name?: string; first_name?: string; middle_name?: string; department?: string; }
interface Role { id: number; name: string; }

const AdminUsers: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState<'create' | 'edit' | null>(null);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [deleteDialog, setDeleteDialog] = useState<{ isOpen: boolean; userId: number | null }>({ isOpen: false, userId: null });
  const [searchQuery, setSearchQuery] = useState('');
  const [resetPwdDialog, setResetPwdDialog] = useState<{ isOpen: boolean; userId: number | null; newPassword: string }>({ isOpen: false, userId: null, newPassword: '' });
  const [formData, setFormData] = useState({ username: '', email: '', password: '', role_id: 0, last_name: '', first_name: '', middle_name: '', department: '' });

  const fetchData = async (search?: string) => {
    try {
      const params: any = {};
      if (search) params.search = search;
      const [usersRes, rolesRes] = await Promise.all([admin.users.list(0, 100, params), admin.roles.list()]);
      setUsers(usersRes.data);
      setRoles(rolesRes.data);
    } catch { toast.error('Ошибка загрузки'); } finally { setLoading(false); }
  };
  useEffect(() => { fetchData(); }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    fetchData(searchQuery);
  };

  const handleBatchImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const lines = text.split('\n').filter(line => line.trim());
    if (lines.length < 2) { toast.error('Файл должен содержать заголовки и данные'); return; }
    const headers = lines[0].split(',').map(h => h.trim());
    const usersData = lines.slice(1).map(line => {
      const values = line.split(',');
      const user: any = {};
      headers.forEach((h, i) => { user[h] = values[i]?.trim(); });
      if (user.role_id) user.role_id = parseInt(user.role_id, 10) || 0;
      return user;
    });
    try {
      await admin.users.batchCreate(usersData);
      toast.success(`Импортировано ${usersData.length} пользователей`);
      fetchData();
    } catch { toast.error('Ошибка импорта'); } finally { if (event.target) event.target.value = ''; }
  };

  const resetForm = () => setFormData({ username: '', email: '', password: '', role_id: 0, last_name: '', first_name: '', middle_name: '', department: '' });

  const startCreate = () => { setEditingUser(null); setShowForm('create'); resetForm(); };
  const startEdit = (user: User) => {
    setEditingUser(user);
    setShowForm('edit');
    setFormData({
      username: user.username, email: user.email, password: '',
      role_id: user.role_id, last_name: user.last_name || '',
      first_name: user.first_name || '', middle_name: user.middle_name || '',
      department: user.department || '',
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingUser) {
        const payload: any = { username: formData.username, email: formData.email, role_id: formData.role_id, last_name: formData.last_name, first_name: formData.first_name, middle_name: formData.middle_name, department: formData.department };
        if (formData.password) payload.password = formData.password;
        await admin.users.update(editingUser.id, payload);
        toast.success('Пользователь обновлён');
      } else {
        if (!formData.password) { toast.error('Введите пароль'); return; }
        await admin.users.create(formData);
        toast.success('Пользователь создан');
      }
      setShowForm(null); setEditingUser(null); resetForm(); fetchData();
    } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка'); }
  };

  const handleToggleActive = async (user: User) => {
    try { await admin.users.update(user.id, { is_active: !user.is_active }); toast.success('Статус обновлён'); fetchData(); } catch { toast.error('Ошибка'); }
  };

  const handleDeleteClick = (id: number) => setDeleteDialog({ isOpen: true, userId: id });
  const handleConfirmDelete = async () => {
    if (deleteDialog.userId === null) return;
    try { await admin.users.delete(deleteDialog.userId); toast.success('Удалён'); fetchData(); } finally { setDeleteDialog({ isOpen: false, userId: null }); }
  };

  const handleResetPwdClick = (userId: number) => setResetPwdDialog({ isOpen: true, userId, newPassword: '' });
  const handleConfirmResetPwd = async () => {
    if (!resetPwdDialog.userId || !resetPwdDialog.newPassword) { toast.error('Введите новый пароль'); return; }
    try {
      await admin.users.resetPassword(resetPwdDialog.userId, resetPwdDialog.newPassword);
      toast.success('Пароль сброшен');
      setResetPwdDialog({ isOpen: false, userId: null, newPassword: '' });
    } catch (err: any) { toast.error(err.response?.data?.detail || 'Ошибка сброса пароля'); }
  };

  if (loading) return <div className="flex items-center justify-center h-64 text-slate-500"><div className="w-5 h-5 border-2 border-slate-300 border-t-indigo-500 rounded-full animate-spin mr-2" />Загрузка...</div>;

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Пользователи</h2>
          <p className="text-sm text-slate-500 mt-1">Управление учётными записями</p>
        </div>
        <div className="flex gap-2">
          <label className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 cursor-pointer transition-colors">
            <Upload className="w-4 h-4" />
            Импорт CSV
            <input type="file" accept=".csv" onChange={handleBatchImport} className="hidden" />
          </label>
          <button onClick={startCreate} className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">
            <Plus className="w-4 h-4" />
            Новый пользователь
          </button>
        </div>
      </div>

      <form onSubmit={handleSearch} className="mb-4 flex gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Поиск по логину, email, фамилии..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full border border-slate-300 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none"
          />
        </div>
        <button type="submit" className="px-4 py-2.5 bg-white border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors">Поиск</button>
        {searchQuery && (
          <button type="button" onClick={() => { setSearchQuery(''); fetchData(); }} className="text-sm text-indigo-600 hover:text-indigo-800 flex items-center gap-1">
            <X className="w-3 h-3" /> Сброс
          </button>
        )}
      </form>

      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => { setShowForm(null); setEditingUser(null); }}>
          <div className="bg-white rounded-2xl shadow-xl w-[550px] p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-6">{editingUser ? 'Редактирование пользователя' : 'Новый пользователь'}</h3>
            <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
              <input type="text" placeholder="Логин *" value={formData.username} onChange={e => setFormData({ ...formData, username: e.target.value })} className="col-span-2 border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" required />
              <input type="email" placeholder="Эл. почта *" value={formData.email} onChange={e => setFormData({ ...formData, email: e.target.value })} className="col-span-2 border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" required />
              <input type="password" placeholder={editingUser ? 'Новый пароль (оставьте пустым)' : 'Пароль *'} value={formData.password} onChange={e => setFormData({ ...formData, password: e.target.value })} className="border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
              <select value={formData.role_id} onChange={e => setFormData({ ...formData, role_id: parseInt(e.target.value) })} className="border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" required>
                <option value={0}>Выберите роль</option>
                {roles.map(role => (<option key={role.id} value={role.id}>{role.name}</option>))}
              </select>
              <input type="text" placeholder="Фамилия" value={formData.last_name} onChange={e => setFormData({ ...formData, last_name: e.target.value })} className="border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
              <input type="text" placeholder="Имя" value={formData.first_name} onChange={e => setFormData({ ...formData, first_name: e.target.value })} className="border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
              <input type="text" placeholder="Отчество" value={formData.middle_name} onChange={e => setFormData({ ...formData, middle_name: e.target.value })} className="border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
              <input type="text" placeholder="Отдел (для RLS)" value={formData.department} onChange={e => setFormData({ ...formData, department: e.target.value })} className="border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none" />
              <div className="col-span-2 flex justify-end gap-3 mt-2">
                <button type="button" onClick={() => { setShowForm(null); setEditingUser(null); }} className="px-5 py-2.5 border border-slate-300 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors">Отмена</button>
                <button type="submit" className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 transition-colors">{editingUser ? 'Сохранить' : 'Создать'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {['ID', 'Логин', 'Эл. почта', 'Роль', 'Отдел', 'Статус', 'Действия'].map(h => (
                <th key={h} className="px-5 py-3.5 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {users.map(user => (
              <tr key={user.id} className="hover:bg-slate-50 transition-colors">
                <td className="px-5 py-3.5 text-sm text-slate-500">{user.id}</td>
                <td className="px-5 py-3.5 text-sm font-medium text-slate-800">{user.username}</td>
                <td className="px-5 py-3.5 text-sm text-slate-600">{user.email}</td>
                <td className="px-5 py-3.5 text-sm text-slate-600">{roles.find(r => r.id === user.role_id)?.name || '—'}</td>
                <td className="px-5 py-3.5 text-sm text-slate-600">{user.department || '—'}</td>
                <td className="px-5 py-3.5">
                  <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${
                    user.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${user.is_active ? 'bg-emerald-500' : 'bg-red-500'}`} />
                    {user.is_active ? 'Активен' : 'Заблокирован'}
                  </span>
                </td>
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-1">
                    <button onClick={() => startEdit(user)} className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="Изменить"><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => handleToggleActive(user)} className={`p-2 rounded-lg transition-colors ${user.is_active ? 'text-slate-400 hover:text-amber-600 hover:bg-amber-50' : 'text-slate-400 hover:text-emerald-600 hover:bg-emerald-50'}`} title={user.is_active ? 'Заблокировать' : 'Активировать'}>
                      {user.is_active ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
                    </button>
                    <button onClick={() => handleResetPwdClick(user.id)} className="p-2 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-colors" title="Сброс пароля"><KeyRound className="w-4 h-4" /></button>
                    <button onClick={() => handleDeleteClick(user.id)} className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="Удалить"><Trash2 className="w-4 h-4" /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog isOpen={deleteDialog.isOpen} title="Удаление пользователя" message="Вы уверены? Все данные пользователя будут удалены." confirmText="Удалить" cancelText="Отмена" onConfirm={handleConfirmDelete} onCancel={() => setDeleteDialog({ isOpen: false, userId: null })} type="danger" />

      {resetPwdDialog.isOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setResetPwdDialog({ isOpen: false, userId: null, newPassword: '' })}>
          <div className="bg-white rounded-2xl shadow-xl w-96 p-6" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-2">Сброс пароля</h3>
            <p className="text-sm text-slate-500 mb-4">Введите новый пароль для пользователя</p>
            <input type="password" placeholder="Новый пароль" value={resetPwdDialog.newPassword} onChange={(e) => setResetPwdDialog({ ...resetPwdDialog, newPassword: e.target.value })} className="w-full border border-slate-300 rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-indigo-500 outline-none mb-4" />
            <div className="flex justify-end gap-3">
              <button onClick={() => setResetPwdDialog({ isOpen: false, userId: null, newPassword: '' })} className="px-4 py-2 border border-slate-300 rounded-xl text-sm text-slate-700 hover:bg-slate-50 transition-colors">Отмена</button>
              <button onClick={handleConfirmResetPwd} className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm hover:bg-indigo-700 transition-colors">Сбросить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminUsers;
