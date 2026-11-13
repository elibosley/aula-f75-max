const assert=require('node:assert/strict');
const AutoSave=require('../ui/autosave.js');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 let doc={wheel:0,base:'old'},calls=[],release,invalid=null,unavailable=false,fail=false;
 const states=[];
 const queue=new AutoSave({document:()=>doc,signature:d=>JSON.stringify(d.wheel),delay:10,
  busy:()=>unavailable,validate:()=>invalid,state:(s,e)=>states.push([s,e]),
  write:async snapshot=>{calls.push(snapshot);if(fail)throw Error('Unconfirmed');await new Promise(r=>release=r);return {...snapshot,base:'verified'+calls.length};},
  accept:(result,newer)=>{doc=newer?{...doc,base:result.base}:result;}
 });
 queue.loaded();await sleep(20);assert.equal(calls.length,0);
 doc.wheel=1;queue.edited();doc.wheel=2;queue.edited();await sleep(20);
 assert.equal(calls.length,1);assert.equal(calls[0].wheel,2);
 doc.wheel=1;queue.edited();release();await sleep(20);
 assert.equal(calls.length,2);assert.deepEqual(calls[1],{wheel:1,base:'verified1'});
 release();await sleep(20);assert.equal(queue.pending,false);assert.equal(doc.wheel,1);
 // Returning to the confirmed value during the debounce does not write flash.
 doc.wheel=2;queue.edited();doc.wheel=1;queue.edited();await sleep(25);assert.equal(calls.length,2);
 invalid='Incomplete macro';doc.wheel=2;queue.edited();await sleep(20);assert.equal(calls.length,2);assert.equal(states.at(-1)[0],'invalid');
 invalid=null;fail=true;queue.edited();await sleep(20);assert.equal(calls.length,3);assert.equal(queue.paused,true);
 doc.wheel=0;queue.edited();await sleep(25);assert.equal(calls.length,3);assert.equal(queue.pending,true);
 fail=false;queue.retry();await sleep(20);assert.equal(calls.length,4);release();await sleep(20);
 unavailable=true;doc.wheel=2;queue.edited();await sleep(30);assert.equal(calls.length,4);
 unavailable=false;const last=queue.flush();await sleep(5);assert.equal(calls.length,5);release();await last;
 assert.equal(queue.pending,false);assert.equal(doc.wheel,2);
 console.log("Autosave queue passed: coalescing, in-flight edits, baseline advance, no-op, validation, failure pause, explicit retry and disconnect.");
})().catch(error=>{console.error(error);process.exitCode=1;});
