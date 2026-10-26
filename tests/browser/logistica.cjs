const { chromium } = require(process.env.FORMOPACK_TEST_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.FORMOPACK_TEST_CHROME});
  const base = process.env.FORMOPACK_TEST_URL, errors = [];
  async function pagina(email, password) {
    const context = await browser.newContext({serviceWorkers: 'block', viewport: {width: 1440, height: 1000}});
    const p = await context.newPage();
    p.on('pageerror', e => errors.push(e.message));
    p.on('dialog', dialog => dialog.accept());
    await p.route('**/*', r => r.request().url().startsWith(base) ? r.continue() : r.fulfill({status:200, body:''}));
    await p.goto(base);
    await p.evaluate(async ({email,password}) => {
      await fetch('/login', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:new URLSearchParams({email,password,csrf_token:document.querySelector('[name=csrf_token]').value})});
    }, {email,password});
    return p;
  }
  try {
    const admin = await pagina('admin@formopack.com','admin123');
    const driver = await pagina('chofer@formopack.com','chofer789');
    for (let intento=1; intento<=2; intento++) {
      await admin.goto(base+'/admin/logistica');
      await admin.locator('[name=nro_despacho]').fill('DES-BROWSER-'+intento);
      await admin.locator('[name=id_chofer]').selectOption('3');
      await admin.locator('[name=id_vehiculo]').selectOption(process.env.FORMOPACK_TEST_VEHICULO);
      await admin.locator(`[name=envios_ids][value="${process.env.FORMOPACK_TEST_ENVIO}"]`).check();
      await admin.getByRole('button',{name:'Crear despacho',exact:true}).click();
      await admin.waitForLoadState('load');
      await driver.goto(base+'/chofer');
      await driver.getByRole('button',{name:'Iniciar ruta',exact:true}).click();
      assert.equal(await driver.locator('#offline-banner').isVisible(), false);
      assert.equal(await driver.locator('#queue-banner').isVisible(), false);
      if (intento===1 && process.env.FORMOPACK_PREVIEW_DIR) {
        fs.mkdirSync(process.env.FORMOPACK_PREVIEW_DIR,{recursive:true});
        await driver.setViewportSize({width:390,height:844});
        assert(await driver.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        await driver.screenshot({path:path.join(process.env.FORMOPACK_PREVIEW_DIR,'logistica-ruta-movil.png'),fullPage:true});
      }
      await driver.getByRole('button',{name:'Registrar resultado',exact:true}).click();
      if (intento===1) {
        await driver.locator('#tipo-intento').selectOption('fallido');
      } else {
        await driver.locator('[name=dni_receptor]').fill('12345678');
        const canvas = driver.locator('#firma-canvas');
        const box = await canvas.boundingBox();
        await driver.mouse.move(box.x+25,box.y+35);
        await driver.mouse.down();
        await driver.mouse.move(box.x+110,box.y+80,{steps:10});
        await driver.mouse.up();
      }
      await driver.getByRole('button',{name:'Guardar entrega',exact:true}).click();
      await driver.getByRole('heading',{name:'No tenés rutas asignadas'}).waitFor();
    }
    await driver.setViewportSize({width:390,height:844});
    assert(await driver.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    if(process.env.FORMOPACK_PREVIEW_DIR) {
      fs.mkdirSync(process.env.FORMOPACK_PREVIEW_DIR,{recursive:true});
      await driver.screenshot({path:path.join(process.env.FORMOPACK_PREVIEW_DIR,'logistica-cierre-movil.png'),fullPage:true});
    }
    assert.deepEqual(errors,[]);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
