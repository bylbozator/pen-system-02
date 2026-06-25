// frontend/src/api.ts

import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  withCredentials: true,
  paramsSerializer: (params) => {
    const sp = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        value.forEach(v => sp.append(key, String(v)));
      } else if (value !== undefined && value !== null) {
        sp.append(key, String(value));
      }
    }
    return sp.toString();
  }
});

let _accessToken: string | null = null;
let _user: User | null = null;

export const setAccessToken = (token: string | null) => {
  _accessToken = token;
  if (token) {
    sessionStorage.setItem('access_token', token);
  } else {
    sessionStorage.removeItem('access_token');
  }
};
export const getAccessToken = () => _accessToken || sessionStorage.getItem('access_token');
export const setCurrentUser = (user: User | null) => { _user = user; };
export const getCurrentUser = () => _user;

let onUnauthorized: (() => void) | null = null;

export const setOnUnauthorized = (handler: () => void) => {
  onUnauthorized = handler;
};

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  const csrfCookie = document.cookie
    .split('; ')
    .find(row => row.startsWith('csrf_token='));
  if (csrfCookie) {
    const csrfToken = csrfCookie.split('=')[1];
    config.headers['X-CSRF-Token'] = csrfToken;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      onUnauthorized?.();
    }
    return Promise.reject(error);
  }
);

export default api;

// ======================== АУТЕНТИФИКАЦИЯ ========================
export const auth = {
  login: (username: string, password: string) =>
    api.post('/auth/login', { username, password }),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
  changePassword: (oldPassword: string, newPassword: string) =>
    api.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword
    }),
  myActivity: (skip = 0, limit = 50, action?: string) =>
    api.get('/auth/me/activity', { params: { skip, limit, action } }),
};

// ======================== ДАТАСЕТЫ ========================
export const datasets = {
  // Список с пагинацией и фильтром архивных
  list: (skip = 0, limit = 100, includeArchived = false) =>
    api.get('/datasets/', { params: { skip, limit, include_archived: includeArchived } }),

  // Создание (можно передать schema_id)
  create: (data: {
    name: string;
    schema_id?: number;
    row_filter?: any;
    default_sort_column?: string;
    default_sort_order?: string;
    unique_columns?: string[];
  }) => api.post('/datasets/', data),

  // Получение одного датасета
  get: (id: number) => api.get(`/datasets/${id}`),

  // Обновление метаданных (имя, фильтры, сортировка, sub_sheets, стили)
  update: (id: number, data: {
    name?: string;
    row_filter?: any;
    default_sort_column?: string;
    default_sort_order?: string;
    unique_columns?: string[];
    styles?: Record<string, any>;
    sub_sheets?: ListDef[];
  }) => api.patch(`/datasets/${id}`, data),

  // Обновление только стилей ячеек
  updateStyles: (id: number, styles: Record<string, any>) =>
    api.patch(`/datasets/${id}`, { styles }),

  // Изменение структуры колонок (доступно владельцу и админу)
  updateStructure: (id: number, data: { columns: any[] }) =>
    api.patch(`/datasets/${id}/columns`, data),

  // Обновление правил валидации колонок
  updateColumns: (id: number, columns: any[]) =>
    api.patch(`/datasets/${id}/columns`, { columns }),

  // Архивация (мягкое удаление)
  delete: (id: number) => api.delete(`/datasets/${id}`),

  // Полное удаление (только админ, только архивные)
  permanentDelete: (id: number) => api.delete(`/datasets/${id}/permanent`),

  // Восстановление из архива
  restore: (id: number) => api.post(`/datasets/${id}/restore`),

  // Дублирование
  duplicate: (id: number, newName?: string) =>
    api.post(`/datasets/${id}/duplicate`, null, { params: { new_name: newName } }),

  // Условное форматирование
  getCondFormatRules: (id: number) => api.get(`/datasets/${id}/cond-formatting`),
  saveCondFormatRules: (id: number, rules: any[]) =>
    api.put(`/datasets/${id}/cond-formatting`, { rules }),

  // Вычисляемые итоги первой строки (header_row_1)
  getHeaderRow1: (id: number) => api.get(`/datasets/${id}/header_row_1`),

  // Сводка по числовым колонкам
  getSummary: (id: number) => api.get(`/datasets/${id}/summary`),

  // Статистика датасета
  getStats: (id: number) => api.get(`/datasets/${id}/stats`),

  // Отчёт план/факт
  getReport: (params: {
    dataset_ids: number[];
    plan_qty_col?: string;
    plan_cost_col?: string;
    actual_qty_col?: string;
    actual_cost_col?: string;
    group_col?: string;
    group_col2?: string;
    filter_col?: string;
    filter_val?: string;
    search?: string;
    direction_col?: string;
    budget_col?: string;
    unit_col?: string;
    year_col?: string;
    month_col?: string;
    group_by?: 'material' | 'category' | 'month';
    include_volume?: boolean;
    year_filter?: number;
    include_rows?: boolean;
    auto_map?: boolean;
    mappings_json?: string;
  }) => api.get('/datasets/report', { params }),

  // Автоопределение колонок по заголовкам
  suggestColumns: (datasetIds: number[]) =>
    api.get('/datasets/report/suggest-columns', { params: { dataset_ids: datasetIds } }),

  // Накопленный факт по месяцам
  getTrend: (params: {
    dataset_ids: number[];
    year_filter?: number;
  }) => api.get('/datasets/report/trend', { params }),

  // Реальный объём по категориям/материалам
  getVolume: (params: {
    dataset_ids: number[];
    group_by?: 'category' | 'material';
    year_filter?: number;
  }) => api.get('/datasets/report/volume', { params }),
};

