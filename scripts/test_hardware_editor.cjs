/* Non-disruptive editor qualification against the connected keyboard. */
const {chromium}=require('playwright');const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const output='analysis/completion/custom-final/ui';fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});const result={hardware:true,tests:[]};
 try{
  const context=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});const page=await context.newPage();page.setDefaultTimeout(8000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8787/hardware.html');await page.getByRole('button',{name:'Read keyboard',exact:true}).click();
  await page.getByRole('status').filter({hasText:'Keyboard settings loaded.'}).waitFor({timeout:10000});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:output+'/phone.png',fullPage:false});result.tests.push('phone layout and real USB read');
  await page.getByRole('button',{name:'Select A',exact:true}).click();await page.getByRole('combobox',{name:'Key action',exact:true}).selectOption(String(0x8000));
  await page.getByRole('button',{name:'Apply',exact:true}).click();await page.getByRole('status').filter({hasText:'Macro 1 has no steps'}).waitFor();result.tests.push('empty macro rejected before upload');
  await page.getByRole('combobox',{name:'Key action',exact:true}).selectOption('0');
  await page.getByRole('combobox',{name:'Layer',exact:true}).selectOption('1');await page.getByRole('button',{name:'Select Esc',exact:true}).click();assert(await page.getByRole('combobox',{name:'Key action',exact:true}).isDisabled());
  await page.getByRole('combobox',{name:'Layer',exact:true}).selectOption('0');result.tests.push('Fn recovery action cannot be rebound');
  await page.getByRole('button',{name:'Use Primary + C preset',exact:true}).click();assert.equal(await page.locator('.macro-step').count(),4);
  for(let n=0;n<4;n++)await page.getByRole('button',{name:'Remove step 1',exact:true}).click();assert.equal(await page.locator('.macro-step').count(),0);result.tests.push('macro preset and step removal');
  await page.getByRole('button',{name:'Apply',exact:true}).click();await page.getByRole('status').filter({hasText:'Settings applied and read back.'}).waitFor({timeout:10000});result.tests.push('unchanged profile applied and read back');
  await page.getByRole('button',{name:'Save to keyboard',exact:true}).click();await page.getByRole('status').filter({hasText:'Settings saved and read back'}).waitFor({timeout:10000});result.tests.push('unchanged profile saved to keyboard flash');
  await page.getByRole('button',{name:'Sync clock from this device',exact:true}).click();await page.getByRole('status').filter({hasText:'Clock synchronized'}).waitFor({timeout:10000});result.tests.push('clock sync acknowledged');
  await page.getByRole('button',{name:'Read keyboard',exact:true}).click();await page.getByRole('status').filter({hasText:'Keyboard settings loaded.'}).waitFor();
  await page.getByRole('button',{name:'Select A',exact:true}).click();assert.equal(await page.getByRole('combobox',{name:'Key action',exact:true}).inputValue(),'0');assert(await page.getByLabel('Swap physical Caps and left Ctrl on every host').isChecked());result.tests.push('test edits restored and Caps swap retained');
  await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'Read keyboard',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:output+'/desktop.png',fullPage:true});
  assert.deepEqual(errors,[]);result.status='passed';result.screenshots=['phone.png','desktop.png'];
 }finally{await browser.close();fs.writeFileSync(output+'/receipt.json',JSON.stringify(result,null,2)+'\n');}
 console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exitCode=1;});
