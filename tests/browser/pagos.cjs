const { chromium } = require(process.env.FORMOPACK_TEST_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.FORMOPACK_TEST_CHROME ? { executablePath: process.env.FORMOPACK_TEST_CHROME } : {}) });
  try {
    const base = process.env.FORMOPACK_TEST_URL;
    const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/*', route => route.request().url().startsWith(base)
      ? route.continue() : route.fulfill({ status: 200, body: '' }));
    await page.goto(base);
    await page.evaluate(async () => {
      const token = document.querySelector('input[name="csrf_token"]').value;
      await fetch('/login', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ email: 'recepcion@formopack.com', password: 'recep456', csrf_token: token }) });
    });
    await page.goto(`${base}/admin/dashboard`);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const estilo = await page.locator('.metric-card').first().evaluate(el => ({
      color: getComputedStyle(el).color, duration: getComputedStyle(el).animationDuration,
      borde: getComputedStyle(el).borderTopWidth,
      overflow: document.documentElement.scrollWidth > window.innerWidth
    }));
    assert.equal(estilo.borde, '1px');
    assert(!estilo.overflow);
    const destino = process.env.FORMOPACK_PREVIEW_DIR;
    if (destino) {
      fs.mkdirSync(destino, { recursive: true });
      await page.screenshot({ path: path.join(destino, 'panel-desktop.png'), fullPage: true });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(150);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    if (destino) await page.screenshot({ path: path.join(destino, 'panel-movil.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1050 });
    await page.goto(`${base}/recepcion/cobrar/${process.env.FORMOPACK_TEST_GUIA}`);
    await page.locator('#btn-mp').click();
    await page.locator('#panel-mp button[type=submit]').click();
    await page.locator('#qrcode img').waitFor();
    assert(await page.locator('#qrcode img').evaluate(img => img.complete && img.naturalWidth > 0));
    await page.locator('#polling-status').getByText('No se pudo consultar', { exact: false }).waitFor();
    assert.equal(await page.locator('#estado-aprobado').isVisible(), false);
    if (destino) await page.screenshot({ path: path.join(destino, 'pago-verificacion.png'), fullPage: true });
    await page.waitForURL('**/recepcion/comprobante/**');
    assert.deepEqual(errors, []);
    console.log('pagos e interfaz verificados');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
