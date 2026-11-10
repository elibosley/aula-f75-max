/* Read-only rendered proof; never changes a real keyboard setting. */
const {chromium}=require('playwright');const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const output=process.argv[2]||'analysis/completion/host-evidence-final/ui';fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});const page=await context.newPage();page.setDefaultTimeout(8000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8787/hardware.html');await page.getByRole('button',{name:'Read keyboard',exact:true}).click();await page.getByRole('status').filter({hasText:'Keyboard settings loaded.'}).waitFor();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:output+'/phone.png'});
  const profile=page.getByRole('combobox',{name:'Bluetooth 1',exact:true});const selected=await profile.locator('option:checked').textContent();assert.match(selected,/^Auto · Mac$/);
  await profile.scrollIntoViewIfNeeded();await page.getByRole('heading',{name:'Host layouts',exact:true}).locator('..').screenshot({path:output+'/host-profile-phone.png'});
  await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'Read keyboard',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:output+'/desktop.png',fullPage:true});assert.deepEqual(errors,[]);
  const result={status:'passed',read_only:true,hardware_read:true,phone_width:390,bluetooth_1_profile:selected,console_errors:errors,phone_overflow:false};fs.writeFileSync(output+'/receipt.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
