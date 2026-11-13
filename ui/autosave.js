/* One verified save at a time. Later edits never get replaced by an old reply. */
'use strict';
class F75AutoSave {
 constructor({document,write,accept,state,busy,validate,signature=JSON.stringify,delay=900}) {
  Object.assign(this,{document,write,accept,state,busy,validate,signature,delay});
  this.revision=0;this.confirmed=0;this.running=false;this.paused=false;
 }
 get pending(){return this.revision!==this.confirmed;}
 loaded(){clearTimeout(this.timer);this.revision=this.confirmed=0;this.paused=false;this.savedSignature=this.signature(this.document());this.persisted=false;this.state('ready');}
 edited(){this.revision++;this.lastEdit=Date.now();if(!this.paused){this.state(this.running?'saving':'waiting');this.schedule();}}
 schedule(){clearTimeout(this.timer);if(this.pending&&!this.paused)this.timer=setTimeout(()=>this.flush(),Math.max(0,this.delay-(Date.now()-this.lastEdit)));}
 async flush(){
  clearTimeout(this.timer);
  if(!this.pending||this.paused||this.running)return;
  const error=this.validate();if(error){this.state('invalid',error);return;}
  if(this.busy()){this.timer=setTimeout(()=>this.flush(),250);return;}
  if(this.signature(this.document())===this.savedSignature){this.confirmed=this.revision;this.state(this.persisted?'saved':'ready');return;}
  const revision=this.revision,snapshot=JSON.parse(JSON.stringify(this.document()));
  this.running=true;this.state('saving');
  try{
   const result=await this.write(snapshot);
   this.accept(result,this.revision!==revision);
   this.savedSignature=this.signature(snapshot);this.persisted=true;
   this.confirmed=revision;this.state(this.pending?'waiting':'saved');
  }catch(error){this.paused=true;this.state('error',error.message);}
  finally{this.running=false;this.schedule();}
 }
 retry(){if(!this.pending||this.running)return;this.paused=false;this.lastEdit=0;this.schedule();}
}
if(typeof module!=='undefined')module.exports=F75AutoSave;