// ======================== СТРОКИ ========================
export const rows = {
  list: (
    datasetId: number,
    page = 1,
    pageSize = 50,
    sortBy?: string,
    sortOrder?: string,
    search?: string,
    filterModel?: string,
    sheetId = 'main'
  ) =>
    api.get(`/datasets/${datasetId}/rows/`, {
      params: { page, page_size: pageSize, sort_by: sortBy, sort_order: sortOrder, search, filter_model: filterModel, sheet_id: sheetId }
    }),

  create: (
    datasetId: number,
    data: { data: Record<string, any>; formulas?: Record<string, string>; row_order?: number }
  ) => api.post(`/datasets/${datasetId}/rows/`, data),

  batchCreate: (
    datasetId: number,
    rows: Array<{ data: Record<string, any>; formulas?: Record<string, string>; cell_styles?: Record<string, any>; row_order?: number }>
  ) => api.post(`/datasets/${datasetId}/rows/batch`, rows),

  update: (
    datasetId: number,
    rowId: number,
    data: { data: Record<string, any>; formulas?: Record<string, string>; cell_styles?: Record<string, any>; version: number }
  ) => api.patch(`/datasets/${datasetId}/rows/${rowId}`, data),

  updateCell: (
    datasetId: number,
    rowId: number,
    columnId: string,
    value: any,
    formula?: string | null,
    expectedVersion?: number,
    metadata?: Record<string, any>,
  ) =>
    api.patch(`/datasets/${datasetId}/rows/${rowId}/cells/${columnId}`, {
      value: String(value),
      formula: formula || null,
      expected_version: expectedVersion,
      metadata: metadata || undefined,
    }),

  updateCellStyles: (
    datasetId: number,
    rowId: number,
    cell_styles: Record<string, any>,
    metadata?: Record<string, any>,
  ) => api.patch(`/datasets/${datasetId}/rows/${rowId}/cell-styles`, { cell_styles, metadata: metadata || undefined }),

  delete: (datasetId: number, rowId: number) =>
    api.delete(`/datasets/${datasetId}/rows/${rowId}`),

  batchUpdate: (
    datasetId: number,
    updates: Array<{ id: number; data: Record<string, any>; formulas?: Record<string, string>; cell_styles?: Record<string, any>; version: number; row_order?: number }>
  ) => api.patch(`/datasets/${datasetId}/rows/batch`, updates),

  batchDelete: (datasetId: number, rowIds: number[]) =>
    api.delete(`/datasets/${datasetId}/rows/batch`, { params: { row_ids: rowIds } }),

  duplicate: (datasetId: number, rowId: number) =>
    api.post(`/datasets/${datasetId}/rows/${rowId}/duplicate`),

  getHistory: (datasetId: number, rowId: number) =>
    api.get(`/datasets/${datasetId}/rows/${rowId}/history`),

  restore: (datasetId: number, rowId: number, version: number) =>
    api.post(`/datasets/${datasetId}/rows/${rowId}/restore/${version}`),

  getCellHistory: (
    datasetId: number,
    rowId: number,
    columnId: string,
    limit = 50
  ) =>
    api.get(`/datasets/${datasetId}/rows/${rowId}/cells/${columnId}/history`, {
      params: { limit }
    }),
};

