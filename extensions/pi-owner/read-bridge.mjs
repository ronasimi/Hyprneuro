// Read-only, one-shot native child transport. Credential stays binary, never in
// JSON/context. This has NO trusted-control or lifecycle operation and NO retry.
import {connect} from 'node:net';
import {lstat,readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {signature,MAX_FRAME} from './socket.mjs';

export async function childRead(root,request,signal) {
  signal?.throwIfAborted();
  const file=join(root,'read.key'),st=await lstat(file);
  if(!st.isFile()||st.nlink!==1||st.uid!==process.getuid()||(st.mode&0o077)||st.size!==32)throw new Error('Unsafe read bridge credential');
  const key=await readFile(file),id=randomUUID();
  const frame=JSON.stringify({...request,op:'read',id})+'\n';
  if(Buffer.byteLength(frame)>MAX_FRAME)throw new Error('Read request exceeds frame bound');
  return new Promise((resolve,reject)=>{
    const socket=connect(join(root,'owner.sock'));let buffer=Buffer.alloc(0),nonce=false,ready=false,finished=false;
    const done=(error,result)=>{if(finished)return;finished=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);socket.destroy();error?reject(error):resolve(result);};
    const abort=()=>done(new Error('Child read cancelled; outcome unknown, never retry'));
    const timer=setTimeout(()=>done(new Error('Child read timed out; outcome unknown, never retry')),125000);
    signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)return abort();
    socket.on('error',()=>done(new Error('Child read bridge unavailable; never retry')));
    socket.on('close',()=>done(new Error('Child read disconnected; outcome unknown, never retry')));
    socket.on('data',chunk=>{
      buffer=Buffer.concat([buffer,chunk]);
      if(buffer.length>MAX_FRAME+32)return done(new Error('Child read response exceeds bound'));
      if(!nonce){if(buffer.length<32)return;socket.write(Buffer.concat([Buffer.from('R'),signature(key,buffer.subarray(0,32),'read')]));buffer=buffer.subarray(32);nonce=true;}
      while(buffer.includes(10)){
        const end=buffer.indexOf(10),line=buffer.subarray(0,end);buffer=buffer.subarray(end+1);
        try{
          const packet=JSON.parse(line);
          if(!ready){if(packet.type!=='ready')throw new Error('Invalid read authentication');ready=true;socket.write(frame);}
          else {if(packet.id!==id)throw new Error('Read correlation mismatch');if(packet.type!=='result')throw new Error(packet.error??'Read outcome unknown');done(null,packet.result);}
        }catch(error){done(error);}
      }
    });
  });
}
