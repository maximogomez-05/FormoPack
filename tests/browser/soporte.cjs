const { chromium } = require(process.env.FORMOPACK_TEST_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.FORMOPACK_TEST_CHROME ? { executablePath: process.env.FORMOPACK_TEST_CHROME } : {}),
  });
  const base = process.env.FORMOPACK_TEST_URL;
  const errors = [];
  async function pagina(context) {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => route.request().url().startsWith(base)
      ? route.continue() : route.fulfill({ status: 200, body: '' }));
    return page;
  }
  try {
    const cliente = await browser.newContext();
    const page = await pagina(cliente);
    await page.goto(`${base}/admin/tracking`);
    await page.locator('#contact-support').click();
    await page.locator('#chat-client-name').fill('Cliente de prueba');
    await page.locator('#chat-client-email').fill('cliente@example.com');
    await page.locator('#chat-init-message').fill('Necesito información de mi envío');
    await page.locator('#form-init-chat button[type=submit]').click();
    await page.locator('#support-active-screen').waitFor({ state: 'visible' });
    await page.locator('#client-chat-messages').getByText('Necesito información de mi envío').waitFor();
    const datos = await page.evaluate(() => ({ cookies: document.cookie,
      storage: sessionStorage.getItem('formopack_chat_session') }));
    assert.equal(datos.storage, null);
    assert(!datos.cookies.includes('session='));

    const otroCliente = await browser.newContext();
    const externo = await pagina(otroCliente);
    await externo.goto(`${base}/admin/tracking`);
    const consulta = await externo.evaluate(() => fetch('/soporte/api/mensajes').then(r => r.json()));
    assert(consulta.finalizado && consulta.mensajes.length === 0);

    const staff = await browser.newContext();
    const operador = await pagina(staff);
    await operador.goto(`${base}/`);
    await operador.evaluate(async () => {
      const token = document.querySelector('input[name="csrf_token"]').value;
      await fetch('/login', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ email: 'recepcion@formopack.com', password: 'recep456', csrf_token: token }) });
    });
    await operador.goto(`${base}/soporte/panel`);
    await operador.locator('form[action$="/tomar"] button').first().click();
    await operador.locator('#input-message').waitFor();
    await operador.locator('#input-message').fill('Respuesta verificada');
    await operador.locator('#btn-submit').click();
    await page.locator('#client-chat-messages').getByText('Respuesta verificada').waitFor();

    await page.locator('#client-chat-input').fill('Texto que debe conservarse');
    await page.route('**/soporte/api/enviar', route => route.fulfill({ status: 503,
      contentType: 'application/json', body: JSON.stringify({ ok: false, error: 'Servicio temporalmente indisponible' }) }));
    page.once('dialog', dialog => dialog.dismiss());
    await page.locator('#form-client-send button[type=submit]').click();
    await page.waitForFunction(() => !document.getElementById('client-chat-input').disabled);
    assert.equal(await page.locator('#client-chat-input').inputValue(), 'Texto que debe conservarse');
    await page.unroute('**/soporte/api/enviar');
    await page.locator('#form-client-send button[type=submit]').click();
    await operador.locator('#messages-box').getByText('Texto que debe conservarse').waitFor();

    operador.once('dialog', dialog => dialog.accept());
    await operador.locator('form[action$="/finalizar"] button').click();
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#support-init-screen').waitFor({ state: 'visible' });
    assert.deepEqual(errors, []);
    console.log('flujo completo verificado');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