// ======================== КОММЕНТАРИИ ========================
export const comments = {
  listAll: (datasetId: number, subUnitId?: string) =>
    api.get(`/datasets/${datasetId}/comments/all`, { params: { sub_unit_id: subUnitId } }),

  list: (datasetId: number, rowId: number, columnId: string) =>
    api.get(`/datasets/${datasetId}/comments/${rowId}/${columnId}`),

  create: (datasetId: number, data: {
    comment: string;
    row_id?: number | null;
    column_id?: string;
    ref?: string | null;
    thread_id?: string | null;
    row_index?: number | null;
    col_index?: number | null;
    parent_id?: number | null;
    sub_unit_id?: string | null;
  }) =>
    api.post(`/datasets/${datasetId}/comments/`, data),

  update: (datasetId: number, commentId: number, data: { comment?: string; resolved?: boolean }) =>
    api.patch(`/datasets/${datasetId}/comments/${commentId}`, data),

  delete: (datasetId: number, commentId: number) =>
    api.delete(`/datasets/${datasetId}/comments/${commentId}`),
};

// ======================== ЛИСТЫ ========================
export const listy = {
  list: (datasetId: number) =>
    api.get(`/datasets/${datasetId}/sheets`),
  create: (datasetId: number, name?: string) =>
    api.post(`/datasets/${datasetId}/sheets`, { name }),
  update: (datasetId: number, listId: string, data: Record<string, any>) =>
    api.patch(`/datasets/${datasetId}/sheets/${listId}`, data),
  delete: (datasetId: number, listId: string) =>
    api.delete(`/datasets/${datasetId}/sheets/${listId}`),
};

