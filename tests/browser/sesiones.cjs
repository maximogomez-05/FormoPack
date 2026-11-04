const { chromium } = require(process.env.FORMOPACK_TEST_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({
    headless: true, executablePath: process.env.FORMOPACK_TEST_CHROME
  });
  const base = process.env.FORMOPACK_TEST_URL;
  try {
    async function ingresar() {
      const context = await browser.newContext({ serviceWorkers: 'block', reducedMotion: 'reduce' });
      const page = await context.newPage();
      await page.route('**/*', route => route.request().url().startsWith(base)
        ? route.continue() : route.fulfill({ status: 200, body: '' }));
      await page.goto(base);
      await page.evaluate(async () => {
        const token = document.querySelector('[name=csrf_token]').value;
        await fetch('/login', {
          method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            email: 'admin@formopack.com', password: 'admin123', csrf_token: token
          })
        });
      });
      await page.goto(base + '/admin/dashboard');
      assert.equal(await page.locator('h1').textContent(), 'Control de jornada');
      return page;
    }
    const primero = await ingresar();
    assert.equal(await primero.locator('#envios tbody tr').count(), 14);
    for (const width of [1440, 820, 390]) {
      await primero.setViewportSize({ width, height: 900 });
      assert(await primero.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      if (process.env.FORMOPACK_PREVIEW_DIR) {
        await primero.screenshot({ path: require('node:path').join(process.env.FORMOPACK_PREVIEW_DIR,
          'jornada-' + width + '.png') });
      }
    }
    const avisos = primero.locator('#alertas');
    assert.equal(await avisos.locator('li').count(), 8);
    const primeraGuia = await avisos.locator('li a').first().textContent();
    await avisos.getByRole('link', { name: 'Siguientes' }).click();
    assert(await avisos.getByText('Página 2 de 2').isVisible());
    assert.equal(await avisos.getByRole('link', { name: primeraGuia, exact: true }).count(), 0);
    await avisos.getByRole('link', { name: 'Anteriores' }).click();
    await primero.goto(base + '/recepcion/caja');
    await primero.goBack();
    await primero.waitForURL(url => url.pathname === '/admin/dashboard');
    await primero.goForward();
    await primero.waitForURL('**/recepcion/caja');
    const segundo = await ingresar();
    const revocada = await primero.evaluate(async () => (
      await fetch('/sesion', { headers: { Accept: 'application/json' } })
    ).status);
    assert.equal(revocada, 401);
    await segundo.goto(base + '/logout');
    await segundo.goBack();
    await segundo.waitForURL(url => !url.pathname.startsWith('/admin/'));
    const respuesta = await segundo.goto(base + '/admin/dashboard');
    assert(!new URL(segundo.url()).pathname.startsWith('/admin/'));
    assert(respuesta.ok());
    console.log('Historial vigente, segundo ingreso, cierre y regreso al panel verificados');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
