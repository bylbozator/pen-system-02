import { test, expect } from '@playwright/test';
import { ADMIN_PASSWORD, ADMIN_USERNAME, LOGIN_PLACEHOLDER, PASSWORD_PLACEHOLDER, gotoLogin, login, loginAsAdmin } from './helpers';

test.describe('Аутентификация', () => {
  test('страница входа отображает форму', async ({ page }) => {
    await gotoLogin(page);

    await expect(page.getByRole('heading', { name: 'Добро пожаловать' })).toBeVisible();
    await expect(page.getByPlaceholder(LOGIN_PLACEHOLDER)).toBeVisible();
    await expect(page.getByPlaceholder(PASSWORD_PLACEHOLDER)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Войти' })).toBeVisible();
  });

  test('успешный вход перенаправляет на список таблиц', async ({ page }) => {
    await loginAsAdmin(page);

    await expect(page.getByRole('heading', { name: 'Таблицы', level: 1 })).toBeVisible();
  });

  test('неверный пароль показывает ошибку и не пускает в систему', async ({ page }) => {
    await login(page, ADMIN_USERNAME, `${ADMIN_PASSWORD}_wrong`);

    await expect(page.getByText('Неверный логин или пароль')).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test('неавторизованный доступ к /datasets перенаправляет на вход', async ({ page }) => {
    await page.goto('/datasets');

    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByPlaceholder(LOGIN_PLACEHOLDER)).toBeVisible();
  });
});
