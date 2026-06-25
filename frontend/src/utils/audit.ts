export const ACTION_LABELS: Record<string, string> = {
  CREATE_DATASET: 'Создание таблицы',
  ARCHIVE_DATASET: 'Архивация таблицы',
  RESTORE_DATASET: 'Восстановление таблицы',
  PERMANENT_DELETE_DATASET: 'Удаление таблицы',
  UPDATE_DATASET_META: 'Изменение настроек',
  UPDATE_DATASET_COLUMNS: 'Изменение колонок',
  UPDATE_DATASET_STRUCTURE: 'Изменение структуры',
  DUPLICATE_DATASET: 'Копирование таблицы',
  CREATE_ROW: 'Добавление строки',
  UPDATE_ROW: 'Изменение строки',
  DELETE_ROW: 'Удаление строки',
  BATCH_DELETE_ROWS: 'Массовое удаление строк',
  DUPLICATE_ROW: 'Копирование строки',
  RESTORE_ROW: 'Восстановление строки',
  UPDATE_CELL: 'Изменение ячейки',
  CREATE_COMMENT: 'Добавление комментария',
  UPDATE_COMMENT: 'Изменение комментария',
  DELETE_COMMENT: 'Удаление комментария',
  LOGIN: 'Вход в систему',
  CHANGE_PASSWORD: 'Смена пароля',
};

const HTTP_METHOD_COLORS: Record<string, string> = {
  GET: 'bg-emerald-100 text-emerald-700',
  POST: 'bg-blue-100 text-blue-700',
  PUT: 'bg-amber-100 text-amber-700',
  PATCH: 'bg-violet-100 text-violet-700',
  DELETE: 'bg-red-100 text-red-700',
};

function humanizePath(path: string): string {
  const clean = path.replace(/^\/api\//, '');
  if (clean.startsWith('auth/')) return clean.replace('auth/', '').replace(/-/g, ' ');
  if (clean.startsWith('datasets/')) {
    const parts = clean.split('/');
    if (parts.length >= 2 && parts[1] && !isNaN(Number(parts[1]))) {
      if (parts[2] === 'rows') return 'Работа со строками';
      if (parts[2] === 'columns') return 'Изменение колонок';
      if (parts[2] === 'comments') return 'Комментарии';
      if (parts[2] === 'duplicate') return 'Копирование таблицы';
      if (parts[2] === 'restore') return 'Восстановление таблицы';
      if (parts[2] === 'permanent') return 'Удаление таблицы';
      return 'Действие с таблицей';
    }
    return 'Таблицы';
  }
  if (clean.startsWith('admin/')) return clean.replace('admin/', '').replace(/-/g, ' ');
  if (clean.startsWith('import-export/')) return clean.replace('import-export/', '').replace(/-/g, ' ');
  return clean;
}

export function formatAction(action: string): { label: string; color: string } {
  const methodMatch = action.match(/^(GET|POST|PUT|PATCH|DELETE) (.+)/);
  if (methodMatch) {
    const [, method, path] = methodMatch;
    return {
      label: `${method} ${humanizePath(path)}`,
      color: HTTP_METHOD_COLORS[method] || 'bg-slate-100 text-slate-700',
    };
  }
  return {
    label: ACTION_LABELS[action] || action,
    color: 'bg-indigo-50 text-indigo-700',
  };
}

export function formatDetails(_action: string, details: Record<string, any>): string {
  if (!details) return '';
  const parts: string[] = [];

  if (details.status != null) {
    parts.push(`Статус: ${details.status}`);
  }
  if (details.duration != null) {
    parts.push(`${Math.round(details.duration * 1000)}мс`);
  }
  if (details.name) {
    parts.push(`"${details.name}"`);
  }
  if (details.error) {
    parts.push(`Ошибка: ${details.error}`);
  }
  if (details.column_id) {
    let text = `Ячейка ${details.column_id}`;
    if (details.old_value != null && details.new_value != null) {
      text += `: ${details.old_value} → ${details.new_value}`;
    }
    parts.push(text);
  }
  if (details.row_id != null && !details.column_id) {
    parts.push(`Строка #${details.row_id}`);
  }
  if (details.count != null) {
    parts.push(`Количество: ${details.count}`);
  }
  if (details.row_ids?.length) {
    parts.push(`Строк: ${details.row_ids.length}`);
  }
  if (details.new_name) {
    parts.push(`Новое имя: ${details.new_name}`);
  }
  if (details.source_id != null && !details.name) {
    parts.push(`Источник: #${details.source_id}`);
  }
  if (details.columns_updated != null) {
    parts.push(details.columns_updated ? 'Колонки обновлены' : 'Колонки не изменены');
  }

  return parts.length > 0 ? parts.join(', ') : JSON.stringify(details);
}
