import { Page, expect } from '@playwright/test';

export const ADMIN_USERNAME = process.env.E2E_ADMIN_USERNAME ?? 'admin';
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'admin';

export const LOGIN_PLACEHOLDER = 'Введите логин';
export const PASSWORD_PLACEHOLDER = 'Введите пароль';

export async function gotoLogin(page: Page): Promise<void> {
  await page.goto('/login');
  await expect(page.getByPlaceholder(LOGIN_PLACEHOLDER)).toBeVisible();
}

export async function login(
  page: Page,
  username: string = ADMIN_USERNAME,
  password: string = ADMIN_PASSWORD,
): Promise<void> {
  await gotoLogin(page);
  await page.getByPlaceholder(LOGIN_PLACEHOLDER).fill(username);
  await page.getByPlaceholder(PASSWORD_PLACEHOLDER).fill(password);
  await page.getByRole('button', { name: 'Войти' }).click();
}

export async function loginAsAdmin(page: Page): Promise<void> {
  await login(page);
  await expect(page).toHaveURL(/\/datasets$/);
}
