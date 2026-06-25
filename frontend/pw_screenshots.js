const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE = 'http://localhost:8080';
const OUT = 'C:\\Users\\Anastasia\\Desktop\\pen-system-02';
const COPY = 'C:\\Users\\Anastasia\\Desktop\\Новая папка';
const BASE_PW = 'C:\\Users\\Anastasia\\Desktop\\pen-system-02';

const shots = [
  { url: '/login',          name: '01_login',           desc: 'Страница входа' },
  { url: '/datasets',       name: '02_datasets',        desc: 'Список таблиц (заявок)' },
  { url: '/my',             name: '03_my',              desc: 'Личный кабинет пользователя' },
  { url: '/my-activity',    name: '04_my_activity',     desc: 'Моя активность' },
  { url: '/reports',        name: '05_reports',         desc: 'Дашборд отчётов' },
  { url: '/admin',          name: '06_admin',           desc: 'Админ-панель (статистика)' },
  { url: '/admin/users',    name: '07_admin_users',     desc: 'Управление пользователями' },
  { url: '/admin/roles',    name: '08_admin_roles',     desc: 'Управление ролями' },
  { url: '/admin/datasets', name: '09_admin_datasets',  desc: 'Управление таблицами' },
  { url: '/admin/audit',    name: '10_admin_audit',     desc: 'Аудит действий' },
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  // 1. Login page screenshot
  console.log('--- Login page ---');
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT, 'pw_01_login.png'), fullPage: false });
  console.log('✓ 01_login - Страница входа');

  // 2. Perform login
  console.log('--- Logging in as admin ---');
  await page.fill('input[type="text"]', 'admin');
  await page.fill('input[type="password"]', 'Strong-Admin-Pass-789');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/datasets', { timeout: 15000 });
  await page.waitForTimeout(2500);
  console.log('✓ Login successful');

  // 3. Screenshot all app pages
  for (const shot of shots) {
    if (shot.name === '01_login') continue;
    try {
      await page.goto(`${BASE}${shot.url}`, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(2500);
      await page.screenshot({ path: path.join(OUT, `pw_${shot.name}.png`), fullPage: false });
      console.log(`✓ ${shot.name} - ${shot.desc}`);
    } catch (e) {
      console.log(`✗ ${shot.name}: ${e.message}`);
    }
  }

  // 4. Open first dataset (spreadsheet editor)
  try {
    console.log('--- Opening dataset editor ---');
    await page.goto(`${BASE}/datasets`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1500);
    const datasetLinks = await page.$$('a[href*="/datasets/"]');
    if (datasetLinks.length > 0) {
      const href = await datasetLinks[0].getAttribute('href');
      await page.goto(`${BASE}${href}`, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(4000);
      await page.screenshot({ path: path.join(OUT, 'pw_11_dataset_editor.png'), fullPage: false });
      console.log('✓ 11_dataset_editor - Редактор таблицы (спредшит)');
    } else {
      const firstRow = await page.$('table tbody tr');
      if (firstRow) {
        const cell = await firstRow.$('td a');
        if (cell) {
          const href = await cell.getAttribute('href');
          await page.goto(`${BASE}${href}`, { waitUntil: 'networkidle', timeout: 30000 });
          await page.waitForTimeout(4000);
          await page.screenshot({ path: path.join(OUT, 'pw_11_dataset_editor.png'), fullPage: false });
          console.log('✓ 11_dataset_editor - Редактор таблицы');
        } else {
          console.log('✗ 11_dataset_editor: no link in row');
        }
      } else {
        console.log('✗ 11_dataset_editor: no dataset rows found');
      }
    }
  } catch (e) {
    console.log(`✗ 11_dataset_editor: ${e.message}`);
  }

  // 5. Swagger API docs
  try {
    console.log('--- Swagger docs ---');
    await page.goto('http://localhost:8000/docs', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(OUT, 'pw_12_swagger.png'), fullPage: false });
    console.log('✓ 12_swagger - Swagger API документация');
  } catch (e) {
    console.log(`✗ 12_swagger: ${e.message}`);
  }

  // 6. Grafana
  try {
    console.log('--- Grafana ---');
    await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.fill('input[name="user"]', 'admin');
    await page.fill('input[name="password"]', 'Strong-Grafana-Pass-789');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(3000);
    // Navigate to the provisioned dashboard
    await page.goto('http://localhost:3000/d/06617689-0dd2-4240-b07a-57fc8161538b/pjen-backend-monitoring?from=now-1h&to=now&refresh=5s', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(5000);
    await page.screenshot({ path: path.join(OUT, 'pw_13_grafana.png'), fullPage: false });
    console.log('✓ 13_grafana - Grafana дашборд с метриками');
  } catch (e) {
    console.log(`✗ 13_grafana: ${e.message}`);
  }

  // 7. Prometheus
  try {
    console.log('--- Prometheus ---');
    // Go to graph with a query pre-filled
    await page.goto('http://localhost:9090/graph?g0.expr=rate(http_requests_total%5B1m%5D)&g0.tab=0&g0.stacked=0', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(4000);
    await page.screenshot({ path: path.join(OUT, 'pw_14_prometheus.png'), fullPage: false });
    console.log('✓ 14_prometheus - Prometheus с графиком HTTP requests');
  } catch (e) {
    console.log(`✗ 14_prometheus: ${e.message}`);
  }

  await browser.close();

  // 8. Copy all screenshots to Новая папка
  console.log('\n--- Copying screenshots ---');
  if (!fs.existsSync(COPY)) {
    fs.mkdirSync(COPY, { recursive: true });
  }
  const files = fs.readdirSync(OUT).filter(f => f.startsWith('pw_') && f.endsWith('.png'));
  for (const f of files) {
    fs.copyFileSync(path.join(OUT, f), path.join(COPY, f));
    console.log(`✓ copied ${f}`);
  }

  console.log(`\n=== All done: ${files.length} screenshots ===`);
  console.log(`Original: ${OUT}`);
  console.log(`Copied to: ${COPY}`);
})();
