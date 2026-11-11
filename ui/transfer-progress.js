/* Foreground transfer progress. Counts come from acknowledged device work. */
'use strict';
(() => {
 const labels={connecting:'Connecting to keyboard…',preparing:'Preparing changes…',reading:'Reading settings…',sending:'Sending changes…',applying:'Applying settings…',saving:'Saving to keyboard…',verifying:'Verifying settings…',checking:'Checking the result…',clock:'Synchronizing clock…'};
 class TransferProgress{
  constructor(element){this.element=element;this.bar=element.querySelector('progress');this.title=element.querySelector('.transfer-title');this.detail=element.querySelector('.transfer-detail');this.time=element.querySelector('.transfer-time');}
  start(action,transport,csrf){
   this.stop();this.action=action;this.transport=transport;this.started=performance.now();
   this.identity=Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
   this.controller=new AbortController();this.element.hidden=false;this.element.dataset.state='running';this.element.dataset.indeterminate='true';this.title.textContent=labels.connecting;this.detail.textContent='Keep your keyboard connected.';this.bar.removeAttribute('value');this.bar.setAttribute('aria-valuetext','Connecting to keyboard');
   this.tick();this.clock=setInterval(()=>this.tick(),1000);this.poll(this.identity,csrf);return this.identity;
  }
  tick(){const elapsed=Math.floor((performance.now()-this.started)/1000);this.time.textContent=`${Math.floor(elapsed/60)}:${String(elapsed%60).padStart(2,'0')} elapsed · ${this.transport==='bluetooth'?'Bluetooth':'USB'}`;}
  async poll(identity,csrf){
   try{
    const response=await fetch('/api/hardware/progress/'+identity,{headers:{'X-F75-CSRF':csrf},signal:this.controller.signal});
    if(!response.ok)throw Error('Progress unavailable');const data=await response.json();
    if(this.identity!==identity)return;
    if(data.state==='running'){
     this.title.textContent=labels[data.phase]||'Working with your keyboard…';
     if(Number.isInteger(data.completed)&&Number.isInteger(data.total)&&data.total>0){
      this.element.dataset.indeterminate='false';this.bar.max=data.total;this.bar.value=data.completed;
      const percentage=Math.floor(data.completed*100/data.total);
      this.detail.textContent=`${data.completed.toLocaleString()} of ${data.total.toLocaleString()} bytes · ${percentage}% of this step`;
      this.bar.setAttribute('aria-valuetext',this.title.textContent+' '+percentage+' percent');
     }else{
      this.element.dataset.indeterminate='true';this.bar.removeAttribute('value');this.detail.textContent=data.phase==='saving'?'Waiting for the keyboard to confirm the save.':'Keep your keyboard connected.';this.bar.setAttribute('aria-valuetext',this.title.textContent);
     }
    }
   }catch(error){if(this.identity===identity&&error.name!=='AbortError')this.detail.textContent='Progress updates unavailable. Waiting for the operation’s result.';}
   if(this.identity===identity)this.pollTimer=setTimeout(()=>this.poll(identity,csrf),750);
  }
  finish(success){
   this.stop();this.element.dataset.state=success?'complete':'error';
   if(success){this.element.dataset.indeterminate='false';this.bar.max=1;this.bar.value=1;this.title.textContent={read:'Settings loaded',apply:'Applied · not saved',save:'Saved and verified',clock:'Clock synchronized'}[this.action];this.detail.textContent=this.action==='apply'?'Save to keep these changes after a restart.':this.action==='save'?'Saved settings match the keyboard’s readback.':'Ready.';}
   else{this.bar.removeAttribute('value');this.title.textContent='Operation not completed';this.detail.textContent='See the message below before trying again.';}
   this.bar.setAttribute('aria-valuetext',this.title.textContent);
  }
  stop(){this.identity=null;this.controller?.abort();clearTimeout(this.pollTimer);clearInterval(this.clock);}
  dismiss(){this.stop();this.element.hidden=true;}
 }
 window.F75TransferProgress=TransferProgress;
})();
