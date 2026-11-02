const {chromium}=require(process.env.FORMOPACK_TEST_PLAYWRIGHT);
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.FORMOPACK_TEST_CHROME});
 try {
  const base=process.env.FORMOPACK_TEST_URL;
  const page=await browser.newPage();
  await page.route('**/*', r=>r.request().url().startsWith(base)?r.continue():r.abort());
  await page.goto(base);
  await page.evaluate(async()=>{await fetch('/login',{method:'POST',body:new URLSearchParams({
   email:'recepcion@formopack.com',password:'recep456',csrf_token:document.querySelector('[name=csrf_token]').value})});});
  await page.goto(base+'/admin/dashboard');
  await page.getByRole('link',{name:'Devoluciones en central'}).click();
  await page.getByRole('button',{name:'Confirmar ingreso físico'}).click();
  await page.getByText('Registrar retiro del remitente',{exact:true}).click();
  await page.locator('[name=dni]').fill(process.env.FORMOPACK_DNI_TEST);
  const box=await page.locator('canvas').boundingBox();
  await page.mouse.move(box.x+8,box.y+12);await page.mouse.down();
  await page.mouse.move(box.x+66,box.y+34,{steps:12});await page.mouse.up();
  await page.getByRole('button',{name:'Confirmar devolución'}).click();
  const enlace=page.getByRole('link',{name:/Descargar constancia firmada/});
  await enlace.waitFor();
  const pdf=await page.request.get(base+await enlace.getAttribute('href'));
  assert.equal((await pdf.body()).subarray(0,4).toString(),'%PDF');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
