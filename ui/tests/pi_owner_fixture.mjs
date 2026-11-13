// Offline fixture: actual authentication/serialization, fake runtime only.
// NEVER imports host/bootstrap, providers, admission or model/service launchers.
import {appendFile,readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {serveOwner} from '../../extensions/pi-owner/socket.mjs';
import {PiOwner} from '../../extensions/pi-owner/owner.mjs';
const [root,log]=process.argv.slice(2);
let state='off',emit,abort;
const record=value=>appendFile(log,JSON.stringify(value)+'\n');
const session={
  subscribe(listener){emit=listener;return ()=>{emit=undefined;};},
  waitForIdle:async()=>{},clearQueue(){},async abort(){abort?.();},
  async prompt(text){
    await record({op:'native_prompt',text});
    const update=(type,delta)=>emit?.({type:'message_update',assistantMessageEvent:{type,delta}});
    update('thinking_delta','Fixture reasoning α');
    if(text==='slow')await new Promise(resolve=>{abort=resolve;});
    if(text==='tool'){
      emit?.({type:'tool_execution_start',toolName:'write'});
      const allowed=await owner.approve({title:'Allow write?',detail:JSON.stringify({task:'fixture-task',workspace:'/disposable',action:'write',path:'example.txt',content:'EXACT fixture content'})});
      await record({op:'tool_consent',allowed});
      emit?.({type:'tool_execution_end',toolName:'write',isError:!allowed});
    }
    if(text==='disconnect'){for(const listener of owner.listeners)listener({type:'fixture_disconnect'});await socket.close();return;}
    update('text_delta',text==='injection'?'/moe on':`Fixture answer: ${text}`);
    emit?.({type:'message_end',message:{role:'assistant',stopReason:text==='error'?'error':'stop',usage:{input:3,output:4}}});
  }
};
const owner=new PiOwner({session,durable:{quiesce:async()=>{},resume:async()=>{}},checkpoint:async()=>{},
  cancelTransition:async()=>{},command:async op=>{
    await record({op});
    if(op==='status'){
      const mode=await readFile(join(root,'mode'),'utf8').catch(()=> '');
      return {state:mode==='stale'?'failed':mode==='foreign'?'on':state};
    }
    if(op==='on') {
      const mode=await readFile(join(root,'mode'),'utf8').catch(()=> '');
      const detail=mode==='oversize-consent'?'x'.repeat(24001):JSON.stringify({task:'fixture-task',action:'on',prior:['text'],model:'fixture-only-NO-LAUNCH'});
      if(!await owner.approve({title:'Exclusive Hermes handoff?',detail}))throw Error('Denied');
    }
    state=op;return {state};
  }});
const socket=await serveOwner(root,owner,{onControlDisconnect:()=>{owner.disconnectControl();void session.abort();}});
process.stdout.write('ready\n');
process.on('SIGTERM',async()=>{await socket.close();process.exit(0);});
