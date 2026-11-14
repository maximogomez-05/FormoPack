const { chromium } = require(process.env.FORMOPACK_TEST_PLAYWRIGHT);
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({executablePath:process.env.FORMOPACK_TEST_CHROME});
  try {
    const base = process.env.FORMOPACK_TEST_URL;
    const ctx = await browser.newContext({viewport:{width:390,height:844}});
    await ctx.route('**/*', r => r.request().url().startsWith(base) ? r.continue() : r.abort());
    const page = await ctx.newPage();
    page.on('dialog', d => d.accept());
    async function login(email) {
      await page.goto(base);
      await page.evaluate(async email => {
        await fetch('/login',{method:'POST',body:new URLSearchParams({email,password:'chofer789',
          csrf_token:document.querySelector('[name=csrf_token]').value})});
      },email);
      await page.goto(base+'/chofer');
      await page.evaluate(()=>navigator.serviceWorker.ready.then(()=>true));
      await page.waitForFunction(()=>!!navigator.serviceWorker.controller);
      await page.waitForFunction(async () => !!(await (await caches.open("formopack-panel")).match("/chofer")));
    }
    const a='chofer@formopack.com', b='otro-chofer@example.com';
    // Una instalación anterior ya tiene el almacén y puede contener evidencia pendiente.
    await page.goto(base);
    await page.evaluate(async () => {
      await (await caches.open('formopack-chofer-v5')).put('/static/manifest.json',new Response('{}'));
    });
    await page.evaluate(() => new Promise((resolve,reject) => {
      const abrir = indexedDB.open('formopack-offline',1);
      abrir.onupgradeneeded = () => {
        const store = abrir.result.createObjectStore('entregas-pendientes',{keyPath:'id',autoIncrement:true});
        store.add({fields:{csrf_token:'otra-sesion-antigua'},photo:new Blob(['evidencia'])});
      };
      abrir.onsuccess = () => { abrir.result.close(); resolve(); };
      abrir.onerror = () => reject(abrir.error);
    }));
    await login(a);
    assert.equal(await page.evaluate(async ()=>(await caches.keys()).includes('formopack-chofer-v5')),false);
    assert(await page.evaluate(async ()=>(await caches.keys()).includes('formopack-chofer-v6')));
    assert.equal(await page.evaluate(async () => {
      const db = await abrirBase();
      const lectura = db.transaction('entregas-pendientes').objectStore('entregas-pendientes').get(1);
      const antigua = await new Promise(resolve => { lectura.onsuccess = () => resolve(lectura.result); });
      return [await antigua.photo.text(), (await leerPendientes()).length].join(',');
    }), 'evidencia,0');
    // Esperar la propagación de la cookie al worker antes de cortar la red.
    await ctx.serviceWorkers()[0].evaluate(async () => {
      for (let intento = 0; intento < 100; intento++) {
        const cookie = await cookieStore.get('fp_panel');
        const panel = await (await caches.open('formopack-panel')).match('/chofer');
        if (cookie && panel?.headers.get('X-Formopack-Panel') === cookie.value) return;
        await new Promise(resolve => setTimeout(resolve,50));
      }
      throw new Error('La identidad offline no coincide con el panel guardado');
    });
    await ctx.setOffline(true);
    const respuestaOffline = await page.reload();
    assert.equal(respuestaOffline.status(),200,await page.locator('body').innerText());
    await page.getByText('DES-COMPARTIDA-A',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Registrar resultado'}).click();
    await page.locator('#tipo-intento').selectOption('fallido');
    await page.getByRole('button',{name:'Guardar entrega'}).click();
    await page.locator('#queue-banner').waitFor();
    // Recuperar señal para cerrar la sesión, sin transmitir el pendiente de A.
    await page.close();
    const nueva = await ctx.newPage();
    await ctx.setOffline(false);
    await nueva.goto(base+'/logout');
    await ctx.setOffline(true);
    const cerrado = await nueva.goto(base+'/chofer');
    assert.equal(cerrado.status(),503);
    await ctx.setOffline(false);
    await nueva.goto(base);
    async function cambiar(email) {
      await nueva.evaluate(async email => {
        await fetch('/login',{method:'POST',body:new URLSearchParams({email,password:'chofer789',
          csrf_token:document.querySelector('[name=csrf_token]').value})});
      },email);
      await nueva.goto(base+'/chofer');
    }
    await cambiar(b);
    await ctx.setOffline(true);
    await nueva.reload();
    await nueva.getByText('Otro Chofer',{exact:true}).waitFor();
    assert.equal(await nueva.getByText('DES-COMPARTIDA-A',{exact:true}).count(),0);
    assert.equal(await nueva.evaluate(async ()=>(await leerPendientes()).length),0);
    await ctx.setOffline(false);
    await nueva.goto(base+'/logout');
    await cambiar(a);
    await nueva.waitForFunction(async ()=> (await leerPendientes()).length===0);
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
