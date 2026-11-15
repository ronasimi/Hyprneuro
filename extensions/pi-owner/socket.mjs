// Two binary challenge-response credentials: chat != trusted UI control. Neither
// credential nor Hermes/lease capabilities ever appear in JSON or model context.
import { createServer } from 'node:net';
import { createHmac,randomBytes,randomUUID,timingSafeEqual } from 'node:crypto';
import { chmod,lstat,mkdir,readFile,realpath,writeFile } from 'node:fs/promises';
import { join } from 'node:path';
export const MAX_FRAME=65536;
export const signature=(key,nonce,role)=>createHmac('sha256',key).update(nonce).update(role).digest();
export async function privateDirectory(root) {
  if(!root.startsWith('/'))throw new Error('Canonical absolute private directory required');
  await mkdir(root,{mode:0o700,recursive:true});
  const st=await lstat(root);
  if(await realpath(root)!==root||!st.isDirectory()||st.uid!==process.getuid()||(st.mode&0o077))throw new Error('Unsafe owner directory');
}
export async function serveOwner(root,owner,{onControlDisconnect=()=>owner.disconnectControl(),singleControl=false,read,registration}={}) {
  await privateDirectory(root);
  const keys={};
  for(const role of (read?['chat','control','read']:['chat','control'])) {
    const file=join(root,role+'.key');
    try{await writeFile(file,randomBytes(32),{flag:'wx',mode:0o600});}catch(e){if(e.code!=='EEXIST')throw e;}
    const st=await lstat(file);
    if(!st.isFile()||st.nlink!==1||st.uid!==process.getuid()||(st.mode&0o077)||st.size!==32)throw new Error('Unsafe bridge credential');
    keys[role]=await readFile(file);
  }
  const path=join(root,'owner.sock'),sockets=new Set();let controls=0;
  const server=createServer(socket=>{
    if(sockets.size>=8){socket.destroy();return;}sockets.add(socket);
    const nonce=randomBytes(32);socket.write(nonce);
    let authenticated=false,role,buffer=Buffer.alloc(0),unsubscribe,pending=0,chat;
    const controlGeneration=randomUUID();
    const cancel=new AbortController();
    const timer=setTimeout(()=>socket.destroy(),5000);
    const send=value=>{
      const line=JSON.stringify(value)+'\n';
      if(Buffer.byteLength(line)>MAX_FRAME||socket.writableLength>MAX_FRAME*4){socket.destroy();return;}
      socket.write(line);
    };
    socket.on('error',()=>{});
    socket.on('close',()=>{
      clearTimeout(timer);cancel.abort();sockets.delete(socket);unsubscribe?.();
      if(role==='control'&&authenticated&&!--controls)onControlDisconnect();
    });
    async function request(value) {
      if(!value||Array.isArray(value)||typeof value!=='object')throw new Error('Object request required');
      const {op,id}=value;
      if(typeof id!=='string'||!/^[\w.-]{1,80}$/.test(id))throw new Error('Bounded correlation id required');
      const fields={grants_invalidated:['op','id'],grant_release_done:['op','id','release_id','success'],broker_proof:['op','id','nonce'],status:['op','id'],on:['op','id'],off:['op','id'],consent:['op','id','answer_id','allowed','receipt'],cancel:['op','id','chat_id','generation'],chat:['op','id','text','recommend'],read:['op','id','call','exec','tool_id','args']};
      if(!fields[op]||Object.keys(value).some(k=>!fields[op].includes(k)))throw new Error('Unknown operation/fields');
      if(role==='read'&&op!=='read'||op==='read'&&(role!=='read'||!read))throw new Error('Read bridge role has no chat/control/lifecycle authority');
      if(op==='read')return read(value,cancel.signal);
      if(['on','off','consent','broker_proof','grants_invalidated','grant_release_done'].includes(op)&&role!=='control')throw new Error('Trusted UI control authentication required');
      if(op==='chat'&&value.recommend===true&&role!=='control')throw new Error('recommend=true requires explicit trusted UI preference');
      if(op==='cancel') {
        if(role!=='chat'||!chat||value.chat_id!==chat.id||value.generation!==chat.generation)
          throw new Error('Cancel requires same connection and exact active chat generation');
        if(!chat.requested){chat.requested=true;chat.fence?.();chat.abort.abort(chat.reason);}
        // Acknowledgement is the completed/drained chat outcome, never abort().
        return chat.done;
      }
      if(op==='grants_invalidated'){owner.grantsInvalidated();return {accepted:true};}
      if(op==='grant_release_done'){owner.releaseDone(value.release_id,value.success);return {accepted:true};}
      if(op==='broker_proof') {
        if(!registration||typeof value.nonce!=='string'||!/^[0-9a-f]{64}$/.test(value.nonce))
          throw new Error('Registered host CONTROL challenge required');
        const binding=await registration();
        cancel.signal.throwIfAborted();
        const body={...binding,control_generation:controlGeneration,nonce:value.nonce};
        const wire=JSON.stringify(Object.fromEntries(Object.entries(body).sort(([a],[b])=>a.localeCompare(b,'en'))));
        return {...body,mac:createHmac('sha256',keys.control).update('hyprneuro.grant-registration/1\0').update(wire).digest('hex')};
      }
      if(op==='status')return owner.status();
      if(op==='consent'){owner.consent(value.answer_id,value.allowed,value.receipt);return {accepted:true};}
      if(op==='on'||op==='off')return owner.transition(op);
      if(chat)throw new Error('One active chat per connection');
      const current={id,generation:randomUUID(),requested:false,abort:new AbortController(),
        reason:new Error('Explicit correlated user cancellation'),disconnected:()=>cancel.signal.aborted};
      chat=current;
      send({id,type:'event',event:{type:'chat_admission',generation:current.generation}});
      try {
        current.done=owner.chat(value,event=>send({id,type:'event',event}),AbortSignal.any([cancel.signal,current.abort.signal]),current);
        return await current.done;
      }finally{if(chat===current)chat=undefined;}
    }
    socket.on('data',chunk=>{
      buffer=Buffer.concat([buffer,chunk]);
      if(buffer.length>MAX_FRAME+33){socket.destroy();return;}
      if(!authenticated) {
        if(buffer.length<33)return;
        role=buffer[0]===67?'control':buffer[0]===84?'chat':buffer[0]===82&&read?'read':undefined;
        if(!role||!timingSafeEqual(buffer.subarray(1,33),signature(keys[role],nonce,role))){socket.destroy();return;}
        if(role==='control'&&singleControl&&(controls||owner.detaching||owner.closing)){socket.destroy();return;}
        buffer=buffer.subarray(33);authenticated=true;clearTimeout(timer);
        if(role==='control') {
          controls++;const listener=event=>send({type:'host_event',event});owner.listeners.add(listener);
          unsubscribe=()=>owner.listeners.delete(listener);
        }
        send({type:'ready',schema:'hyprneuro.pi-owner/1'});
      }
      while(buffer.includes(10)) {
        const index=buffer.indexOf(10),line=buffer.subarray(0,index);buffer=buffer.subarray(index+1);
        if(line.length>MAX_FRAME){socket.destroy();return;}
        let value;try{value=JSON.parse(line);}catch{socket.destroy();return;}
        // Consent/status bypass the transition queue; otherwise a waiting native
        // tool confirmation would deadlock its own UI reply.
        if(++pending>8){socket.destroy();return;}
        Promise.resolve().then(()=>request(value)).then(result=>send({id:typeof value?.id==='string'?value.id:undefined,type:'result',result}),error=>send({id:typeof value?.id==='string'?value.id:undefined,type:'error',error:error.message.slice(0,500)})).finally(()=>{pending--;});
      }
    });
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(path,resolve);});
  await chmod(path,0o600);
  return {path,async close(){for(const socket of sockets)socket.destroy();await new Promise(r=>server.close(r));}};
}
