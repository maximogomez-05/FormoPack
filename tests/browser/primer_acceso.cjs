const { chromium } = require(process.env.FORMOPACK_TEST_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.FORMOPACK_TEST_CHROME ? { executablePath: process.env.FORMOPACK_TEST_CHROME } : {}) });
  const errores = [], base = process.env.FORMOPACK_TEST_URL;
  async function nuevaPagina() {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, reducedMotion: 'reduce' });
    const p = await context.newPage();
    p.on('pageerror', e => errores.push(e.message));
    await p.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.fulfill({ status: 200, body: '' }));
    return p;
  }
  async function login(p, email, password) {
    await p.goto(base);
    await p.evaluate(async ({ email, password }) => {
      const token = document.querySelector('input[name="csrf_token"]').value;
      await fetch('/login', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ email, password, csrf_token: token }) });
    }, { email, password });
  }
  async function captura(p, nombre) {
    const destino = process.env.FORMOPACK_PREVIEW_DIR;
    if (destino) { fs.mkdirSync(destino, { recursive: true }); await p.screenshot({ path: path.join(destino, nombre), fullPage: true }); }
  }
  try {
    const publico = await nuevaPagina();
    await publico.goto(`${base}/admin/tracking`);
    assert.equal(await publico.locator('.home-link').getAttribute('href'), '/');
    await captura(publico, 'tracking-inicio.png');
    await publico.locator('.home-link').click();
    await publico.waitForURL(base + '/');
    const admin = await nuevaPagina();
    await login(admin, 'admin@formopack.com', 'admin123');
    await admin.goto(`${base}/admin/usuarios`);
    await admin.getByRole('button', { name: 'Nuevo Usuario', exact: true }).click();
    const modal = admin.locator('#modalNuevoUsuario');
    await modal.locator('[name=nombre]').fill('Persona Nueva');
    await modal.locator('[name=email]').fill('nueva@example.com');
    await modal.locator('[name=tipo_usuario]').selectOption('recepcionista');
    await modal.locator('[name=password]').fill('Provisoria123');
    await modal.getByRole('button', { name: 'Guardar', exact: true }).click();
    await admin.waitForLoadState('load');
    const persona = await nuevaPagina();
    await login(persona, 'nueva@example.com', 'Provisoria123');
    await persona.goto(`${base}/dashboard`);
    await persona.waitForURL('**/primer-acceso');
    await captura(persona, 'primer-acceso.png');
    await persona.locator('[name=password_actual]').fill('Provisoria123');
    await persona.locator('[name=nueva_password]').fill('PersonalNueva456');
    await persona.locator('[name=confirmar_password]').fill('PersonalNueva456');
    await persona.getByRole('button', { name: 'Guardar contraseña y continuar' }).click();
    await persona.waitForURL('**/admin/dashboard');
    await persona.locator('.activity-empty').waitFor();
    assert.equal(await persona.locator('.history-day').count(), 0);
    await captura(persona, 'actividad-vacia.png');
    await persona.getByRole('link', { name: 'Ver los 7 días', exact: true }).click();
    assert.equal(await persona.locator('.history-day').count(), 7);
    await persona.getByRole('link', { name: 'Con movimiento', exact: true }).click();
    await persona.setViewportSize({ width: 390, height: 844 });
    assert(await persona.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    await captura(persona, 'actividad-movil.png');
    await persona.goto(`${base}/admin/tracking`);
    assert.equal(await persona.locator('.home-link').getAttribute('href'), '/dashboard');
    await persona.locator('.home-link').click();
    await persona.waitForURL('**/admin/dashboard');
    assert.deepEqual(errores, []);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
