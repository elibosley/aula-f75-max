'use strict';
const $=selector=>document.querySelector(selector);
let api, previewBusy=false, installing=false, previewSequence=0, pendingPreview=[];
const quiet=matchMedia('(prefers-reduced-motion: reduce)');
async function preview(command=null,args=[],identifier=$('#preview-model').value){
 if(!api||document.hidden)return;
 if(previewBusy){if(command!==null)pendingPreview.push([command,args,identifier]);return;}
 previewBusy=true;
 const sequence=++previewSequence;
 try{
  const result=await api.preview_keyboard(identifier,command,args);
  if(identifier!==$('#preview-model').value||sequence!==previewSequence)return;
  const portrait=identifier==='s75pro';
  $('#panel-preview').width=portrait?135:128;$('#panel-preview').height=portrait?240:128;
  $('#panel-preview').src='data:image/png;base64,'+result.frame;
  $('#panel-dimensions').textContent=portrait?'135 × 240 pixels · portrait':'128 × 128 pixels · square';
  $('#preview-companion').value=String(result.config.companion);
  $('#preview-status').textContent='';
 }catch(error){$('#preview-status').textContent=error.message||String(error);}
 finally{previewBusy=false;if(pendingPreview.length)preview(...pendingPreview.shift());}
}
async function checkFirmware(){
 if(!api||installing)return;
 $('#check-firmware').disabled=true;
 try{
  const result=await api.firmware_availability();
  $('#firmware-availability').textContent=result.message;
  $('#install-firmware').disabled=!result.available;
 }catch(error){$('#firmware-availability').textContent=error.message||String(error);$('#install-firmware').disabled=true;}
 finally{$('#check-firmware').disabled=false;}
}
async function installationStatus(){
 if(!api||!installing)return;
 try{
  const result=await api.firmware_install_status();
  $('#firmware-status').textContent=result.message;
  $('#firmware-progress').hidden=!result.busy;
  $('#firmware-progress').value=result.bytes_written||0;
  installing=result.busy;
  if(!installing)await checkFirmware();
 }catch(error){$('#firmware-status').textContent=error.message||String(error);}
}
$('#install-firmware').onclick=async()=>{
 if(!api||installing)return;
 installing=true;$('#install-firmware').disabled=true;$('#check-firmware').disabled=true;
 try{await api.start_firmware_install();await installationStatus();}
 catch(error){installing=false;$('#firmware-status').textContent=error.message||String(error);await checkFirmware();}
};
$('#check-firmware').onclick=checkFirmware;
$('#preview-model').onchange=()=>{++previewSequence;preview('openPage',['Home']);};
for(const button of document.querySelectorAll('[data-page]'))button.onclick=()=>preview('openPage',[button.dataset.page]);
$('#wheel-left').onclick=()=>preview('turn',[-1]);$('#wheel-right').onclick=()=>preview('turn',[1]);
$('#wheel-press').onclick=()=>preview('press');$('#wheel-back').onclick=()=>preview('back');
$('#preview-typing').onclick=()=>preview('petTaps',[24]);
$('#preview-companion').onchange=()=>preview('visualSettings',[{companion:Number($('#preview-companion').value),screenFace:'Chibi'}]);
window.addEventListener('pywebviewready',async()=>{
 api=window.pywebview.api;
 const state=await api.firmware_install_status();installing=state.busy;
 if(installing)installationStatus();else checkFirmware();
 preview();
 const timer=setInterval(()=>{installationStatus();if(!quiet.matches)preview();},500);
 window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
});
if(!window.pywebview){$('#firmware-availability').textContent='Open this page in the F75 Studio desktop app to inspect USB and use the simulator.';$('#check-firmware').disabled=true;}
