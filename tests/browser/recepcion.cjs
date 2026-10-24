const { chromium } = require(process.env.FORMOPACK_TEST_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.FORMOPACK_TEST_CHROME ? { executablePath: process.env.FORMOPACK_TEST_CHROME } : {}) });
  try {
    const base = process.env.FORMOPACK_TEST_URL;
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => route.request().url().startsWith(base)
      ? route.continue() : route.fulfill({ status: 200, body: '' }));
    await page.goto(base);
    await page.evaluate(async () => {
      const token = document.querySelector('input[name="csrf_token"]').value;
      await fetch('/login', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ email: 'recepcion@formopack.com', password: 'recep456', csrf_token: token }) });
    });
    await page.goto(`${base}/recepcion/nuevo-envio`);
    for (const [name, value] of Object.entries({ rem_dni: '12345678', rem_nombre: 'José Pérez',
      rem_telefono: '3704123456', dest_dni: '23456789', dest_nombre: 'María Gómez',
      dest_telefono: '3704654321', direccion_destino: 'Av. San Martín 123' })) {
      await page.locator(`[name="${name}"]`).fill(value);
    }
    assert(await page.locator('[name="rem_nombre"]').evaluate(input => input.checkValidity()));
    await page.locator('#id_localidad_destino').selectOption('1');
    await page.locator('.peso-real').fill('10');
    await page.locator('button[onclick="agregarBulto()"]').click();
    await page.locator('button[onclick="agregarBulto()"]').click();
    await page.locator('.peso-real').nth(1).fill('4');
    await page.locator('.peso-real').nth(2).fill('6');
    const cotizacion = page.waitForResponse(r => r.url().endsWith('/recepcion/cotizador/calcular') && r.status() === 200);
    await page.locator('.es-fragil').nth(1).check();
    const detalle = await (await cotizacion).json();
    assert.equal(detalle.cantidad_bultos, 3);
    // Saltar solo la validación HTML para comprobar la protección del servidor.
    await page.locator('[name="dest_nombre"]').fill('123456');
    await page.locator('#form-envio').evaluate(form => { form.noValidate = true; });
    const rechazada = page.waitForResponse(r => r.url().endsWith('/recepcion/nuevo-envio') && r.request().method() === 'POST');
    await page.locator('#form-envio button[type="submit"]').click();
    assert.equal((await rechazada).status(), 400);
    await page.waitForLoadState('load');
    assert.equal(await page.locator('[name="rem_nombre"]').inputValue(), 'José Pérez');
    assert.equal(await page.locator('.peso-real').count(), 3);
    assert(await page.locator('.es-fragil').nth(1).isChecked());
    await page.locator('[name="dest_nombre"]').fill('María Gómez');
    await page.locator('#form-envio button[type="submit"]').click();
    await page.waitForURL('**/recepcion/cobrar/**');
    assert.deepEqual(errors, []);
    console.log('recepción y validaciones verificadas');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
