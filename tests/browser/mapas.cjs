// Verifica las solicitudes reales de Leaflet en Chrome con el proveedor simulado.
const { chromium } = require(process.env.FORMOPACK_TEST_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({
    headless: true, executablePath: process.env.FORMOPACK_TEST_CHROME
  });
  try {
    const leaflet = fs.readFileSync(process.env.FORMOPACK_TEST_LEAFLET, 'utf8');
    for (const template of ['admin/logistica.html', 'tracking.html']) {
      const source = fs.readFileSync(path.join(__dirname, '../../web/templates', template), 'utf8');
      const layer = source.match(/L\.tileLayer\([\s\S]*?\)\.addTo\(map\);/)[0];
      const page = await browser.newPage({ serviceWorkers: 'block' });
      const requests = [];
      await page.route('**/*', async route => {
        if (route.request().url().startsWith('https://formopack.example/')) {
          return route.fulfill({
            contentType: 'text/html', headers: { 'Referrer-Policy': 'same-origin' },
            body: '<div id="map" style="height:256px;width:256px"></div>'
          });
        }
        requests.push(route.request());
        return route.fulfill({ contentType: 'image/png', body: Buffer.from(
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64') });
      });
      await page.goto('https://formopack.example/admin/tracking?guia=PRIVADA');
      await page.addScriptTag({ content: leaflet });
      await page.evaluate(layer => {
        const map = L.map('map').setView([-26.18, -58.17], 8);
        eval(layer);
      }, layer);
      await page.waitForFunction(() => document.querySelectorAll('.leaflet-tile-loaded').length > 0);
      assert(requests.length > 0);
      for (const request of requests) {
        assert.equal(new URL(request.url()).hostname, 'tile.openstreetmap.org');
        assert.equal((await request.allHeaders()).referer, 'https://formopack.example/');
      }
      console.log(template + ': dominio enviado, guía privada omitida');
      await page.close();
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
