const {chromium} = require(process.env.FORMOPACK_TEST_PLAYWRIGHT);
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const leaflet = process.env.FORMOPACK_TEST_LEAFLET;
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.FORMOPACK_TEST_CHROME});
  try {
    for (const mobile of [false, true]) {
      const page = await browser.newPage({viewport: mobile ? {width:390,height:844} : {width:1440,height:1000}, serviceWorkers:'block'});
      const errors = [];
      page.on('pageerror', e=>errors.push(e.message));
      await page.clock.install();
      let status = 'correcto', calls = 0;
      let terminal = false;
      let gps = {latitud:-26.18,longitud:-58.17,fecha_actualizacion:new Date().toISOString()};
      await page.route('**/*', async r => {
        const url = r.request().url();
        if (url.includes('/admin/tracking/estado')) {
          calls++;
          if (status === 'error') return r.fulfill({status:503,body:'no disponible'});
          if (status === 'invalido') return r.fulfill({json:{ok:true}});
          return r.fulfill({json:{ok:true, estado:terminal ? 'entregado' : 'en_ruta', ubicacion_gps:terminal ? null : gps}});
        }
        if (url.includes('/admin/tracking?')) return r.fulfill({contentType:'text/html', body:fs.readFileSync(path.join(process.env.FORMOPACK_HTML_TEST,terminal ? 'tracking_terminal.html' : 'tracking.html'))});
        if (url.includes('leaflet.js')) return r.fulfill({contentType:'text/javascript', body:fs.readFileSync(leaflet)});
        if (url.includes('/static/')) {
          const file = path.join(root,'web',new URL(url).pathname);
          if (fs.existsSync(file)) return r.fulfill({path:file});
        }
        if (url.includes('router.project-osrm')) return r.fulfill({json:{code:'Ok',routes:[{geometry:{type:'LineString',coordinates:[[999,999]]}}]}});
        return r.fulfill({status:200,body:''});
      });
      await page.goto('https://formopack.example/admin/tracking?guia=FP-TEST');
      await page.waitForFunction(()=>!!driverMarker);
      assert.match(await page.locator('#tracking-map-note').textContent(), /GPS reciente/);
      assert.match(await page.locator('#tracking-map-note').textContent(), /referencia directa/);
      status='error';
      await page.evaluate(()=>consultaGps.consultar());
      assert.match(await page.locator('#tracking-live-note').textContent(), /No se pudo/);
      status='correcto';
      await page.evaluate(()=>consultaGps.consultar());
      assert.match(await page.locator('#tracking-live-note').textContent(), /Consulta correcta/);
      gps=null;
      await page.evaluate(()=>consultaGps.consultar());
      assert.equal(await page.evaluate(()=>driverMarker),null);
      gps={latitud:-26.18,longitud:-58.17,fecha_actualizacion:new Date().toISOString()};
      await page.evaluate(()=>consultaGps.consultar());
      assert(await page.evaluate(()=>!!driverMarker));
      status='error';
      await page.clock.fastForward(310000);
      assert.equal(await page.evaluate(()=>driverMarker),null);
      assert.match(await page.locator('#tracking-map-note').textContent(), /Última señal GPS/);
      // Nunca interpretar null como coordenada cero, ni hora local del visitante.
      assert.equal(await page.evaluate(()=>FormoPackMapas.coordenadas(null,null)),false);
      assert.equal(await page.evaluate(()=>FormoPackMapas.fechaGps('2026-11-10T12:00:00')),Date.parse('2026-11-10T15:00:00Z'));
      await page.waitForFunction(()=>!consultaGps.controlador);
      terminal=true; status='correcto';
      await page.evaluate(()=>consultaGps.consultar());
      await page.waitForFunction(()=>currentStatus==='entregado');
      const llamadasAlFinal=calls;
      await page.clock.fastForward(60000);
      assert.equal(calls,llamadasAlFinal);
      assert.equal(await page.evaluate(()=>driverMarker),null);
      assert.match(await page.locator('#tracking-live-note').textContent(),/finalizado/);
      assert.deepEqual(errors,[]);
      await page.close();
    }
    const operativo = await browser.newPage({serviceWorkers:'block', viewport:{width:390,height:844}});
    await operativo.clock.install();
    let falloOperativo = false;
    let registro = {id_envio:1,nro_guia:'FP-TEST',estado_actual:'en_ruta',localidad_destino:'Clorinda',
      gps_en_vivo:true,gps_latitud:-26.18,gps_longitud:-58.17,gps_fecha:new Date().toISOString()};
    const erroresOperativos = [];
    operativo.on('pageerror',e=>erroresOperativos.push(e.message));
    await operativo.route('**/*', async r=>{
      const url=r.request().url();
      if (url.includes('/mapa/envios')) return falloOperativo ? r.fulfill({status:503,body:''}) : r.fulfill({json:{envios:[registro]}});
      if (url.endsWith('/admin/logistica')) return r.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(process.env.FORMOPACK_HTML_TEST,'logistica.html'))});
      if (url.includes('leaflet.js')) return r.fulfill({contentType:'text/javascript',body:fs.readFileSync(leaflet)});
      if (url.includes('/static/')) {
        const file=path.join(root,'web',new URL(url).pathname);
        if (fs.existsSync(file)) return r.fulfill({path:file});
      }
      return r.fulfill({status:200,body:''});
    });
    await operativo.goto('https://formopack.example/admin/logistica');
    await operativo.waitForFunction(()=>document.querySelectorAll('.map-marker-live').length===1);
    falloOperativo=true;
    await operativo.locator('#mapa-refresh').click();
    await operativo.waitForFunction(()=>document.querySelector('#mapa-live-status').textContent.includes('interrumpida'));
    falloOperativo=false;
    await operativo.locator('#mapa-refresh').click();
    await operativo.waitForFunction(()=>document.querySelector('#mapa-live-status').textContent.includes('actualizado'));
    await operativo.clock.fastForward(310000);
    assert.equal(await operativo.locator('.map-marker-live').count(),0);
    await operativo.locator('#mapa-envio-select').selectOption('1');
    assert.match(await operativo.locator('#mapa-envio-detalle').textContent(),/Última ubicación conocida/);
    assert.deepEqual(erroresOperativos,[]);
    await operativo.close();
    // Comprobar exclusión de consultas y cancelación de respuestas tardías.
    const page = await browser.newPage();
    await page.goto('about:blank');
    await page.clock.install();
    await page.addScriptTag({path:path.join(root,'web/static/js/mapas-seguimiento.js')});
    await page.evaluate(async () => {
      window.total=0; window.recibidas=0;
      window.fetch=(_url,{signal})=>new Promise((resolve,reject)=>{
        total++; window.responder=()=>resolve({ok:true,json:async()=>({})});
        signal.addEventListener('abort',()=>reject(new Error('cancelada')));
      });
      window.c = new FormoPackMapas.ConsultaPeriodica('/test',()=>recibidas++,()=>{});
      c.iniciar(); c.consultar(); c.consultar();
      if (total!==1) throw new Error('Consultas superpuestas');
      c.pausar(); responder();
      await Promise.resolve();
      await Promise.resolve();
      if (recibidas!==0) throw new Error('Se aplicó una respuesta cancelada');
    });
    await page.evaluate(()=>{
      window.fallos=0;
      window.c2=new FormoPackMapas.ConsultaPeriodica('/test',()=>recibidas++,()=>fallos++);
      c2.iniciar();
    });
    await page.clock.runFor(8100);
    assert.equal(await page.evaluate(()=>fallos),1);
    assert.equal(await page.evaluate(()=>recibidas),0);
    await page.evaluate(()=>c2.pausar());
    await page.close();
    console.log('Mapas: GPS vencido, recuperación, OSRM inválido y consultas concurrentes verificados en escritorio y móvil.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
