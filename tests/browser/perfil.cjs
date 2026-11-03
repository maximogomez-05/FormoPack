const { chromium } = require(process.env.FORMOPACK_TEST_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ headless: true,
    executablePath: process.env.FORMOPACK_TEST_CHROME });
  const base = process.env.FORMOPACK_TEST_URL;
  try {
    const page = await browser.newPage({ serviceWorkers: 'block', reducedMotion: 'reduce' });
    const errores = [];
    page.on('pageerror', error => errores.push(error.message));
    await page.route('**/*', route => route.request().url().startsWith(base)
      ? route.continue() : route.fulfill({ status: 200, body: '' }));
    await page.goto(base);
    await page.evaluate(async () => {
      await fetch('/login', { method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ email: 'admin@formopack.com', password: 'admin123',
          csrf_token: document.querySelector('[name=csrf_token]').value }) });
    });
    await page.goto(base + '/perfil/');
    await page.getByLabel('Nombre completo').fill('Administrador Perfil');
    await page.getByRole('button', { name: 'Guardar datos', exact: true }).click();
    await page.getByLabel('Elegí una foto').setInputFiles(process.env.FORMOPACK_TEST_FOTO);
    await page.getByRole('button', { name: 'Guardar foto', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.perfil-foto').naturalWidth === 256);
    for (const width of [1440, 820, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.waitForFunction(width => width > 768 ||
        document.querySelector('.main-content').getBoundingClientRect().x < 1, width);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert.equal(await page.getByLabel('Nombre completo').inputValue(), 'Administrador Perfil');
      if (process.env.FORMOPACK_PREVIEW_DIR) {
        await page.screenshot({ path: path.join(process.env.FORMOPACK_PREVIEW_DIR, 'perfil-' + width + '.png'), fullPage: true, animations: 'disabled' });
      }
    }
    await page.getByRole('button', { name: 'Quitar foto', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Quitar foto', exact: true }).count(), 0);
    await page.goto(base + '/admin/usuarios');
    await page.locator('a[href="/perfil/cuentas/2"]').click();
    await page.getByLabel('Nombre completo').fill('Recepcionista Actualizada');
    await page.getByLabel('Correo de acceso').fill('recepcionista@example.com');
    await page.getByRole('button', { name: 'Guardar datos', exact: true }).click();
    assert(await page.getByText('recepcionista@example.com', { exact: true }).isVisible());
    assert.deepEqual(errores, []);
    console.log('Perfil, foto, edición administrativa y tres tamaños verificados');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