// ======================== ИМПОРТ / ЭКСПОРТ ========================
export const excel = {
  // Предпросмотр файла (xlsx, xls, csv, tsv, ods)
  preview: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/import-export/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  // Импорт (xlsx, xls, csv, tsv, ods)
  import: (
    file: File,
    options: {
      sheet_names?: string[];
      header_row_index?: number;
      create_mode?: 'new' | 'replace';
      target_dataset_ids?: number[];
    }
  ) => {
    const params = new URLSearchParams();
    if (options.sheet_names) options.sheet_names.forEach(name => params.append('sheet_names', name));
    if (options.header_row_index !== undefined) params.append('header_row_index', String(options.header_row_index));
    if (options.create_mode) params.append('create_mode', options.create_mode);
    if (options.target_dataset_ids && options.target_dataset_ids.length > 0) {
      options.target_dataset_ids.forEach(id => params.append('target_dataset_ids', String(id)));
    }
    const formData = new FormData();
    formData.append('file', file);
    return api.post(`/import-export/import?${params.toString()}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  // Экспорт датасета в Excel
  export: (datasetId: number) =>
    api.get(`/import-export/export/${datasetId}`, { responseType: 'blob' }),
};

// ======================== АДМИНИСТРИРОВАНИЕ ========================
export const admin = {
  users: {
    list: (skip = 0, limit = 100, filters?: { role_id?: number; is_active?: boolean; search?: string }) =>
      api.get('/admin/users', { params: { skip, limit, ...filters } }),
    get: (userId: number) => api.get(`/admin/users/${userId}`),
    create: (data: any) => api.post('/admin/users', data),
    batchCreate: (users: any[]) => api.post('/admin/users/batch', users),
    update: (userId: number, data: any) => api.patch(`/admin/users/${userId}`, data),
    delete: (userId: number) => api.delete(`/admin/users/${userId}`),
    resetPassword: (userId: number, newPassword: string) =>
      api.post(`/admin/users/${userId}/reset-password`, { new_password: newPassword }),
  },
  roles: {
    list: () => api.get('/admin/roles'),
    get: (roleId: number) => api.get(`/admin/roles/${roleId}`),
    create: (data: any) => api.post('/admin/roles', data),
    update: (roleId: number, data: any) => api.patch(`/admin/roles/${roleId}`, data),
    delete: (roleId: number) => api.delete(`/admin/roles/${roleId}`),
    duplicate: (roleId: number, newName: string) =>
      api.post(`/admin/roles/${roleId}/duplicate`, null, { params: { new_name: newName } }),
  },
  schemas: {
    list: () => api.get('/admin/schemas'),
    get: (schemaId: number) => api.get(`/admin/schemas/${schemaId}`),
    create: (data: any) => api.post('/admin/schemas', data),
    update: (schemaId: number, data: any) => api.patch(`/admin/schemas/${schemaId}`, data),
    delete: (schemaId: number) => api.delete(`/admin/schemas/${schemaId}`),
    duplicate: (schemaId: number, newName: string) =>
      api.post(`/admin/schemas/${schemaId}/duplicate`, null, { params: { new_name: newName } }),
  },
  datasets: {
    list: (skip = 0, limit = 100, includeArchived = true, ownerId?: number, search?: string) =>
      api.get('/admin/datasets', { params: { skip, limit, include_archived: includeArchived, owner_id: ownerId, search } }),
    get: (datasetId: number) => api.get(`/admin/datasets/${datasetId}`),
    changeOwner: (datasetId: number, newOwnerId: number) =>
      api.patch(`/admin/datasets/${datasetId}/owner`, null, { params: { new_owner_id: newOwnerId } }),
    archive: (datasetId: number) => api.delete(`/admin/datasets/${datasetId}`),
    restore: (datasetId: number) => api.post(`/admin/datasets/${datasetId}/restore`),
    permanentDelete: (datasetId: number) => api.delete(`/admin/datasets/${datasetId}/permanent`),
    updateStructure: (datasetId: number, data: any) =>
      api.patch(`/admin/datasets/${datasetId}/structure`, data),
  },
  settings: {
    list: () => api.get('/admin/settings'),
    get: (key: string) => api.get(`/admin/settings/${key}`),
    update: (key: string, data: { value: any; description?: string }) => api.put(`/admin/settings/${key}`, data),
    delete: (key: string) => api.delete(`/admin/settings/${key}`),
  },
  stats: () => api.get('/admin/stats'),
  audit: (skip = 0, limit = 100, filters?: { user_id?: number; action?: string; entity_type?: string }) =>
    api.get('/admin/audit', { params: { skip, limit, ...filters } }),
};

// ======================== СОХРАНЁННЫЕ ФИЛЬТРЫ (FILTER VIEWS) ========================
export const filterViews = {
  list: (datasetId: number) => api.get(`/datasets/${datasetId}/filters`),
  create: (datasetId: number, data: {
    name: string;
    filter_model: any;
    sort_model?: any[];
    column_state?: any;
    is_default?: boolean;
  }) => api.post(`/datasets/${datasetId}/filters`, { dataset_id: datasetId, ...data }),
  update: (datasetId: number, filterId: number, data: any) =>
    api.patch(`/datasets/${datasetId}/filters/${filterId}`, data),
  delete: (datasetId: number, filterId: number) =>
    api.delete(`/datasets/${datasetId}/filters/${filterId}`),
};

// ======================== СРЕЗЫ (SLICERS) ========================
export const slicersApi = {
  list: (datasetId: number) => api.get(`/datasets/${datasetId}/slicers`),
  create: (datasetId: number, data: {
    column_id: string;
    title?: string;
    position?: any;
    items?: string[];
  }) => api.post(`/datasets/${datasetId}/slicers`, { dataset_id: datasetId, ...data }),
  update: (datasetId: number, slicerId: number, data: any) =>
    api.patch(`/datasets/${datasetId}/slicers/${slicerId}`, data),
  delete: (datasetId: number, slicerId: number) =>
    api.delete(`/datasets/${datasetId}/slicers/${slicerId}`),
};

// ======================== ИМЕНОВАННЫЕ ДИАПАЗОНЫ ========================
export const namedRangesApi = {
  list: (datasetId: number) => api.get(`/datasets/${datasetId}/named-ranges`),
  create: (datasetId: number, data: {
    name: string;
    sheet_id?: string;
    start_col: string;
    start_row: number;
    end_col?: string;
    end_row?: number;
    formula?: string;
  }) => api.post(`/datasets/${datasetId}/named-ranges`, { dataset_id: datasetId, ...data }),
  update: (datasetId: number, rangeId: number, data: any) =>
    api.patch(`/datasets/${datasetId}/named-ranges/${rangeId}`, data),
  delete: (datasetId: number, rangeId: number) =>
    api.delete(`/datasets/${datasetId}/named-ranges/${rangeId}`),
};

// ======================== PDF ПАРСЕР ========================
export const pdf = {
  parse: (file: File, keywords?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams();
    if (keywords) params.append('keywords', keywords);
    return api.post(`/pdf/parse?${params.toString()}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};

// ======================== ТИПЫ ========================
export interface User {
  id: number;
  username: string;
  email: string;
  role_id: number;
  role_name: string | null;
  is_active: boolean;
  last_login: string | null;
  created_at: string;
  last_name: string | null;
  first_name: string | null;
  middle_name: string | null;
  department: string | null;
}

export interface Role {
  id: number;
  name: string;
  permissions: Record<string, boolean>;
  description: string | null;
}

export interface ValidationRule {
  type: 'list' | 'number' | 'text_length' | 'custom';
  allow_blank?: boolean;
  show_dropdown?: boolean;
  items?: string[];
  min_value?: number;
  max_value?: number;
  min_length?: number;
  max_length?: number;
  formula?: string;
  help_text?: string;
}

export interface ColumnDef {
  id: string;
  header: string;
  type: 'string' | 'number' | 'date';
  editableBy: string[];
  colorGroup?: string;
  validation?: ValidationRule;
}

export interface ListDef {
  id: string;
  name: string;
  order: number;
  frozen_rows?: number;
  frozen_columns?: number;
  merged_cells?: any[];
  column_widths?: Record<string, number>;
  row_heights?: Record<string, number>;
  hidden_columns?: string[];
  hidden_rows?: number[];
  group_rows?: Array<{start: number; end: number; collapsed?: boolean}>;
  group_columns?: Array<{start: number; end: number; collapsed?: boolean}>;
}

export interface Dataset {
  id: number;
  name: string;
  owner_id: number;
  owner_name?: string;
  columns: ColumnDef[];
  header_row_1?: Record<string, any>;
  header_row_2?: Record<string, string>;
  header_row_2_colors?: Record<string, string>;
  row_filter?: any;
  unique_columns?: string[];
  default_sort_column?: string;
  default_sort_order?: string;
  schema_id?: number;
  styles?: Record<string, any>;
  sub_sheets?: ListDef[];
  named_ranges?: any[];
  archived: boolean;
  created_at: string;
  updated_at?: string;
}

export interface DatasetSchema {
  id: number;
  name: string;
  columns: ColumnDef[];
  header_row_1?: Record<string, any>;
  header_row_2?: Record<string, string>;
  header_row_2_colors?: Record<string, string>;
  created_by?: number;
  created_at: string;
  updated_at?: string;
}

export interface Row {
  id: number;
  dataset_id: number;
  sheet_id: string;
  data: Record<string, any>;
  formulas: Record<string, string> | null;
  cell_styles?: Record<string, any>;
  row_order: number;
  version: number;
  updated_at: string | null;
}

export interface CellHistory {
  id: number;
  dataset_id: number;
  row_id: number;
  column_id: string;
  old_value: string | null;
  new_value: string | null;
  changed_by: number | null;
  changed_at: string;
}

export interface CellComment {
  id: number;
  dataset_id: number;
  row_id: number;
  column_id: string;
  comment: string;
  created_by: number;
  created_by_name?: string;
  created_at: string;
  updated_at: string | null;
  resolved: boolean;
  resolved_by: number | null;
  resolved_at: string | null;
}

export interface DatasetsListResponse {
  items: Dataset[];
  total: number;
  skip: number;
  limit: number;
}

export interface RowsListResponse {
  items: Row[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// ======================== ХЕЛПЕРЫ ========================
export const isAdmin = (): boolean => {
  const user = getCurrentUser();
  return user?.role_name === 'администратор';
};