// Lifecycle-only process adapter. Pi still owns every conversation/tool turn.
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

export function control(action, role, token) {
  if (!process.env.HYPRNEURO_RESIDENCY_DIR) throw new Error('HYPRNEURO_RESIDENCY_DIR must be explicitly shared by Pi and ALL sidecars');
  const source = fileURLToPath(new URL('../../python/src',import.meta.url));
  const child = spawn(process.env.HYPRNEURO_PYTHON ?? '/usr/bin/python3', ['-m','hyprneuro.residency',action,...(role?[role]:[])],
    {env:{...process.env,PYTHONPATH:source,HYPRNEURO_HANDOFF_TOKEN:token??''},stdio:['pipe','pipe','pipe']});
  const lines=createInterface({input:child.stdout});
  const queue=[],waiters=[]; let ended=false,error='';
  child.stderr.on('data',d=>{error=(error+d.toString()).slice(-2048);});
  const closed=new Promise((resolve,reject)=>{
    child.on('error',()=>reject(new Error('Residency helper unavailable')));
    child.on('close',code=>{
      ended=true;
      const failure=new Error('Residency helper closed: '+(error || 'inspect retained checkpoint'));
      for(const w of waiters.splice(0)) w.reject(failure);
      lines.close();code===0?resolve():reject(failure);
    });
  });
  // Attach a handler immediately: unexpected process loss must not be an unhandled rejection.
  closed.catch(()=>{});
  lines.on('line',line=>{
    if(line.length>4096){child.kill('SIGTERM');return;}
    try {
      const packet=JSON.parse(line),waiter=waiters.shift();
      if(waiter) waiter.resolve(packet);else queue.push(packet);
    } catch {child.kill('SIGTERM');}
  });
  return {child,closed,
    send(value){if(ended)throw new Error('Residency helper no longer owns transaction');child.stdin.write(JSON.stringify(value)+'\n');},
    async next(timeout=130000){
      if(queue.length)return queue.shift();
      if(ended)throw new Error('Residency helper exited; inference blocked');
      let waiter;
      const pending=new Promise((resolve,reject)=>{waiter={resolve,reject};waiters.push(waiter);});
      const timer=setTimeout(()=>waiter.reject(new Error('Residency helper timed out')),timeout);
      try{return await pending;}finally{clearTimeout(timer);const i=waiters.indexOf(waiter);if(i>=0)waiters.splice(i,1);}
    },
    async stop(){child.stdin.end();child.kill('SIGTERM');await closed;}
  };
}

export async function admit(role,token) {
  const owner=control('admit',role,token);
  try {
    const packet=await owner.next(10000);
    if(packet.admitted!==true)throw new Error('Inference admission denied');
    return async()=>{
      owner.send({ok:true});
      const released=await owner.next(10000);
      if(released.released!==true)throw new Error('Residency release unverified');
      await owner.closed;
    };
  } catch(e){await owner.stop().catch(()=>{});throw e;}
}

// Gate in the real native transport, NOT extension hooks: Pi reports hook errors
// but deliberately continues. Forward native events, never parse a new agent loop.
export function guardedStream(native,model,context,options={},token,acquire=admit) {
  return native.lazyStream(model,async()=>{
    const role={'lfm-text':'text','lfm-omni':'omni','lfm-moe':'hermes'}[model.id];
    const release=await acquire(role,token);
    let released=false;
    const releaseOnce=async()=>{if(!released){released=true;await release();}};
    try {
      const bound=new AbortController();let bytes=0;
      const signals=[bound.signal,AbortSignal.timeout(120000),...(options.signal?[options.signal]:[])];
      const signal=AbortSignal.any(signals);
      const source=native.streamSimple(model,context,{...options,signal,maxRetries:0,timeoutMs:120000,
        onProviderStreamEvent:(data,m)=>{
          bytes+=Buffer.byteLength(JSON.stringify(data));
          if(bytes>2*1024*1024)bound.abort();
          else return options.onProviderStreamEvent?.(data,m);
        },
        onPayload:async(payload,m)=>{
          const replacement=await options.onPayload?.(payload,m);
          const result=replacement??payload;
          return model.id==='lfm-text'?{...result,cache_prompt:true,chat_template_kwargs:{enable_thinking:false}}:result;
        }});
      return (async function*(){
        try {
          for await(const event of source) {
            if(event.type==='done'||event.type==='error')await releaseOnce();
            yield event;
          }
        } finally {await releaseOnce();}
      })();
    } catch(e){await releaseOnce();throw e;}
  },undefined,options.signal);
}

export async function releaseOwnedLease(rpc,taskId,capability) {
  const lease=(await rpc({action:'lease_status'})).active;
  if(!lease)return;
  if(!capability || capability.task_id!==taskId || lease.task_id!==taskId || typeof capability.token!=='string' || !capability.token)
    throw new Error('Active desktop lease is not held by this owner');
  // Status is observation only. Only an actual acquisition capability is used.
  if((await rpc({action:'lease_release',task_id:taskId,token:capability.token})).released!==true)
    throw new Error('Owned desktop lease capability was rejected');
}

export function watchHandoff(owner,onLoss) {
  const ended=()=>{
    owner.token=undefined;
    if(!owner.expectedClose)return onLoss(new Error('Handoff owner helper terminated unexpectedly; review checkpoint'));
  };
  const observed=owner.closed.then(ended,ended);
  // The caller owns reporting; never leave a rejected background observer.
  observed.catch(()=>{});
  return observed;
}
