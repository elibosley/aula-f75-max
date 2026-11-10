/* Tailnet bridge. Critical state and display pixels are produced by compiled C. */
if(location.protocol.startsWith('http')) (async()=>{
  window.F75_NATIVE_BOOT=true;
  const queue=[];let sequence=0,busy=false,attached=null,nativeBudget=null,connected=false,lastUpdate=0,displayFps=0;
  const tag=document.querySelector('.prototype');
  let depth=0;
  const methods=['activity','changed','setOS','toggleCaps','setControl','switchHost','requestPair','holdConfirm','connectedEvent','cancelPairing','save','reboot','tick','turn','press','back','controlKey'];
  function attach(){
    const e=F75_PREVIEW.engine;if(e===attached)return;attached=e;
    for(const method of methods){
      const original=e[method];
      e[method]=function(...args){
        const outer=depth===0;depth++;let result;try{result=original.apply(this,args);}finally{depth--;}
        if(method==='toggleCaps')args=[this.config.capsSwap];
        if(outer&&(method!=='tick'||Number(args[0])>=5000)){queue.push({name:method==='changed'?'visualSettings':method,args:method==='changed'?[structuredClone(this.config)]:args});queueMicrotask(update);}
        return result;
      };
    }
    const originalPower=e.powerState.bind(e);
    e.powerState=()=>nativeBudget?{...nativeBudget,low:e.battery<=10&&!e.charging,critical:e.battery<=5&&!e.charging}:originalPower();
  }
  function view(){
    const e=F75_PREVIEW.engine;const out={status_left:'',status_right:'',title:e.page,rows:[],footer:'TURN / PRESS / BACK',home:e.page==='Home',caps_swap:e.config.capsSwap,
      clock:new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}),host_label:e.host().name,os:e.host().os==='mac'?'MAC':'WIN',selected:e.cursor};
    if(e.confirm){out.home=false;out.title=e.confirm.replacing?'REPLACE DEVICE?':'PAIR DEVICE?';out.rows=[hostLabel(e.confirm.id),'HOLD ENTER 1.2 SEC','ESC CANCELS'];out.selected=255;out.footer='WAITING FOR CONFIRM';}
    else if(e.pairing){out.home=false;out.title='PAIRING';out.rows=[hostLabel(e.pairing.id),'OPEN BLUETOOTH','ON YOUR COMPUTER'];out.selected=255;out.footer=Math.ceil((e.pairing.deadline-e.time)/1000)+' SEC REMAINING';}
    else if(e.control){out.home=false;out.title='BOARD CONTROLS';out.rows=['1 DEVICES  2 KEYS','3 LIGHTS   4 POWER','ARROWS / J K MOVE','ENTER SELECT'];out.selected=255;out.footer='ESC BACK   S SAVE';}
    else if(!out.home){let rows=e.rows();if(e.page==='Devices')rows=rows.map(id=>hostLabel(id)+' '+e.config.hosts[id].name);out.rows=rows.slice(0,5);out.selected=e.cursor;}
    else out.footer=e.notice?e.notice.slice(0,20):e.action?e.action.toUpperCase()+' '+(e.action==='Volume'?e.volume+'%':''):'';
    return out;
  }
  function hydrate(data){
    window.F75_NATIVE_STATE=data;
    window.F75_TIMER=data.timer;
    window.F75_PET=data.pet;
    const e=F75_PREVIEW.engine;const previousPhase=JSON.stringify([e.confirm,e.pairing?.id,e.error]);Object.assign(e.config,data.config);e.connected=data.connected;e.control=data.control;e.page=data.page;e.cursor=data.cursor;e.volume=data.volume;e.editing=data.editing;e.wheelDivisor=data.wheelDivisor;document.querySelector('#wheel-feel').value=data.wheelDivisor;e.confirm=data.confirm;e.pairing=data.pairing?{id:data.pairing.id,deadline:e.time+data.pairing.remaining}:null;e.error=data.error;nativeBudget=data.power;displayFps=data.motion?.fps||0;window.F75_NATIVE_MOTION=data.motion;F75.Engine.prototype.changed.call(e);
    if(data.frame){const img=new Image();img.onload=()=>{if(data.sequence<(window.F75_NATIVE_DRAWN_SEQUENCE||0))return;window.F75_NATIVE_FRAME=img;window.F75_NATIVE_DRAWN_SEQUENCE=data.sequence;drawScreen();};img.src='data:image/png;base64,'+data.frame;}
    connected=true;tag.textContent='Live C core + renderer · simulated radio';tag.style.color='var(--accent)';
    document.querySelector('#screen-theme').setAttribute('aria-pressed',String(e.config.screenTheme==='Light'));updateFocus();updatePet();
    for(const key of ['brightness','speed']){const input=document.querySelector('#'+key);if(input&&input!==document.activeElement)input.value=e.config.lighting[key];const output=document.querySelector('#'+key+'-value');if(output)output.textContent=e.config.lighting[key]+'%';}
    if(previousPhase!==JSON.stringify([e.confirm,e.pairing?.id,e.error]))renderInspector();paint();
  }
  async function update(){
    if(busy||!connected||document.hidden)return;attach();busy=true;lastUpdate=performance.now();
    const commands=queue.splice(0);const body={sequence:++sequence,commands,explicitSettings:true,config:engine.config,battery:engine.battery,charging:engine.charging,systemReducedMotion:motionQuery.matches,view:view()};
    try{
      const response=await fetch('/api/state',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(!response.ok)throw Error('Native core returned '+response.status);
      const data=await response.json();if(!queue.length)hydrate(data);
    }catch(error){
      connected=false;tag.textContent='C core disconnected · reload to reconnect';tag.style.color='var(--danger)';live(error.message+'. Reload to reconcile with the native core.');
      for(const button of document.querySelectorAll('button'))button.disabled=true;
    }finally{busy=false;if(queue.length)queueMicrotask(update);}
  }
  try{
    const response=await fetch('/api/state');if(!response.ok)throw Error('Native core unavailable');
    const state=await response.json();sequence=state.sequence;attach();hydrate(state);engine.saved=F75.serialize(engine.config);engine.changed();render();
    await update();setInterval(()=>{if(queue.length||performance.now()-lastUpdate>=1000/(displayFps||1))update();},16);
    window.F75_NATIVE={update,petTaps(count=1){if(!Number.isInteger(count)||count<1||count>64)return;const last=queue.at(-1);if(last?.name==='petTaps'&&last.args[0]+count<=64)last.args[0]+=count;else queue.push({name:'petTaps',args:[count]});queueMicrotask(update);},timer(action){queue.push({name:'timer'+action,args:[]});queueMicrotask(update);},openPage(page){queue.push({name:'openPage',args:[page]});queueMicrotask(update);},wheelFeel(value){queue.push({name:'wheelFeel',args:[value]});queueMicrotask(update);},adoptProfile(config){attach();queue.push({name:'importProfile',args:[config]});},get connected(){return connected;},get sequence(){return sequence;}};
    updateFocus();updatePet();
  }catch(error){tag.textContent='C core unavailable · offline design preview';live(error.message);}
})();
