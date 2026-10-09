import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './helpers';

test.describe('Список таблиц', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('страница списка таблиц загружается', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Таблицы', level: 1 })).toBeVisible();
    await expect(page).toHaveURL(/\/datasets$/);
  });

  test('доступна кнопка создания таблицы', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Новая таблица', exact: true })).toBeVisible();
  });
});
