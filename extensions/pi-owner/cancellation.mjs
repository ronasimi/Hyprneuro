// One budget for the entire local cancellation proof, including SDK promises.
// Observing both race arms also consumes failures after timeout; no replay.
export async function boundedProof(completion, milliseconds) {
  let timer;
  try {
    return await Promise.race([completion,new Promise(resolve=>{timer=setTimeout(()=>resolve(false),milliseconds);})]);
  } catch {return false;}
  finally {clearTimeout(timer);}
}

// Request-local HTTP ownership, only for the closed normal-only parent profile.
// Neither abort() nor a terminal model event alone is closure evidence.
export class CancellationScope {
  constructor(fetch = globalThis.fetch) {
    this.fetchRequest=fetch;this.closed=false;this.uncertain=false;this.streams=[];this.requests=[];
  }
  toolAdmission() {
    this.uncertain=true; // Even a blocked/queued native tool is not tool-free.
    if(this.closed)throw new Error('Cancelled request tool admission sealed');
  }
  assertOpen() {
    if(this.closed){this.uncertain=true;throw new Error('Cancelled request inference admission sealed');}
  }
  native(native) {
    // Capture this generation BEFORE guardedStream's asynchronous lazy setup.
    const scope=this;
    return {...native,
      lazyStream(model,setup,observer,signal) {
        scope.assertOpen();const state={drained:false};
        state.completion=new Promise(resolve=>{state.complete=resolve;});scope.streams.push(state);
        return native.lazyStream(model,setup,{
          onEvent:event=>{
            if(event.type.startsWith('toolcall_')||event.type==='error'&&
                (!scope.closed||event.reason!=='aborted'||event.error?.errorMessage!=='Request was aborted'))scope.uncertain=true;
            observer?.onEvent?.(event);
          },
          // SDK lazyStream calls onResult only AFTER inner iteration/result drain.
          onResult:result=>{state.drained=true;state.complete();observer?.onResult?.(result);}
        },signal);
      },
      streamSimple(model,context,options) {
        scope.assertOpen();
        return native.streamSimple(model,context,{...options,fetch:(...args)=>scope.fetch(...args)});
      }
    };
  }
  async fetch(input,init) {
    this.assertOpen();
    const state={fetching:true,closed:false};this.requests.push(state);
    try {
      const response=await this.fetchRequest(input,{...init,redirect:'error'});
      if(!response.ok||!response.body)this.uncertain=true;
      if(!response.body){state.closed=true;return response;}
      const reader=response.body.getReader();state.reader=reader;
      state.cancel=()=>state.cancellation??=reader.cancel().then(()=>{state.closed=true;},error=>{
        this.uncertain=true;throw error;
      });
      if(this.closed){this.uncertain=true;await state.cancel();throw new Error('Response arrived after cancellation fence');}
      let cancelled=false;
      const body=new ReadableStream({
        pull:async controller=>{
          try {
            const result=await reader.read();
            if(result.done){state.closed=true;reader.releaseLock();if(!cancelled)controller.close();}
            else if(!cancelled)controller.enqueue(result.value);
          }catch(error){this.uncertain=true;controller.error(error);}
        },
        cancel:()=>{cancelled=true;return state.cancel();}
      },{highWaterMark:0});
      return new Response(body,{status:response.status,statusText:response.statusText,headers:response.headers});
    }catch(error){this.uncertain=true;throw error;}
    finally{state.fetching=false;}
  }
  seal() {
    if(this.closed)return;
    this.closed=true; // Synchronous fence BEFORE any abort/consent cleanup.
    for(const request of this.requests)if(request.cancel&&!request.closed) {
      try{void request.cancel().catch(()=>{});}catch{this.uncertain=true;}
    }
  }
  async drained() {
    // The owner bounds the ENTIRE proof. Keep tracking these real closures
    // after that deadline; timeout is never evidence that cleanup completed.
    const results=await Promise.allSettled([...this.streams.map(s=>s.completion),
      ...this.requests.map(r=>r.cancellation)]);
    if(results.some(result=>result.status==='rejected'))return false;
    // No header-only abort guess: an owned body and positive reader closure are
    // mandatory. SDK onResult additionally proves lazy producer/iterator drain.
    return this.closed&&!this.uncertain&&this.streams.length>0&&this.streams.every(s=>s.drained)&&
      this.requests.length>0&&this.requests.every(r=>!r.fetching&&r.reader&&r.closed);
  }
}
